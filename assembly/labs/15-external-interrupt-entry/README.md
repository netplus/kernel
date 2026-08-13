# 普通外部中断入口、hardirq context 与 IRQ stack 验证实验

本实验对应 A15 第三部分正文 [`../../docs/15-external-interrupt-entry-and-irq-stack.md`](../../docs/15-external-interrupt-entry-and-irq-stack.md)，目标是验证 Linux 5.10 x86-64 普通 device IRQ 的几个关键边界，而不是分析某个具体设备驱动。

源码事实基线见 [`../../source-paths/15-external-interrupt-entry-linux-5.10.md`](../../source-paths/15-external-interrupt-entry-linux-5.10.md)。

## 1. 要验证的问题

实验围绕下面四个问题展开：

1. 普通 device IRQ 的 vector 是否由 Linux vector stub 压入，而不是 CPU 作为 exception error code 压入；
2. 到达 `common_interrupt()` 时，vector 是否已经作为第二参数传递，而 `pt_regs.orig_ax` 已被规范化为 `-1`；
3. `irq_enter_rcu()` / `irq_exit_rcu()` 是否包围真正的 common IRQ handling，从而标出 hardirq context 的软件边界；
4. x86-64 在条件满足时，真正的 IRQ handler 是否从被中断现场所在的 task kernel stack 切到 per-CPU IRQ stack，再恢复原栈。

实验不要求制造特定 vector，也不修改 APIC/IOAPIC 配置。优先选择隔离 guest 中已有、能够稳定增长的普通 device IRQ。

## 2. 环境要求

推荐环境：

```text
Linux kernel: 5.10.x x86-64
CONFIG_DEBUG_INFO=y
匹配正在运行内核的 vmlinux
QEMU/KVM guest（推荐）
GDB，可通过 QEMU gdbstub 停机调试 guest
objdump/readelf/nm
```

如果只具备运行中的 Linux 5.10 而不能停机调试，可以完成 `/proc/interrupts`、符号和静态反汇编检查；不要把静态推导写成动态断点结果。

## 3. 先选择一个普通 device IRQ

在 guest 中执行：

```bash
cat /proc/interrupts
sleep 2
cat /proc/interrupts
```

选择计数稳定增长、且不是 `NMI`、`LOC`、`RES`、`CAL` 等 system-vector/IPI 类项目的普通设备 IRQ。virtio block/network 等虚拟设备通常比主动制造异常更适合本实验。

记录：

```text
IRQ number:
设备/说明:
观察 CPU:
两次计数差:
```

注意：Linux IRQ number 与 x86 interrupt vector 不是同一个编号。后续必须在内核入口处观察 vector，不能把 `/proc/interrupts` 第一列直接当作 IDT vector。

## 4. 静态核验 vector stub

用当前 `vmlinux` 而不是硬编码地址：

```bash
nm -n vmlinux | grep -E 'irq_entries_start|asm_common_interrupt'
objdump -dr vmlinux | less
```

在 `irq_entries_start` 附近检查重复的固定长度 stub。Linux 5.10 的关键形式应与下面的语义一致：

```text
push imm8(vector)
jmp asm_common_interrupt
```

需要检查两点：

- `push` 是 Linux stub 的指令，因此 vector slot 是软件创建的；
- imm8 在 x86-64 `push` 中会符号扩展，因此不能只凭栈上的 64-bit 数值直接解释 0..255 vector；C wrapper 最终按 `u8` 使用它。

记录实际反汇编中的一个 stub 和跳转目标。

## 5. 在 `common_interrupt` 入口观察 `pt_regs` 与 vector

### 5.1 断点定位原则

不要硬编码源码行地址。先用当前 `vmlinux`：

```gdb
(gdb) disassemble /r asm_common_interrupt
(gdb) disassemble /r common_interrupt
```

宏展开和编译配置会影响具体符号/指令布局。目标是在 `idtentry_body` 已完成 `error_entry` 和参数整理、即将进入或刚进入 C wrapper 的稳定位置观察。

### 5.2 预期参数关系

Linux 5.10 主线在调用 C wrapper 前完成：

```text
RDI = struct pt_regs *
RSI = vector slot 中的值
regs->orig_ax = -1
```

因此在合适断点处检查：

```gdb
(gdb) p/x $rdi
(gdb) p/x $rsi
(gdb) p/x ((struct pt_regs *)$rdi)->orig_ax
(gdb) p/x ((struct pt_regs *)$rdi)->ip
(gdb) p/x ((struct pt_regs *)$rdi)->cs
(gdb) p/x ((struct pt_regs *)$rdi)->flags
(gdb) p/x ((struct pt_regs *)$rdi)->sp
(gdb) p/x ((struct pt_regs *)$rdi)->ss
```

验收重点不是某个固定 vector 数值，而是：

```text
(u8)$rsi == 本次实际 interrupt vector
regs->orig_ax == -1
```

如果 `$rsi` 的高位看起来像符号扩展后的负数，应同时检查其低 8 位；这正是 vector stub 使用 imm8 push 后需要 `(u8)` 语义的原因。

## 6. 观察 hardirq context 边界

在当前 `vmlinux` 中定位：

```gdb
(gdb) info address irq_enter_rcu
(gdb) info address __common_interrupt
(gdb) info address irq_exit_rcu
```

根据编译结果决定使用函数断点还是在 `common_interrupt` wrapper 的反汇编中设置指令断点。记录同一次 IRQ 的顺序：

```text
irqentry_enter
irq_enter_rcu
__common_interrupt
irq_exit_rcu
irqentry_exit
```

不要把“CPU 已经通过 IDT 进入 CPL0”与“Linux 已执行 `irq_enter_rcu()`”视为同一个时刻。前者是架构入口，后者属于 Linux hardirq bookkeeping。

如果函数被内联或调试信息不足，改用 `objdump`/GDB 反汇编确认调用或内联后的控制流，并明确记录无法建立函数断点的原因。

## 7. 观察 vector 到 `irq_desc` 的交接

在 `__common_interrupt()` 中观察当前 vector，并核对源码中的 per-CPU：

```text
vector_irq[vector]
```

得到的对象是 `struct irq_desc *`。只需要确认：

```text
vector -> 当前 CPU 的 vector_irq[] -> irq_desc
```

本实验不继续展开 irqchip、generic IRQ flow handler 或设备驱动。

再次强调：

```text
interrupt vector != Linux IRQ number
```

两者即使某次恰好数值相同，也不能据此认为属于同一个编号空间。

## 8. 观察 task kernel stack 与 per-CPU IRQ stack

这是本实验最容易误判的部分。

### 8.1 先记录进入 IRQ C path 时的栈

在尚未执行 IRQ-stack policy 的位置记录：

```gdb
(gdb) p/x $rsp
```

如果中断来自用户态，CPU 的 CPL3 -> CPL0 换栈已经发生，此时低层入口位于当前 task 的 kernel stack。若中断本来就打断内核态，则不存在这次 privilege-level stack switch。

### 8.2 定位 `run_irq_on_irqstack_cond()`

检查当前构建的：

```gdb
(gdb) disassemble /r handle_irq
```

以及必要时：

```bash
objdump -dr vmlinux | grep -n -A40 -B10 'asm_call_irq_on_stack'
```

Linux 5.10 x86-64 在条件满足时通过 IRQ-stack helper 让真正的 flow handler 在 per-CPU IRQ stack 上运行。分别记录切换前和 handler 内的 `%rsp`。

验收时应证明的是“地址属于不同的栈区间”，而不是期待某两个 `%rsp` 有固定差值。

如果本次 IRQ 到达时已经处于 IRQ stack，或者配置/现场使条件不要求再次切换，则记录“未发生第二次切栈”以及当时的条件；这不是实验失败。

## 9. 三种栈切换必须分别记录

最终实验记录中建议使用下表：

| 机制 | 决定者 | 发生时机 | 本实验是否观察 |
| --- | --- | --- | --- |
| CPL3 -> CPL0 task kernel stack | CPU + TSS privilege stack | 第一条 Linux IRQ 指令之前 | 视中断来源而定 |
| IST exception stack | CPU + IDT.IST/TSS.ist[] | 第一条特殊异常指令之前 | 普通 device IRQ 不使用 |
| per-CPU IRQ stack | Linux 软件策略 | 已进入 IRQ path 后 | 条件满足时观察 |

普通 device IRQ 实验中不要把第三行称为 IST。

## 10. 返回路径检查

在反汇编中沿 `common_interrupt` 返回侧检查：

```text
irq_exit_rcu
irqentry_exit
idtentry return
error_return
interrupt/IRET return
```

本实验只要求确认它回到 IDT interrupt-return 主线。不要套用 A14 syscall 的 opportunistic `SYSRETQ` 模型。

## 11. 可选的 ftrace 观测

如果 guest 的 tracing 配置允许，可用 function/function_graph tracer 辅助观察 `common_interrupt`、`__common_interrupt`、`handle_irq` 等函数关系。由于低层汇编入口、noinstr 区域和编译器内联会限制可跟踪范围，ftrace 只能作为 C 层顺序的辅助证据，不能替代对 vector stub、hardware frame 和低层 `%rsp` 的 GDB/反汇编验证。

具体可用函数必须以：

```bash
cat /sys/kernel/debug/tracing/available_filter_functions
```

的实际结果为准，不假定所有入口函数都可 trace。

## 12. 安全边界

- 只在隔离 guest 中使用 kernel-GDB 停机断点；
- 不修改生产机 IDT/APIC/IOAPIC；
- 不主动屏蔽中断后长时间停机；
- 不通过破坏栈、伪造 interrupt frame 或错误 EOI 制造观察条件；
- NMI、`#DF`、`#MC` 不属于本实验的普通 device IRQ 主线。

## 13. 当前执行状态

本次课程维护环境没有可停机调试的 Linux 5.10 guest、与其完全匹配的 `vmlinux` 和 kernel-GDB 会话，因此没有填写具体 vector、`irq_desc` 地址或切栈前后的 `%rsp` 数值。

本实验已经给出可执行的选择 IRQ、静态反汇编、断点定位、`pt_regs`/vector、hardirq context、`vector_irq[]` 和 IRQ-stack 验证步骤。真实动态结果必须在匹配的 Linux 5.10 隔离 guest 中补录，不能用其他内核版本的观察值替代。
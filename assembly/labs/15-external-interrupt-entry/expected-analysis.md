# 普通外部中断入口实验预期分析

本文给出 `README.md` 中普通 device IRQ 实验的验收基线。这里描述的是 Linux 5.10 x86-64 主线应满足的关系；没有匹配 guest、`vmlinux` 和 kernel-GDB 的情况下，不把下面的预期值写成动态实测结果。

## 1. 验收时先区分四个编号/对象

实验中至少会遇到：

```text
Linux IRQ number
x86 interrupt vector
vector stub 压入的 64-bit slot
struct irq_desc *
```

它们不能互换。`/proc/interrupts` 第一列给出 Linux IRQ number；CPU 通过 vector 选择 IDT entry；Linux 的 vector stub 再把 vector 放入入口栈；C 层最终通过当前 CPU 的 `vector_irq[vector]` 找到 `irq_desc`。

因此，不能因为一次观察中 IRQ number 与 vector 恰好相同，就把它们解释成同一个编号空间。

## 2. vector slot 的来源

普通 device IRQ 没有类似 `#GP` 的 CPU hardware error code。CPU 建立 interrupt frame 后，Linux 5.10 的 vector stub 执行等价于：

```asm
push imm8(vector)
jmp asm_common_interrupt
```

所以额外 slot 的来源应判定为 **Linux 软件入口**。

如果 vector >= 0x80，8-bit immediate 的 `push` 会先符号扩展到操作数宽度。因此在低层栈或 `%rsi` 中可能看到高位全 1 的 64-bit 值。验收 vector 时应使用低 8 位：

```text
(u8)slot == actual vector
```

不能要求完整 64-bit slot 总是等于 0..255 的零扩展值。

## 3. `orig_ax` 的时间关系

vector stub 刚压栈后，额外 slot 暂时位于后续 `pt_regs.orig_ax` 对应的位置。它此时保存的是 vector，而不是 syscall number。

`idtentry_body` 在进入 C wrapper 前应完成：

```text
RSI <- vector slot
regs->orig_ax <- -1
RDI <- struct pt_regs *
```

因此两个观察时刻必须分开：

```text
vector slot 尚未搬走：slot == sign-extended vector
进入 common_interrupt C wrapper：low8(RSI) == vector，orig_ax == -1
```

如果在 C wrapper 中仍把 `orig_ax` 解释成 vector，说明观察点或解释错误。

## 4. `pt_regs` 的预期含义

若 IRQ 打断用户态，进入规范化 C path 后关键字段应表示被打断的用户现场：

```text
orig_ax = -1
ip      = interrupted user RIP
cs      = user CS
flags   = interrupted RFLAGS
sp      = interrupted user RSP
ss      = user SS
```

CPU 并没有直接生成 `struct pt_regs`。CPU 只建立架构 interrupt frame；Linux 的 `error_entry`/公共入口继续保存 GPR 并整理额外 slot，最终形成 `pt_regs`。

若 IRQ 打断内核态，则 `ip/cs/flags` 仍表示被打断现场，但不能机械地套用“发生 CPL3 -> CPL0 换栈并保存 user RSP/SS”的描述。验收记录必须注明中断来源 CPL。

## 5. hardirq context 的验收边界

普通 IRQ 已经通过 IDT 进入内核，并不等于 Linux 的 hardirq bookkeeping 已经全部建立。Linux 5.10 的主线应保持：

```text
irqentry_enter(regs)
irq_enter_rcu()
__common_interrupt(regs, vector)
irq_exit_rcu()
irqentry_exit(regs, state)
```

因此实验应把 CPU architecture entry 与 `irq_enter_rcu()` 软件边界分开记录。

若当前构建发生内联，不能以“GDB 找不到独立函数断点”判定流程不存在；应转而用当前 `vmlinux` 的反汇编确认等价控制流，并记录编译器造成的观察限制。

## 6. vector 到 `irq_desc` 的验收关系

在 `__common_interrupt()` 主线中，期望验证：

```text
actual vector
    -> this CPU's vector_irq[vector]
    -> struct irq_desc *
```

实验只需要证明这一级交接，不要求继续展开 irqchip、generic flow handler 或设备驱动。

如果观察到无效/特殊映射，应先确认所选中断是否真的是普通 device IRQ，而不是 system vector、IPI 或已经进入 unexpected-vector 分支。

## 7. 三种栈机制不能混淆

### 7.1 CPL3 -> CPL0 task kernel stack

若 IRQ 在用户态被接受，CPU 在执行第一条 Linux IRQ 指令前已经依据 privilege-level stack 机制切换到当前 task 的 kernel stack。这个动作属于 x86-64 architecture entry。

### 7.2 IST exception stack

普通 device IRQ 主线不依赖 A15 第二部分讨论的 IST 特殊异常栈。不能把“进入内核后 `%rsp` 变化”自动称为 IST。

### 7.3 per-CPU IRQ stack

Linux 已进入 IRQ path 后，`run_irq_on_irqstack_cond()` 可根据当前现场决定让真正的 IRQ handler 在 per-CPU IRQ stack 上运行。这是 Linux 软件策略。

如果发生切换，验收标准是：

```text
before-handler RSP 属于原 task/kernel entry stack 区间
handler RSP 属于当前 CPU IRQ stack 区间
handler 返回后恢复原 stack
```

不要求两个 `%rsp` 之间存在固定数值差。

如果现场已经在 IRQ stack，或者当前条件不要求第二次切栈，则“未发生第二次切栈”可以是正确结果；必须同时记录条件，不能仅凭一次 `%rsp` 未变化断言 Linux 5.10 没有 IRQ-stack 机制。

## 8. 返回路径

普通 device IRQ 应沿 IDT interrupt-return 主线恢复被打断现场。概念上：

```text
IRQ handler
 -> irq_exit_rcu()
 -> irqentry_exit()
 -> low-level idtentry/error return
 -> restore interrupt frame
 -> IRET semantics
```

这里不使用 A14 syscall 返回侧的 opportunistic `SYSRETQ` 模型。若实验记录把普通 device IRQ 返回解释为 syscall SYSRET fast path，应判为不合格。

## 9. 一组完整的通过条件

一次动态实验达到独立验收标准时，应至少留下下面这些证据：

1. `/proc/interrupts` 证明选择的是稳定发生的普通 device IRQ，并记录 CPU；
2. 当前 `vmlinux` 反汇编证明对应入口族由 vector stub 执行 `push imm8` 后跳向公共入口；
3. C wrapper 观察到 `low8(RSI) == actual vector` 且 `regs->orig_ax == -1`；
4. `pt_regs` 中 RIP/CS/RFLAGS 与实际被中断现场的 CPL 和地址范围一致；
5. 控制流证据能区分 architecture entry 与 `irq_enter_rcu()`/`irq_exit_rcu()` hardirq bookkeeping；
6. 能从当前 CPU 的 `vector_irq[vector]` 取得本次 `irq_desc`；
7. 对 IRQ stack 明确记录“发生切换并证明两个栈区间”或“本次未切换以及对应条件”；
8. 返回路径按 interrupt/IRET 模型解释，而不是套用 syscall SYSRET。

## 10. 当前未完成的动态证据

当前课程维护环境没有匹配的 Linux 5.10 隔离 guest、运行内核对应的 `vmlinux` 和 kernel-GDB 会话，因此以下值仍必须在后续实验环境中实测：

```text
actual vector
vector_irq[vector] / irq_desc 地址
被中断现场的 pt_regs 值
irq_enter/exit 的实际断点顺序
切换前后的 RSP 与 IRQ-stack 地址范围
```

这些缺失不改变源码模型，但在真实动态验证完成前，不应把任何示例地址或预期数值标记为“实验结果”。
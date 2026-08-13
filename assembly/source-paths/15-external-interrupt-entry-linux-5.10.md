# Linux 5.10 x86-64 普通外部中断入口源码事实核验

本文只固定 A15 第三部分需要依赖的 Linux 5.10 源码事实：普通 device IRQ 如何从 vector stub 进入 `common_interrupt()`，如何形成 `pt_regs`，何时进入 hardirq context，以及 IRQ stack 与返回路径的边界。这里不展开具体设备驱动和 IRQ chip 细节。

## 1. 问题边界

普通外部中断与前两部分的同步异常有两个关键差别。

第一，设备中断没有类似 `#GP` 的 CPU exception error code。Linux 需要把 **interrupt vector** 自己压入栈，并复用普通 `idtentry` 的“error-code slot”接口把 vector 送入 C 层。

第二，进入 C 层后还要建立 hardirq 语义，并且 x86-64 可以在需要时把真正的 IRQ handler 放到独立 IRQ stack 上执行。因此不能把“CPU 因 CPL3 -> CPL0 而切到 task kernel stack”和“Linux 后续切到 IRQ stack”混成一次硬件换栈。

## 2. Linux 5.10 关键源码

主线涉及：

```text
arch/x86/include/asm/idtentry.h
arch/x86/entry/entry_64.S
arch/x86/kernel/irq.c
arch/x86/include/asm/irq_stack.h
```

关键生成关系是：

```text
irq_entries_start
  -> push vector
  -> jmp asm_common_interrupt
  -> idtentry_irq ... common_interrupt
  -> idtentry ... has_error_code=1
  -> idtentry_body common_interrupt, 1
  -> error_entry
  -> common_interrupt(regs, vector-as-error_code)
```

## 3. vector stub：Linux 主动压入 vector

`arch/x86/include/asm/idtentry.h` 在汇编模式下生成 `irq_entries_start`。范围从 `FIRST_EXTERNAL_VECTOR` 到 `FIRST_SYSTEM_VECTOR - 1`，每个 stub 固定为 8 bytes，核心动作是：

```asm
.byte 0x6a, vector
jmp asm_common_interrupt
```

这里的 `pushq imm8` 由字节编码显式生成。原因是 vector 大于 `0x7f` 时，8-bit immediate 会按有符号数扩展到 64 位。Linux 因而在 C 入口把传入值截断为 `u8`，恢复真正的 0..255 vector。

这一步是 **Linux 软件入口动作**，不是 CPU 自动压栈的一部分。

CPU 在中断 gate 入口建立的是架构定义的 interrupt frame；若发生 CPL3 -> CPL0 特权级变化，还会按 TSS 提供的 ring-0 stack 完成相应栈切换。普通 device IRQ gate 不依赖 A15 第二部分所讲的 IST exception stack。

## 4. 为什么 `idtentry_irq` 使用 `has_error_code=1`

`entry_64.S` 中：

```text
idtentry_irq vector cfunc
  -> idtentry vector asm_cfunc cfunc has_error_code=1
```

这并不表示设备中断拥有 CPU hardware error code。

真正含义是：vector stub 已经在与异常 error-code slot 相同的位置压入一个 vector，因此后续可以复用 `idtentry_body(..., has_error_code=1)` 的布局和参数搬运逻辑。

`idtentry_body` 在 `error_entry` 返回后：

```text
RDI = RSP                 -> struct pt_regs *
RSI = ORIG_RAX(RSP)       -> vector（暂存在该 slot）
ORIG_RAX(RSP) = -1        -> 规范化为“不是 syscall”
call common_interrupt
```

所以必须区分三个时刻：

```text
vector stub 后：slot 保存 vector
进入 common_interrupt 前：RSI 保存 vector，pt_regs.orig_ax 已变成 -1
C handler 内：vector 从第二参数取得，不从 regs->orig_ax 取得
```

这与 A15 第一部分 `#GP` 的“hardware error code 暂占同一 slot，再搬到 RSI”在软件布局上相似，但来源不同：`#GP` 的 error code 来自 CPU；device IRQ 的 vector 来自 Linux stub。

## 5. `error_entry` 与 `pt_regs`

普通 IRQ 继续复用 `error_entry` 保存通用寄存器并建立 Linux 可使用的 `struct pt_regs`。因此进入 `common_interrupt()` 时，C 层拿到的是已经规范化后的寄存器现场。

对从用户态被中断的情况，`pt_regs` 尾部仍可解释为：

```text
orig_ax = -1
ip      = 被中断用户指令的 RIP
cs      = 用户 CS
flags   = 被中断时的 RFLAGS
sp      = 用户 RSP
ss      = 用户 SS
```

这里的 `ip` 与 syscall 返回地址不同：外部中断是异步到达的，保存的是 CPU 接受中断时的 interrupted RIP，而不是程序显式执行某条入口指令产生的“下一条地址”。

## 6. C 入口：`DEFINE_IDTENTRY_IRQ(common_interrupt)`

`arch/x86/kernel/irq.c` 使用：

```text
DEFINE_IDTENTRY_IRQ(common_interrupt)
```

Linux 5.10 的 `DEFINE_IDTENTRY_IRQ` wrapper 顺序为：

```text
irqentry_enter(regs)
instrumentation_begin()
irq_enter_rcu()
kvm_set_cpu_l1tf_flush_l1d()
__common_interrupt(regs, (u8)error_code)
irq_exit_rcu()
instrumentation_end()
irqentry_exit(regs, state)
```

因此“CPU 已经跳入 interrupt gate”与“Linux 已进入完整 hardirq accounting/context”不是同一个瞬间。`irq_enter_rcu()` / `irq_exit_rcu()` 是 C wrapper 明确建立和撤销 hardirq 语义的重要边界。

## 7. vector 到 `irq_desc`

`__common_interrupt()` 的主体位于 `arch/x86/kernel/irq.c`。它先：

```text
old_regs = set_irq_regs(regs)
desc = __this_cpu_read(vector_irq[vector])
```

若 `desc` 有效，则进入：

```text
handle_irq(desc, regs)
```

否则走 unexpected/unused vector 的 APIC acknowledge 与诊断路径。

这里 `vector_irq[]` 是 per-CPU 的 vector -> `irq_desc` 映射。A15 只需要理解这一交接点；`irq_desc`、generic IRQ flow handler 和具体设备驱动属于 IRQ 子系统更深层内容，不在本基础汇编章节展开。

## 8. x86-64 IRQ stack 是第二次、软件控制的栈选择

`handle_irq()` 在 x86-64 下调用：

```text
run_irq_on_irqstack_cond(desc->handle_irq, desc, regs)
```

它决定 handler 是否需要在 per-CPU IRQ stack 上执行。

因此从用户态收到普通 device IRQ 时，可能存在两个概念上完全不同的栈阶段：

```text
1. CPU interrupt gate：
   user stack -> 当前 task 的 kernel stack
   原因：CPL3 -> CPL0

2. Linux handler 执行阶段：
   task kernel stack -> per-CPU IRQ stack（若条件要求）
   原因：Linux x86-64 IRQ-stack policy
```

第二步不是 IDT/TSS privilege stack switch，也不是 IST。

`entry_64.S` 中的 `asm_call_irq_on_stack`/`asm_call_on_stack` 会保存旧 frame pointer，把旧 stack pointer 链接到新栈，再切换 `%rsp` 调用 handler，返回时恢复原来的 stack pointer。这一设计也给 ORC unwinder 保留跨栈展开所需的连接信息。

## 9. 返回路径

IRQ handler 完成后，wrapper 依次执行 `irq_exit_rcu()` 和 `irqentry_exit()`，再返回低层汇编。

普通 `idtentry` 的汇编主体最终走：

```text
common_interrupt
  -> return to idtentry_body
  -> error_return
```

`error_return` 根据最终 `pt_regs` 所表示的来源返回用户态或内核态；真正寄存器恢复与 `iretq` 位于 `entry_64.S` 的公共返回代码中。

这里不应套用 A14 syscall 的 opportunistic SYSRET 模型。普通外部中断保存的是架构 interrupt/IRET frame，返回主线使用 interrupt return/IRET 语义。

## 10. 与普通异常的对照

```text
普通 #DE：
CPU frame
-> Linux push synthetic -1
-> error_entry
-> pt_regs
-> exception C handler

普通 #GP：
CPU frame + hardware error code
-> error_entry
-> error code 搬到 RSI
-> orig_ax = -1
-> exception C handler

普通 device IRQ：
CPU interrupt frame
-> Linux vector stub push vector
-> error_entry
-> vector 搬到 RSI 并截断为 u8
-> orig_ax = -1
-> irqentry_enter
-> irq_enter_rcu
-> common_interrupt body
-> 可条件切到 IRQ stack 执行 flow handler
-> irq_exit_rcu
-> irqentry_exit
-> interrupt return
```

三条路径复用了相似的 `pt_regs` 规范化机制，但“额外 slot”的来源和 C 层语义完全不同。

## 11. 配置与边界

本文件以 Linux v5.10 x86-64 native 主线为准。

需要注意：

- `CONFIG_X86_64` 决定这里讨论的 64-bit IRQ-stack 路径；
- `CONFIG_X86_LOCAL_APIC` 影响 APIC/system-vector 相关入口，但普通 device IRQ 的 common path 与 system-vector path 不应混写；
- SMP IPI、local APIC timer 等 system vectors 使用 `DECLARE/DEFINE_IDTENTRY_SYSVEC*`，不是普通 `common_interrupt` device-IRQ path；
- Xen/PV 等虚拟化入口存在额外路径，不作为本章正常主线；
- IRQ stack 是 Linux 软件执行栈策略，不是 TSS IST。

## 12. 后续正文应固定的结论

A15 第三部分正式教程至少应让读者建立以下模型：

```text
external event
-> CPU IDT interrupt gate / hardware frame
-> per-vector Linux stub pushes vector
-> asm_common_interrupt / idtentry_irq
-> error_entry / pt_regs
-> vector: slot -> RSI -> u8
-> irqentry_enter
-> irq_enter_rcu
-> vector_irq[vector] -> irq_desc
-> optional per-CPU IRQ stack
-> irq_exit_rcu / irqentry_exit
-> common interrupt return / iretq
```

同时必须持续区分：CPU hardware frame、Linux vector slot、task kernel stack、per-CPU IRQ stack、IST exception stack，以及 exception error code。
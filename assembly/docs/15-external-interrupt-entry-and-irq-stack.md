# 普通外部中断入口、hardirq context 与 IRQ stack

A15 前两部分讨论了同步异常和 IST。本节转向普通外部设备中断。重点不是某一种设备，而是 CPU 接受一个普通 x86-64 外部中断后，Linux 5.10 如何把硬件现场转换成 `pt_regs`，如何把 interrupt vector 送入 C 层，以及为什么 handler 还可能再次切换到 per-CPU IRQ stack。

源码事实基线见 [`../source-paths/15-external-interrupt-entry-linux-5.10.md`](../source-paths/15-external-interrupt-entry-linux-5.10.md)。

## 1. 为什么外部中断需要单独建立模型

异常和外部中断最终都通过 IDT 进入内核，但事件来源不同。

同步异常由当前指令执行直接引起。例如除零产生 `#DE`，非法段选择子可能产生 `#GP`。保存的 RIP 与发生异常的指令语义存在直接关系。

普通外部中断来自 CPU 外部或本地中断控制逻辑。它可以在程序没有执行任何“进入内核”指令时到达。因此这里首先要建立的是异步打断模型：

```text
用户或内核代码正在执行
        |
        | 外部中断被 CPU 接受
        v
IDT gate
        |
        v
CPU 建立 interrupt frame
        |
        v
Linux vector stub
        |
        v
pt_regs / hardirq context
        |
        v
IRQ handler
        |
        v
恢复被打断的执行现场
```

这也解释了为什么不能把 syscall 的“返回 RIP”模型直接套到中断：中断 frame 中的 RIP 是 CPU 接受中断时需要恢复的 interrupted instruction pointer。

## 2. 四种必须分开的动作

理解普通 IRQ 时最容易把几种换栈和保存动作混在一起。本节始终区分：

1. **CPU hardware interrupt entry**：读取 IDT gate，并按架构规则建立 interrupt frame；
2. **CPL3 -> CPL0 privilege stack switch**：若从用户态进入，CPU 使用 TSS 提供的 ring-0 stack；
3. **Linux entry normalization**：vector stub、`error_entry` 和 `pt_regs` 构造；
4. **Linux IRQ-stack policy**：进入 IRQ 子系统后，必要时把 handler 放到 per-CPU IRQ stack 上执行。

第 2 项不是 IST；第 4 项更不是 CPU 的 TSS/IDT 换栈动作。IST 已在 A15 第二部分单独讨论。

## 3. CPU 首先做什么

CPU 接受一个可递送的普通外部中断后，通过 vector 选择 IDT descriptor，并把返回所需状态形成 interrupt frame。

若中断发生在 CPL3，进入 CPL0 时还需要保存旧用户栈状态并使用内核栈。概念上，Linux 随后能够在 `pt_regs` 尾部看到：

```text
ip      interrupted RIP
cs      interrupted CS
flags   interrupted RFLAGS
sp      interrupted user RSP
ss      interrupted user SS
```

这里还没有 Linux 的 vector slot，也没有完整 GPR 保存；这些是后续软件入口完成的。

普通 device IRQ 也没有 `#GP` 那样由 CPU 自动压入的 exception error code。

## 4. Linux 为什么主动压入 vector

Linux 5.10 x86-64 为普通外部中断生成一组固定大小的 vector stubs。主线从 `irq_entries_start` 开始，每个 stub 的核心动作可概括为：

```asm
push vector
jmp asm_common_interrupt
```

因此入口栈在 CPU hardware frame 之外多出一个 Linux 软件创建的槽。

这个槽不是 error code。它保存的是 interrupt vector。Linux 之所以把它放在这里，是为了复用普通 `idtentry` 已有的“额外 slot + `error_entry`”入口框架。

需要特别注意实际编码。stub 使用 8-bit immediate 的 push 形式；高于 `0x7f` 的值在压栈时会发生符号扩展。因此后面的 C wrapper 把传入值转换为 `u8`，恢复真正的 0..255 vector。

## 5. `has_error_code=1` 不表示 IRQ 有硬件 error code

普通 IRQ 通过 `idtentry_irq` 进入公共入口，而该宏最终使用 `has_error_code=1` 的布局。

这个名字容易产生误解。这里的含义只是：**栈上已经存在一个可按 error-code slot 处理的额外槽**。对不同入口，它的来源不同：

```text
#DE       Linux 主动 push synthetic -1
#GP       CPU 自动 push exception error code
device IRQ Linux vector stub 主动 push vector
```

所以相同的软件栈布局不代表相同的架构语义。

## 6. vector 如何变成 C 参数

公共入口经过 `error_entry` 保存 GPR，形成 Linux 使用的 `struct pt_regs`。随后 `idtentry_body` 处理刚才的额外槽：

```text
RDI <- RSP
      struct pt_regs *

RSI <- ORIG_RAX(RSP)
      暂存在该槽中的 vector

ORIG_RAX(RSP) <- -1
      规范化为“不是 syscall”
```

因此要按时间理解 `orig_ax`：

```text
vector stub 刚执行后
    orig_ax 对应槽暂存 vector

调用 common_interrupt 前
    RSI 保存 vector
    regs->orig_ax 已经是 -1

进入 C wrapper 后
    vector 从第二参数取得
```

这与 A15 第一部分 `#GP` 的处理形式相似，但 `#GP` 搬运的是 CPU error code，而这里搬运的是 Linux 自己压入的 vector。

## 7. `pt_regs` 表示什么现场

对从用户态被中断的普通 IRQ，进入 C 层时可把关键字段理解为：

```text
orig_ax = -1
ip      = 被中断现场的 RIP
cs      = 用户 CS
flags   = 被中断现场的 RFLAGS
sp      = 用户 RSP
ss      = 用户 SS
```

其余通用寄存器由 `error_entry` 保存。

这里的 `pt_regs` 是 Linux 对入口现场的规范化表示。不要把它说成“CPU 自动生成的结构体”：CPU 只建立架构定义的 interrupt frame，Linux 汇编入口继续保存和整理寄存器后才得到 `pt_regs`。

## 8. 什么时候才进入 hardirq context

到达 C wrapper 并不意味着 CPU 刚跳进 IDT gate 的那一刻就已经完成 Linux 的 hardirq bookkeeping。

Linux 5.10 的 `DEFINE_IDTENTRY_IRQ(common_interrupt)` 主线可概括为：

```text
irqentry_enter(regs)
    |
irq_enter_rcu()
    |
__common_interrupt(regs, (u8)vector)
    |
irq_exit_rcu()
    |
irqentry_exit(regs, state)
```

`irq_enter_rcu()` / `irq_exit_rcu()` 是理解 hardirq execution context 的重要软件边界。它们属于 Linux 的入口/退出管理，而不是 CPU interrupt gate 的硬件语义。

本章只需要掌握这一上下文交接。generic IRQ flow handler、irqchip 和设备驱动的完整机制不在 assembly 基础课程展开。

## 9. vector 如何找到具体 IRQ

`__common_interrupt()` 首先把当前寄存器现场登记为 IRQ regs，然后读取当前 CPU 的 vector 映射：

```text
vector
  |
  v
per-CPU vector_irq[vector]
  |
  v
irq_desc
  |
  v
handle_irq(...)
```

这里的重要概念是 **vector 是 CPU/架构入口编号，而 `irq_desc` 是 Linux IRQ 子系统对象**。二者不是同一个编号空间或同一个对象。

如果 vector 没有有效映射，Linux 走 unexpected/unused vector 的处理路径；本节不展开该异常分支。

## 10. 为什么还需要 per-CPU IRQ stack

如果中断发生在用户态，CPU 已经因为 CPL3 -> CPL0 切到当前 task 的 kernel stack。为什么 Linux 后面还可能换栈？

原因不同。task kernel stack 服务于当前任务的内核执行现场，而硬中断可能嵌套在任意内核路径上。x86-64 Linux 可以让真正的 IRQ handler 在独立的 per-CPU IRQ stack 上运行，从而减少对被中断任务 kernel stack 的消耗，并建立清晰的中断栈边界。

Linux 5.10 x86-64 的 `handle_irq()` 通过 `run_irq_on_irqstack_cond()` 决定是否需要这样执行。概念过程是：

```text
CPU entry
user stack
   |
   | CPL3 -> CPL0
   v
task kernel stack
   |
   | Linux IRQ-stack policy（条件成立时）
   v
per-CPU IRQ stack
   |
   | handler 完成
   v
task kernel stack
```

第二次切换由 Linux 软件完成，不读取 IDT IST 字段，也不是 TSS privilege-level stack switch。

## 11. IRQ stack 与 IST 的区别

A15 第二部分的 IST 路径是：

```text
IDT gate.IST
   -> CPU 查询 TSS.ist[]
   -> 在第一条 Linux entry 指令执行前切栈
```

普通 IRQ stack 路径则是：

```text
CPU 已经进入 Linux
   -> 已形成 pt_regs
   -> 已进入 IRQ C path
   -> Linux 根据条件选择 per-CPU IRQ stack
```

因此二者在决定者、时刻和目的上都不同。

## 12. 返回路径为什么不是 SYSRET

handler 完成后，Linux 依次退出 hardirq context，并回到低层公共返回代码：

```text
handler
 -> irq_exit_rcu()
 -> irqentry_exit()
 -> idtentry return
 -> error_return
 -> 恢复 interrupt frame
 -> iretq 语义返回
```

A14 的 `SYSRETQ` 是 syscall 专用的机会性快路径。普通外部中断从 IDT interrupt frame 进入，返回应按 interrupt/IRET 模型理解，不能因为二者最终都回到用户态就混为同一条路径。

## 13. 与同步异常做一次完整对照

```text
#DE
CPU exception frame
 -> Linux synthetic -1
 -> error_entry
 -> pt_regs
 -> exception handler

#GP
CPU exception frame + hardware error code
 -> error_entry
 -> error code: slot -> RSI
 -> orig_ax = -1
 -> exception handler

device IRQ
CPU interrupt frame
 -> Linux stub push vector
 -> error_entry
 -> vector: slot -> RSI -> u8
 -> orig_ax = -1
 -> irqentry_enter
 -> irq_enter_rcu
 -> vector_irq[vector]
 -> optional per-CPU IRQ stack
 -> irq_exit_rcu
 -> irqentry_exit
 -> interrupt return
```

共同点是 Linux 尽量把不同入口规范化成统一的寄存器现场；差异则来自事件性质、额外 slot 的来源以及 C 层执行上下文。

## 14. Linux 5.10 的实现边界

本节以 Linux v5.10 x86-64 native 普通 device IRQ 为主线。

- SMP IPI、local APIC timer 等 system vectors 使用专门的 system-vector 入口，不等同于普通 `common_interrupt` 路径；
- Xen/PV 等虚拟化配置可能改变低层入口细节；
- per-CPU IRQ stack 是 x86-64 Linux 软件策略，不是架构要求；
- 本节不展开 irqchip、generic IRQ flow handler 和具体设备驱动；
- IST 特殊异常栈已经在 A15 第二部分说明，不在这里重复展开。

## 15. 阅读源码时应保持的检查顺序

看到一个普通外部中断入口时，可以按下面的顺序检查：

```text
1. vector 对应哪个 IDT gate？
2. CPU 是否发生 privilege-level stack switch？
3. vector 是谁压栈的？
4. 何时形成完整 pt_regs？
5. vector 何时从 slot 搬到 C 参数？
6. 何时进入 hardirq context？
7. vector_irq[] 如何把 vector 交给 irq_desc？
8. handler 是否切到 per-CPU IRQ stack？
9. handler 完成后如何恢复原栈？
10. 最终走哪条 interrupt-return 路径？
```

能把这十个问题按执行顺序回答清楚，就已经建立了 Linux 5.10 x86-64 普通外部中断入口的基础模型。
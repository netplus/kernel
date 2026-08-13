# A15 异常、中断与特权级切换：整章一致性复核

本页用于把 A15 三条入口主线放回同一个执行模型中，并记录进入 A16 前的章节边界。它不是新的机制教程；各机制的完整说明仍在 A15 对应正文、实验和 Linux 5.10 `source-paths/` 中。

## 1. A15 已覆盖的三个入口模型

### 1.1 普通同步异常

第一部分以 `#DE` 与 `#GP` 对照，建立：

```text
IDT gate
 -> CPU hardware frame
 -> hardware/synthetic error-code slot
 -> error_entry
 -> GPR 保存与 pt_regs
 -> C exception handler
 -> IRET 语义返回
```

这里必须保持两个事实：CPU 不会自动生成 `struct pt_regs`；`#GP` 的 hardware error code 在进入 C handler 前被移到第二参数，`regs->orig_ax` 随后被规范化为 `-1`。

### 1.2 IST 特殊异常入口

第二部分建立：

```text
per-CPU exception stack
 -> TSS.ist[]
 -> TSS descriptor / TR
 -> IDT gate.IST
 -> CPU 在第一条 Linux entry 指令前切换 RSP
 -> special/paranoid entry
```

IST 与 CPL3 -> CPL0 的 privilege-level stack switch 不是同一机制。IDT descriptor 中的 IST 编码是 1-based；Linux 使用的 `IST_INDEX_*`/TSS 数组下标按零基理解，不能直接把两个数值空间等同。

### 1.3 普通外部 device IRQ

第三部分建立：

```text
IDT gate
 -> CPU interrupt frame
 -> Linux vector stub push vector
 -> error_entry / pt_regs
 -> vector slot -> RSI -> u8 vector
 -> irqentry_enter
 -> irq_enter_rcu
 -> vector_irq[vector] -> irq_desc
 -> optional per-CPU IRQ stack
 -> irq_exit_rcu / irqentry_exit
 -> interrupt/IRET return
```

普通 device IRQ 没有 CPU exception error code。入口宏中的 error-code-style slot 在这里由 Linux vector stub 放入 vector；进入 C wrapper 时 `orig_ax` 已规范化为 `-1`。

## 2. 四个分类轴必须保持独立

A15 最容易产生的概念错误，是把下面四组概念混成一组：

```text
同步异常 / 异步中断
fault / trap 等异常报告语义
IDT interrupt gate / trap gate / DPL / IST
hardware error code 是否存在
```

它们是不同分类轴。例如 fault 不等于 interrupt gate，trap 也不等于 trap gate；是否有 hardware error code 同样不能用于判断 fault/trap。

saved RIP 的解释也必须依事件语义区分：fault 通常指向需要重新执行或报告失败的 faulting instruction；single-step `#DB` 的 trap 场景保存的是完成被单步指令后的继续位置；普通 IRQ 保存的是恢复被异步打断执行流所需的位置。

## 3. 三种栈切换的最终对照

A15 至少涉及三种独立的栈机制：

```text
CPL3 -> CPL0 privilege stack switch
    CPU 在特权级变化时完成，目标来自 TSS 的 privilege stack 信息。

IST stack switch
    IDT gate 指定 IST 时由 CPU 完成，可在已经处于 CPL0 时发生。

per-CPU IRQ stack
    Linux 已进入普通 IRQ C path 后按条件执行的软件换栈策略。
```

看到 `%rsp` 变化时，必须先确定发生在哪个阶段，再判断属于哪一种机制；不能仅凭“换了栈”就称为 IST。

## 4. `pt_regs` 的统一边界

三条主线最终都使用 Linux 规范化的寄存器现场，但来源不同。统一原则是：

- CPU 只建立架构规定的 exception/interrupt frame；
- Linux 汇编入口继续保存 GPR、处理额外 slot，才形成 `struct pt_regs`；
- `orig_ax` 是 Linux 入口布局中的槽，不能在所有入口中机械解释为 syscall number；
- 对异常/IRQ，进入规范化 C path 后通常以 `orig_ax = -1` 表示“不是 syscall”；
- `ip/cs/flags` 的含义来自被保存的架构现场；`sp/ss` 是否来自硬件 privilege transition 必须结合入口 CPL 判断。

## 5. Linux 5.10 实现边界

A15 的 Linux 实现结论以 v5.10 x86-64 native 主线为基线。阅读时继续保留以下条件：

- `#MC` 等入口受 `CONFIG_X86_MCE` 等配置影响；
- PTI、虚拟化和特殊 entry 配置可能改变低层指令序列，但不能据此改写主线架构模型；
- 普通 device IRQ 的 `common_interrupt` 路径不能推广到 IPI、local APIC timer 等全部 system vector；
- generic IRQ flow handler、irqchip 和具体设备驱动不属于 assembly 基础课程；
- `#PF` 的入口交接在 A16 继续，真正的缺页处理策略属于 `memory/`。

## 6. 实验状态与证据边界

A15 三部分均已提供实验和 `expected-analysis.md`。其中用户态可构建/触发部分用于确认 faulting/trapping instruction 与用户现场；需要读取真实 IDT/TSS、入口 `%rsp`、vector、`irq_desc` 或早期 `pt_regs` 的部分需要匹配 Linux 5.10 guest、`vmlinux` 与 kernel-GDB。

当前课程维护环境缺少这一套可停机调试环境，因此这些动态值继续标记为待实测。源码事实、预期关系和调试步骤可以作为验收基线，但不能把示例地址或预期寄存器值写成已经观察到的结果。

## 7. A15 完成边界

从课程内容看，A15 已经回答：

```text
CPU 为什么以及如何通过 IDT 进入内核？
特权级变化时硬件 frame 和栈如何变化？
Linux 如何把不同入口规范化为 pt_regs？
有/无 hardware error code 的异常有何差别？
TSS/IST 如何提供特殊异常栈？
普通外部 IRQ 如何传递 vector 并进入 hardirq context？
privilege stack、IST stack 与 IRQ stack 如何区分？
fault、trap、interrupt 与 gate/error-code 分类为什么不能混用？
```

因此 A15 内容层面的机制已经闭合。进入 A16 后，只沿 `#PF` 这一具体 fault 继续追踪 `CR2`、page-fault error code、异常入口到内存管理代码的交接，以及处理完成后的返回；页表查找、VMA、缺页分配和 COW 等主体留在 `memory/`，避免在 assembly 中重复展开。
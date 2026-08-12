# Linux 5.10 x86-64 异常/中断入口基础源码事实核验

本文为 A15 的第一项源码事实核验，范围严格限制在“CPU 进入 x86-64 异常/中断入口时，Linux 5.10 如何把架构入口现场规范化为后续 entry code 可处理的栈布局”。缺页处理主体留给 A16，具体中断控制器和设备中断不在本基础课程展开。

## 1. 需要先区分的三个层次

异常/中断入口容易把三类规则混在一起：

1. **x86-64 架构规则**：IDT gate、特权级变化、硬件保存 RIP/CS/RFLAGS，以及某些异常由 CPU 额外压入 error code；
2. **Linux 入口设计**：为不同 vector 建立统一的汇编入口形态，补齐没有硬件 error code 的情况，再保存通用寄存器；
3. **Linux 5.10 具体实现**：相关宏和入口位于 `arch/x86/entry/entry_64.S`、`arch/x86/entry/entry_64_compat.S`、`arch/x86/include/asm/idtentry.h`、`arch/x86/include/asm/traps.h` 等文件，并由 IDT entry 宏生成具体符号。

后续正文必须始终标明结论属于哪一层。

## 2. CPU 自动保存的 frame 不是 Linux `pt_regs` 全部内容

从用户态进入 64-bit exception/interrupt gate 时，CPU 的架构入口动作会保存返回所需的控制状态。发生 CPL3 -> CPL0 特权级变化时，返回 frame 包含用户态的：

```text
SS
RSP
RFLAGS
CS
RIP
```

栈向低地址增长，因此分析汇编时必须区分“压栈时间顺序”和“最终从低地址到高地址看到的字段顺序”。

重要边界：CPU **不会自动保存所有通用寄存器**。Linux 后续看到的完整 `struct pt_regs` 是硬件 frame 与软件入口继续压入的寄存器共同形成的，不能把 `pt_regs` 整体称为“CPU 自动压栈”。

如果异常发生时没有发生特权级切换，硬件 frame 的栈切换/SS:RSP 语义与从用户态进入不同；A15 正文需要单独对照 user -> kernel 与 kernel -> kernel 两种入口，不能只用用户态模型泛化所有异常。

## 3. error code 必须区分“CPU 提供”和“Linux 补齐”

x86 异常并非都由 CPU 压入 error code。Linux 的入口宏需要把不同 vector 规范化为后续代码能够统一处理的布局。

因此后续讲解必须分成两类：

```text
CPU-error-code exception
    hardware already supplied error code

no-error-code exception / interrupt
    Linux entry code supplies a synthetic slot when统一入口布局需要它
```

不能写成“所有异常 CPU 都会压 error code”，也不能反过来写成“error code 都由 Linux 构造”。具体哪些 vector 带硬件 error code，应以 x86 架构定义和 Linux 5.10 对应 `idtentry` 宏实例共同核对。

## 4. Linux 5.10 的关键源码入口

A15 后续正文应从以下 Linux v5.10 路径继续核验，而不是套用更新内核版本的 entry 重构：

```text
arch/x86/entry/entry_64.S
arch/x86/entry/entry_64_compat.S
arch/x86/include/asm/idtentry.h
arch/x86/include/asm/traps.h
arch/x86/include/asm/segment.h
arch/x86/include/asm/ptrace.h
arch/x86/kernel/idt.c
arch/x86/kernel/traps.c
```

其中需要重点追踪：

- IDT gate 如何安装到具体入口符号；
- `idtentry`/相关汇编宏如何区分带 error code 与不带 error code 的入口；
- 何时执行 `swapgs` 或相应 GS 状态判断；
- 何时保存 GPR 并形成 `pt_regs`；
- C handler 接收到的 `struct pt_regs *` 与 error code/vector 信息从哪里来；
- 返回路径何时能够复用 A14 已讲过的 IRET 基础设施。

## 5. 与 TSS/IST 的边界

A15 大纲还包含 TSS 和 IST。这里先固定一个原则：

- 普通的 CPL3 -> CPL0 gate 可以因为特权级变化而使用 TSS 中的 ring-0 stack 信息；
- 配置了 IST 的 IDT gate 使用指定 IST stack，解决某些入口不能安全依赖当前栈的问题；
- “发生异常就使用 IST”是错误概括，必须逐个核对 Linux 5.10 的 IDT gate 配置。

IST 的具体 vector、TSS 字段和 Linux 5.10 初始化路径留给 A15 后续最小单元，不在本文件凭记忆列举。

## 6. 与 A14 的连续关系

A14 已经说明 syscall 入口的一个关键特征：`SYSCALL` 本身不自动构造 IRET frame，Linux 在 `entry_SYSCALL_64` 中软件构造 `pt_regs`。异常/中断入口恰好提供重要对照：它们经 IDT gate 进入时，CPU 会先提供架构定义的返回 frame，Linux 再把软件保存的寄存器接到这个 frame 上。

因此 A15 的第一条教学主线应是：

```text
IDT gate
→ CPU architecture frame
→ error-code normalization
→ Linux GPR save
→ pt_regs
→ C-level handler
→ return preparation
→ IRET
```

这条线能避免把 syscall、exception 和 interrupt 三种入口误认为同一种“CPU 自动压栈”。

## 7. 本次核验结论与下一步

本次只完成 A15 的入口模型边界和源码定位，不宣称已经完成具体 vector 的逐条实现核验。下一最小单元应在 Linux v5.10 源码中选择一组“无硬件 error code”与“有硬件 error code”的代表性异常，展开实际生成的 entry symbol、栈布局和 `pt_regs` 对应关系；随后再进入 TSS/IST。

动态实验应优先使用隔离 Linux 5.10 guest + 匹配 `vmlinux` 的 kernel-GDB。当前课程维护环境缺少这一组合时，只记录可执行步骤和源码预期，不伪造断点结果。

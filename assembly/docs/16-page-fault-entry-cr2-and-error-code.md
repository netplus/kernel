# A16 第一部分：`#PF` 入口、CR2 与 page-fault error code

缺页异常是理解“CPU 异常入口如何与内存管理交接”的最好例子之一。它和 A15 中的 `#GP` 一样属于同步异常，也由 CPU 提供 error code；但 `#PF` 还额外依赖 CR2 保存导致异常的线性地址。因此，分析 `#PF` 时必须同时跟踪三类现场：触发异常的指令、访问的地址，以及 CPU 对这次访问失败原因的编码。

本节只讲 x86-64 异常入口到 Linux 5.10 内存管理代码的交接。VMA 查找、页表建立、匿名页分配、Copy-on-Write 等缺页处理主体放在 `memory/` 课程中。

Linux 5.10 源码事实核验见 [`../source-paths/16-page-fault-entry-linux-5.10.md`](../source-paths/16-page-fault-entry-linux-5.10.md)。

## 1. `#PF` 要回答三个不同的问题

假设用户程序执行一条访存指令：

```asm
movq (%rax), %rdx
```

如果 `%rax` 指向的线性地址当前不能完成访问，处理器可能产生 `#PF`。此时至少有三个不同的问题：

```text
哪条指令触发了异常？        -> saved RIP / pt_regs->ip
访问哪个线性地址失败？      -> CR2
为什么这次访问失败？        -> page-fault error code
```

这三个值不能互相替代。

`pt_regs->ip` 描述执行位置；CR2 描述地址；error code 描述访问性质和失败条件。尤其要避免把 CR2 理解成“异常 RIP”，或者把 `pt_regs->orig_ax` 当作 page-fault error code。

## 2. 架构层：CPU 在进入 Linux 之前已经做了什么

`#PF` 是 x86-64 的 hardware-error-code exception。处理器根据 IDT 中 vector 14 的 gate 转移控制流，并建立异常返回所需的 hardware frame；同时把 page-fault error code 放入入口栈。

如果异常导致 CPL3 -> CPL0 的特权级变化，hardware frame 还包含旧用户栈的 SS/RSP。这里的具体 frame 规则属于 x86-64 架构，而不是 Linux 自己的 `pt_regs` 设计。

另一个关键架构动作是更新 CR2。CR2 保存导致 page fault 的线性地址。CR2 不属于 CPU 自动压入的 exception frame，也不属于 Linux `struct pt_regs`。

因此，刚进入内核时可以把现场抽象为：

```text
CPU register state
        |
        +-- saved RIP/RFLAGS/... -> hardware exception frame
        +-- PF error code        -> hardware error-code slot
        +-- fault address        -> CR2
```

Linux 必须把这些来源不同的信息重新组织后再交给 C 代码。

## 3. Linux 5.10 如何把入口现场组织成 `pt_regs`

A15 已经建立普通 hardware-error-code exception 的入口模型。`#PF` 沿用同一个重要原则：低层汇编入口保存通用寄存器并形成 `struct pt_regs`，真实 error code 作为独立参数传给 C handler。

最终应区分：

```text
struct pt_regs *regs
    -> 通用寄存器和异常返回现场
    -> regs->ip 是 faulting instruction 的 RIP

unsigned long error_code
    -> CPU 提供的 page-fault error code

unsigned long address
    -> 从 CR2 读取的 faulting linear address
```

对于 hardware-error-code exception，入口过程中 error-code slot 会被消费并转交给 handler；`orig_ax` 会恢复为 Linux 对异常入口使用的规范化值。因此进入 page-fault C 主线后，不应再通过 `orig_ax` 寻找 page-fault error code。

## 4. Linux 5.10 的 C 入口：`exc_page_fault()`

Linux 5.10 x86-64 在：

```text
arch/x86/mm/fault.c
```

定义 page-fault C 入口。该入口使用：

```text
DEFINE_IDTENTRY_RAW_ERRORCODE(exc_page_fault)
```

这里的 `RAW` 很重要。普通 idtentry wrapper 可以统一包办一部分 irqentry bookkeeping，而 page fault 需要在自己的入口中先处理 CR2 和若干特殊情况，因此使用 raw variant，自行安排进入/退出 bookkeeping 的时机。

主线可以先简化成：

```text
#PF
 |
 v
low-level IDT entry
 |
 | 形成 pt_regs
 | error code -> 独立参数
 v
exc_page_fault(regs, error_code)
 |
 | read_cr2()
 v
address
 |
 v
irqentry_enter(regs)
 |
 v
handle_page_fault(regs, error_code, address)
 |
 v
irqentry_exit(regs, state)
```

这个模型比直接背函数名更重要：到 `handle_page_fault()` 时，入口代码已经把“执行现场、失败原因、失败地址”整理成三个清晰对象。

## 5. 为什么要尽早读取 CR2

CR2 是架构寄存器，而不是本次异常专属的栈槽。后续执行过程中如果再次发生 page fault，CR2 会被新的 fault address 更新。

因此 Linux 在 `exc_page_fault()` 入口早期执行 `read_cr2()`，把当前 fault address 保存到普通 C 变量 `address` 中。后续主线使用这个已经保存的值，而不是任意晚的时候重新读取 CR2。

这说明一个通用的入口设计原则：

> 对可能被后续事件覆盖的硬件现场，应在入口足够早的位置把它转存为本次事件自己的软件状态。

## 6. page-fault error code 表达什么

Linux 5.10 使用 `X86_PF_*` 位解释 CPU 给出的 page-fault error code。主线中需要认识：

```text
X86_PF_PROT   页不存在与保护性错误的基本区分
X86_PF_WRITE  访问是否为写
X86_PF_USER   访问是否发生在 user context 对应的权限语义下
X86_PF_RSVD   页表项保留位违规
X86_PF_INSTR  instruction fetch fault
X86_PF_PK     protection-key 相关错误
```

这些位是 CPU 报告的架构信息。Linux 内存管理随后会据此构造自己的 fault flags、选择处理分支。不要把 `X86_PF_*` 与内存管理内部的 `FAULT_FLAG_*` 当成同一层编码。

## 7. `handle_page_fault()` 是 assembly 与 memory 的交接点

`handle_page_fault()` 首先根据 fault address 判断这次 fault 应进入 kernel-address 还是 user-address 主线：

```text
handle_page_fault()
    |
    +-- fault_in_kernel_space(address)
    |       |
    |       +-- true  -> do_kern_addr_fault(...)
    |       |
    |       +-- false -> do_user_addr_fault(...)
```

从 assembly 课程的角度，到这里已经完成主要任务：

```text
入口寄存器现场  -> regs
CPU failure info -> error_code
CR2              -> address
```

接下来 VMA 是否存在、访问权限是否合法、页是否需要分配、页表是否需要建立等问题属于内存管理课程。

这种课程边界也对应真实的软件边界：异常入口负责保存和规范化 CPU 现场，内存管理负责解释地址空间状态并尝试解决 fault。

## 8. 为什么可恢复 `#PF` 会重新执行原指令

`#PF` 是 fault 语义的典型例子。对于 demand paging 等可恢复情况，内核修复导致 fault 的地址空间状态后，异常返回恢复的是 faulting instruction 的 RIP。

例如：

```asm
movq (%rax), %rdx
```

第一次执行时目标页尚未建立有效映射：

```text
movq
  -> #PF
  -> 内核建立/修复映射
  -> 返回原 RIP
  -> movq 再执行一次
  -> 访问成功
```

因此 `regs->ip` 的意义与 A15 中 single-step `#DB` 的 trap 语义不同，也与普通外部 IRQ 保存“被异步打断位置”的语义不同。

不是所有 page fault 都能这样恢复。非法地址、权限错误、reserved-bit violation 或无法修复的 kernel access 可能转入 signal、exception-table fixup、oops 等路径。

## 9. 中断状态不能简化成“page fault 全程关中断”

异常刚进入低层入口时的 interrupt state 与真正执行内存管理主线时的状态不是一回事。

Linux 5.10 的 `do_user_addr_fault()` 在已经保存 CR2 并完成早期处理之后，会按 fault 来源恢复适合的中断状态。对 user-mode fault，主线可以执行 `local_irq_enable()`；对 kernel-mode fault，则依据保存的 `X86_EFLAGS_IF` 判断。返回低层退出路径前又需要满足相应的中断状态约束。

因此阅读源码时应逐阶段问：

```text
当前在哪个入口阶段？
CR2 是否已经安全保存？
irqentry bookkeeping 是否已经建立？
当前 IF 状态是什么？
后续代码是否允许中断重新打开？
```

不能用“异常入口会关中断”一句话概括整个 `#PF` 生命周期。

## 10. 一次 user demand fault 的连续模型

把前面的内容连起来，可以得到 A16 第一部分的核心执行模型：

```text
用户指令访问一个尚未建立有效映射的地址
        |
        v
CPU 产生 #PF
        |
        +-- saved RIP -> faulting instruction
        +-- PF error code -> hardware error-code slot
        +-- fault address -> CR2
        |
        v
Linux low-level exception entry
        |
        +-- 保存 GPR
        +-- 构造/规范化 pt_regs
        +-- error code 独立传给 C handler
        |
        v
exc_page_fault(regs, error_code)
        |
        +-- address = read_cr2()
        |
        v
irqentry_enter(regs)
        |
        v
handle_page_fault(regs, error_code, address)
        |
        v
do_user_addr_fault(...)
        |
        v
memory subsystem 修复地址空间状态
        |
        v
返回异常入口
        |
        v
恢复 faulting RIP
        |
        v
原访存指令重新执行
```

这个模型中最重要的不是记住某一个函数，而是始终同时跟踪 `RIP`、CR2、error code 和入口栈。

## 11. 与 A15 的关系

A15 已经解释了 IDT、hardware frame、error-code exception、`pt_regs`、TSS/IST 和普通 IRQ。A16 不重复这些基础机制，只增加 `#PF` 特有的 CR2 和与内存管理的交接。

可以把 `#GP` 与 `#PF` 做如下对照：

| 项目 | `#GP` | `#PF` |
| --- | --- | --- |
| 同步异常 | 是 | 是 |
| CPU 提供 error code | 是 | 是 |
| 额外 fault-address 寄存器 | 无 | CR2 |
| saved RIP | faulting instruction | faulting instruction |
| Linux C handler 的错误信息 | 独立 error-code 参数 | 独立 error-code 参数 |
| 主要后续子系统 | trap/error handling | memory management |

## 12. 本节验收点

完成本节后，应能准确回答：

1. `regs->ip`、CR2 和 page-fault error code 分别描述什么；
2. 为什么 CR2 不在 `pt_regs` 中；
3. 为什么 Linux 要在 `exc_page_fault()` 早期保存 CR2；
4. hardware error code 如何与 `orig_ax` 区分；
5. `DEFINE_IDTENTRY_RAW_ERRORCODE()` 的 `RAW` 对入口组织意味着什么；
6. `handle_page_fault()` 为什么是 assembly 与 memory 课程的主要交接点；
7. 为什么可恢复 user demand fault 返回后会重新执行 faulting instruction；
8. 为什么不能把 page-fault handler 简化成“全程关中断”。

下一步实验应安全触发一个可恢复的 user demand fault，并同时观测 faulting RIP、fault address、page-fault error code 和处理后的重试行为；需要 kernel-GDB 的入口现场仍应在匹配 Linux 5.10 guest/vmlinux 环境中验证。
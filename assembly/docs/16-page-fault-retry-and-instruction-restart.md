# A16 第二部分：page fault 内部重试、异常返回与原指令重新执行

A16 第一部分已经建立 `#PF` 的入口模型：CPU 保存 faulting RIP，把失败地址写入 CR2，并提供 page-fault error code；Linux 5.10 在入口早期保存这些现场，再把处理交给内存管理。

这一部分只回答返回侧的一个问题：**内核修复 fault 之后，为什么用户指令能够继续执行？**

这里最容易混淆的是两个都叫“retry”的过程。Linux 内存管理内部可以因为 `VM_FAULT_RETRY` 重新进入 fault 处理；而 CPU 真正重新执行 faulting instruction，则发生在整个异常处理结束、低层返回恢复原 RIP 之后。二者发生在不同层次，不能合并成一个动作。

Linux 5.10 源码事实核验见 [`../source-paths/16-page-fault-retry-return-linux-5.10.md`](../source-paths/16-page-fault-retry-return-linux-5.10.md)。

## 1. 先区分两种 retry

假设用户程序第一次写一个合法但尚未建立实际页映射的匿名页：

```asm
movb $0x5a, (%rax)
```

第一次执行该指令时可能产生 `#PF`。从这之后存在两种完全不同的“重试”。

第一种发生在 Linux fault handler 内部：

```text
do_user_addr_fault()
    -> handle_mm_fault()
    -> VM_FAULT_RETRY
    -> 设置 FAULT_FLAG_TRIED
    -> 回到 do_user_addr_fault() 内部 retry 标签
```

此时 CPU **仍然处于同一次 #PF 的内核处理过程中**。内核还没有返回用户态，原来的 `movb` 也没有重新执行。

第二种发生在异常处理已经成功完成之后：

```text
fault handler 成功
    -> 返回低层异常入口
    -> 恢复保存的用户寄存器和 faulting RIP
    -> 返回 CPL3
    -> CPU 再次执行原 movb
```

这才是 instruction restart。

因此应使用两个不同术语：

```text
fault-handler retry       Linux 内存管理内部重新尝试处理同一次 #PF
instruction restart       异常返回后 CPU 重新执行 faulting instruction
```

## 2. 为什么 faulting RIP 不需要向前移动

x86 的 page fault 具有 fault 语义。对于可恢复 `#PF`，CPU 保存的 RIP 指向**触发 fault 的那条指令**，而不是它的下一条指令。

这意味着 Linux 正常修复 demand fault 时不需要做类似下面的动作：

```text
regs->ip += instruction_length
```

相反，正常主线应保持 `regs->ip` 指向 faulting instruction：

```text
第一次执行 movb
    |
    +-- 目标映射尚不可用
    v
#PF
    |
    +-- pt_regs->ip = movb 的 RIP
    v
Linux 修复映射
    |
    +-- 不推进 pt_regs->ip
    v
异常返回恢复同一个 RIP
    |
    v
第二次执行 movb
```

如果 Linux 在成功修复 fault 后把 RIP 推到下一条指令，原本失败的访存就会被跳过，程序语义反而被破坏。

这与 A15 中 single-step `#DB` 的 trap 语义不同：trap 报告的是已经完成的指令之后的执行位置，而 page fault 的恢复点是尚未成功完成的 faulting instruction。

## 3. `VM_FAULT_RETRY` 解决的不是“重新执行用户指令”

Linux 5.10 `arch/x86/mm/fault.c` 的 `do_user_addr_fault()` 调用 `handle_mm_fault()`。某些 fault 处理过程可能需要暂时放弃当前持有状态，再重新取得 `mmap_lock` 并继续。

当返回值包含 `VM_FAULT_RETRY`，且当前 fault 仍允许 retry 时，x86 fault 主线会设置 `FAULT_FLAG_TRIED`，再回到函数内部的 `retry:`。

可以把它抽象成：

```text
同一次 #PF
    |
    v
do_user_addr_fault()
    |
    +-- attempt 1
    |      |
    |      +-- VM_FAULT_RETRY
    |
    +-- attempt 2
           |
           +-- success
    |
    v
退出 #PF handler
```

这里始终只有一次硬件异常入口。`VM_FAULT_RETRY` 不意味着：

```text
iret -> 用户态 -> 原指令 -> 再次 #PF
```

把这两个过程分开，对后续阅读锁、阻塞和 major fault 路径尤其重要。

## 4. 正常 demand fault 的返回主线

对一个最终成功修复的 user demand fault，可以把 A16 的入口和返回连成下面的完整模型：

```text
用户 faulting instruction
        |
        v
CPU #PF
        |
        +-- saved RIP = faulting RIP
        +-- CR2 = fault address
        +-- PF error code
        |
        v
Linux low-level entry / pt_regs
        |
        v
exc_page_fault()
        |
        +-- 尽早保存 CR2
        v
handle_page_fault()
        |
        v
do_user_addr_fault()
        |
        +-- 可能发生 fault-handler retry
        v
handle_mm_fault() 最终成功
        |
        v
返回 exc_page_fault()
        |
        v
irqentry_exit() / 低层异常返回
        |
        +-- 恢复保存的用户 RIP/RSP/RFLAGS 等现场
        v
CPU 回到 faulting RIP
        |
        v
原访存指令重新执行
```

这里 assembly 课程关注的是两端的交接：入口如何保存现场，以及处理成功后如何保持并恢复 faulting RIP。匿名页分配、页表安装、COW 等实际“如何修复映射”的机制属于 `memory/`。

## 5. 为什么不能把所有 `#PF` 都描述成“修复后重试”

只有**成功修复并选择正常返回**的 fault 才会沿上述主线重新执行原指令。

Linux 5.10 在 `handle_mm_fault()` 返回后还需要检查多种结果，例如：

```text
VM_FAULT_RETRY
VM_FAULT_ERROR
fault_signal_pending(...)
```

此外，具体 fault 还可能进入：

```text
用户态 signal
kernel exception-table fixup
oops/error path
```

这些路径的最终控制流并不等价于“恢复原 RIP 后重新执行”。

因此准确表述应是：

> 对已经成功修复、并从异常处理正常返回的可恢复 page fault，低层异常返回恢复 faulting RIP，CPU 随后重新执行原指令。

而不是：

> page fault 总会重新执行原指令。

## 6. 中断状态也有阶段边界

`#PF` 刚进入低层 entry 时的中断状态，不等于整个 fault 处理过程中的中断状态。

Linux 5.10 在 `exc_page_fault()` 入口早期已经保存 CR2 后，user fault 主体可以重新打开中断。`do_user_addr_fault()` 会根据 fault 来源恢复适合执行内存管理代码的中断状态。

当 user-address fault 主线返回到 `handle_page_fault()` 的公共汇合点时，Linux 再执行 `local_irq_disable()`，使返回 `exc_page_fault()`、`irqentry_exit()` 和低层异常退出时满足入口代码要求的状态。

所以连续模型是：

```text
低层 #PF entry
    -> 保存 CR2
    -> irqentry bookkeeping
    -> fault 主体可重新开中断
    -> fault 处理完成
    -> 公共汇合点重新关中断
    -> irqentry_exit()
    -> 低层异常返回
```

不能把它简化成“page fault handler 全程关中断”。

## 7. 与现有 demand-fault 实验如何对应

[`../labs/16-page-fault-demand/`](../labs/16-page-fault-demand/) 已经通过一个合法匿名 VMA 的首次写访问观察到：

```text
页面：non-resident -> resident
写操作最终完成
数据能够读回
```

这证明了用户可见层面的“fault 可恢复并且原访问最终完成”。实验还通过反汇编固定了实际 faulting store，避免只从 C 源码猜测 RIP 对应哪条机器指令。

但用户态现象本身不能证明下面这些内核入口事实：

```text
pt_regs->ip 的具体值
CR2 的具体值
hardware PF error code
VM_FAULT_RETRY 是否在本次 fault 中发生
```

这些值仍应在匹配 Linux 5.10 `vmlinux` 的 kernel-GDB 环境中直接观察。尤其不能看到一次 minor fault 就推断发生了 `VM_FAULT_RETRY`；二者不是同一个概念。

## 8. kernel-GDB 的关键验收点

在可停机调试的 Linux 5.10 guest 中，对现有 demand-fault 实验应至少检查：

```text
regs->ip == trigger 程序中 faulting store 的 RIP
CR2/address == mmap 返回页内的目标地址
error_code 包含本次用户写访问对应的语义位
```

在 `handle_mm_fault()` 成功返回、准备退出正常 user-fault 主线时再次检查：

```text
regs->ip 仍等于原 faulting store RIP
```

最后继续执行，程序应完成原 store，并能读回写入值。

如果要专门验证 `VM_FAULT_RETRY`，必须选择确实能触发该内核返回值的场景，并在 `do_user_addr_fault()` 的 `retry:` 路径观察；不能把普通匿名页首次 minor fault 当作它的替代证据。

## 9. 本节与 memory 课程的边界

A16 到这里已经能够回答 assembly/entry 侧的完整问题：

```text
CPU 为什么进入 #PF？
入口保存了什么？
CR2/error code/pt_regs 分别承担什么角色？
内存管理成功后为什么能够继续原指令？
异常返回恢复什么现场？
```

而下面这些问题继续留在 `memory/`：

```text
VMA 如何查找？
PTE 如何建立？
匿名页如何分配？
Copy-on-Write 如何复制页面？
major/minor fault 如何形成？
VM_FAULT_RETRY 在具体内存管理路径中为什么出现？
```

这种划分避免在 assembly 领域重复讲解完整缺页处理算法。

## 10. 本节验收点

完成本节后，应能准确回答：

1. `VM_FAULT_RETRY` 与 CPU instruction restart 有什么区别；
2. 为什么正常可恢复 `#PF` 不推进 `regs->ip`；
3. faulting RIP 在入口和返回两端分别起什么作用；
4. 为什么一次普通 minor fault 不能证明发生了 `VM_FAULT_RETRY`；
5. 哪些 error/signal/fixup 路径不能套用“修复后重新执行”模型；
6. 为什么 page-fault 主体可能重新打开中断；
7. assembly 课程与 memory 课程在 `#PF` 处理上的交接边界在哪里。

下一步应把 A16 第一部分的入口教程、demand-fault 实验、本节返回教程以及两份 Linux 5.10 source-path 一并接入领域 README；在 README 状态与实际内容一致后，再判断 A16 是否已经达到整章完成标准。
# A16 缺页异常入口：整章一致性复核

本页用于把 A16 已完成的两部分放回同一条执行主线，并检查进入 A17 前的课程边界。它不是新的缺页处理教程；页表建立、VMA 查找、匿名页分配、Copy-on-Write 等内存管理主体仍属于 `memory/`。

## 1. A16 要解决的问题

A15 已经建立普通异常入口、IST 和外部中断的通用模型。A16 只选择 `#PF` 这个重要异常继续追踪两个问题：

1. CPU 如何把“哪条指令失败、访问哪个线性地址、为什么失败”交给 Linux 5.10；
2. 内核修复一个可恢复的 page fault 后，为什么原访存指令能够继续完成。

因此 A16 的边界是：

```text
faulting instruction
        |
        v
#PF hardware entry
        |
        +-- saved RIP        哪条指令需要恢复
        +-- CR2              哪个线性地址访问失败
        +-- PF error code    这次失败的架构原因
        |
        v
Linux x86 entry / pt_regs
        |
        v
exc_page_fault()
        |
        v
handle_page_fault()
        |
        +--> do_user_addr_fault()
        |       |
        |       +--> memory subsystem fixes mapping
        |       +--> possible VM_FAULT_RETRY inside handler
        |
        v
exception return
        |
        v
restore saved faulting RIP
        |
        v
CPU executes the original instruction again
```

## 2. 三类入口现场不能混为一个对象

第一部分已经固定三类彼此独立的信息：

| 信息 | 来源 | 主要含义 |
| --- | --- | --- |
| `pt_regs->ip` | CPU 保存的异常返回现场，随后由 Linux 纳入 `pt_regs` | fault 发生时需要恢复的指令位置 |
| CR2 | x86 控制寄存器 | 导致 `#PF` 的线性地址 |
| page-fault error code | CPU 压入异常栈 | present/protection、read/write、user/supervisor 等架构原因 |

CR2 不属于 `struct pt_regs`。page-fault error code 也不能与 Linux 内存管理内部的 `FAULT_FLAG_*` 或 `VM_FAULT_*` 返回位混用。前者属于 x86 架构入口现场，后两者属于 Linux 内存管理实现语义。

## 3. `#PF` 与 A15 普通异常模型的关系

`#PF` 是同步异常，并且由 CPU 提供 hardware error code。因此它继承 A15 已经建立的普通异常基本模型，但又增加 CR2 这一独立状态。

Linux 5.10 中 A16 已核验的关键交接点是：

```text
DEFINE_IDTENTRY_RAW_ERRORCODE(exc_page_fault)
        |
        +--> read_cr2()
        +--> irqentry_enter()
        +--> handle_page_fault(regs, error_code, address)
                    |
                    +--> do_kern_addr_fault(...)
                    `--> do_user_addr_fault(...)
```

这里 `address`、`error_code` 和 `regs` 分别承载不同信息。正文和实验都不应把“fault address”写成 `regs->ip`，也不应把 CR2 写成 `pt_regs` 字段。

## 4. 两种 retry 必须保持分层

第二部分已经明确区分两个都可能被口语称为“重试”的过程。

### 4.1 fault handler 内部的 retry

Linux 5.10 的 `do_user_addr_fault()` 调用 `handle_mm_fault()` 后，可能收到 `VM_FAULT_RETRY`。在允许重试的条件下，它设置相应状态并重新进入 fault handler 内部的 `retry:` 路径。

此时 CPU 仍没有返回用户态；这是**同一次 `#PF` 处理过程内部**的 Linux 控制流。

### 4.2 CPU 对 faulting instruction 的重新执行

当缺页已经成功修复，异常入口逐层返回，并恢复 CPU 最初保存的 faulting RIP。对于正常可恢复的 demand fault，Linux 不通过手工增加 `regs->ip` 来“跳过”原指令。

返回后 CPU 从保存的 RIP 继续，于是原访存指令重新执行；由于映射已经建立，这一次可以完成。

所以：

```text
VM_FAULT_RETRY
!=
exception return + instruction restart
```

前者发生在 fault handler 内部，后者发生在异常处理已经完成之后。

## 5. demand-fault 实验已经验证什么

`labs/16-page-fault-demand/` 使用一个合法匿名 VMA 的首次写访问触发可恢复 demand fault。当前可执行环境已经完成用户态验证：

- 首次访问前目标页不驻留；
- 首次写访问后目标页驻留；
- minor-fault 计数增加；
- faulting store 最终成功，随后能够读回写入值；
- 反汇编已经定位实际 faulting store 指令。

这些结果能够证明“首次访问触发可恢复缺页，修复后原操作最终完成”的用户可见结果，但不能单独证明某个具体内核入口寄存器值。

CR2、hardware PF error code、`pt_regs->ip` 以及 Linux 5.10 入口/返回的逐指令动态现场仍需要匹配的 Linux 5.10 guest、`vmlinux` 与 kernel-GDB 环境。没有该环境时，仓库只记录源码事实与预期观测，不把预期值冒充实测结果。

## 6. 不能把所有 `#PF` 都概括成“修复后重试”

A16 的 restart 模型只适用于内核成功修复、并按原 RIP 正常返回的 fault。下面几类路径不能机械套用该结论：

- fault 无法修复并最终向用户态递送 signal；
- kernel fault 命中 exception table，通过 fixup 修改返回位置；
- 内核判断地址或访问类型非法并进入错误路径；
- 其他路径显式修改最终异常返回现场。

因此准确表述应是：**可恢复 page fault 在成功修复且返回现场未被改写时，会恢复 faulting RIP，使 CPU 再次执行原指令。**

## 7. A16 与 memory 课程的交接边界

assembly 课程需要回答：

```text
#PF 如何进入内核？
RIP、CR2、error code 分别是什么？
pt_regs 如何承载返回现场？
入口如何把 fault 交给 memory 代码？
成功处理后为什么能够从 faulting RIP 继续？
```

下面的问题属于 `memory/`：

```text
VMA 如何查找？
页表项如何判断和建立？
匿名页从哪里分配？
COW 如何复制页面？
缺页期间如何处理 mmap_lock？
VM_FAULT_RETRY 为什么产生？
```

A16 可以指出这些对象是交接后的处理主体，但不在 assembly 中重复完整讲解。

## 8. 进入 A17 前的验收结论

从内容本身看，A16 已经形成完整的 assembly-side 主线：

```text
#PF architecture state
-> Linux 5.10 exception entry
-> CR2 / error code / pt_regs
-> memory-subsystem handoff
-> successful return
-> faulting-instruction restart
```

对应材料包括：

- 第一部分正文：`docs/16-page-fault-entry-cr2-and-error-code.md`；
- 第一部分源码核验：`source-paths/16-page-fault-entry-linux-5.10.md`；
- demand-fault 实验：`labs/16-page-fault-demand/`；
- 第二部分正文：`docs/16-page-fault-retry-and-instruction-restart.md`；
- 第二部分源码核验：`source-paths/16-page-fault-retry-return-linux-5.10.md`。

在领域 README 接入这些材料并完成链接复核后，A16 可以按 assembly 课程边界收口。下一章 A17 再进入 `switch_to` / `__switch_to_asm` 和任务内核栈切换，不在 A16 提前展开调度器主体。
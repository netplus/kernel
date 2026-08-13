# Linux 5.10 x86-64 `#PF` 修复、重试与返回源码事实核验

本文补充 A16 的返回边界，源码基线为 upstream Linux v5.10 `arch/x86/mm/fault.c`。

## 1. 两种“重试”必须分开

A16 第一部分已经建立：

```text
#PF -> exc_page_fault() -> handle_page_fault() -> do_user_addr_fault()
```

Linux 5.10 的 `do_user_addr_fault()` 调用 `handle_mm_fault(vma, address, flags, regs)`。如果返回值包含 `VM_FAULT_RETRY` 且当前仍允许 retry，代码设置 `FAULT_FLAG_TRIED` 后跳回函数内部的 `retry:` 标签，重新取得 `mmap_lock` 并继续 fault 处理。

因此 `VM_FAULT_RETRY` 表示 **同一次 #PF 处理过程中的内核内部重试**，不是 CPU 已经返回用户态并重新执行 faulting instruction。

真正的 instruction retry 发生在可恢复 fault 被成功处理之后：低层异常返回恢复 CPU 为 fault 保存的 RIP，CPU 随后再次执行原访存指令。

## 2. 为什么正常 demand fault 不需要修改 `regs->ip`

`#PF` 是 fault 语义异常。CPU 保存的 RIP 指向 faulting instruction。Linux 5.10 的正常 user demand-fault 主线在 `handle_mm_fault()` 成功后不会为了“跳过”这条指令而推进 `regs->ip`。

连续模型是：

```text
faulting instruction
 -> CPU 保存 faulting RIP
 -> Linux 修复地址空间状态
 -> 保留该 RIP
 -> 公共异常返回恢复 RIP
 -> 原指令重新执行
```

这与 single-step `#DB` 的 trap 语义不同。

## 3. error/signal 路径不是正常 instruction retry

`handle_mm_fault()` 返回后，Linux 5.10 会检查 `fault_signal_pending()`、`VM_FAULT_RETRY` 和 `VM_FAULT_ERROR`。因此“page fault 返回后会重试原指令”必须限定为 fault 已成功修复且没有转入 signal、exception-table fixup 或内核错误处理等其他结果。

## 4. 中断状态的返回边界

CR2 已在 `exc_page_fault()` 入口早期保存后，`do_user_addr_fault()` 对 user-mode fault 可以执行 `local_irq_enable()`。`handle_page_fault()` 从 user-address 主线返回后统一执行 `local_irq_disable()`，再回到 `exc_page_fault()` 的 `irqentry_exit()` 和低层 IDT 返回代码。

所以 page-fault 生命周期不能概括成“全程关中断”。正确模型是：

```text
低层入口
 -> 保存 CR2
 -> fault 主体可重新开中断
 -> 公共汇合点重新关中断
 -> irqentry_exit()
 -> 低层异常返回
```

## 5. 与现有实验的对应

`labs/16-page-fault-demand/` 已通过首次匿名页写访问观察到页面从 non-resident 变为 resident，并在本次环境中出现一次 minor fault。该用户态结果证明 fault 可恢复，但不能单独证明内核入口时的 `pt_regs->ip`、CR2 和 hardware error code。

匹配 Linux 5.10 `vmlinux` 的 kernel-GDB 验证应进一步检查：

```text
regs->ip == faulting store 的 RIP
address == CR2 保存的目标线性地址
error_code 的 WRITE/USER/PROT 位符合本次访问
```

正常 demand-fault 主线在处理成功后，`regs->ip` 应仍保持 faulting store 的 RIP；随后由公共异常返回恢复该 RIP。

## 6. 本次核验结论

- `VM_FAULT_RETRY` 是 fault-handler 内部 retry，不是 CPU instruction retry；
- 正常可恢复 `#PF` 不需要人工推进 `regs->ip`；
- instruction retry 来自异常返回恢复 faulting RIP；
- signal/error/fixup 路径必须与正常 demand-fault 返回分开；
- user fault 主体可以重新开中断，返回低层 entry 前再恢复所需中断状态；
- `handle_mm_fault()` 内部的页分配、COW 和页表修改属于 `memory/`，A16 只跟踪入口与返回交接。
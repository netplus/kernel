# Linux 5.10 x86-64 `#PF` 入口源码事实核验

A16 只追踪 page-fault 的架构入口与内存管理交接；VMA、页表分配、COW 等主体留在 `memory/`。

## 已核验源码

基线为 upstream Linux v5.10 x86-64：

- `arch/x86/include/asm/idtentry.h`
- `arch/x86/mm/fault.c`
- `arch/x86/entry/entry_64.S`
- `arch/x86/entry/calling.h`
- `arch/x86/include/asm/ptrace.h`

`#PF` 是 hardware-error-code 异常。低层入口把 CPU exception frame 与 error-code slot 规范化为 Linux `pt_regs`，并把 error code 作为独立参数传给 C handler；不能把 `orig_ax` 当成 page-fault error code。

## `exc_page_fault()`

Linux v5.10 在 `arch/x86/mm/fault.c` 使用 `DEFINE_IDTENTRY_RAW_ERRORCODE(exc_page_fault)`。RAW variant 不由宏自动执行 `irqentry_enter()/irqentry_exit()`，因为 page-fault 入口需要先完成自己的早期工作。

函数入口立即通过 `read_cr2()` 取得 faulting linear address。这里必须区分三个对象：

```text
regs->ip    触发 fault 的指令现场
error_code  CPU 给出的 page-fault 访问/权限信息
CR2         导致 fault 的线性地址
```

`CR2` 不属于 `pt_regs`。

处理 KVM async-PF 特例后，主线执行：

```text
irqentry_enter(regs)
 -> handle_page_fault(regs, error_code, address)
 -> irqentry_exit(regs, state)
```

`handle_page_fault()` 再按 `fault_in_kernel_space(address)` 分到 `do_kern_addr_fault()` 或 `do_user_addr_fault()`。这就是 assembly 与 memory 课程的主要交接点。

## error-code 位

v5.10 主线直接使用 `X86_PF_PROT`、`X86_PF_WRITE`、`X86_PF_USER`、`X86_PF_RSVD`、`X86_PF_INSTR` 和 `X86_PF_PK`。这些是 CPU error code 的架构信息；Linux 再据此设置自己的 fault flags，例如 write/instruction fault 标志。两层语义不能混写。

## 中断状态

不能把 page-fault handler 简化成“全程关中断”。`do_user_addr_fault()` 在 CR2 已保存且早期处理完成后，对 user-mode fault 执行 `local_irq_enable()`；kernel-mode fault 则依据保存的 `X86_EFLAGS_IF` 决定。user-address fault 返回后，`handle_page_fault()` 再 `local_irq_disable()`，满足低层退出路径的状态要求。

## fault 语义

可恢复的 `#PF` 返回后需要重新执行触发访问，因此 `pt_regs.ip` 保存的是 faulting instruction 的现场；这与 single-step `#DB` 的 trap 语义、普通 IRQ 的 asynchronous interrupted RIP 不同。并非所有 `#PF` 都可恢复：非法地址、权限错误、reserved-bit violation 或不可修复 kernel access 会进入信号、exception-table fixup 或 oops 等路径。

## 配置和边界

主线是 Linux v5.10 x86-64 native。KVM async-PF、`CONFIG_VMAP_STACK`、kmmio、kprobes、vsyscall 等只作为特殊分支记录；x86-32 的 vmalloc fault 同步逻辑不能混入 x86-64 主线。

A16 后续正文与实验应验证：`regs->ip` 与 CR2 的区别、hardware error code 到 C 参数的传递、CR2 到 `address` 的传递，以及可恢复 user demand fault 在处理完成后重试原指令。
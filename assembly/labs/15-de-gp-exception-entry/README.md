# A15 实验：`#DE/#GP` 异常入口与 `pt_regs`

本实验对应 [`../../docs/15-idt-exception-entry-and-pt-regs.md`](../../docs/15-idt-exception-entry-and-pt-regs.md)。目标不是只看到进程收到 `SIGFPE/SIGSEGV`，而是把用户态可重复触发的异常与 Linux 5.10 内核入口现场对应起来。

## 1. 验证问题

需要验证四件事：

1. 整数除零通过 `idivq` 触发 `#DE`，CPU 不提供 hardware error code；Linux 普通入口补 `-1` 槽。
2. 在 CPL3 执行 `mov %ax,%ds` 并装入无效 selector `0xffff`，触发 selector-related `#GP`；CPU 提供 hardware error code。
3. 到 C handler 前，`#GP` 的 hardware error code 已从 `ORIG_RAX(%rsp)` 移到第二个 C 参数，`regs->orig_ax` 被规范化为 `-1`。
4. 两条路径最终都得到同一 `struct pt_regs` 布局，其中 `ip/cs/flags/sp/ss` 对应异常发生时的返回现场。

## 2. 构建与用户态运行

```bash
make
make disasm
make run
```

`trigger.c` 使用内联汇编固定两条 faulting instruction：

```asm
idivq %rcx       # rcx == 0，触发 #DE
mov %ax,%ds      # ax == 0xffff，触发 #GP
```

signal handler 使用 `ucontext_t` 打印 Linux 交给用户态 signal frame 的 RIP/RSP/EFLAGS，并跳过已知长度的 faulting instruction，使同一进程可以继续执行第二个 case。

**必须先执行 `make disasm` 核对指令编码和长度。** 当前源码假定 `idivq %rcx` 编码为 `48 f7 f9`（3 bytes），`mov %ax,%ds` 为 `8e d8`（2 bytes）。如果当前工具链生成结果不同，应先修改 handler 中 RIP 增量，不能盲目运行。

用户态结果只能证明异常被触发并最终被 Linux 转换为 signal；它不能证明入口栈上的 hardware/synthetic error-code slot。后者需要下面的 Linux 5.10 kernel-GDB 观察。

## 3. Linux 5.10 kernel-GDB 环境

只在隔离 guest 中执行。需要：

- 正在运行的 Linux 5.10 x86-64 guest；
- 与 guest **完全匹配**、带调试信息的 `vmlinux`；
- QEMU gdbstub 或等价的可停机 kernel debugger；
- 关闭或正确处理 KASLR；
- 能从当前 `vmlinux` 反汇编 `asm_exc_divide_error`、`asm_exc_general_protection`、`error_entry` 和对应 `idtentry` body。

不要把其他版本源码的地址或本实验文档中的示意偏移当作断点地址。

## 4. Case A：观察 `#DE`

先从当前 `vmlinux` 反汇编定位 `asm_exc_divide_error`。在 `pushq $-1` 之后、`call error_entry` 之前停下，只运行 `trigger` 并等待 `#DE`。

此时检查：

```text
$rsp + 0   : Linux synthetic -1
$rsp + 8   : saved RIP
$rsp + 16  : saved CS
$rsp + 24  : saved RFLAGS
$rsp + 32  : saved user RSP   (CPL3 -> CPL0)
$rsp + 40  : saved user SS
```

再在 GPR 已保存、`pt_regs` 已形成而尚未调用 `exc_divide_error()` 的位置观察：

```text
regs->orig_ax == -1
regs->ip      == trigger_de() 中 faulting idivq 的 RIP
regs->cs      表示用户态代码段
regs->sp      == fault 时用户 RSP
```

`#DE` 不存在“CPU 压入 0 error code”这一步。

## 5. Case B：观察 `#GP`

对 `asm_exc_general_protection` 做同样的源码/反汇编定位。在进入共同 `error_entry` 之前停下。

此时 `%rsp` 顶部应是 **CPU hardware error code**，后面才是 RIP/CS/RFLAGS/RSP/SS。不要预期 Linux 再额外 `pushq $-1`。

随后在 `idtentry_body` 已执行 error-code 参数整理、即将调用 `exc_general_protection(regs, error_code)` 的位置观察：

```text
%rdi             = struct pt_regs *regs
%rsi             = hardware error code
regs->orig_ax    = -1
regs->ip         = trigger_gp() 中 faulting mov %ax,%ds 的 RIP
```

本 case 使用 selector `0xffff` 是为了得到可重复的用户态 `#GP`。error code 的具体数值必须以实际 CPU/guest 观察为准；实验的核心结论是它来自硬件 slot，并在 C 调用前被转移到 `%rsi`，而不是预先写死某个数值。

## 6. 对照 signal frame

kernel-GDB 记录完成后继续 guest，让 signal handler 输出用户态 `ucontext_t`。对比：

```text
kernel pt_regs->ip     <-> signal ucontext REG_RIP
kernel pt_regs->sp     <-> signal ucontext REG_RSP
kernel pt_regs->flags  <-> signal ucontext REG_EFL
```

两者处在异常处理链的不同阶段，但对同步 fault，未被 handler 主动修改前应指向同一条 faulting user instruction 和对应用户现场。

## 7. 环境与安全边界

本实验的用户态程序不会故意破坏内核，但 kernel-GDB 会停止整个 guest，必须在隔离虚拟机执行。当前课程维护环境没有匹配的 Linux 5.10 guest、`vmlinux` 与 kernel-GDB 会话，因此本次只完成了源码、构建规则和可执行验证步骤，**没有把预期断点值写成实测结果**。

下一次具备实验环境时，应保存：

- `make disasm` 的实际 faulting instruction 编码；
- 用户态 signal 输出；
- `#DE` synthetic slot 的 GDB dump；
- `#GP` hardware error-code slot 与 `%rsi` 的 GDB dump；
- 两个 case 的 `pt_regs` 关键字段。

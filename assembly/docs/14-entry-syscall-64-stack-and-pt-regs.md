# A14 第一部分：`entry_SYSCALL_64`、内核栈切换与 `pt_regs`

A13 从用户态建立了 Linux x86-64 syscall ABI：用户程序把系统调用号放入 `%rax`，把参数放入 `%rdi/%rsi/%rdx/%r10/%r8/%r9`，随后执行 `syscall`。A14 开始回答另一半问题：CPU 到达内核入口以后，Linux 如何把一个仍然带着用户态现场的 CPU，变成可以安全调用 C 代码的内核执行现场。

本节只走到完整 `struct pt_regs` 建立为止。`do_syscall_64()` 的分派、退出检查以及 `SYSRETQ/IRETQ` 返回路径留给后续部分。

## 1. 先建立最重要的区别：`syscall` 不是 `call`

普通 `call` 会在当前栈上保存返回地址。64 位 `SYSCALL` 的入口模型不同：硬件把用户返回 RIP 保存到 `%rcx`，把用户 RFLAGS 保存到 `%r11`，并跳到 MSR 配置的内核入口；但它不会替 Linux 切换到任务的内核栈，也不会自动压出一个 `pt_regs`。

因此 `entry_SYSCALL_64` 刚开始执行时有一个看似矛盾但非常关键的状态：CPU 已经进入内核入口代码，`%rsp` 却仍然是用户 RSP。

这决定了 Linux 不能立即把 `%rsp` 当作可信内核栈使用。入口代码必须先保存 user RSP，再取得内核栈顶，最后用软件逐项构造后续 C 代码所需的寄存器现场。

## 2. 三层规则不要混在一起

理解这一段代码时，应把三层规则分开：

1. **x86-64 架构规则**：`SYSCALL` 把返回 RIP 放入 `%rcx`、RFLAGS 放入 `%r11`，并按 MSR 状态完成控制转移；它不自动切换 `%rsp`。
2. **Linux syscall ABI**：入口时 `%rax` 是 syscall number，六个参数使用 `%rdi/%rsi/%rdx/%r10/%r8/%r9`。
3. **Linux 5.10 入口实现**：`entry_SYSCALL_64` 使用 `swapgs`、per-CPU 临时槽和 `cpu_current_top_of_stack`，随后软件构造 `struct pt_regs`。

后两项是 Linux 约定和实现，不应反过来描述成 `SYSCALL` 指令本身的行为。

## 3. Linux 5.10 的入口主线

本节以 upstream Linux v5.10 为基线，已经逐项核验：

```text
arch/x86/entry/entry_64.S
arch/x86/entry/calling.h
arch/x86/include/asm/ptrace.h
```

主线可以先压缩成：

```text
user executes syscall
        |
        v
entry_SYSCALL_64
        |
        +-- swapgs
        +-- save user RSP in per-CPU TSS_sp2 scratch slot
        +-- SWITCH_TO_KERNEL_CR3
        +-- RSP = cpu_current_top_of_stack
        +-- build ss/sp/flags/cs/ip/orig_ax
        +-- PUSH_AND_CLEAR_REGS rax=$-ENOSYS
        |
        v
RSP -> complete struct pt_regs
```

后面所有细节都应能放回这条主线上解释。

## 4. 入口时的寄存器现场

从 A13 的用户态视角跨过 `syscall` 后，可以得到下面的入口快照：

```text
%rax = syscall number
%rdi = arg0
%rsi = arg1
%rdx = arg2
%r10 = arg3
%r8  = arg4
%r9  = arg5
%rcx = user return RIP
%r11 = saved user RFLAGS
%rsp = user RSP
```

这里 `%rcx/%r11` 已经不再是普通 caller-saved 寄存器的意义，而承担 `SYSCALL` 的返回现场。Linux 后面构造 `pt_regs->ip` 和 `pt_regs->flags` 时正是使用这两个值。

## 5. `swapgs`：为 per-CPU 访问建立内核 GS base

Linux 5.10 的 64 位 syscall 入口首先执行 `swapgs`。紧接着入口就要通过 `PER_CPU_VAR(...)` 访问 per-CPU 数据，因此必须让 GS base 处于内核预期状态。

`swapgs` 不是“进入 Ring 0”的动作。控制权已经由 `SYSCALL` 转入内核；这里交换 GS base 相关状态，是为了让入口代码能够访问内核 per-CPU 数据。

## 6. 为什么必须先保存 user RSP

入口随后把 `%rsp` 写入：

```text
cpu_tss_rw + TSS_sp2
```

Linux 5.10 源码明确把这里的 `tss.sp2` 当作 scratch space。此时的状态是：

```text
%rsp               = user RSP
per-CPU TSS_sp2     = user RSP
kernel pt_regs      = 尚未建立
```

这个顺序不能反过来。后续 CR3 切换宏允许使用 `%rsp` 作 scratch，而再下一步 `%rsp` 本身会被覆盖为内核栈顶。如果不先保存原始 user RSP，后面就无法可靠建立 `pt_regs->sp`。

## 7. `SWITCH_TO_KERNEL_CR3` 是条件性的入口动作

接下来执行 `SWITCH_TO_KERNEL_CR3 scratch_reg=%rsp`。这里尤其不能把教程写成“syscall 必然写 CR3”。

在 Linux 5.10 中，该宏受 `CONFIG_PAGE_TABLE_ISOLATION` 以及运行时 CPU feature 等条件影响；关闭相应配置时可以展开为空。准确的模型是：入口在这个位置执行 Linux 的 kernel-CR3 切换抽象，是否产生实际 CR3 更新取决于构建配置和 CPU 条件。

这也是阅读内核汇编宏时的重要方法：看到宏名之后，要继续核对配置分支和 alternative，而不能把宏名直接当作无条件硬件动作。

## 8. 真正的栈切换发生在哪里

随后 Linux 执行等价于：

```text
%rsp = PER_CPU_VAR(cpu_current_top_of_stack)
```

这一步之后，`%rsp` 才真正指向当前执行上下文的内核栈顶：

```text
SYSCALL 刚进入：       RSP = user RSP
保存 user RSP 后：     TSS_sp2 = user RSP
切换内核栈后：         RSP = kernel stack top
```

所以“syscall 进入内核会切内核栈”作为宏观描述没有问题，但实现责任属于 Linux 入口软件，而不是 `SYSCALL` 硬件指令。

## 9. Linux 手工建立返回现场

有了可用的 kernel stack 后，入口按顺序压入用户态返回所需的信息：

```text
__USER_DS
saved user RSP
%r11             -> user RFLAGS
__USER_CS
%rcx             -> user return RIP
%rax             -> syscall number
```

最终对应：

```text
pt_regs->ss
pt_regs->sp
pt_regs->flags
pt_regs->cs
pt_regs->ip
pt_regs->orig_ax
```

这里可以称为 iret-compatible frame，但必须记住：这是 Linux 软件构造的布局，不是 `SYSCALL` 自动压栈的结果。

`orig_ax` 保存原始 syscall number。它与后面的 `pt_regs->ax` 是两个不同字段。

## 10. `PUSH_AND_CLEAR_REGS` 补齐通用寄存器

`arch/x86/entry/calling.h` 中的 `PUSH_AND_CLEAR_REGS` 继续保存通用寄存器。syscall 入口调用它时指定：

```text
rax = -ENOSYS
```

因此完整现场刚建立时：

```text
regs->orig_ax = 原始 syscall number
regs->ax      = -ENOSYS
```

这不是同一个 `%rax` 被重复保存。`orig_ax` 是入口请求号的记录；`ax` 是系统调用返回槽的初始值，后续分派成功后会被真正返回值覆盖。

宏还会清理若干工作寄存器。因此“某个用户寄存器已经保存在 `pt_regs` 中”不意味着 CPU 当前同名寄存器仍保留那个用户值。

## 11. `pt_regs` 为什么恰好是 168 bytes

Linux 5.10 x86-64 的 `struct pt_regs` 地址顺序为：

```text
r15 r14 r13 r12 bp bx
r11 r10 r9 r8 ax cx dx si di
orig_ax
ip cs flags sp ss
```

共有 21 个 8-byte 字段，所以大小是：

```text
21 * 8 = 168 bytes
```

完整构造后 `%rsp` 指向结构体最低地址，也就是 `r15`：

```text
低地址

RSP -> +0x00  r15
       +0x08  r14
       +0x10  r13
       +0x18  r12
       +0x20  bp
       +0x28  bx
       +0x30  r11
       +0x38  r10
       +0x40  r9
       +0x48  r8
       +0x50  ax       = -ENOSYS
       +0x58  cx
       +0x60  dx
       +0x68  si
       +0x70  di
       +0x78  orig_ax  = syscall number
       +0x80  ip       = user return RIP
       +0x88  cs
       +0x90  flags    = user RFLAGS
       +0x98  sp       = user RSP
       +0xa0  ss

高地址
```

为什么汇编的 push 顺序看起来与结构体定义相反？因为 x86-64 栈向低地址增长。最后压入的 `%r15` 落在最低地址，正好成为 C 结构体的第一个字段。

## 12. 从入口汇编交给 C 代码前发生了什么

到这里，Linux 已完成一次非常重要的“表示转换”：

```text
硬件/ABI 留在 CPU 寄存器中的用户现场
                |
                v
Linux 软件保存、切栈、逐项 push
                |
                v
kernel stack 上连续的 struct pt_regs
```

后续 C 代码不需要继续依赖“进入 syscall 那一瞬间 `%rcx` 到底是什么”这种易失寄存器状态，而可以通过 `pt_regs` 读取和修改统一的入口现场。

这也是 `pt_regs` 的核心价值之一：它把架构入口现场转换成内核后续代码可以稳定传递和操作的数据结构。

## 13. 本节应该能回答的几个问题

学习完这一部分，应能明确回答：

- 为什么 `SYSCALL` 后不能立刻把原 `%rsp` 当作内核栈？
- user RSP 在 Linux 5.10 中先保存到哪里？
- 真正把 `%rsp` 改成 kernel stack top 的是谁？
- `%rcx/%r11` 如何最终变成 `pt_regs->ip/flags`？
- 为什么同时存在 `orig_ax` 和 `ax`？
- 为什么 `pt_regs` 是 168 bytes？
- 为什么不能无条件说每次 syscall 都会实际写 CR3？

如果这些问题还需要靠背诵入口汇编回答，说明还没有建立完整执行模型；应重新沿“入口寄存器状态 → 保存 user RSP → 切 kernel stack → 构造 pt_regs”这条线检查每一步的状态变化。

## 14. 源码核验与后续边界

本节的 Linux 5.10 具体实现依据见：

[`../source-paths/14-entry-syscall-64-stack-switch-linux-5.10.md`](../source-paths/14-entry-syscall-64-stack-switch-linux-5.10.md)

下一部分再从完整 `pt_regs` 开始进入 `do_syscall_64()`，分析 syscall number 检查、系统调用表分派、返回值写回，以及进入退出路径前 `pt_regs` 中哪些字段已经发生变化。这里不提前展开 `SYSRETQ/IRETQ` 的返回选择。
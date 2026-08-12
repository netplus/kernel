# Linux 5.10 x86-64 syscall 返回路径源码事实核验

本文只记录 A14 第三部分所需的 Linux kernel 5.10 源码事实：`do_syscall_64()` 完成系统调用分派后，内核怎样执行返回用户态前的工作，以及 `entry_SYSCALL_64` 怎样判断能否使用 `SYSRETQ` 快路径。异常/中断通用返回机制留到 A15，不在这里展开。

## 1. 核验范围与源码基线

版本基线：Linux v5.10，x86-64。

主要路径：

```text
arch/x86/entry/common.c
    do_syscall_64()

include/linux/entry-common.h
kernel/entry/common.c
    syscall_exit_to_user_mode()
    exit_to_user_mode_prepare()
    exit_to_user_mode_loop()

arch/x86/entry/entry_64.S
    entry_SYSCALL_64
    syscall_return_via_sysret
    swapgs_restore_regs_and_return_to_usermode
```

A14 前两部分已经核验入口栈和 `do_syscall_64()` 分派；本文从 `do_syscall_64()` 尾部继续。

## 2. `do_syscall_64()` 不直接执行 `SYSRETQ`

Linux v5.10 的 `arch/x86/entry/common.c:do_syscall_64()` 在系统调用表分派之后执行：

```text
syscall_exit_to_user_mode(regs)
```

因此需要区分两层工作：

1. C 层先完成 exit-to-user work，并返回到 `entry_SYSCALL_64`；
2. 汇编层再根据最终 `pt_regs` 判断能否走 `SYSRETQ` 快路径，否则转入 IRET 返回路径。

不能把 `syscall_exit_to_user_mode()` 理解为“执行 SYSRET 的函数”。

## 3. 返回用户态前为什么还需要工作循环

系统调用主体结束时，`regs->ax` 已经保存系统调用返回值，但任务不一定可以立即回到用户态。执行系统调用期间可能产生需要在用户态重新获得 CPU 控制权之前处理的状态，例如：

- reschedule；
- pending signal；
- notify-resume / task work；
- uprobe 等 entry/exit work。

Linux 5.10 的通用 entry/exit 层通过 thread flags 判断这些工作，并在 `exit_to_user_mode_loop()` 中处理。循环是必要的：一次处理动作本身可能再次设置另一项 work flag，所以需要重新检查，直到不存在当前必须处理的 exit work。

这里的职责属于内核 entry/exit 设计，不属于 x86 `SYSRET` 指令本身。

## 4. `syscall_exit_to_user_mode()` 的边界

`syscall_exit_to_user_mode(regs)` 属于通用 entry/exit 框架。它在返回汇编前完成 syscall-specific exit work 和 exit-to-user preparation，并保证返回侧满足入口代码要求的状态。

A14 关注的关键结论是：

```text
syscall handler return
        |
        v
regs->ax contains result
        |
        v
syscall_exit_to_user_mode(regs)
        |
        +--> process pending exit-to-user work
        |
        v
return to entry_SYSCALL_64 assembly
```

信号递送、调度等子系统内部机制在各自领域讲解；这里只记录它们为什么位于“系统调用已经完成”和“真正返回用户态”之间。

## 5. `entry_SYSCALL_64` 的 opportunistic SYSRET

`arch/x86/entry/entry_64.S` 在 `call do_syscall_64` 返回后明确说明：只有返回到一个“completely clean 64-bit userspace context”时才尝试 SYSRET，否则跳到慢路径。

Linux 5.10 依次检查以下关键条件。

### 5.1 `RCX` 必须仍与 `pt_regs->ip` 一致

入口时硬件把 syscall 后的用户 RIP 保存到 `%rcx`，Linux 同时把它复制进 `pt_regs->ip`。返回时：

```text
RCX(%rsp) -> %rcx
RIP(%rsp) -> %r11
compare %rcx and %r11
```

若二者不同，说明保存现场被内核路径修改，不能简单依赖 SYSRET 的 `%rcx` 返回语义，于是转慢路径。

### 5.2 返回 RIP 必须是 canonical address

Linux 5.10 显式对候选 RIP 做 canonicality 检查。4-level paging 使用 48-bit canonical 规则；在 `CONFIG_X86_5LEVEL` 构建中通过 `ALTERNATIVE` 根据 `X86_FEATURE_LA57` 选择 48-bit 或 57-bit 检查。

原因不是普通 ABI 偏好，而是安全边界：源码明确记录 Intel CPU 上对 non-canonical RCX 执行 SYSRET 可能在内核态触发 `#GP`，因此不能把用户可控的异常状态交给 SYSRET。

### 5.3 `CS` 必须是 `__USER_CS`

SYSRET 不能任意恢复一个被修改过的完整 segment frame。若 `pt_regs->cs` 不再等于正常 64-bit syscall 返回所期望的 `__USER_CS`，Linux 转入 IRET 路径。

### 5.4 `R11` 必须仍与 `pt_regs->flags` 一致

入口时硬件把用户 RFLAGS 保存到 `%r11`，Linux 又把该值保存到 `pt_regs->flags`。返回时两者必须一致，否则说明最终 flags 不能由当前 SYSRET 快路径安全恢复。

### 5.5 `RF` 或 `TF` 被设置时不能走该快路径

Linux 5.10 对 `X86_EFLAGS_RF | X86_EFLAGS_TF` 做显式检查。

源码说明了两个不同原因：SYSRET 不能正确恢复 RF；而 TF 虽可恢复，但会使单步调试场景产生不合适的 trap 行为，甚至造成重复返回循环。因此任一位存在都走慢路径。

### 5.6 `SS` 必须是 `__USER_DS`

和 CS 类似，若 `pt_regs->ss` 不再是普通 64-bit syscall 返回所要求的用户数据段选择子，则必须由更完整的 IRET frame 恢复。

源码特别注明“不需要检查 RSP”。这不表示用户 RSP 不重要，而是 SYSRETQ 自身不从完整 IRET frame 恢复 RSP；Linux 在真正执行 SYSRET 前单独恢复保存的 user RSP。

## 6. SYSRET 快路径如何恢复现场

全部检查通过后进入 `syscall_return_via_sysret`。

主线为：

```text
POP_REGS ...
        |
        | restore normal GPRs
        | keep rcx/r11 for SYSRET semantics
        v
save current kernel-stack pointer in rdi
        |
        v
switch to per-CPU trampoline stack
        |
        v
SWITCH_TO_USER_CR3_STACK   [PTI-sensitive macro]
        |
        v
restore user rdi
restore user rsp
        |
        v
USERGS_SYSRET64
```

这里必须注意顺序：在 PTI 配置下切换到用户页表之后，不能继续依赖普通 kernel stack 映射，所以 Linux 先转到为返回路径准备的 trampoline stack，再切 user CR3，最后恢复 user RSP。

`USERGS_SYSRET64` 最终包含返回用户 GS 状态以及 `sysretq` 所需动作；其具体展开受 x86 entry 宏和 paravirt 配置影响，因此正文应避免把宏名等同于单条 `sysretq`。

## 7. 为什么慢路径使用 IRET frame

任一 SYSRET 条件失败时，`entry_SYSCALL_64` 跳转到：

```text
swapgs_restore_regs_and_return_to_usermode
```

Linux 5.10 的该路径恢复通用寄存器，并把：

```text
SS
RSP
RFLAGS
CS
RIP
```

复制到 trampoline stack 上形成 IRET frame；随后完成必要的 user CR3/GS 切换，并通过 `INTERRUPT_RETURN` 最终执行架构返回动作（native 路径对应 `iretq`）。

因此 IRET 回退不是“SYSRET 执行失败后再试一次”。Linux 在执行 SYSRET **之前**检查现场，只要不能证明快路径安全，就主动选择能恢复完整 frame 的 IRET 路径。

## 8. SYSRET 与 IRET 的职责差异

可以把 Linux 5.10 的设计概括为：

```text
                  final pt_regs
                       |
                       v
             SYSRET eligibility checks
                 /             \
              pass             fail
               |                 |
               v                 v
       compact fast restore   full IRET frame
               |                 |
               v                 v
            SYSRETQ            IRETQ
```

SYSRET 快，但它依赖更严格的寄存器/segment/flags 条件；IRET 能从完整 frame 恢复更一般的用户现场。因此 Linux 使用的是 opportunistic SYSRET，而不是“系统调用固定用 SYSRET”。

## 9. 配置条件

本次核验中与返回路径直接相关的配置包括：

- `CONFIG_X86_64`：本文讨论的 64-bit syscall 主线；
- `CONFIG_X86_5LEVEL` + `X86_FEATURE_LA57`：影响 canonical address 检查位宽；
- `CONFIG_PAGE_TABLE_ISOLATION`：通过 CR3 切换宏影响返回用户页表的具体动作；
- `CONFIG_PARAVIRT_XXL`：存在 `native_usergs_sysret64` 等 paravirt 相关入口/宏展开差异；
- `CONFIG_DEBUG_ENTRY`：慢路径包含额外的 user-mode frame 断言。

这些条件影响具体指令序列，但不改变“C 层 exit work → 汇编判断 SYSRET eligibility → 不满足则 IRET”的主模型。

## 10. 本单元已经核验的事实

- `do_syscall_64()` 最后调用 `syscall_exit_to_user_mode(regs)`，不是直接返回用户态；
- exit-to-user work 位于 syscall handler 完成与架构返回指令之间；
- `entry_SYSCALL_64` 返回侧把 SYSRET 当作机会性快路径；
- Linux 5.10 实际检查 RCX/RIP 一致性、RIP canonicality、CS、R11/RFLAGS、RF/TF 和 SS；
- SYSRET 快路径单独恢复 user RSP，并在 PTI 场景下通过 trampoline stack 完成最终 CR3 切换；
- 条件不满足时在执行 SYSRET 前主动转入 `swapgs_restore_regs_and_return_to_usermode`；
- native 慢路径最终以完整 IRET frame 执行 `iretq`。

## 11. 后续边界

下一最小单元应把这些事实写成 A14 第三部分正式教程，并设计验证：优先观察普通 syscall 的 SYSRET 快路径，再构造或利用 ptrace/signal/debug 状态让最终 `pt_regs` 不满足快路径条件，确认进入 IRET 回退路径。

A15 再系统讲异常/中断入口、CPU 自动压栈、错误码、IST 与通用 IRET 返回；本文件不提前展开。
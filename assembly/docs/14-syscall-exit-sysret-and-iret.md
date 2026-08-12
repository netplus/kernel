# A14 第三部分：系统调用返回、SYSRET 快路径与 IRET 回退

前两部分已经说明了用户态执行 `syscall` 后，Linux 5.10 如何建立 `pt_regs`，以及 `do_syscall_64()` 如何根据系统调用号分派处理函数并把结果写回 `regs->ax`。本节继续回答最后一个问题：系统调用处理函数已经结束以后，CPU 为什么还不能立刻回到用户态，以及 Linux 最终怎样在 `SYSRETQ` 与 `IRETQ` 之间选择。

本文以 Linux kernel v5.10、x86-64 为基线。具体源码事实见 [`../source-paths/14-syscall-exit-sysret-iret-linux-5.10.md`](../source-paths/14-syscall-exit-sysret-iret-linux-5.10.md)。

## 1. 问题背景：handler 返回不等于已经返回用户态

系统调用处理函数返回时，最直观的结果已经存在：例如 `read()` 返回读取字节数，失败时返回负 errno，最终都写入 `pt_regs->ax`。但这时 CPU 仍处于内核态，当前任务也可能还有必须在回到用户态之前完成的工作。

典型情况包括 pending signal、重新调度请求、notify-resume/task work 和 uprobe 相关工作。因此 Linux 不能把：

```text
syscall handler returns
```

直接等同于：

```text
execute sysretq
```

Linux 5.10 的主线实际是：

```text
syscall handler
    |
    v
regs->ax = return value
    |
    v
syscall_exit_to_user_mode(regs)
    |
    v
return to entry_SYSCALL_64
    |
    v
inspect final pt_regs
    |
    +--> SYSRET fast path
    |
    `--> IRET fallback
```

这里存在两个不同层次：通用 entry/exit 代码负责处理“回用户态之前还有什么工作”，x86 汇编返回代码负责决定“最终用哪条架构返回路径恢复用户现场”。

## 2. 基本原理：最终 `pt_regs` 才是返回依据

入口时，Linux 把用户现场保存到内核栈上的 `struct pt_regs`。系统调用执行期间，这份现场并不是只读快照。信号、ptrace、调试状态等路径可能修改最终要恢复的 RIP、RFLAGS 或 segment 状态。

因此返回代码不能只相信 `SYSCALL` 指令最初留在 `%rcx/%r11` 中的值，而要把这些快速返回所依赖的寄存器状态与最终 `pt_regs` 比较。

这解释了一个重要设计原则：

> SYSRET 是满足严格条件时采用的优化；`pt_regs` 描述的最终用户现场才是语义依据。

如果最终现场仍然是一个普通、干净的 64-bit syscall 返回现场，Linux 可以利用 SYSRET 的紧凑语义；如果现场已经变化，则使用能恢复完整 frame 的 IRET 路径。

## 3. 第一阶段：`syscall_exit_to_user_mode()`

Linux v5.10 的 `arch/x86/entry/common.c:do_syscall_64()` 在系统调用分派结束后调用：

```c
syscall_exit_to_user_mode(regs);
```

这个函数不执行 `sysretq`。它属于通用 entry/exit 框架，负责在返回用户态之前处理当前任务仍然挂起的 exit work。

可以把它理解为一个边界：

```text
系统调用主体已经结束
        |
        v
处理必须在 user mode 重新运行前完成的工作
        |
        v
形成最终 pt_regs
        |
        v
交回 x86 汇编返回代码
```

其中 `exit_to_user_mode_loop()` 会根据 thread flags 处理工作，并在需要时重复检查。使用循环而不是一次检查，是因为某项处理本身可能再次产生另一项必须完成的工作。

信号如何递送、调度器如何真正切换任务并不是本节主题；这里需要掌握的是它们在系统调用返回路径中的位置。

## 4. 第二阶段：为什么不能无条件使用 `SYSRETQ`

x86-64 的 `SYSCALL/SYSRET` 为快速系统调用设计。入口时，CPU 把 syscall 后的用户 RIP 放入 `%rcx`，把用户 RFLAGS 放入 `%r11`。`SYSRETQ` 又依赖这些寄存器恢复关键用户状态。

这种接口比完整的 IRET frame 更紧凑，但也意味着它不能表达任意修改后的用户现场。

Linux 5.10 因此在 `entry_SYSCALL_64` 返回侧逐项判断最终现场是否仍满足 SYSRET 快路径要求。

### 4.1 `%rcx` 必须等于最终 `pt_regs->ip`

入口时 `%rcx` 保存 syscall 后的用户 RIP，Linux 又把这个值写入 `pt_regs->ip`。如果系统调用执行过程中最终 RIP 被修改，两者就可能不再相等。

返回侧重新装载并比较它们。如果不同，Linux 不能再直接利用 SYSRET 的 `%rcx` 语义，而必须走完整恢复路径。

### 4.2 RIP 必须是 canonical address

候选用户 RIP 必须满足当前 x86-64 地址宽度的 canonical 规则。Linux v5.10 对这一点显式检查。

4-level paging 下使用 48-bit canonical 模型；启用 `CONFIG_X86_5LEVEL` 时，实际检查还受 CPU 的 `X86_FEATURE_LA57` 影响。

这个检查具有安全意义。不能把用户可控的 non-canonical RCX 直接交给 SYSRET，因为某些 CPU 上这可能在错误的特权上下文中产生 `#GP`。

### 4.3 `CS` 必须是正常的 64-bit 用户代码段

Linux 检查 `pt_regs->cs == __USER_CS`。如果最终 CS 已经不是普通 64-bit syscall 快速返回所期待的选择子，就需要 IRET frame 来恢复。

### 4.4 `%r11` 必须等于最终 `pt_regs->flags`

入口时 CPU 把用户 RFLAGS 放入 `%r11`，Linux 同时把它保存进 `pt_regs->flags`。如果最终 flags 被修改，原 `%r11` 就不能再代表应恢复的状态。

因此返回代码要求两者一致。

### 4.5 RF 和 TF 会阻止当前 SYSRET 快路径

Linux v5.10 显式检查 `X86_EFLAGS_RF | X86_EFLAGS_TF`。

RF 不能由这条 SYSRET 快路径正确恢复；TF 涉及单步调试语义，直接走快路径会产生不合适的 trap 行为。因此任一位存在时都转慢路径。

### 4.6 `SS` 必须是正常用户数据段

Linux 还检查 `pt_regs->ss == __USER_DS`。这与 CS 检查的原因类似：SYSRET 快路径只适用于预期的普通用户 segment 状态。

值得注意的是，源码特别说明这里不需要把 RSP 纳入同类 eligibility 比较。这不意味着用户 RSP 不重要，而是 Linux 会在真正执行 SYSRET 前从保存现场单独恢复 user RSP。

## 5. SYSRET 快路径怎样恢复现场

所有条件都满足后，控制流进入 `syscall_return_via_sysret`。

概念上的恢复顺序是：

```text
final pt_regs
    |
    v
restore ordinary GPRs
    |
    | keep RCX/R11 for SYSRET semantics
    v
preserve kernel-stack position
    |
    v
move to return/trampoline stack
    |
    v
switch toward user CR3       [PTI-dependent]
    |
    v
restore user RDI and user RSP
    |
    v
restore user GS state
    |
    v
SYSRETQ
```

这里最容易忽略的是页表和栈的先后关系。在启用 Kernel Page Table Isolation（PTI）的配置中，一旦切换到用户 CR3，普通内核栈不能再被假定仍可通过原来的内核映射访问。因此 Linux 先把返回所需状态转移到专门的 trampoline stack，再进行用户页表切换，最后恢复用户 `%rsp`。

源码中这一过程由多个 entry 宏完成。不能把 `USERGS_SYSRET64` 这样的宏名简单理解成“就是一条 `sysretq`”；宏展开还受 PTI、paravirt 等配置影响。

## 6. IRET 回退路径怎样工作

只要任何 SYSRET eligibility check 不满足，Linux 就在执行 SYSRET **之前**跳到：

```text
swapgs_restore_regs_and_return_to_usermode
```

这不是“先执行 SYSRET，失败后再补救”。选择发生在架构返回指令之前。

慢路径恢复通用寄存器，并准备完整的用户返回 frame：

```text
SS
RSP
RFLAGS
CS
RIP
```

随后完成必要的 CR3 和 GS 状态切换，native 路径最终通过 `iretq` 返回用户态。

IRET 的价值在于它能从完整 frame 恢复更一般的现场。例如最终 RIP 或 RFLAGS 被内核合法修改后，原始 `%rcx/%r11` 已经不能代表目标状态，但 `pt_regs` 中的完整 frame 仍可以准确描述应该恢复什么。

## 7. SYSRET 与 IRET 不是“正常/异常”的简单二分

容易产生的误解是：正常系统调用总是 SYSRET，只有发生错误才 IRET。

Linux 5.10 的实际模型更准确地表示为：

```text
                  final pt_regs
                       |
                       v
             SYSRET eligibility checks
                 /             \
              pass             fail
               |                 |
               v                 v
       compact fast restore   full-frame restore
               |                 |
               v                 v
            SYSRETQ            IRETQ
```

系统调用本身返回 `-ENOENT` 或 `-EINVAL` 并不会因为“出错”就天然要求 IRET；真正决定返回路径的是最终用户现场是否满足 SYSRET 快路径条件。

## 8. 寄存器、栈和控制流连续模型

把 A14 三部分连起来，可以得到一次普通 64-bit syscall 的完整骨架：

```text
userspace
  RAX = syscall number
  RDI/RSI/RDX/R10/R8/R9 = arguments
  RSP = user stack
        |
        | syscall
        v
CPU
  RCX <- return RIP
  R11 <- user RFLAGS
        |
        v
entry_SYSCALL_64
  save user RSP
  switch kernel CR3 if required
  switch kernel stack
  build pt_regs
        |
        v
do_syscall_64
  validate nr
  dispatch sys_call_table[nr]
  regs->ax <- result
        |
        v
syscall_exit_to_user_mode
  process pending exit work
        |
        v
entry_SYSCALL_64 return side
  inspect final pt_regs
        |
        +--> SYSRET eligibility passes
        |      restore GPRs / user RSP / CR3 / GS
        |      SYSRETQ
        |
        `--> eligibility fails
               construct full IRET frame
               restore CR3 / GS
               IRETQ
        |
        v
userspace
```

这条连续模型比记忆某一段汇编更重要：`pt_regs` 是入口、C 语言分派和最终架构返回之间共享的现场载体。

## 9. 配置条件和实现边界

阅读 Linux 5.10 源码时至少要注意：

- `CONFIG_X86_64`：本文的 64-bit syscall 主线；
- `CONFIG_X86_5LEVEL` 与 `X86_FEATURE_LA57`：影响 RIP canonicality 检查；
- `CONFIG_PAGE_TABLE_ISOLATION`：影响返回时 CR3/trampoline stack 的具体动作；
- `CONFIG_PARAVIRT_XXL`：影响 user-GS/SYSRET 等宏的具体展开；
- `CONFIG_DEBUG_ENTRY`：慢路径可能加入额外的 frame 检查。

这些配置改变部分指令序列，但不改变主模型：

```text
exit-to-user work
→ inspect final pt_regs
→ opportunistic SYSRET
→ otherwise IRET
```

## 10. 常见误区

**误区一：`syscall_exit_to_user_mode()` 会执行 `sysretq`。**

不会。它完成通用返回用户态前工作，真正的 SYSRET/IRET 选择仍在 x86 汇编返回路径。

**误区二：`SYSCALL` 入口保存的 `%rcx/%r11` 永远可以直接用于返回。**

不成立。最终 `pt_regs->ip/flags` 可能被内核路径修改，因此 Linux 返回前会比较。

**误区三：IRET 是 SYSRET fault 后的补救路径。**

不是。Linux 在执行 SYSRET 前完成 eligibility checks，不满足就主动选择 IRET。

**误区四：系统调用返回负 errno 就会走 IRET。**

返回值和架构返回方式是两个维度。`regs->ax` 中的成功/失败结果本身不决定 SYSRET/IRET。

**误区五：看到 `sysretq` 就可以忽略栈、CR3 和 GS。**

不可以。真正回到用户态前，Linux 还必须把 kernel stack/page table/GS 状态有序地恢复为用户上下文。

## 11. 与下一章的边界

本节只解释 64-bit syscall 的返回路径。A15 将从异常和中断入口重新建立另一套模型：哪些入口由 CPU 自动压栈、哪些异常带 error code、Linux 怎样统一 `pt_regs`，以及 IST 和通用 IRET 返回如何工作。

因此这里出现的 IRET 只解释“为什么 syscall 快路径不适用时需要完整 frame”，不提前展开异常/中断通用入口。
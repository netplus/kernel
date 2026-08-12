# A14 Linux 5.10 源码核验：`do_syscall_64()` 的进入、分派与返回值写回

本文件核验 A14 的第二个最小单元：`entry_SYSCALL_64` 已经建立完整 `struct pt_regs` 以后，Linux 5.10 如何进入 C 层、处理 syscall number、从系统调用表选择实现，并把返回值写回 `pt_regs->ax`。

本单元只走到 `syscall_exit_to_user_mode(regs)` 被调用为止。返回用户态前的 exit work，以及汇编层最终选择 `SYSRETQ` 或 `IRETQ`，留给 A14 后续单元。

## 1. 源码基线

本节按 upstream Linux **v5.10** 核验，主要文件为：

```text
arch/x86/entry/entry_64.S
arch/x86/entry/common.c
arch/x86/entry/syscall_64.c
arch/x86/include/asm/syscall.h
```

第一部分已经确认 `entry_SYSCALL_64` 构造完整 `pt_regs` 后执行：

```asm
movq %rax, %rdi
movq %rsp, %rsi
call do_syscall_64
```

因此按照普通 x86-64 C ABI，进入 C 函数时：

```text
%rdi = nr
%rsi = regs
```

对应 Linux 5.10 中的声明：

```c
void do_syscall_64(unsigned long nr, struct pt_regs *regs);
```

这里的 `nr` 来自入口时的 `%rax`；而同一个原始 syscall number 还已经保存在 `regs->orig_ax` 中。两者在入口交接点上值相同，但用途不同：`nr` 是本次 C 层分派的工作变量，`orig_ax` 是保存于入口现场中的原始请求号。

## 2. `do_syscall_64()` 的主线

Linux 5.10 `arch/x86/entry/common.c` 中的 64 位主线可以压缩为：

```text
do_syscall_64(nr, regs)
    |
    +-- nr = syscall_enter_from_user_mode(regs, nr)
    |
    +-- instrumentation_begin()
    |
    +-- if (nr < NR_syscalls)
    |       nr = array_index_nospec(nr, NR_syscalls)
    |       regs->ax = sys_call_table[nr](regs)
    |
    +-- [CONFIG_X86_X32_ABI]
    |       检查 x32 syscall number
    |       regs->ax = x32_sys_call_table[nr](regs)
    |
    +-- instrumentation_end()
    |
    `-- syscall_exit_to_user_mode(regs)
```

这个顺序很重要。不能把 `do_syscall_64()` 简化成“检查范围然后直接查表”：真正的 syscall number 在查表前先经过通用 entry work，返回用户态前也要进入通用 exit work。

## 3. `syscall_enter_from_user_mode()` 可能改变 `nr`

`do_syscall_64()` 的第一条 C 层主线是：

```c
nr = syscall_enter_from_user_mode(regs, nr);
```

因此后续真正用于查表的不是必须等于入口 `%rax` 的一个不可变常量，而是该函数返回的 `nr`。

这一点对 ptrace、seccomp、audit、syscall tracing 等入口工作很重要：这些机制可以参与 syscall entry work。A14 基础课程只需要建立这个边界，不在 assembly 领域展开这些子系统。

所以应区分：

```text
regs->orig_ax : 入口现场保存的原始 syscall number
nr            : C 层当前用于后续分派的工作 syscall number
```

后续若要分析 restart、ptrace 修改或 seccomp 行为，应进入对应专题，而不是把这些细节混入本章主线。

## 4. 原生 x86-64 syscall 的范围检查

entry work 返回后，Linux 5.10 首先检查：

```c
if (likely(nr < NR_syscalls)) {
```

这里 `nr` 的类型是 `unsigned long`。因此一个由用户 `%rax` 传入的负数位模式，在解释成 `unsigned long` 后会成为很大的正数，不会通过这个 `< NR_syscalls` 检查。

这也是阅读边界条件时必须同时核对 C 类型的例子：只看汇编位模式而忽略 `unsigned long`，容易错误理解负 syscall number 的行为。

入口阶段 `regs->ax` 已由 `PUSH_AND_CLEAR_REGS rax=$-ENOSYS` 初始化为 `-ENOSYS`。如果原生 syscall number 不通过范围检查、且也不进入后面的 x32 分支，那么本函数不会用系统调用实现的返回值覆盖它，因此 `-ENOSYS` 可以继续作为无效 syscall 的返回值。

## 5. 为什么范围检查后还有 `array_index_nospec()`

通过范围检查后，Linux 5.10 执行：

```c
nr = array_index_nospec(nr, NR_syscalls);
```

然后才访问：

```c
sys_call_table[nr]
```

`array_index_nospec()` 服务于推测执行边界，不改变“架构上先验证索引范围、再从 syscall table 选择函数”的基本模型。课程在这里应认识它为什么位于数组索引之前，但不展开完整 Spectre 缓解专题。

因此正常原生 64 位 syscall 的核心分派是：

```text
validated nr
   |
   v
array_index_nospec
   |
   v
sys_call_table[nr]
   |
   v
__x64_sys_... (const struct pt_regs *)
```

## 6. `sys_call_table` 的元素类型和生成方式

Linux 5.10 `arch/x86/include/asm/syscall.h` 定义：

```c
typedef long (*sys_call_ptr_t)(const struct pt_regs *);
extern const sys_call_ptr_t sys_call_table[];
```

`arch/x86/entry/syscall_64.c` 通过包含生成的 syscall 定义，把表项初始化为对应的 `__x64_*` 入口；未被有效表项覆盖的位置以 `__x64_sys_ni_syscall` 作为默认实现。

因此 `sys_call_table[nr](regs)` 不是把六个 syscall 参数重新按照普通 C ABI 逐个传给系统调用函数。表项接收的是一个 `struct pt_regs *`，需要参数时再从已经保存的入口现场取得。

这与 A13 的用户态 syscall ABI 并不矛盾：

```text
用户态 ABI
RDI/RSI/RDX/R10/R8/R9
        |
        v
entry_SYSCALL_64 保存现场
        |
        v
struct pt_regs
        |
        v
__x64_sys_* wrapper / syscall implementation
```

用户寄存器约定先被固化为 `pt_regs`，内核 C 层再围绕该结构体工作。

## 7. 返回值最终写到哪里

正常原生 64 位 syscall 的关键语句是：

```c
regs->ax = sys_call_table[nr](regs);
```

因此系统调用实现返回的 `long` 被写回：

```text
pt_regs->ax
```

这与第一部分的入口状态形成完整前后关系：

```text
刚构造 pt_regs：
    regs->orig_ax = 原始 syscall number
    regs->ax      = -ENOSYS

正常 syscall 分派完成：
    regs->orig_ax = 仍保存原始 syscall number
    regs->ax      = syscall implementation return value
```

之后返回汇编会从 `pt_regs` 恢复用户寄存器，因此用户最终在 `%rax` 中观察到的 raw syscall return value，来源就是这里的 `regs->ax`。

libc 是否把负 errno 编码转换成 `-1` 并设置线程局部 `errno`，仍然属于 A13 已经区分过的用户态包装层行为，不是 `do_syscall_64()` 的工作。

## 8. `CONFIG_X86_X32_ABI` 是独立条件分支

Linux 5.10 在原生范围检查之后还有：

```c
#ifdef CONFIG_X86_X32_ABI
    else if (...)
        regs->ax = x32_sys_call_table[nr](regs);
#endif
```

因此不能把 `do_syscall_64()` 写成永远只有一张 `sys_call_table`。当 `CONFIG_X86_X32_ABI=y` 时，还存在 x32 ABI 的编号识别和 `x32_sys_call_table` 分派。

本基础课程的主线仍以原生 x86-64 syscall 为主；这里记录配置边界即可，不展开 x32 ABI 的参数宽度和兼容语义。

## 9. `do_syscall_64()` 的执行上下文边界

`do_syscall_64()` 在 Linux 5.10 中标记为：

```c
__visible noinstr
```

函数先进入 `syscall_enter_from_user_mode()`，然后用 `instrumentation_begin()` / `instrumentation_end()` 包围实际的 syscall table 调用区域，最后调用 `syscall_exit_to_user_mode(regs)`。

这说明入口/退出框架对 instrumentation 的可用区间有明确约束。不能因为主体已经是 C 代码，就假定从函数第一条语句到最后一条语句都处于普通可插桩上下文。

关于 RCU、lockdep、trace、reschedule、signal 等 entry/exit work 的具体细节，应在后续单元围绕 `syscall_enter_from_user_mode()` 和 `syscall_exit_to_user_mode()` 单独核验；本文件不凭记忆展开。

## 10. 与返回路径的交接点

`do_syscall_64()` 最后执行：

```c
syscall_exit_to_user_mode(regs);
```

返回到 `entry_SYSCALL_64` 汇编时，源码注释说明 IRQs disabled。随后汇编才开始判断当前 `pt_regs` 是否仍满足 opportunistic `SYSRET` 的严格条件；不满足时转入通用的 IRET 返回路径。

因此 A14 到目前为止的主线是：

```text
SYSCALL hardware entry
        |
        v
entry_SYSCALL_64
        |
        +-- 保存 user RSP
        +-- 切 kernel stack
        +-- 构造 pt_regs
        |
        v
do_syscall_64(nr, regs)
        |
        +-- entry work
        +-- number validation
        +-- nospec index
        +-- sys_call_table[nr](regs)
        +-- regs->ax = return value
        +-- exit-to-user work
        |
        v
entry_SYSCALL_64 return-side assembly
```

下一最小单元应从这里继续核验 `syscall_exit_to_user_mode()` 完成了哪些返回前工作，以及 `entry_SYSCALL_64` 为什么只有在 `RCX/RIP`、`R11/RFLAGS`、`CS/SS`、canonical RIP 和 `RF/TF` 等条件全部满足时才选择 `SYSRETQ`；否则为什么转入 `swapgs_restore_regs_and_return_to_usermode` / IRET 路径。

## 11. 本单元的核验结论

本单元应固定以下事实：

1. `entry_SYSCALL_64` 用普通 C ABI 把 `nr` 和 `regs` 传给 `do_syscall_64()`；
2. `nr` 在查表前先经过 `syscall_enter_from_user_mode()`，因此应与保存原始请求号的 `regs->orig_ax` 区分；
3. 原生 64 位分派先检查 `nr < NR_syscalls`，再经过 `array_index_nospec()`；
4. `sys_call_table` 元素类型是接收 `const struct pt_regs *`、返回 `long` 的函数指针；
5. 正常系统调用返回值写入 `regs->ax`，而 `regs->orig_ax` 继续承担原始 syscall number 的现场记录角色；
6. 无效编号若未命中有效分支，会保留入口阶段预置的 `-ENOSYS` 返回槽；
7. `CONFIG_X86_X32_ABI` 会增加独立的 x32 分派分支；
8. `do_syscall_64()` 最后进入 `syscall_exit_to_user_mode()`，真正的 `SYSRETQ/IRETQ` 选择仍在后续返回路径。

这些结论均以 Linux 5.10 的具体源码为边界，不从其他版本补全。
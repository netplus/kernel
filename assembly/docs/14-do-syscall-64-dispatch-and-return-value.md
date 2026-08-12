# A14 第二部分：`do_syscall_64()`、系统调用表与返回值写回

A14 第一部分解决的是“CPU 执行 `SYSCALL` 后，Linux 怎样得到一个完整的内核入口现场”。当 `entry_SYSCALL_64` 已经切到内核栈并构造好 `struct pt_regs` 后，下一个问题是：内核怎样把一个 syscall number 变成具体系统调用，又怎样把结果送回用户态 `%rax`。

本节只讲 Linux 5.10 的 64 位原生 syscall 分派主线。返回用户态前的 exit work，以及最终 `SYSRETQ`/`IRETQ` 选择，留到 A14 后续部分。

## 1. 从汇编入口进入 C

Linux 5.10 的 `arch/x86/entry/entry_64.S` 在建立 `pt_regs` 后，以普通 x86-64 C ABI 调用：

```asm
movq %rax, %rdi
movq %rsp, %rsi
call do_syscall_64
```

所以进入 C 时：

```text
%rdi = nr
%rsi = regs
```

这里有两个容易混淆的 syscall number：

```text
nr            C 层继续处理和分派的工作值
regs->orig_ax 入口现场保存的原始请求号
```

刚进入这一阶段时二者来自同一个用户 `%rax`，但不能把它们理解成永远相同。`nr` 随后会经过 syscall entry work；`orig_ax` 则是已经保存在 `pt_regs` 中的入口现场字段。

## 2. `do_syscall_64()` 不是简单的数组查表

Linux 5.10 `arch/x86/entry/common.c` 的主线是：

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
    |       x32 number check and dispatch
    |
    +-- instrumentation_end()
    |
    `-- syscall_exit_to_user_mode(regs)
```

因此“系统调用就是 `sys_call_table[rax]()`”只适合作为最初的抽象。Linux 5.10 的真实路径在查表前后都有统一的 entry/exit 框架。

## 3. 为什么先调用 `syscall_enter_from_user_mode()`

第一条 C 层主线是：

```c
nr = syscall_enter_from_user_mode(regs, nr);
```

这一步建立了一个重要设计边界：系统调用的入口工作先于实际分派。ptrace、seccomp、audit、syscall tracing 等机制可能参与这一阶段，所以后面的 `nr` 应看作“entry work 处理后的工作 syscall number”。

本课程在这里不展开这些子系统，只需要避免两个错误模型：

```text
错误 1：用户 %rax 一进入内核就直接作为数组下标。
错误 2：regs->orig_ax 与后续工作 nr 在任何情况下都必须相等。
```

## 4. syscall number 的范围检查

原生 x86-64 主线首先判断：

```c
if (likely(nr < NR_syscalls)) {
```

`nr` 是 `unsigned long`。因此如果用户在 `%rax` 中放入一个按有符号数理解为负数的 64 位位模式，转换到这里的无符号比较语义后会成为很大的正整数，不会因为“它是负数”而通过范围检查。

这也是阅读内核 C/汇编边界时必须同时检查位宽和 signed/unsigned 类型的典型例子。

## 5. `array_index_nospec()` 为什么在查表前

通过架构上的范围检查后，Linux 5.10 还执行：

```c
nr = array_index_nospec(nr, NR_syscalls);
```

然后才访问：

```c
sys_call_table[nr]
```

这里的 `array_index_nospec()` 用于约束推测执行下的数组索引。对本章而言，关键结论是：正常主线仍然是“验证索引 → nospec 处理 → 访问 syscall table”。Spectre 缓解机制本身不在 assembly 基础课程中展开。

## 6. `sys_call_table` 的表项接收什么参数

Linux 5.10 `arch/x86/include/asm/syscall.h` 中，表项类型本质上是：

```c
typedef long (*sys_call_ptr_t)(const struct pt_regs *);
```

所以：

```c
sys_call_table[nr](regs)
```

并不是把 `%rdi/%rsi/%rdx/%r10/%r8/%r9` 中的六个用户参数重新按照普通 C ABI 原样调用某个函数。进入内核时，这些用户寄存器已经被固化到 `pt_regs`。

x86 的 syscall wrapper 再按 syscall ABI 解码：

```text
regs->di
regs->si
regs->dx
regs->r10
regs->r8
regs->r9
```

并把参数送入后续 `__se_sys_*` / `__do_sys_*` 层。于是 A13 与 A14 的模型可以连起来：

```text
用户 syscall ABI
RDI RSI RDX R10 R8 R9
        |
        v
entry_SYSCALL_64
        |
        v
struct pt_regs
        |
        v
__x64_sys_* wrapper
        |
        v
系统调用实现
```

这也解释了为什么“用户态 syscall ABI”和“内核内部普通 C ABI”不能混为一套寄存器约定。

## 7. `orig_ax` 与 `ax` 的生命周期不同

第一部分已经看到，Linux 5.10 构造入口现场时把：

```text
regs->orig_ax = 原始 syscall number
regs->ax      = -ENOSYS
```

其中 `orig_ax` 是原始请求号的现场记录，而 `ax` 是将来返回 `%rax` 的槽位。

当有效 syscall 被成功分派时，核心语句是：

```c
regs->ax = sys_call_table[nr](regs);
```

于是状态变成：

```text
regs->orig_ax = 原始 syscall number
regs->ax      = syscall implementation return value
```

随后返回路径从 `pt_regs` 恢复寄存器，用户最终看到的 raw `%rax` 就来自这个 `regs->ax`。

## 8. 为什么无效 syscall 会得到 `-ENOSYS`

这里有一个很好的“入口初始化 + 条件覆盖”设计。

入口建立 `pt_regs` 时先把 `ax` 预置为：

```text
-ENOSYS
```

如果 `nr` 通过有效范围检查，系统调用返回值会覆盖这个槽；如果编号没有命中原生有效分支，也没有命中启用时的 x32 分支，`do_syscall_64()` 就不会用正常 syscall 返回值覆盖它。

因此无效 syscall 的主线可以理解为：

```text
entry: regs->ax = -ENOSYS
        |
        v
invalid nr
        |
        +-- no valid table call
        |
        v
regs->ax remains -ENOSYS
```

A13 的用户态实验已经说明，raw syscall 能直接观察负 errno 编码；libc 再决定是否转换成 `-1` 并设置线程局部 `errno`。这个转换不属于 `do_syscall_64()`。

## 9. `CONFIG_X86_X32_ABI` 的边界

如果 Linux 5.10 配置了 `CONFIG_X86_X32_ABI`，原生 x86-64 分支后还存在 x32 syscall number 的识别与 `x32_sys_call_table` 分派。

因此严谨的表述是：

```text
原生 x86-64 主线使用 sys_call_table；
启用 CONFIG_X86_X32_ABI 时，do_syscall_64() 还具有 x32 分派分支。
```

本课程以原生 x86-64 为主，不在这里展开 x32 ABI。

## 10. instrumentation 与执行上下文

Linux 5.10 的 `do_syscall_64()` 标记为 `__visible noinstr`。实际 syscall table 调用位于：

```text
instrumentation_begin()
...
instrumentation_end()
```

之间。

这提醒我们：虽然已经从汇编进入 C，入口/退出代码仍然不是“任意位置都和普通内核 C 函数一样可以插桩”的普通上下文。RCU、lockdep、trace、signal、reschedule 等具体 entry/exit work 留在后续返回路径单元按源码继续核验。

## 11. 到返回路径的交接

`do_syscall_64()` 最后调用：

```c
syscall_exit_to_user_mode(regs);
```

完成后控制流才返回 `entry_SYSCALL_64` 的汇编返回侧。

到这里可以把当前已经建立的完整主线写成：

```text
user executes SYSCALL
        |
        v
entry_SYSCALL_64
        |
        +-- save user state
        +-- switch kernel stack
        +-- build pt_regs
        |
        v
do_syscall_64(nr, regs)
        |
        +-- entry work
        +-- validate nr
        +-- array_index_nospec
        +-- sys_call_table[nr](regs)
        +-- regs->ax = return value
        +-- exit-to-user work
        |
        v
entry_SYSCALL_64 return-side assembly
```

下一部分再回答：返回前为什么还要做统一 exit work，以及 Linux 5.10 为什么不能无条件使用较快的 `SYSRETQ`，而必须在严格条件不满足时走 `IRETQ` 路径。

## 12. 阅读这一部分时应能回答的问题

完成本节后，应能回答：

1. `entry_SYSCALL_64` 怎样把 syscall number 和 `pt_regs` 交给 C；
2. 为什么 `nr` 与 `regs->orig_ax` 必须区分；
3. Linux 5.10 为什么在 syscall table 前做范围检查和 `array_index_nospec()`；
4. `sys_call_table` 表项为什么接收 `struct pt_regs *`；
5. 用户态六参数 syscall ABI 怎样经过 `pt_regs` 进入 x86 syscall wrapper；
6. `regs->orig_ax` 与 `regs->ax` 分别承担什么角色；
7. 为什么有效 syscall 会覆盖 `regs->ax`，无效编号则可以保留入口预置的 `-ENOSYS`；
8. `CONFIG_X86_X32_ABI` 对主线增加了什么条件分支；
9. `do_syscall_64()` 与后续返回路径的交接点在哪里。

对应 Linux 5.10 源码事实核验见 [`../source-paths/14-do-syscall-64-dispatch-linux-5.10.md`](../source-paths/14-do-syscall-64-dispatch-linux-5.10.md)。
# A17 第一部分：`switch_to`、内核栈切换与控制流恢复

## 1. 问题背景

调度器已经选出 `next` 后，CPU 仍在 `prev` 的内核栈上执行，callee-saved 寄存器和返回链也仍属于 `prev`。因此任务切换不能只修改任务指针，而必须保存旧任务可恢复的执行现场，把 `%rsp` 换成新任务保存的内核栈位置，并沿新任务自己的返回链继续。

本节只讲 Linux 5.10 x86-64 的寄存器、内核栈和控制流切换。调度器为什么选择 `next` 留在 scheduler 课程；FS/GS、TLS、FPU 等额外架构状态留给 A17 后续部分。

## 2. 基本模型

设任务 A 切换到以前运行过的任务 B：

```text
A kernel stack
  -> 保存 A callee-saved registers
  -> A->thread.sp = %rsp
  -> %rsp = B->thread.sp
B kernel stack
  -> 恢复 B callee-saved registers
  -> 进入 __switch_to(A, B)
  -> 沿 B 保存的返回链继续
```

核心不是复制栈，而是直接改变 CPU 的 `%rsp`。从装入 `B->thread.sp` 开始，后续栈访问已经属于 B。

## 3. Linux 5.10 的交接点

`kernel/sched/core.c:context_switch()` 在架构切换处调用：

```text
switch_to(prev, next, prev)
```

x86-64 的 `arch/x86/include/asm/switch_to.h` 将其连接到 `__switch_to_asm(prev, next)`。因此 A17 从调度层已经确定 `prev/next` 后开始。

## 4. `inactive_task_frame`

Linux 5.10 x86-64 的保存格式依次包含：

```text
r15, r14, r13, r12, bx, bp, ret_addr
```

`__switch_to_asm` 的保存顺序则是：

```asm
pushq %rbp
pushq %rbx
pushq %r12
pushq %r13
pushq %r14
pushq %r15
```

栈向低地址增长，所以最终从 `%rsp` 向高地址观察正好得到：

```text
+0  r15
+8  r14
+16 r13
+24 r12
+32 rbx
+40 rbp
+48 ret_addr
```

`ret_addr` 来自进入 `__switch_to_asm()` 时的调用返回地址，不是上述六条 `pushq` 额外创建的字段。

这些寄存器是 System V AMD64 ABI 中需要跨调用保持的 callee-saved GPR。这里没有保存全部 CPU 状态；其他架构线程状态由后续代码处理。

## 5. 真正的栈交换

保存寄存器后，主线执行：

```asm
movq %rsp, TASK_threadsp(%rdi)
movq TASK_threadsp(%rsi), %rsp
```

此时 `%rdi=prev`、`%rsi=next`。语义分别是：

```text
prev->thread.sp = 当前 %rsp
%rsp = next->thread.sp
```

第二条指令执行前 `%rsp` 指向 prev 的内核栈；执行后 `%rsp` 指向 next 的内核栈。这是理解整个上下文切换的关键状态跃迁。

## 6. 为什么 push 与 pop 属于不同任务

栈交换后执行：

```asm
popq %r15
popq %r14
popq %r13
popq %r12
popq %rbx
popq %rbp
```

这些值已经来自 next 的 inactive frame。因此不能按普通函数理解成“push 后再 pop 自己刚保存的值”：push 写入 prev 的栈，pop 读取 next 的栈，中间由 `%rsp = next->thread.sp` 分开。

## 7. 为什么最后使用 `jmp __switch_to`

恢复 GPR 后，Linux 5.10 通过 tail jump 进入 `__switch_to()`，而不是再创建一层普通调用。当前 next 栈中已经保留历史返回地址；如果额外创建返回地址，会改变这套暂停/恢复调用链。

`__switch_to()` 返回时，使用的是当前 next 内核栈上的返回地址，因此控制流沿 next 以前冻结的调用链继续。

## 8. “旧任务调用，从新任务返回”的准确含义

假设 B 以前运行过。B 被切出时，它自己的 kernel stack 上冻结了一次尚未完成的 `switch_to()`。后来 A 切换到 B 时，并不是让 B 从 A 的调用返回，而是：

```text
保存 A 当前的 switch_to 调用
-> 装入 B 当年冻结时的 %rsp
-> 恢复 B 的 inactive frame
-> 完成 B 自己那次历史 switch_to 调用
```

因此更准确的模型是：每个被切出的任务都把一个尚未完成的 `switch_to()` 调用冻结在自己的内核栈上；以后切回该任务，就是恢复这个被冻结的调用。

这也解释了为什么 `finish_task_switch(prev)` 会在恢复后的当前任务上下文中继续执行。

## 9. 新任务的首次运行

新创建的任务没有历史 `switch_to()` 可恢复。fork 路径会预构造它的初始 inactive frame，并让返回目标进入 `ret_from_fork`。第一次切入时仍使用同样的 `%rsp = next->thread.sp` 和 frame 恢复机制，只是返回地址来自预构造现场，而不是过去冻结的调用链。

## 10. RFLAGS 与配置边界

`inactive_task_frame` 没有 RFLAGS 字段，`__switch_to_asm()` 也没有在这条主线上通过 `pushfq/popfq` 保存任务级 RFLAGS。不能把这里与系统调用/异常入口保存 architectural return frame 的场景混为一谈。

具体反汇编还可能受配置影响。例如 `CONFIG_STACKPROTECTOR` 会加入 next stack canary 更新，retpoline/CPU feature 可能加入返回栈缓解动作。这些不改变 `prev->thread.sp` 保存和 `next->thread.sp` 装载的基本模型。

## 11. 第一部分的完成边界

第一部分的连续执行模型是：

```text
context_switch(prev, next)
 -> switch_to
 -> __switch_to_asm
 -> 保存 prev callee-saved GPR
 -> prev->thread.sp = %rsp
 -> %rsp = next->thread.sp
 -> 恢复 next callee-saved GPR
 -> jmp __switch_to(prev, next)
 -> 沿 next kernel stack 恢复历史控制流
```

`__switch_to()` 中的 FS/GS、TLS、TSS/task-stack 等状态，以及 FPU 上下文管理，不属于这组六个 push/pop，应在后续单元单独核验。

## 12. 常见误区

- 上下文切换不是只修改 `current`；CPU 的 kernel `%rsp` 和架构状态必须与 next 匹配。
- `__switch_to_asm()` 不复制内核栈，而是直接交换 CPU 当前使用的栈位置。
- 保存和恢复 GPR 的栈不是同一个任务的栈。
- `inactive_task_frame` 不是完整 CPU register dump。
- 新任务首次运行不是恢复一次过去的 `schedule()`，而是使用 fork 路径预构造的 frame 进入 `ret_from_fork`。

## 13. 验证目标

配套实验应交叉检查：

```text
inactive_task_frame 字段偏移
__switch_to_asm 实际 push/pop 顺序
TASK_threadsp 的 store/load
切换前后 %rsp 分属 prev/next kernel stack
普通恢复的历史返回地址与新任务 ret_from_fork 的区别
```

静态结构和反汇编可以在匹配源码/`vmlinux` 时直接核验；动态 `%rsp` 与新任务首次切入需要匹配 Linux 5.10 kernel-GDB/ftrace 环境，未执行时必须明确记录，不能把预期地址当成实测结果。
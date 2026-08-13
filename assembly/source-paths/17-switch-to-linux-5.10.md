# A17 源码核验：Linux 5.10 x86-64 `switch_to` 与 `__switch_to_asm`

本文只核验 A17 所需的架构上下文切换事实。调度器为什么选择某个 `next`、调度类和运行队列策略属于 `scheduler/`；这里从 `context_switch()` 已经拿到 `prev`/`next` 之后开始。

## 1. 问题背景

任务切换不能只改一个 `current` 指针。CPU 此刻正在旧任务的内核栈上执行 C/汇编代码，寄存器中还有旧任务的调用现场。要让另一个任务继续执行，至少需要解决两件事：

1. 保存旧任务下一次恢复时所需的内核执行现场；
2. 把 `%rsp` 换成新任务之前保存的内核栈位置，并恢复与该栈匹配的 callee-saved 寄存器。

Linux x86-64 把这部分最小寄存器/栈切换放在 `__switch_to_asm()` 中，其他架构线程状态继续由 C 函数 `__switch_to()` 处理。

## 2. Linux 5.10 源码位置

本次以 upstream Linux tag `v5.10` 为基线核验：

```text
kernel/sched/core.c
    context_switch()

arch/x86/include/asm/switch_to.h
    switch_to(prev, next, last)
    struct inactive_task_frame
    __switch_to_asm()
    __switch_to()

arch/x86/entry/entry_64.S
    __switch_to_asm
    ret_from_fork

arch/x86/kernel/process_64.c
    __switch_to()
```

## 3. scheduler 与 assembly 的交接点

Linux 5.10 `context_switch()` 在完成地址空间等准备后写道：

```text
/* Here we just switch the register state and the stack. */
switch_to(prev, next, prev);
barrier();
return finish_task_switch(prev);
```

因此 A17 的起点不是调度决策，而是 `switch_to()` 已经收到确定的 `prev` 与 `next`。

`arch/x86/include/asm/switch_to.h` 中 x86 的宏为：

```c
#define switch_to(prev, next, last)            \
do {                                            \
        ((last) = __switch_to_asm((prev), (next))); \
} while (0)
```

这里第三个实参在 `context_switch()` 中也是变量 `prev`。这不是普通意义上的“调用后 `prev` 仍指向调用前旧任务”这么简单；`__switch_to_asm()`/`__switch_to()` 的返回值会成为切换恢复后的 `last`。

## 4. `inactive_task_frame` 是保存格式

Linux 5.10 x86-64 定义：

```c
struct inactive_task_frame {
        unsigned long r15;
        unsigned long r14;
        unsigned long r13;
        unsigned long r12;
        unsigned long bx;
        unsigned long bp;
        unsigned long ret_addr;
};
```

源码明确要求字段顺序与 `__switch_to_asm()` 匹配。

在 x86-64 System V C ABI 中 `%rbx/%rbp/%r12-%r15` 属于 callee-saved 寄存器。`__switch_to_asm()` 不需要把所有 GPR 都保存到这里：caller-saved 寄存器已经由普通 C 调用边界负责，跨越这个“暂停后再恢复”的调用必须保住的是 callee-saved 状态和返回控制流。

`ret_addr` 不由显式 `pushq` 指令生成；它是调用 `__switch_to_asm()` 时硬件 `call` 已经压到旧任务栈上的返回地址。六个 callee-saved `pushq` 再压入后，`%rsp` 正好指向上述结构的首字段 `r15`。

## 5. `__switch_to_asm()` 的准确保存顺序

Linux 5.10 `arch/x86/entry/entry_64.S`：

```asm
/* %rdi: prev task, %rsi: next task */
pushq %rbp
pushq %rbx
pushq %r12
pushq %r13
pushq %r14
pushq %r15

movq %rsp, TASK_threadsp(%rdi)
movq TASK_threadsp(%rsi), %rsp
```

栈向低地址增长，因此六次 push 后，从新 `%rsp` 向高地址看恰好是：

```text
+0   r15
+8   r14
+16  r13
+24  r12
+32  rbx
+40  rbp
+48  ret_addr
```

这与 `struct inactive_task_frame` 完全一致。

最关键的两条指令是：

```asm
movq %rsp, TASK_threadsp(%rdi)   # prev->thread.sp = old RSP
movq TASK_threadsp(%rsi), %rsp   # RSP = next->thread.sp
```

第一条把旧任务的“暂停点”保存到 `prev->thread.sp`；第二条不是复制新任务的栈内容，而是直接把 CPU 的 `%rsp` 改成 `next` 先前保存的栈位置。从第二条执行完成开始，后续 `pop` 和最终控制流都由新任务的内核栈决定。

## 6. 配置条件不能混入基本模型

保存 `prev->thread.sp`、装载 `next->thread.sp` 是 x86-64 主线。其间还存在配置相关工作：

- `CONFIG_STACKPROTECTOR`：把 `next` 的 stack canary 装入 per-CPU canary 位置；
- `CONFIG_RETPOLINE`：按 CPU feature 通过 `FILL_RETURN_BUFFER` 处理 RSB 上下文切换缓解。

这些动作位于栈交换之后、恢复 callee-saved 寄存器之前，但不是理解 `%rsp` 交换的前提。

## 7. 从新任务栈恢复寄存器

之后的顺序为：

```asm
popq %r15
popq %r14
popq %r13
popq %r12
popq %rbx
popq %rbp
jmp __switch_to
```

这些 `pop` 已经从 `next` 的栈读取。因此从语义上看，同一个 `__switch_to_asm()` 调用在旧任务栈上开始，却在新任务之前保存的栈上继续。

这也是上下文切换最反直觉但最重要的模型：

```text
prev 在自己的内核栈上调用 switch_to
    ↓
保存 prev callee-saved + prev->thread.sp
    ↓
%rsp = next->thread.sp
    ↓
从 next 栈恢复 callee-saved
    ↓
jmp __switch_to(prev, next)
    ↓
最终沿 next 栈上的历史返回链继续
```

## 8. 为什么是 `jmp __switch_to` 而不是 `call`

`__switch_to_asm()` 已经利用新任务栈上的既有 `ret_addr` 表示恢复后应回到哪里。如果这里再普通 `call __switch_to`，就会额外创建一个新的返回地址层次，改变这套刻意构造的 inactive frame。

因此汇编用 tail jump 进入 C `__switch_to()`。按照 x86-64 C ABI，`%rdi/%rsi` 仍携带 `prev`/`next`；`__switch_to()` 返回时，`ret` 使用的是**当前（next）栈**顶部的返回地址。

## 9. `__switch_to()` 处理的不是同一批状态

`arch/x86/kernel/process_64.c::__switch_to()` 继续处理不能简单靠六个 push/pop 表达的架构线程状态。Linux 5.10 源码中包括 FS/GS 保存与恢复、TLS、`arch_end_context_switch()`、`update_task_stack(next_p)`、额外 thread state，以及与 FPU 等架构状态相关的切换工作。

A17 第一部分只建立“callee-saved + kernel `%rsp` + 控制流”的主干；这些额外状态应在后续小单元逐项核验，不能把 `__switch_to_asm()` 误写成完整 CPU 上下文的全部内容。

## 10. “旧任务调用，从新任务返回”应该怎样准确理解

`context_switch()` 中：

```c
switch_to(prev, next, prev);
...
finish_task_switch(prev);
```

第一次看到时容易认为一次 C 调用应在同一任务中返回。实际情况是：

1. 任务 A 在自己的内核栈中进入 `switch_to(A, B, ...)`；
2. `__switch_to_asm()` 保存 A 的 inactive frame 和 `A->thread.sp`；
3. CPU `%rsp` 改为 `B->thread.sp`；
4. B 的 inactive frame 被恢复；
5. `__switch_to()` 返回时使用 B 栈中保存的返回地址；
6. 因而恢复的是 B **上一次被切走时暂停的那次** `switch_to()` 调用；
7. 返回值让恢复后的代码知道“刚刚从哪个任务切过来”，随后 `finish_task_switch(prev)` 在当前任务 B 的上下文中完成切换收尾。

所以更精确的表述不是“一次普通函数调用跨任务返回”，而是：**每个被切出的任务都把一个尚未完成的 `switch_to()` 调用冻结在自己的内核栈上；切入该任务就是恢复这个被冻结的调用。**

新创建、从未运行过的任务是特殊情况：它的初始 `inactive_task_frame` 由 fork 路径预先构造，`ret_addr` 指向 `ret_from_fork`，因此第一次切入不是恢复旧的 `schedule()` 调用，而是进入新任务的启动路径。

## 11. 已核验结论

本单元可以确定：

- Linux 5.10 `context_switch()` 在 `switch_to()` 前已经完成调度决策；
- x86-64 `switch_to` 直接调用 `__switch_to_asm(prev, next)`；
- `__switch_to_asm()` 保存 `%rbp/%rbx/%r12/%r13/%r14/%r15`，其栈布局与 `inactive_task_frame` 一致；
- `prev->thread.sp` 保存切出任务的 kernel `%rsp`，随后 CPU `%rsp` 直接换成 `next->thread.sp`；
- 恢复寄存器发生在 next 的内核栈上；
- 汇编以 `jmp __switch_to` 进入 C 架构状态切换；
- `__switch_to()` 返回后，控制流沿 next 栈中冻结的调用链继续；
- 新任务通过预构造 frame/`ret_from_fork` 进入首次运行路径；
- `CONFIG_STACKPROTECTOR`、`CONFIG_RETPOLINE` 会在汇编切换路径增加动作，但不改变上述基本栈交换模型。

## 12. 下一步

下一最小单元应基于本事实核验编写 A17 第一部分正式教程，并设计验证方式。实验至少应能交叉检查：

```text
inactive_task_frame 字段偏移
__switch_to_asm 实际反汇编 push/pop 顺序
TASK_threadsp 的 store/load
切换前后 %rsp 属于不同 task kernel stack
新任务 ret_from_fork 与普通恢复路径的区别
```

若没有匹配 Linux 5.10 `vmlinux`/kernel-GDB 环境，静态反汇编步骤仍可执行，动态 `%rsp` 观测必须明确记录为待实测。
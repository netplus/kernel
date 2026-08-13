# A17 源码核验：Linux 5.10 x86-64 `__switch_to()` 的非栈架构状态

本文继续 A17 第一部分的 `__switch_to_asm()` 主线，只核验 `%rsp` 已切到 `next` 之后，Linux 5.10 x86-64 的 `__switch_to()` 还要处理哪些不能由 callee-saved GPR frame 表达的状态。调度器如何选择 `next` 仍属于 `scheduler/`。

## 1. 基本问题

第一部分已经确认 `__switch_to_asm()` 完成 callee-saved GPR 保存、`prev->thread.sp` 保存、`next->thread.sp` 装入和 next GPR 恢复，随后 tail-jump 到 `__switch_to(prev, next)`。

此时 CPU 已使用 next 的内核栈，但 FS/GS、TLS descriptor、DS/ES、FPU、per-CPU current task、task stack top 与 TSS 入口栈状态仍需要与 next 对齐。因此应把任务切换分成两层：

```text
__switch_to_asm()
    callee-saved GPR + kernel %rsp + 返回控制流

__switch_to()
    FS/GS/TLS/segment + FPU + per-CPU current/task-stack/TSS + 其他条件状态
```

## 2. Linux 5.10 源码位置

本次以 upstream Linux tag `v5.10` 为基线核验：

```text
arch/x86/kernel/process_64.c
    __switch_to()
    save_fsgs()
    x86_fsgsbase_load()

arch/x86/kernel/process.c
    cpu_tss_rw

arch/x86/include/asm/switch_to.h
    update_task_stack()
```

## 3. 进入 `__switch_to()` 时的状态

`__switch_to_asm()` 恢复 next 的 callee-saved GPR 后使用 `jmp __switch_to`。所以进入 C 函数时，`%rsp` 已属于 next，而参数仍表示 `prev_p` 和 `next_p`。这说明“当前使用谁的栈”和“函数参数描述哪个任务”是两个不同问题。

## 4. FPU 不属于 inactive GPR frame

Linux 5.10 的 `__switch_to()` 分别取得 prev/next 的 FPU 对象，并在切换过程中调用 FPU prepare/finish helper。具体是否需要加载受线程状态控制。

因此不能把 `__switch_to_asm()` 的六次 push/pop 描述成完整 CPU context。FPU/XSTATE 有独立的保存和恢复机制。

## 5. FS/GS 保存必须早于 TLS 装载

Linux 5.10 的主线明确执行：

```text
save_fsgs(prev_p)
-> load_TLS(next, cpu)
```

源码注释说明，TLS 装载过程可能影响 `%fs/%gs`，所以 outgoing FS/GS 必须先保存。

`save_fsgs()` 保存 selector；在支持 `X86_FEATURE_FSGSBASE` 的 CPU 上还直接读取 FS/GS base，否则走 legacy base 逻辑。恢复 next 时，`x86_fsgsbase_load(prev, next)` 同样根据 CPU feature 选择对应路径。

因此 FS/GS 至少包含两个必须区分的对象：selector/index 与 base address。

## 6. TLS 必须先于相关 segment restore

源码顺序为：

```text
save_fsgs(prev)
load_TLS(next, cpu)
arch_end_context_switch(next)
恢复 DS/ES
x86_fsgsbase_load(prev, next)
```

TLS descriptor 先进入 GDT，之后才恢复可能引用这些 descriptor 的 segment。这个顺序体现真实依赖关系，而不是任意排列。

## 7. DS/ES 与 FS/GS 的恢复重点不同

Linux 5.10 保存 prev 的 ES/DS selector，并在需要时装入 next 的 selector。FS/GS 除 selector 外还要处理 base。因此不能把所有 segment register 简化成完全相同的保存/恢复问题。

## 8. `current_task`、task stack top 与 TSS 入口栈

完成 segment/FSGS 状态后，Linux 5.10 更新 per-CPU `current_task` 为 `next_p`，并把 `cpu_current_top_of_stack` 更新为 `task_top_of_stack(next_p)`。之后完成 incoming FPU 状态，并调用 `update_task_stack(next_p)` 更新与 ring-3 到 ring-0 入口相关的 task-stack/TSS 状态。

这里必须与第一部分的 `next->thread.sp` 区分：

```text
next->thread.sp
    是任务被切出时冻结的内核执行位置，用来恢复 kernel control flow。

task_top_of_stack(next)
    是该任务 kernel stack 的顶部边界/入口相关位置。

TSS 入口栈状态
    服务于 CPU 从较低特权级进入 ring 0 的 privilege stack switch。
```

它们都与“栈”有关，但用途和时间点不同。

## 9. 与 A15 的 TSS/IST 模型衔接

A15 已经完整讲解 TSS/IST。A17 这里只补上下文切换交接点：current task 改为 next 后，后续从用户态进入 ring 0 时必须使用与 next 匹配的 task kernel stack 入口，因此 context switch 需要更新相关 per-CPU stack-top/TSS 状态。

IST exception stack 是 per-CPU 特殊异常栈，不等于普通任务的 `thread.sp`。

## 10. 已核验主线

Linux 5.10 x86-64 可按以下层次理解：

```text
__switch_to_asm(prev, next)
    保存 prev callee-saved GPR
    prev->thread.sp = %rsp
    %rsp = next->thread.sp
    恢复 next callee-saved GPR
    jmp __switch_to

__switch_to(prev, next)
    FPU outgoing prepare（按状态）
    save_fsgs(prev)
    load_TLS(next)
    arch_end_context_switch(next)
    保存/恢复 DS、ES
    x86_fsgsbase_load(prev, next)
    current_task = next
    cpu_current_top_of_stack = task_top_of_stack(next)
    FPU incoming finish
    update_task_stack(next)
    处理其他条件性 thread state
    return prev_p
```

最后的返回仍沿 next 内核栈中冻结或预构造的返回地址继续，与第一部分控制流模型一致。

## 11. 配置与 CPU feature 边界

- `X86_FEATURE_FSGSBASE` 会改变 FS/GS base 的具体读写方式；
- Xen/paravirt 会影响部分 helper 的具体实现；
- FPU prepare/load 行为受线程状态影响；
- 其他 thread state 的更新也可能受内核配置和 CPU feature 影响。

这些条件不改变“先由 `__switch_to_asm()` 完成 GPR/%rsp 主干，再由 `__switch_to()` 安装非栈架构状态”的总体分层。

## 12. 下一步验证目标

后续教程与实验至少应验证：

```text
1. %rsp 切换发生在 __switch_to() 之前；
2. save_fsgs(prev) 在 load_TLS(next) 之前；
3. TLS GDT 更新在相关 segment restore 之前；
4. FS/GS selector 与 base 是不同状态；
5. current_task 和 cpu_current_top_of_stack 最终与 next 对齐；
6. update_task_stack(next) 与 next->thread.sp 不是同一个概念；
7. FPU 不属于 inactive_task_frame。
```

若缺少匹配 Linux 5.10 `vmlinux`/kernel-GDB 环境，具体 FS/GS base、TSS 和 per-CPU 地址保持待实测，不从源码预期值推导成实验结果。
# A17 第二部分：`__switch_to()` 的非栈架构状态

## 问题背景

A17 第一部分已经确认，Linux 5.10 x86-64 的 `__switch_to_asm()` 会保存 `prev` 的 callee-saved GPR，把当前 `%rsp` 保存到 `prev->thread.sp`，再装入 `next->thread.sp`，恢复 next 的寄存器并跳转到 `__switch_to(prev, next)`。因此进入 `__switch_to()` 时，CPU 已经运行在 next 的内核栈上，但上下文切换还没有全部完成。

原因是任务相关状态不只有通用寄存器和 `%rsp`。FS/GS、TLS descriptor、DS/ES、FPU/XSTATE、per-CPU current-task 信息，以及以后从用户态进入内核时所需的 task-stack 入口状态，都不能由第一部分的 `inactive_task_frame` 表达。

## 两层切换模型

应把 Linux 5.10 x86-64 的架构上下文切换分成两层：

```text
__switch_to_asm()
    callee-saved GPR
    kernel %rsp
    返回控制流

__switch_to()
    FS/GS、TLS、segment
    FPU/XSTATE
    current task 与 task stack top
    TSS 入口栈等条件性架构状态
```

这一区分很重要：`%rsp = next->thread.sp` 只说明 CPU 已经取得 next 的内核执行位置，不能推出所有任务相关 CPU 状态都已经属于 next。

## FS/GS 与 TLS 的依赖顺序

Linux 5.10 主线先执行 `save_fsgs(prev)`，再执行 `load_TLS(next, cpu)`。这个顺序存在真实依赖：outgoing task 的 FS/GS 可能引用 TLS descriptor，因此必须先保存 prev 的状态，再让 GDT 中的 TLS 槽变成 next 的内容。

FS/GS 还必须区分 selector 与 base。支持 `X86_FEATURE_FSGSBASE` 时，base 的具体读写路径与 legacy CPU 不同，所以不能把“恢复 FS/GS”简化为恢复一个 16-bit selector。

TLS descriptor 安装后，Linux 才恢复可能引用这些 descriptor 的 segment 状态。DS/ES 的重点主要是 selector，而 FS/GS 在 x86-64 下还具有独立 base 语义。

## FPU 不属于 inactive frame

第一部分的 `inactive_task_frame` 只包含 `%rbx/%rbp/%r12-%r15` 与返回控制流。浮点、SSE、AVX 及其他 XSTATE 由独立的 FPU context machinery 管理。Linux 5.10 在上下文切换过程中通过 FPU helper 处理 outgoing/incoming 状态，具体是否实际保存或装入取决于线程状态。

因此六次 `pushq/popq` 不是完整 CPU context 的保存与恢复。

## 三个不同的栈位置

A17 中同时出现三个容易混淆的对象。

`next->thread.sp` 是 next 被切出时冻结的 kernel execution position。`__switch_to_asm()` 把它直接装入 CPU `%rsp`，用于恢复 next 的 inactive frame 与历史控制流。

`task_top_of_stack(next)` 是 next 的 task kernel stack 顶部/入口相关边界。Linux 5.10 会把 per-CPU `cpu_current_top_of_stack` 更新为这个值。它不是当前执行 `%rsp` 的同义词。

TSS 中与普通 privilege entry 相关的 task-stack 状态服务于以后从 ring 3 进入 ring 0 的栈切换。Linux 5.10 通过 `update_task_stack(next)` 更新相关状态。它解决的是“下一次用户态进入内核时从哪里取得内核入口栈”，而 `thread.sp` 解决的是“当前 context switch 从哪里恢复 next 的内核执行”。

A15 中的 IST exception stack 又是另一套 per-CPU 特殊异常栈，不等于上述任一 task execution position。

## per-CPU current 状态

在 `__switch_to()` 中，Linux 5.10 最终把 per-CPU `current_task` 更新为 `next`，并更新 `cpu_current_top_of_stack`。这说明上下文切换是一个有顺序的状态迁移，而不是单独执行一次 `current = next`。

可以把主线概括为：

```text
__switch_to_asm(prev, next)
 -> 保存 prev GPR
 -> prev->thread.sp = %rsp
 -> %rsp = next->thread.sp
 -> 恢复 next GPR
 -> jmp __switch_to

__switch_to(prev, next)
 -> FPU outgoing prepare（按状态）
 -> save_fsgs(prev)
 -> load_TLS(next, cpu)
 -> arch_end_context_switch(next)
 -> 保存/恢复 DS、ES
 -> x86_fsgsbase_load(prev, next)
 -> current_task = next
 -> cpu_current_top_of_stack = task_top_of_stack(next)
 -> FPU incoming finish（按状态）
 -> update_task_stack(next)
 -> 处理其他条件性 thread state
 -> return prev
```

最后的返回仍使用 next 内核栈中冻结或预构造的返回地址，因此与第一部分的控制流模型连续。

## 配置与 CPU feature 边界

`X86_FEATURE_FSGSBASE` 会改变 FS/GS base 的具体读写方式；Xen/paravirt 可能改变部分 helper 的实现；FPU/XSTATE 的实际 load/save 受线程状态影响；其他 thread state 也可能受配置或 CPU feature 控制。这些条件不改变总体分层：先由 `__switch_to_asm()` 切换 GPR/%rsp，再由 `__switch_to()` 完成其余架构状态。

## 常见误区

- 换成 `next->thread.sp` 后，不代表整个 architecture context 已完成切换。
- `inactive_task_frame` 不是完整寄存器快照。
- FS/GS selector 与 base 是不同状态。
- `thread.sp` 与 `task_top_of_stack(next)` 用途不同。
- TSS privilege-entry stack 不等于当前 kernel `%rsp`。
- IST stack 不等于普通 task kernel stack。

## 验证目标

配套实验应至少核验：`%rsp` 在进入 `__switch_to()` 前已经属于 next；`save_fsgs(prev)` 位于 `load_TLS(next)` 之前；TLS 更新先于相关 segment restore；FS/GS selector 与 base 分开处理；`current_task` 和 `cpu_current_top_of_stack` 最终与 next 对齐；`thread.sp` 与 `task_top_of_stack(next)` 不是同一对象；FPU 状态不属于 `inactive_task_frame`。

静态顺序可以通过 Linux 5.10 源码和匹配 `vmlinux` 的反汇编核验。具体 FS/GS base、per-CPU 地址、TSS 与 FPU 动态状态需要匹配 Linux 5.10 kernel-GDB 环境；没有该环境时必须明确记录为待实测。
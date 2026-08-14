# A17 第二部分实验预期分析：`__switch_to()` 的非栈架构状态

本文给出 `17-switch-to-arch-state` 实验的验收基线。它只描述根据 Linux 5.10 源码和 A17 正文可以预期的关系；需要匹配 `vmlinux`、guest 和 kernel-GDB 才能得到的地址、寄存器值和具体 helper 路径，仍必须记录为实测数据，不能用本文的预期代替。

## 1. 先固定观察时刻

A17 第一部分已经发生过真正的 kernel execution stack 交换：

```text
prev callee-saved GPR 已压入 prev kernel stack
prev->thread.sp = %rsp
%rsp = next->thread.sp
next callee-saved GPR 已从 next kernel stack 弹出
jmp __switch_to
```

因此，**刚进入 `__switch_to(prev, next)` 时 CPU 已经在 next 的 kernel stack 上执行**。但这只是架构上下文切换的中间状态，不代表 FS/GS、TLS、per-CPU current、FPU 或未来 privilege-entry stack 已全部切到 next。

验收时必须同时记录“在哪一条指令/哪个逻辑点观察”和“此时哪个状态已经切换”。不要把整个 `__switch_to()` 当成原子瞬间。

## 2. `%rsp`、`thread.sp` 与 stack top 的关系

需要区分至少三个值：

```text
CPU %rsp
next->thread.sp
task_top_of_stack(next)
```

它们的语义分别是：

- `next->thread.sp`：next 上一次被切出时保存的 inactive-frame 起点，也就是恢复 next kernel execution 的位置；
- CPU `%rsp`：当前真实执行栈指针；
- `task_top_of_stack(next)`：next task kernel stack 的顶部/入口相关边界。

`__switch_to_asm()` 刚执行 `%rsp = next->thread.sp` 时两者相等；但随后会弹出 `%r15/%r14/%r13/%r12/%rbx/%rbp`，再进入 `__switch_to()`。因此在 `__switch_to()` 入口，正常情况下应验证：

```text
next kernel-stack low <= %rsp < next kernel-stack high
```

而不应要求：

```text
%rsp == next->thread.sp
```

同样不能要求 `%rsp == task_top_of_stack(next)`。这里的关键是对象用途与时间关系，不是制造一个“永远不相等”的 ABI 规则。

## 3. FS/GS、TLS 与 segment restore 的顺序

Linux 5.10 主线要求先保存 outgoing FS/GS，再安装 incoming TLS descriptors，然后才恢复可能引用这些 descriptors 的 segment/FSGS 状态。实验应得到如下逻辑顺序：

```text
save_fsgs(prev)
    before
load_TLS(next, cpu)
    before
incoming segment / FSGS restore
```

这里的“before”是源码与实际指令执行顺序，不要求反汇编中一定存在三个独立的 `call`；helper 可能被内联。

如果 prev/next 没有不同的自定义 TLS，GDT TLS slot 的数值可能看起来没有变化。这不否定顺序本身。验收重点是：不能在保存 prev 的 selector/base 之前就覆盖其可能依赖的 TLS descriptors。

## 4. FS/GS selector 与 base 必须分开验收

`%fs`/`%gs` selector 是 segment selector 语义，而 FS/GS base 是独立的 64-bit linear base 状态。只观察 selector 不能证明完整 FS/GS context 已恢复。

实验记录至少应区分：

```text
FS selector / GS selector
FS base / GS base
```

若 CPU/内核启用了 FSGSBASE，具体指令路径可能与 legacy MSR/segment 路径不同；应记录当前 CPU feature 与实际反汇编，而不是把某一种实现写成 Linux 5.10 在所有机器上的固定指令序列。

## 5. per-CPU `current_task` 与 `cpu_current_top_of_stack`

在 `__switch_to()` 的相应更新完成后，应满足：

```text
current_task == next
cpu_current_top_of_stack == task_top_of_stack(next)
```

这两个关系描述的是 per-CPU bookkeeping 已经对齐 incoming task。

它们不意味着：

```text
CPU %rsp == cpu_current_top_of_stack
```

CPU 此时仍在 next kernel stack 的某个普通函数执行位置。`cpu_current_top_of_stack` 保存的是 task stack top/入口相关状态，不是当前 C 函数的 stack pointer。

## 6. `update_task_stack(next)` 与 TSS/entry-stack 边界

`update_task_stack(next)` 服务于**未来**的 privilege-level entry。它与第一部分的 `%rsp = next->thread.sp` 解决不同问题：

```text
thread.sp
    恢复当前 context switch 中 next 的 kernel execution

TSS / task entry-stack state
    为以后从用户态进入内核准备正确的入口栈状态
```

具体写入哪个 TSS/entry-stack 对象必须以当前 Linux 5.10 配置展开为准，特别要记录 PTI/paravirt 等条件。验收标准不是强行要求某个固定 TSS 字段永远等于 `task_top_of_stack(next)`，而是确认 context switch 完成后，未来 privilege entry 使用的状态已经与 next 对齐。

A15 的 IST exception stack 仍是另一套机制，不应出现在这个等式中。

## 7. FPU/XSTATE 的验收边界

第一部分的 56-byte `inactive_task_frame` 只保存：

```text
r15 r14 r13 r12 bx bp ret_addr
```

因此 FPU/SSE/AVX/XSTATE 必须由独立 machinery 管理。实验应能从源码/反汇编定位 outgoing/incoming FPU helper 或相应逻辑，但不能要求每一次 `sched_switch` 都出现完整 XSAVE/XRSTOR。

是否真正保存/恢复某些扩展状态取决于线程状态、CPU feature 和 Linux 5.10 的优化路径。正确结论是“FPU/XSTATE 不属于 inactive frame，并由独立 context machinery 管理”，而不是“每次切换固定执行某条 XSAVE/XRSTOR 指令”。

## 8. 一次合格的动态记录应形成的时间线

若环境具备 kernel-GDB，推荐把一次 prev -> next 切换记录成：

```text
T0: __switch_to_asm 保存 prev inactive frame
T1: prev->thread.sp 写入完成
T2: CPU %rsp 装入 next->thread.sp
T3: next callee-saved GPR 恢复完成
T4: 进入 __switch_to，%rsp 已位于 next kernel stack
T5: outgoing FS/GS 保存完成
T6: incoming TLS descriptors 安装完成
T7: incoming segment/FSGS 状态恢复完成
T8: current_task / cpu_current_top_of_stack 与 next 对齐
T9: incoming FPU 状态按实际条件完成
T10: future privilege-entry task/TSS state 与 next 对齐
T11: __switch_to 返回，沿 next 的历史或预构造控制流继续
```

不同编译配置会改变中间 helper 和具体指令，但不能改变第一部分与第二部分之间的核心分层：先切 kernel execution stack/control flow，再完成剩余 task-specific architecture state。

## 9. 不应接受的结论

以下观察不足以单独通过实验：

- 只看到 `sched_switch`，就声称验证了 `%rsp`、FS/GS 或 TSS；
- 只看到 `%rsp` 改变，就声称证明它属于 next kernel stack；
- 只读取 `%fs/%gs` selector，就声称验证了 FS/GS base；
- 把 `next->thread.sp`、`task_top_of_stack(next)` 和 TSS entry stack 当成同一指针；
- 没看到 TLS slot 数值变化，就声称 `load_TLS()` 没有执行；
- 没看到 XSAVE/XRSTOR，就声称 FPU context 没有被管理；
- 用其他 kernel version 的结构偏移或反汇编地址代替当前 Linux 5.10 `vmlinux`。

## 10. 当前环境没有 kernel-GDB 时

如果没有匹配 Linux 5.10 的 `vmlinux`、guest 和可停机 debugger，本实验仍可以完成源码顺序、结构语义和反汇编定位方法的检查，但以下项目必须明确标记为“待实测”：

```text
具体 %rsp 与 kernel-stack 地址
FS/GS selector/base 数值
TLS GDT slot 数值
per-CPU current_task 地址
cpu_current_top_of_stack 地址
TSS/entry-stack 动态值
实际采用的 FPU helper/指令路径
```

这属于实验环境限制，不应通过从源码推导一组看似合理的地址来填充结果。

# A17 第二部分实验：验证 `__switch_to()` 的非栈架构状态

## 实验目标

A17 第一部分已经验证 `__switch_to_asm()` 的 callee-saved GPR frame、`thread.sp` 和内核 `%rsp` 切换。本实验继续验证 `%rsp` 已经切到 `next` 之后，Linux 5.10 x86-64 的 `__switch_to()` 如何完成其余架构状态交接。

重点不是证明调度器为什么选择某个 `next`，而是验证已经选定 `prev/next` 后的架构切换顺序：

```text
__switch_to_asm()
    %rsp -> next kernel execution position

__switch_to(prev, next)
    FS/GS save
    TLS install
    segment/FSGS restore
    current_task / stack-top update
    FPU incoming state
    task/TSS entry-stack update
```

需要验证以下结论：

1. 进入 `__switch_to()` 时 `%rsp` 已属于 `next` 的 kernel stack；
2. `save_fsgs(prev)` 发生在 `load_TLS(next, cpu)` 之前；
3. TLS descriptor 安装先于可能引用它的 segment/FSGS restore；
4. FS/GS selector 与 base 是不同状态；
5. `current_task` 与 `cpu_current_top_of_stack` 最终切到 `next`；
6. `next->thread.sp`、`task_top_of_stack(next)` 和 privilege-entry/TSS stack 状态不是同一个对象；
7. FPU/XSTATE 不属于第一部分的 56-byte `inactive_task_frame`。

## 实验环境

动态实验需要隔离的 Linux 5.10 x86-64 guest，并具有与正在运行内核完全匹配的：

```text
vmlinux
kernel config
GDB
QEMU gdbstub 或等价的可停机 kernel debugger
```

建议关闭 KASLR，或在 GDB 中完成符号重定位。不要把其他版本 `vmlinux` 的偏移套到 Linux 5.10。

本实验不修改 FS/GS/TLS/TSS/FPU 状态，也不主动写 per-CPU 数据；只观察正常 context switch。

## 第一阶段：静态确认源码和反汇编顺序

先在当前 Linux 5.10 源码中确认：

```text
arch/x86/kernel/process_64.c
    __switch_to()
    save_fsgs()
    x86_fsgsbase_load()

arch/x86/include/asm/switch_to.h
    update_task_stack()

arch/x86/entry/entry_64.S
    __switch_to_asm
```

再对匹配的 `vmlinux` 执行：

```bash
objdump -drS vmlinux | less
```

搜索 `__switch_to_asm` 和 `__switch_to`。由于 helper 可能内联，不能要求反汇编中一定存在独立的 `call save_fsgs` 或 `call load_TLS`。应结合源码、DWARF/source interleave 和实际指令确认逻辑顺序。

静态检查至少记录：

```text
A. __switch_to_asm 中 next->thread.sp 被装入 %rsp 的位置；
B. 跳入 __switch_to 的位置；
C. save_fsgs(prev) 对应逻辑；
D. load_TLS(next, cpu) 对应逻辑；
E. DS/ES 与 FSGS restore 的位置；
F. current_task/cpu_current_top_of_stack 更新位置；
G. update_task_stack(next) 对应逻辑。
```

## 第二阶段：在 `__switch_to()` 入口验证当前栈已经属于 next

在隔离 guest 中运行两个持续让出 CPU 的普通用户任务，并尽量固定到同一 CPU。通过 kernel-GDB 在 `__switch_to` 入口断下。

先记录函数参数：

```gdb
p prev_p
p next_p
p prev_p->pid
p next_p->pid
p/x next_p->thread.sp
p/x $rsp
```

再取得 next task kernel stack 的实际范围。具体 helper/字段依赖当前调试符号，应优先用当前内核的 `task_stack_page(next_p)`、`THREAD_SIZE` 或等价源码定义计算，不硬编码地址。

验收关系是：

```text
next kernel-stack low <= $rsp < next kernel-stack high
```

并且在刚进入 `__switch_to()` 时，`$rsp` 已经不是 prev 的当前执行栈。

注意：此时 `$rsp` 不要求等于 `next_p->thread.sp`。`__switch_to_asm()` 在装入 `thread.sp` 后还会从 next frame pop 六个 callee-saved GPR，再 `jmp __switch_to`，所以进入 C 函数时 `%rsp` 已向高地址移动。

## 第三阶段：观察 FS/GS 与 TLS 的先后关系

根据当前 `vmlinux` 的实际反汇编设置断点，不使用本文中的固定地址。

在 outgoing FS/GS 保存逻辑完成前后，记录：

```text
prev->thread.fsindex
prev->thread.gsindex
prev->thread.fsbase
prev->thread.gsbase
```

字段名必须以当前 Linux 5.10 DWARF 为准；如果编译配置或结构定义导致名称不同，应记录实际字段，不猜测。

随后在 TLS install 前后观察当前 CPU GDT 中 TLS slots 的变化，并与 `next->thread.tls_array` 对照。

验收重点不是要求每次 context switch 都发生可见变化。若 prev/next 恰好没有自定义 TLS，slot 内容可能相同；此时仍应通过执行顺序确认：

```text
save outgoing FS/GS
    before
install incoming TLS descriptors
    before
restore incoming segment/FSGS state
```

若要提高可见性，可让用户任务通过正常 libc/pthread TLS 使用路径产生不同 TLS 状态，但不要从 debugger 强行写 GDT。

## 第四阶段：区分 FS/GS selector 与 base

在支持 FSGSBASE 的 guest 与不支持/禁用该 feature 的 guest 上，具体指令路径可能不同。先检查：

```bash
grep -w fsgsbase /proc/cpuinfo
```

再结合 `x86_fsgsbase_load(prev, next)` 的当前反汇编观察 selector/base restore。

需要记录两类状态：

```text
selector/index: 16-bit segment selector 语义
base:           64-bit linear base address 语义
```

不能仅观察 `%fs`/`%gs` selector 就宣称 FS/GS context 已完整恢复。

## 第五阶段：观察 `current_task` 与 stack top

在 `__switch_to()` 中更新 per-CPU current-task 状态之前和之后各停一次，记录：

```text
prev_p
next_p
per-CPU current_task
per-CPU cpu_current_top_of_stack
next->thread.sp
task_top_of_stack(next)
CPU %rsp
```

预期在更新完成后：

```text
current_task == next
cpu_current_top_of_stack == task_top_of_stack(next)
```

同时通常有：

```text
$rsp != next->thread.sp
$rsp != task_top_of_stack(next)
next->thread.sp != task_top_of_stack(next)
```

这里的“不等”用于强调语义，不应写成对所有瞬间都成立的 ABI 断言；真正验收应以对象用途和当前执行时刻为准。

## 第六阶段：观察 `update_task_stack(next)` 与 TSS 入口状态

A15 已解释 TSS privilege-entry stack。本实验只验证 context switch 的交接点。

在 `update_task_stack(next)` 前后读取当前 CPU 的 `cpu_tss_rw` 中与普通 ring-3 -> ring-0 entry 相关的 stack pointer，并与 `task_top_of_stack(next)`/当前配置的 entry-stack 策略对照。

必须先阅读当前 Linux 5.10 `update_task_stack()` 展开，因为 PTI/paravirt 等配置会改变具体写入对象。验收目标不是强制某个固定 TSS 字段等于 `task_top_of_stack(next)`，而是确认：

```text
context switch 后，未来 privilege entry 所依赖的 task-stack/TSS 状态与 next 对齐。
```

不要把这一状态与 CPU 当前 `%rsp` 或 `next->thread.sp` 混为一谈。

## 第七阶段：FPU/XSTATE 边界

第一部分 `inactive_task_frame` 只有：

```text
r15 r14 r13 r12 bx bp ret_addr
```

本实验通过源码/反汇编定位 `__switch_to()` 周围的 FPU prepare/finish helper，确认 FPU/XSTATE 使用独立 machinery。

动态实验可以让两个用户任务分别执行浮点/SIMD 运算，再在正常调度中观察 FPU thread state；但不得仅因看到一次 context switch 就假设一定发生完整 XSAVE/XRSTOR。Linux 5.10 的实际保存/装入行为受 FPU 状态和优化路径影响。

## 可选的 ftrace 辅助观察

可以使用 `sched_switch` tracepoint 确认正在发生目标任务之间的切换：

```bash
mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
cd /sys/kernel/debug/tracing
echo 0 > tracing_on
echo 1 > events/sched/sched_switch/enable
echo 1 > tracing_on
sleep 1
echo 0 > tracing_on
cat trace
```

这只能证明调度事件及 prev/next 身份，不能替代 GDB 对 `%rsp`、FS/GS、GDT/TSS 或 per-CPU state 的验证。

## 结果记录模板

```text
kernel commit/config:
CPU/FSGSBASE:
KASLR/PTI/paravirt:

prev pid:
next pid:

__switch_to entry RSP:
next kernel stack range:
next->thread.sp:
task_top_of_stack(next):

FS/GS save observation:
TLS install observation:
segment/FSGS restore observation:

current_task before/after:
cpu_current_top_of_stack before/after:
TSS/task-stack state before/after:

FPU helper path observed:

unexecuted items and reason:
```

## 当前环境执行边界

本实验需要匹配 Linux 5.10 的 `vmlinux`、运行中的同构 guest 和可停机 kernel-GDB 会话。若维护环境不具备这些条件，应完成源码、反汇编步骤设计和字段/时序核验，但必须把具体 `%rsp`、FS/GS base、GDT/TSS 地址、per-CPU 地址和 FPU 动态路径记录为“待实测”，不能从源码预期值伪造实验数据。

## 与课程正文的关系

正文：[`../../docs/17-switch-to-arch-state.md`](../../docs/17-switch-to-arch-state.md)

Linux 5.10 源码核验：[`../../source-paths/17-switch-to-arch-state-linux-5.10.md`](../../source-paths/17-switch-to-arch-state-linux-5.10.md)

第一部分实验：[`../17-switch-to-stack-control-flow/`](../17-switch-to-stack-control-flow/)

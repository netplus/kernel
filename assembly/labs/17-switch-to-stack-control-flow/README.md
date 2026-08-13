# A17 实验：验证 `switch_to` 的 inactive frame、内核栈交换与控制流恢复

## 1. 实验目标

本实验对应 A17 第一部分，只验证 Linux 5.10 x86-64 `switch_to()` 主线中的寄存器、内核 `%rsp` 与控制流切换，不验证调度器为什么选择 `next`，也不把 FS/GS、TLS、FPU 等 `__switch_to()` 后续状态混入本实验。

需要回答五个问题：

1. `struct inactive_task_frame` 的字段偏移是否与 `__switch_to_asm` 的 push/pop 顺序一致；
2. `prev->thread.sp` 保存的是否正是压入六个 callee-saved GPR 后的 `%rsp`；
3. 装入 `next->thread.sp` 后，CPU `%rsp` 是否已经落在 next 的 kernel stack；
4. 为什么恢复 next GPR 后可以沿 next 过去冻结的 `switch_to()` 调用继续；
5. 新任务第一次被切入时，为什么会走预构造的 `ret_from_fork`，而不是恢复历史 `schedule()` 调用。

## 2. 版本与源码基线

实验以 upstream Linux v5.10 x86-64 为语义基线。开始前先对照：

```text
kernel/sched/core.c
    context_switch()

arch/x86/include/asm/switch_to.h
    switch_to
    struct inactive_task_frame

arch/x86/entry/entry_64.S
    __switch_to_asm
    ret_from_fork

arch/x86/kernel/process_64.c
    __switch_to()
```

配套源码核验：`../../source-paths/17-switch-to-linux-5.10.md`。

配套教程：`../../docs/17-switch-to-stack-and-control-flow.md`。

不要用其他内核版本的反汇编代替当前 v5.10 `vmlinux` 的事实。

## 3. 环境要求

静态部分需要：

```text
Linux 5.10 源码树
匹配配置构建出的 vmlinux
objdump 或 llvm-objdump
GDB（建议带 vmlinux 调试信息）
```

动态部分建议使用隔离的 Linux 5.10 QEMU/KVM guest，并通过 QEMU gdbstub 或等价 kernel-GDB 环境停机观察。生产机不应为了本实验停在调度切换路径中。

如果当前环境只有源码而没有匹配 `vmlinux`，可以完成源码/结构体核验，但必须把实际机器指令与动态地址记录为“未执行”。

## 4. 静态验证一：确认 inactive frame 的结构布局

在匹配 `vmlinux` 的 GDB 中：

```gdb
ptype /o struct inactive_task_frame
p sizeof(struct inactive_task_frame)
```

x86-64 v5.10 主线应得到七个 8-byte 字段，总大小 56 bytes，地址从低到高为：

```text
+0x00 r15
+0x08 r14
+0x10 r13
+0x18 r12
+0x20 bx
+0x28 bp
+0x30 ret_addr
```

不要只根据本文抄写结果；验收时保存当前 `vmlinux` 的 `ptype /o` 输出。如果编译配置或源码树不是目标版本，先停止并修正环境。

## 5. 静态验证二：反汇编 `__switch_to_asm`

先定位符号：

```bash
nm -n vmlinux | grep -E ' (__switch_to_asm|__switch_to|ret_from_fork)$'
```

再反汇编：

```bash
objdump -dr --no-show-raw-insn vmlinux \
  | sed -n '/<__switch_to_asm>:/,/^$/p'
```

也可以在 GDB 中：

```gdb
disassemble /r __switch_to_asm
```

必须实际确认以下顺序，而不是只搜索符号名：

```asm
pushq %rbp
pushq %rbx
pushq %r12
pushq %r13
pushq %r14
pushq %r15

movq %rsp, TASK_threadsp(%rdi)
movq TASK_threadsp(%rsi), %rsp

...

popq %r15
popq %r14
popq %r13
popq %r12
popq %rbx
popq %rbp
jmp __switch_to
```

具体指令间可能出现 `CONFIG_STACKPROTECTOR`、retpoline/CPU feature 相关代码；验收目标是确认保存、`thread.sp` store/load、恢复和 tail jump 的相对关系。

### 为什么 push 顺序与结构体字段顺序相反

`call __switch_to_asm` 已经在 prev 栈上留下 `ret_addr`。随后栈向低地址增长，依次 push `%rbp` 到 `%r15`。最终 `%rsp` 指向最后压入的 `%r15`，所以从低地址向高地址观察得到：

```text
r15 r14 r13 r12 rbx rbp ret_addr
```

这正是 `inactive_task_frame` 的内存顺序。

## 6. 动态验证一：在 `%rsp` 交换前后观察两个任务的栈

### 6.1 选择可重复切换的两个任务

在 guest 中启动两个只做轻量循环并周期性 `sched_yield()`/sleep 的测试进程，记录 PID。实验目的只是提高它们互相切换的概率，不要求修改调度策略。

### 6.2 根据实际反汇编设置断点

不要硬编码本文中的地址。先在当前 `vmlinux` 反汇编中定位：

```text
A: movq %rsp, TASK_threadsp(%rdi) 之前
B: movq TASK_threadsp(%rsi), %rsp 之后
C: 第一个 popq %r15 之前
D: jmp __switch_to 之前
```

在 kernel-GDB 中对这些实际地址设置断点。命中后先确认：

```gdb
p/x $rdi
p/x $rsi
p/x $rsp
```

`%rdi`/`%rsi` 分别是 `prev`/`next` task pointer。可结合调试信息读取：

```gdb
p ((struct task_struct *)$rdi)->pid
p ((struct task_struct *)$rsi)->pid
p/x ((struct task_struct *)$rdi)->thread.sp
p/x ((struct task_struct *)$rsi)->thread.sp
```

只记录目标 PID 对应的切换，避免把其他 CPU/任务的命中混入同一组数据。

### 6.3 在 store 后验证 prev->thread.sp

单步越过：

```asm
movq %rsp, TASK_threadsp(%rdi)
```

立即比较：

```gdb
p/x $rsp
p/x ((struct task_struct *)$rdi)->thread.sp
```

两者应相等。此时 `%rsp` 仍属于 prev 的 kernel stack，并指向 prev inactive frame 的 `r15` 槽。

进一步查看 7 个 qword：

```gdb
x/7gx $rsp
```

结合进入函数前记录的 callee-saved GPR 和 `ret_addr`，检查布局是否符合：

```text
[rsp+0x00] r15
[rsp+0x08] r14
[rsp+0x10] r13
[rsp+0x18] r12
[rsp+0x20] rbx
[rsp+0x28] rbp
[rsp+0x30] ret_addr
```

### 6.4 在 load 后验证 CPU 已换到 next 栈

单步越过：

```asm
movq TASK_threadsp(%rsi), %rsp
```

立即比较：

```gdb
p/x $rsp
p/x ((struct task_struct *)$rsi)->thread.sp
x/7gx $rsp
```

此时 `$rsp == next->thread.sp`。从这一条指令之后开始，`x/7gx $rsp` 看到的是 next 的 inactive frame；随后 `popq %r15 ... %rbp` 读取的也全部来自 next。

不要用“前后 `%rsp` 数值不同”作为唯一证据。至少同时确认：

```text
prev/next task pointer
prev->thread.sp
next->thread.sp
当前 %rsp
两个 stack 地址所属任务
```

## 7. 动态验证二：观察冻结和恢复的返回链

在 next 的 inactive frame 上记录：

```gdb
x/gx $rsp+0x30
info symbol *(unsigned long *)($rsp+0x30)
```

对于以前运行过的普通任务，这个 `ret_addr` 应属于它过去被切出时冻结的 `switch_to()` 调用返回链。执行完六个 pop 后，当前 `%rsp` 正好移到该返回地址；`jmp __switch_to` 不额外压入返回地址，因此 `__switch_to()` 最终 `ret` 会消费 next 栈中的这一地址。

可在 `__switch_to` 返回点附近结合 backtrace/反汇编观察，但不要假设跨过栈交换后 GDB 的普通 unwinder 一定能无条件给出完整调用链。上下文切换本身就是非普通 C 栈行为，必要时以原始 `%rsp`、frame 内容和符号地址为准。

## 8. 动态验证三：新任务的 `ret_from_fork`

新任务没有过去冻结的 `switch_to()` 调用。要验证首次切入：

1. 在 guest 中创建一个短生命周期子进程或内核线程；
2. 在其第一次被调度前，根据 fork 路径读取 `next->thread.sp`；
3. 查看该地址处的 `inactive_task_frame`；
4. 检查 `ret_addr` 是否解析到 `ret_from_fork`；
5. 继续执行并观察首次切入最终进入 `ret_from_fork`。

关键验收点不是某个固定虚拟地址，而是：

```text
普通恢复：ret_addr 来自过去冻结的调用链
首次运行：ret_addr 来自 fork 路径预构造，并导向 ret_from_fork
```

KASLR、编译配置和符号布局都会改变具体地址，因此必须使用当前 `vmlinux` 解析。

## 9. RFLAGS 的观察边界

本实验不要期待在 `inactive_task_frame` 中找到 RFLAGS。Linux 5.10 x86-64 这条主线没有用 `pushfq/popfq` 把 RFLAGS 作为 inactive frame 字段保存。

这并不表示“任务切换不需要任何 CPU 状态管理”，而只说明第一部分讨论的最小 frame 是 callee-saved GPR + 返回控制流。FS/GS、TLS、FPU 等属于后续 A17 单元；中断/异常返回 frame 中的 RFLAGS 则属于 A14/A15 的另一种入口/返回模型。

## 10. 可选 ftrace 交叉验证

如果 guest 的 tracing 配置允许，可使用 function/function_graph tracer 观察 `context_switch`、`__switch_to` 等 C 侧事件，或结合 `sched:sched_switch` tracepoint 确认 PID 切换顺序。

tracepoint 可以证明“哪个任务切到哪个任务”，但不能单独证明 `%rsp = next->thread.sp` 的具体机器级事实；后者仍以反汇编和 kernel-GDB 现场为主。

## 11. 结果记录模板

```text
Kernel: Linux 5.10.x
vmlinux Build ID:
CONFIG_STACKPROTECTOR:
retpoline/RSB related config/features:

inactive_task_frame sizeof:
r15 offset:
r14 offset:
r13 offset:
r12 offset:
bx offset:
bp offset:
ret_addr offset:

prev pid:
next pid:
RSP before prev thread.sp store:
prev->thread.sp after store:
next->thread.sp before load:
RSP after next thread.sp load:

next inactive frame ret_addr:
ret_addr symbol:
normal-resume or first-run:

Static disassembly executed: yes/no
Kernel-GDB stack-switch observation executed: yes/no
ret_from_fork first-run observation executed: yes/no
Unexecuted reason:
```

## 12. 当前实验的验收标准

完成实验后应能够用实际输出说明：

- `inactive_task_frame` 是 7 个 64-bit 槽，字段顺序与汇编保存/恢复一致；
- `prev->thread.sp` 等于保存 prev frame 后的 `%rsp`；
- `next->thread.sp` 被直接装入 CPU `%rsp`，不是复制内核栈；
- 栈交换后的 pop 来自 next frame；
- `jmp __switch_to` 不创建新的返回地址层；
- 普通 next 恢复历史冻结调用，新任务则通过预构造 frame 进入 `ret_from_fork`；
- RFLAGS 不属于该 inactive frame；
- 配置附加代码不能被误认为基本栈交换机制。

当前维护环境如果没有匹配 Linux 5.10 `vmlinux`/kernel-GDB guest，必须明确把动态地址、PID、`%rsp` 和 `ret_from_fork` 现场留为待实测；不得用预期值填充结果。
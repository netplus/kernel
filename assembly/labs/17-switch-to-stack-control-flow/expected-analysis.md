# A17 实验预期分析：`switch_to` 的 inactive frame、栈交换与控制流恢复

本文是 A17 第一部分实验的验收基线。它描述 Linux 5.10 x86-64 在匹配源码、配置和 `vmlinux` 时应满足的结构关系，不把尚未执行的 kernel-GDB 地址、PID 或寄存器值写成实测结果。

## 1. inactive frame 布局

Linux 5.10 x86-64 的 `struct inactive_task_frame` 有 7 个 64-bit 槽，总大小 56 bytes：

```text
+0x00 r15
+0x08 r14
+0x10 r13
+0x18 r12
+0x20 bx
+0x28 bp
+0x30 ret_addr
```

进入 `__switch_to_asm` 时，调用者已经在 prev 的 kernel stack 上留下返回地址。随后代码依次保存 `%rbp/%rbx/%r12/%r13/%r14/%r15`。由于栈向低地址增长，最终 `%rsp` 指向 `%r15`，所以从低地址向高地址正好得到上述字段顺序。

验收时应以当前 `vmlinux` 的 DWARF 和反汇编为准；如果不一致，先检查版本、架构和配置。

## 2. `prev->thread.sp` 的保存时刻

关键顺序是：

```text
保存 prev callee-saved GPR
-> %rsp 指向 prev inactive frame 起点
-> prev->thread.sp = %rsp
-> %rsp = next->thread.sp
```

因此在保存 `thread.sp` 后、装入 next 栈之前，应有 `$rsp == prev->thread.sp`，而且该地址仍属于 prev kernel stack。六次 push 共使 `%rsp` 下降 48 bytes，所以不能拿进入 `__switch_to_asm` 之前的 `%rsp` 与 `thread.sp` 比较。

## 3. `%rsp = next->thread.sp` 是任务栈边界

装入 next 的 `thread.sp` 后，应有 `$rsp == next->thread.sp`。从此开始，后续六次 pop 读取的是 next inactive frame，而不是刚刚写入 prev 栈的值。

一次完整观察应至少记录 prev、next、两个 `thread.sp` 与 CPU `%rsp`。仅看到 `%rsp` 数值变化不能证明栈归属正确。

推荐按四个时刻记录：

| 时刻 | `%rsp` 所属任务 | 含义 |
| --- | --- | --- |
| 六次 push 完成 | prev | prev frame 起点 |
| 保存 `prev->thread.sp` 后 | prev | 与 `prev->thread.sp` 相等 |
| 装入 `next->thread.sp` 后 | next | next frame 起点 |
| 六次 pop 完成 | next | 指向 next 的 `ret_addr` |

## 4. `jmp __switch_to` 与返回地址

恢复 GPR 后使用 tail jump 进入 `__switch_to(prev, next)`。`jmp` 不会像 `call` 一样在当前 next 栈再压入返回地址，因此 `__switch_to()` 最终返回时消费的是 next inactive frame 中原有的 `ret_addr`。

若把这里误解为普通 `call __switch_to`，就会多出一个返回地址层，与实际 frame 布局不符。

## 5. 普通任务恢复

对以前运行过的 next，它过去被切出时已经在自己的 kernel stack 上冻结了一次尚未完成的 `switch_to()` 调用。以后重新切回时：

```text
保存当前 prev
-> 装入 next 历史 thread.sp
-> 恢复 next frame
-> 完成 next 自己过去被冻结的 switch_to 调用
```

所以“旧任务调用、从新任务返回”只能作为简写；next 并不是从 prev 的 C 调用栈返回。

动态验收时，普通 next 的 `ret_addr` 应解析到与其历史调度调用链一致的位置。具体地址受 KASLR、编译器和配置影响，不设固定值。

## 6. 新任务首次运行

新任务没有历史 `switch_to()` 调用。fork 路径会预构造 inactive frame，使它第一次被调度时仍复用相同的 `%rsp` 交换和 GPR 恢复机制，但预构造的 `ret_addr` 应把首次执行导向 `ret_from_fork`。

因此普通恢复与首次运行的关键差异是 `ret_addr` 的来源，而不是栈交换机制不同。

## 7. RFLAGS 边界

`inactive_task_frame` 中没有 RFLAGS，本主线也没有用 `pushfq/popfq` 把 RFLAGS 保存为该 frame 的字段。这只说明本实验讨论的最小 inactive frame 是 callee-saved GPR 加返回控制流，不能推出“Linux 不关心其他 CPU 状态”或“该 frame 是完整寄存器快照”。

## 8. 配置相关代码

实际 `__switch_to_asm` 可能包含 stack protector、retpoline/RSB 等配置或 CPU feature 相关指令。它们可以改变反汇编细节，但第一部分的基本不变量仍应是：

```text
保存 prev GPR
prev->thread.sp = frame 起点
%rsp = next->thread.sp
恢复 next GPR
tail jump 到 __switch_to
```

验收时应记录实际配置和机器指令，不应把配置附加代码误认为基本栈交换机制。

## 9. 静态证据与动态证据

静态证据至少包括：当前 `vmlinux` 的 `inactive_task_frame` 字段偏移、`__switch_to_asm` 反汇编、`TASK_threadsp` store/load，以及 `ret_from_fork` 符号。

动态证据至少包括：store 后 `$rsp == prev->thread.sp`，load 后 `$rsp == next->thread.sp`，两个地址分别属于对应任务 kernel stack，以及普通恢复与首次运行时 `ret_addr` 来源不同。

`sched_switch` tracepoint 可以证明任务切换顺序，但不能单独证明机器级 `%rsp` 的 store/load；静态反汇编也不能替代一次真实切换的寄存器现场。

## 10. 当前环境未执行项

如果维护环境没有匹配 Linux 5.10 guest、带符号 `vmlinux` 和 kernel-GDB 会话，则以下项目保持待实测：具体 prev/next PID、kernel stack 地址、store/load 前后 `%rsp`、普通恢复 `ret_addr` 的实际符号，以及新任务进入 `ret_from_fork` 的动态现场。

这些值不得从预期模型推导后写成实验结果。

## 11. 最终验收问题

完成实验后，应能用当前 Linux 5.10 构建的实际证据解释：

1. 六次 push 如何形成 `r15 ... bp` 的内存顺序；
2. 为什么 frame 总大小为 56 bytes；
3. `prev->thread.sp` 保存的是哪个时刻的 `%rsp`；
4. 哪条指令使 CPU 从 prev kernel stack 切到 next kernel stack；
5. 为什么之后的 pop 恢复 next；
6. 为什么 `jmp __switch_to` 不增加返回地址层；
7. 普通任务的 `ret_addr` 从哪里来；
8. 新任务为什么通过预构造 frame 进入 `ret_from_fork`；
9. 为什么 RFLAGS 不属于本实验的 inactive frame；
10. 哪些结论来自静态核验，哪些仍需要真实 kernel-GDB 现场。

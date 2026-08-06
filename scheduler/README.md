# Linux Kernel 5.10 调度基础

本目录学习任务如何进入运行队列、如何被选中运行，以及何时发生阻塞、唤醒、抢占和上下文切换。

## 学习目标

完成本部分后，应能够沿 Linux 5.10 源码说明：

```text
任务进入可运行状态
→ 加入运行队列
→ 调度器选择任务
→ 任务在 CPU 上运行
→ 任务阻塞、被抢占或主动让出 CPU
→ 上下文切换
→ 任务再次被唤醒和调度
```

本阶段重点研究调度器的基本工作过程。CPU cgroup、调度组带宽控制和更复杂的资源隔离不在本阶段展开。

## 课程大纲

### S00：任务和调度问题

- 进程、线程与 `task_struct`；
- running、runnable、sleeping；
- 任务状态；
- CPU-bound 与 I/O-bound；
- 调度器需要处理的公平性、响应时间和优先级问题。

### S01：调度器总体结构

- 每 CPU 运行队列 `struct rq`；
- `sched_class`；
- fair、rt、deadline、idle 等调度类；
- `schedule()` 和 `__schedule()`；
- 调度类之间的选择顺序。

### S02：CFS 的基本模型

- `nice` 与权重；
- `vruntime`；
- `min_vruntime`；
- Linux 5.10 中的红黑树；
- 为什么选择最左侧任务；
- 公平运行时间如何转换为虚拟运行时间。

### S03：任务入队、出队和运行时间统计

- `enqueue_task_fair()`；
- `dequeue_task_fair()`；
- `update_curr()`；
- `exec_start`；
- `sum_exec_runtime`；
- 运行时间与 `sched_clock()` 的关系。

### S04：任务睡眠和唤醒

核心路径：

```text
任务设置睡眠状态
→ schedule
→ 事件发生
→ wake_up_process
→ try_to_wake_up
→ 选择目标 CPU
→ 加入运行队列
→ 检查是否需要抢占
```

重点包括：

- 为什么修改任务状态和进入调度必须按规定顺序完成；
- 等待队列的基本作用；
- 跨 CPU 唤醒；
- 唤醒时的并发和内存屏障；
- 唤醒不等于立即运行。

### S05：抢占和执行上下文

- `TIF_NEED_RESCHED`；
- 主动调度和被动抢占；
- 用户态返回前的调度检查；
- 内核抢占；
- preempt count；
- hardirq、softirq 和 NMI 上下文对调度的限制。

### S06：时钟 Tick 如何推动调度

- `scheduler_tick()`；
- `task_tick_fair()`；
- 运行时间更新；
- 设置重新调度标志；
- tickless 系统中的调度；
- 与 [`timekeeping/`](../timekeeping/) 的关系。

### S07：上下文切换

核心路径：

```text
schedule
→ __schedule
→ context_switch
→ switch_mm_irqs_off
→ switch_to
→ __switch_to_asm
→ __switch_to
```

重点包括：

- 保存旧任务和恢复新任务；
- 内核栈切换；
- callee-saved 寄存器；
- 地址空间切换；
- FS/GS、TLS 和扩展处理器状态；
- 为什么切换栈后，后续代码已经属于另一个任务。

### S08：多核系统中的任务迁移

- 调度域和调度组；
- 周期性负载均衡；
- idle balance；
- CPU capacity；
- cache affinity；
- 任务迁移的收益和代价。

### S09：其他调度类概览

- `SCHED_FIFO`；
- `SCHED_RR`；
- Deadline 调度的 runtime、deadline 和 period；
- 不同调度类为何需要不同的任务选择规则；
- 本阶段只建立总体认识，不深入资源配额和带宽控制。

### S10：调度观测和故障分析

- `/proc/sched_debug`；
- `/proc/<pid>/sched`；
- sched tracepoints；
- `perf sched`；
- ftrace；
- runqueue latency；
- soft lockup；
- hung task；
- crash 中查看任务、运行队列和调用栈。

## 推荐源码入口

```text
kernel/sched/core.c
kernel/sched/fair.c
kernel/sched/rt.c
kernel/sched/deadline.c
kernel/sched/sched.h
arch/x86/include/asm/switch_to.h
arch/x86/entry/entry_64.S
arch/x86/kernel/process_64.c
```

## 推荐实验

```text
观察不同 nice 值任务的运行时间
跟踪一次任务睡眠和唤醒
使用 tracepoint 观察 sched_switch
使用 perf sched 观察调度延迟
用 GDB 或 crash 分析一次上下文切换现场
构造 CPU-bound 与周期睡眠任务并比较行为
```

## 与其他主题的关系

- 汇编：寄存器保存、内核栈和 `switch_to`；
- 时钟：运行时间、tick 和重新调度；
- 内存：任务地址空间、内核栈和缺页阻塞；
- 启动：调度器初始化和第一个内核线程。

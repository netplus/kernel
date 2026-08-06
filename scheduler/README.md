# Linux Kernel 5.10 调度子系统课程

本目录研究“谁在 CPU 上运行、运行多久、何时切换、如何唤醒和迁移”。

## 学习目标

完成本维度后，应能够沿 Linux 5.10 源码解释：

```text
任务创建或唤醒
→ 进入运行队列
→ 选择下一个任务
→ 上下文切换
→ 运行时间统计
→ 抢占或阻塞
→ 再次调度
```

## 课程大纲

### S00：调度问题背景与任务模型

- 进程、线程和 `task_struct`；
- task state；
- runnable、running、sleeping；
- CPU-bound 与 I/O-bound；
- 调度策略、优先级和公平性的基本矛盾。

### S01：调度器总体架构

- 每 CPU `struct rq`；
- `sched_class`；
- stop、deadline、rt、fair、idle 的类层次；
- `schedule()`、`__schedule()`；
- 为什么调度器采用分层策略接口。

### S02：CFS 基本模型

- `nice`、weight；
- `vruntime`；
- `min_vruntime`；
- Linux 5.10 CFS 红黑树；
- 选择最左任务；
- 时间片为什么不是固定常量。

### S03：任务入队、出队与运行时间统计

- `enqueue_task_fair`；
- `dequeue_task_fair`；
- `update_curr`；
- `exec_start`、`sum_exec_runtime`；
- 时间统计与 timekeeping/scheduler clock 的关系。

### S04：唤醒路径

核心路径：

```text
wake_up_process
→ try_to_wake_up
→ select_task_rq
→ ttwu_queue
→ enqueue_task
→ check_preempt_curr
```

重点：

- 睡眠与唤醒的并发关系；
- task state 检查；
- 跨 CPU 唤醒；
- wakeup preemption；
- 内存屏障为何重要。

### S05：抢占模型

- voluntary preemption；
- `TIF_NEED_RESCHED`；
- kernel preemption；
- preempt count；
- hardirq、softirq、NMI 上下文；
- 用户态返回和中断返回时的调度检查。

### S06：调度时钟与周期性更新

- `scheduler_tick()`；
- `task_tick_fair()`；
- tick 与抢占；
- tickless 系统中的调度；
- 与 [`timekeeping/`](../timekeeping/) 的交叉关系。

### S07：上下文切换

核心路径：

```text
schedule
→ context_switch
→ switch_mm_irqs_off
→ switch_to
→ __switch_to_asm
→ __switch_to
```

重点：

- 保存和恢复 callee-saved 寄存器；
- 切换内核栈；
- `RSP` 为什么决定当前执行任务；
- 地址空间、TLS、FS/GS、FPU 状态；
- 与 [`assembly/`](../assembly/) 的交叉关系。

### S08：SMP 负载均衡

- scheduler domain；
- scheduling group；
- CPU capacity；
- periodic balance；
- idle balance；
- task migration；
- cache affinity 与公平性的权衡。

### S09：实时调度

- `SCHED_FIFO`；
- `SCHED_RR`；
- RT runqueue；
- 优先级抢占；
- RT throttling；
- priority inversion 与 PI mutex。

### S10：Deadline 调度

- runtime、deadline、period；
- EDF 与 CBS；
- admission control；
- deadline bandwidth。

### S11：调度组与 CPU cgroup

- task group；
- group scheduling；
- CFS bandwidth；
- quota、period、throttling；
- cgroup v1/v2 的接口联系。

### S12：调度观测与故障分析

- `/proc/sched_debug`；
- `/proc/<pid>/sched`；
- `perf sched`；
- ftrace sched events；
- runqueue latency；
- soft lockup、RCU stall、任务夯死；
- crash 中查看任务和运行队列。

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
观察不同 nice 值的 CPU 分配
跟踪 sleep/wakeup
使用 perf sched 观察调度延迟
使用 ftrace 还原一次上下文切换
分析 CPU cgroup throttling
构造 CPU-bound 与 I/O-bound 混合负载
```

## 与其他维度的关系

- 汇编：上下文切换、内核入口和寄存器保存；
- 时钟：运行时间统计、tick 和 hrtimer；
- 内存：任务内核栈、地址空间与 NUMA；
- 网络：socket 唤醒、softirq 与用户任务调度。
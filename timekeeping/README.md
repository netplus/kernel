# Linux Kernel 5.10 时钟、定时器与 Tick 课程

本目录研究“内核如何知道现在几点、经过了多久，以及如何在未来某个时刻触发事件”。

## 先区分三个问题

```text
时间读取：现在是什么时间？经过了多久？
事件产生：何时让 CPU 收到下一次时钟事件？
延迟执行：某个回调应在何时运行？
```

它们分别对应 clocksource、clock event device、timer/hrtimer 等不同机制。

## 课程大纲

### T00：时间子系统全景

- wall clock、monotonic time、boottime、raw time；
- jiffies、ktime、纳秒时间；
- 硬件时钟与软件时间；
- 为什么“读时间”和“产生中断”必须分离。

### T01：x86 硬件时间基础

- TSC；
- invariant/constant TSC；
- HPET；
- PIT；
- RTC；
- local APIC timer；
- 虚拟机中的 paravirtual clock。

### T02：Clocksource

- `struct clocksource`；
- cycle counter；
- mask、mult、shift；
- cycle 到纳秒转换；
- clocksource rating 与选择；
- watchdog；
- TSC 不稳定问题。

### T03：Timekeeper 与时间读取

- `struct timekeeper`；
- seqlock/seqcount；
- `ktime_get*()`；
- `do_gettimeofday` 的历史关系；
- wall time 与 monotonic offset；
- vDSO 为什么能在用户态快速读时间。

### T04：Clock Event Device

- `struct clock_event_device`；
- periodic 与 oneshot；
- next event 编程；
- local APIC timer；
- clockevent 与 clocksource 的职责区别。

### T05：Tick 基础

- `HZ`；
- jiffies；
- periodic tick；
- `tick_handle_periodic`；
- timekeeping 更新；
- scheduler tick；
- process accounting。

### T06：Dynamic Tick 与 NO_HZ

- oneshot mode；
- `NO_HZ_IDLE`；
- `NO_HZ_FULL`；
- tick stop 条件；
- 下一事件计算；
- tickless 对调度、RCU 和性能分析的影响。

### T07：低精度 Timer Wheel

- `struct timer_list`；
- timer wheel；
- bucket 分层；
- `add_timer`、`mod_timer`、`del_timer_sync`；
- timer callback 执行上下文；
- 并发删除与生命周期问题。

### T08：High Resolution Timer

- `struct hrtimer`；
- 红黑树；
- absolute 与 relative mode；
- soft/hard hrtimer；
- hrtimer interrupt；
- 高精度定时器与 clockevent 重新编程。

### T09：Scheduler Clock

- `sched_clock()`；
- 每 CPU 时间；
- 调度统计为何不总能直接使用 wall clock；
- 不同 CPU 时钟同步；
- 与 [`scheduler/`](../scheduler/) 的联系。

### T10：用户态时间与 POSIX Timer

- `clock_gettime`；
- nanosleep；
- interval timer；
- POSIX timer；
- timerfd；
- signal delivery；
- syscall、vDSO 与内核定时器路径。

### T11：网络协议中的时间

- TCP retransmission timer；
- delayed ACK；
- keepalive；
- TIME_WAIT；
- qdisc watchdog；
- NAPI busy polling 的时间边界；
- 与 [`network/`](../network/) 的交叉关系。

### T12：时钟故障与观测

- `/proc/timer_list`；
- clocksource sysfs；
- ftrace timer events；
- timer callback 延迟；
- time jump；
- TSC unstable；
- soft lockup 与 watchdog；
- 虚拟机 steal time。

## 推荐源码入口

```text
kernel/time/timekeeping.c
kernel/time/clocksource.c
kernel/time/clockevents.c
kernel/time/tick-common.c
kernel/time/tick-sched.c
kernel/time/timer.c
kernel/time/hrtimer.c
kernel/sched/clock.c
arch/x86/kernel/tsc.c
arch/x86/kernel/apic/apic.c
```

## 推荐实验

```text
比较 CLOCK_REALTIME 与 CLOCK_MONOTONIC
读取和切换可用 clocksource
观察 /proc/timer_list
编写 timerfd 与 nanosleep 示例
用 ftrace 跟踪 hrtimer callback
观察 NO_HZ idle 下 tick 停止
关联一次 scheduler_tick 与任务抢占
```

## 与其他维度的关系

- 汇编：时钟中断入口、TSC 指令与 vDSO；
- 调度：运行时间统计、周期 tick、抢占与带宽控制；
- 内存：timer 对象生命周期和并发释放；
- 网络：重传、保活、超时和 qdisc 定时。
# Linux Kernel 5.10 时钟和定时器基础

本目录学习内核如何读取时间、如何安排下一次时钟事件，以及如何在将来某个时刻执行定时回调。

## 先区分三个问题

```text
时间读取：现在是什么时间？已经经过了多久？
事件产生：何时让 CPU 收到下一次时钟事件？
延迟执行：某个回调应在什么时候运行？
```

它们分别由 clocksource、clock event device、timer 和 hrtimer 等机制完成。

本阶段重点研究时间子系统的基础结构，不系统展开 POSIX timer、网络协议定时器和其他上层接口。

## 课程大纲

### T00：时间子系统概览

- wall clock；
- monotonic time；
- boottime；
- raw time；
- jiffies 与纳秒时间；
- 硬件计数器与软件时间；
- 为什么时间读取和时钟事件需要分开处理。

### T01：x86 时间硬件基础

- TSC；
- constant TSC 与 invariant TSC；
- HPET；
- PIT；
- RTC；
- local APIC timer；
- 虚拟机中的时钟来源。

### T02：Clocksource

- `struct clocksource`；
- cycle counter；
- mask、mult 和 shift；
- cycle 到纳秒的转换；
- clocksource rating；
- clocksource 选择；
- watchdog；
- TSC 不稳定问题。

### T03：Timekeeper 和时间读取

- `struct timekeeper`；
- `ktime_get*()`；
- wall time 与 monotonic time；
- seqcount 保护；
- 时间更新和时间读取如何并发；
- vDSO 快速读时间只作必要说明。

### T04：Clock Event Device

- `struct clock_event_device`；
- periodic 模式；
- oneshot 模式；
- next event 编程；
- local APIC timer；
- clockevent 与 clocksource 的职责区别。

### T05：周期 Tick

- `HZ`；
- jiffies；
- `tick_handle_periodic()`；
- 时间更新；
- process accounting；
- `scheduler_tick()`；
- 一个周期 tick 中依次完成哪些工作。

### T06：Dynamic Tick 和 NO_HZ

- oneshot mode；
- `NO_HZ_IDLE`；
- `NO_HZ_FULL` 的基本含义；
- 停止 tick 的条件；
- 下一事件的计算；
- tick 停止后，时间和调度如何继续正确工作。

### T07：低精度 Timer

- `struct timer_list`；
- timer wheel；
- `add_timer()`；
- `mod_timer()`；
- `del_timer_sync()`；
- timer callback 的执行上下文；
- 删除定时器和对象生命周期之间的关系。

### T08：高精度 Hrtimer

- `struct hrtimer`；
- 红黑树；
- absolute 与 relative；
- hrtimer interrupt；
- 高精度定时器如何重新设置 clockevent；
- hrtimer callback 的执行限制。

### T09：Scheduler Clock

- `sched_clock()`；
- 每 CPU 时间；
- 调度统计为何不能简单使用 wall clock；
- 多 CPU 时钟同步问题；
- 与 [`scheduler/`](../scheduler/) 的关系。

### T10：时钟观测和故障分析

- `/proc/timer_list`；
- clocksource sysfs；
- timer 和 hrtimer tracepoints；
- timer callback 延迟；
- time jump；
- TSC unstable；
- soft lockup watchdog；
- 虚拟机中的 steal time 和时钟异常。

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
查看当前 clocksource
观察 /proc/timer_list
用 ftrace 跟踪 timer 和 hrtimer 回调
观察 NO_HZ idle 下 tick 的停止和恢复
关联一次 local APIC timer 中断与 scheduler_tick
```

## 与其他主题的关系

- 汇编：TSC 指令和时钟中断入口；
- 调度：运行时间统计、tick 和抢占；
- 内存：定时器对象的生命周期；
- 启动：时钟源、时钟事件设备和 tick 的初始化。

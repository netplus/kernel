# Linux Kernel 5.10 跨子系统执行链

本目录用于分析跨越多个内核子系统的完整执行过程。各专题会引用汇编、调度、时钟、内存、网络以及启动与崩溃转储课程中的基础知识。

## 为什么需要综合路径

真实内核问题很少只属于一个目录。例如一次 TCP 收包可能同时涉及：

```text
网卡 DMA
→ hardirq
→ NAPI
→ softirq
→ skb 分配
→ TCP timer
→ socket wait queue
→ 任务唤醒
→ 调度运行
```

如果只按单一子系统阅读，容易理解局部函数，却难以说明完整过程为何这样运行。因此，本目录重点分析执行上下文、数据对象、时间顺序和子系统之间的交接关系。

## 综合课程大纲

### I01：用户系统调用完整路径

```text
用户函数
→ libc wrapper
→ syscall instruction
→ entry_SYSCALL_64
→ pt_regs
→ do_syscall_64
→ __x64_sys_xxx
→ exit to user mode
```

关联：assembly、scheduler、memory。

### I02：时钟中断驱动调度

```text
local APIC timer
→ interrupt entry
→ tick handler
→ scheduler_tick
→ task_tick
→ TIF_NEED_RESCHED
→ return path / preempt
→ schedule
→ switch_to
```

关联：assembly、timekeeping、scheduler。

### I03：任务睡眠与唤醒

```text
任务检查条件
→ prepare_to_wait
→ set task state
→ schedule
→ 事件发生
→ wake_up
→ try_to_wake_up
→ enqueue
→ preemption decision
```

关联：scheduler、memory ordering、wait queue。

### I04：缺页异常完整路径

```text
用户内存访问
→ page-table walk failure
→ #PF
→ exception entry
→ CR2/error code
→ VMA lookup
→ anonymous/file/COW fault
→ page allocation
→ page-table update
→ return and retry
```

关联：assembly、memory、scheduler。

### I05：Fork 与首次写入

```text
fork
→ 复制 mm/VMA
→ 共享只读 PTE
→ child/parent write
→ COW fault
→ allocate/copy page
→ update PTE
```

关联：memory、scheduler、TLB。

### I06：网络收包到用户进程

```text
NIC DMA
→ IRQ
→ NAPI
→ NET_RX_SOFTIRQ
→ skb
→ IP/TCP
→ socket receive queue
→ wake_up_interruptible
→ try_to_wake_up
→ scheduler
→ recv/read returns
```

关联：network、memory、timekeeping、scheduler、assembly。

### I07：用户发送到网卡

```text
send/write
→ syscall
→ socket send
→ TCP/IP
→ neighbour
→ qdisc
→ driver TX ring
→ DMA
→ completion interrupt
→ skb free
```

关联：network、memory、timekeeping。

### I08：TCP 重传

```text
send queue
→ retransmission timer armed
→ timer expires
→ TCP write timer
→ loss/retransmission decision
→ packet retransmit
→ congestion control update
```

关联：network、timekeeping、memory。

### I09：内存压力影响网络与调度

```text
skb/page allocation
→ allocator slow path
→ direct reclaim/compaction
→ task latency increase
→ packet backlog
→ softirq pressure
→ drops or retransmission
```

关联：memory、network、scheduler、timekeeping。

### I10：Softirq 过载与 ksoftirqd

```text
hardirq schedules NAPI
→ softirq budget/time limit
→ remaining work deferred
→ wake ksoftirqd
→ scheduler chooses ksoftirqd
→ process-context softirq work
```

关联：network、scheduler、timekeeping。

### I11：上下文切换与地址空间切换

```text
schedule
→ context_switch
→ switch_mm
→ CR3/PCID decision
→ switch_to
→ kernel stack and registers restored
```

关联：assembly、scheduler、memory。

### I12：从内核崩溃到 Vmcore 分析

```text
fault/oops/watchdog
→ panic
→ crash_kexec
→ machine_crash_shutdown
→ Kexec 过渡代码
→ 捕获内核启动
→ elfcorehdr
→ /proc/vmcore
→ makedumpfile
→ crash
→ 根因路径还原
```

本专题重点分析：

- 生产内核和捕获内核的职责；
- `crashkernel=` 保留内存如何建立；
- panic 环境中如何保存 CPU 状态并停止其他 CPU；
- 捕获内核为什么不能覆盖生产内核留下的物理内存；
- `/proc/vmcore`、`VMCOREINFO` 和 ELF program header 的作用；
- `vmcore` 与匹配的 `vmlinux`、模块符号和 Build ID；
- 调用栈展开、故障指令定位和关键对象检查；
- Kdump 失败时如何判断问题发生在哪个阶段。

关联：boot-crash、assembly、memory、scheduler、timekeeping，以及具体故障所属的子系统。

基础课程见：[`../boot-crash/`](../boot-crash/)。

## 每个综合专题的固定产物

```text
01-background.md        问题背景和总体机制
02-call-path.md         完整调用链
03-data-structures.md   关键数据结构与字段
04-context.md           process/softirq/hardirq/NMI 上下文
05-timeline.md          时间顺序和并发关系
06-source-walk.md       Linux 5.10 源码逐层分析
07-lab.md               可复现实验
08-debugging.md         ftrace/perf/eBPF/crash 观测方法
```

## 建议使用方式

先在各主题中完成相关基础章节，再进入综合路径。例如学习网络收包到用户进程前，至少应掌握：

```text
assembly：寄存器、栈、异常和中断入口基础
scheduler：task state、wake-up、schedule
memory：page、SLUB、skb 内存基础
timekeeping：tick、timer 基础
network：NAPI、skb、IP/TCP、socket
```

学习 Kdump 综合路径前，建议先掌握：

```text
assembly：早期入口、寄存器、栈和控制流
memory：物理内存、页表和 memblock
boot-crash：正常启动、Kexec、双内核和 vmcore
scheduler：CPU、任务和多核停止基础
```

综合路径的目标不是记住更长的调用链，而是能够解释：

```text
当前在哪种执行上下文？
数据对象由谁拥有？
何时可能睡眠或抢占？
哪个时钟或定时器推动事件？
内存从哪里分配和释放？
下一阶段为何被唤醒？
故障发生后哪些内核服务仍然可信？
```

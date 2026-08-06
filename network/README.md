# Linux Kernel 5.10 网络协议栈（后续专题）

网络协议栈不属于当前“内核基础机制”学习阶段。本阶段先完成汇编、x86_64 启动、内存管理、时钟、调度、Kexec、Kdump 和 vmcore 分析。

这些基础内容完成后，再单独学习网络协议栈。这样在分析中断、NAPI、softirq、`sk_buff`、TCP 定时器和 socket 唤醒时，已经具备所需的执行上下文、内存、时间和调度知识。

已经整理的网络课程规划保存在：

[`course-outline.md`](course-outline.md)

当前阶段不会继续扩展本目录，也不会把 network namespace、cgroup、Netfilter、traffic control 或 eBPF 纳入基础课程主线。

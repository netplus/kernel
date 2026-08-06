# Linux Kernel 5.10 系统学习仓库

本仓库用于系统学习 Linux kernel 5.10。课程不再按一条超长线性目录组织，而是按“能力维度 + 内核子系统维度 + 综合执行链”组织。

## 目录地图

```text
kernel/
├── assembly/           x86-64 汇编、ABI、ELF、内核入口
├── scheduler/          调度器、抢占、唤醒、负载均衡、上下文切换
├── timekeeping/        时钟源、时钟事件、tick、timer、hrtimer、NO_HZ
├── memory/             页表、memblock、伙伴系统、SLUB、缺页、回收、NUMA
├── network/            Linux 5.10 网络协议栈主线
└── integrated-paths/   跨子系统执行链与综合案例
```

每个维度内部统一采用：

```text
README.md               该维度的完整课程地图

docs/                   分章节教程
labs/                   可复现实验、脚本和调试记录
source-paths/           Linux 5.10 源码路径、调用链和关键数据结构
```

## 为什么按维度组织

汇编、调度、时钟、内存和网络不是互相独立的知识：

- 汇编解释寄存器、栈、异常入口和上下文切换的底层动作；
- 调度依赖时钟统计运行时间，并通过中断和抢占触发切换；
- 内存管理为任务、内核栈、页表、网络报文和 DMA 提供存储；
- 网络收包依赖中断、NAPI、softirq、内存分配、定时器和调度；
- 一个真实问题往往同时跨越多个子系统。

因此，本仓库采用两种阅读方式。

### 方式一：按维度纵向学习

```text
assembly → scheduler → timekeeping → memory → network
```

适合系统建立每个子系统的完整认识。

### 方式二：按执行链横向学习

例如：

```text
系统调用：用户态 → syscall entry → 内核函数 → 返回用户态

调度切换：时钟中断 → scheduler tick → 设置抢占标志 → schedule → switch_to

缺页异常：内存访问 → #PF → page fault entry → VMA → 页表建立或信号

网络收包：网卡 IRQ → NAPI → softirq → skb → IP/TCP → socket 唤醒 → 任务调度
```

跨子系统路径统一放在 [`integrated-paths/`](integrated-paths/) 中。

## 学习层次

每一章尽量同时服务不同基础的学习者：

```text
主线：先讲清楚是什么、解决什么问题。
原理：解释为什么采用这种设计。
源码：定位 Linux 5.10 的具体实现。
实验：通过命令、代码、objdump、GDB、ftrace、perf 或 crash 验证。
进阶：讨论性能、并发、安全、边界条件和版本差异。
关联：提示与其他子系统的连接，但不打断当前主线。
```

## 推荐总体顺序

### 第一阶段：机器执行基础

学习 [`assembly/`](assembly/) 的寄存器、取址、标志位、算术、控制流、栈和 ABI。

### 第二阶段：内核运行基础

并行学习：

- [`scheduler/`](scheduler/)：任务为什么运行、停止、唤醒和迁移；
- [`timekeeping/`](timekeeping/)：内核如何感知时间、产生事件和驱动调度；
- [`memory/`](memory/)：地址如何映射，物理页如何分配和回收。

### 第三阶段：网络协议栈

进入 [`network/`](network/)，把中断、softirq、内存、定时器和调度知识带入收发包路径。

### 第四阶段：综合执行链

通过 [`integrated-paths/`](integrated-paths/) 完成系统调用、调度、缺页、网络收包、崩溃分析等综合专题。

## 统一源码基线

```text
Linux kernel 5.10
架构：x86-64
汇编器：GNU assembler
主要汇编语法：AT&T
用户态 ABI：System V AMD64 ABI
```

后续涉及其他内核版本时，会先以 5.10 建立机制，再单独说明版本差异。
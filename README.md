# Linux Kernel 课程与专题学习

这个仓库用于系统学习 Linux 内核中最基础、最重要的运行机制，并在基础课程之外逐步扩展网络等专题。

现有基础课程已经按 **Linux kernel 5.10** 建立并核验；新启用的 [`network/`](network/) 专题按其目录规则使用 **upstream Linux v6.12**。不同版本的实现不能混写成同一条调用路径，也不能通过机械替换版本号宣称已经完成迁移。

## 基础课程目录

```text
kernel/
├── assembly/           x86-64 指令、栈、ABI、系统调用和异常入口
├── boot-crash/         x86_64 启动、Kexec、Kdump、双内核和 vmcore
├── memory/             页表、memblock、伙伴系统、SLUB、缺页和回收
├── timekeeping/        clocksource、clockevent、tick、timer 和 hrtimer
├── scheduler/          任务、运行队列、唤醒、抢占和上下文切换
├── integrated-paths/   将上述机制串联成完整执行过程
└── network/            Linux 网络协议栈、Netfilter/nftables、routing 等专题
```

## 基础课程学习问题

```text
CPU 如何执行内核代码？
内核如何完成启动？
虚拟地址如何映射到物理内存？
物理页和内核对象如何分配？
内核如何维护时间并触发定时事件？
任务如何运行、阻塞、唤醒和切换？
系统崩溃后，如何通过 Kdump 和 vmcore 保留并分析现场？
```

基础课程推荐顺序仍然是：

```text
assembly
→ boot-crash + memory
→ memory + timekeeping + scheduler
→ Kexec/Kdump/vmcore
→ integrated-paths
```

这些领域分别整理，但实际运行时彼此联系紧密：

- 汇编知识用于理解寄存器、栈、系统调用、异常入口、启动入口和上下文切换；
- 启动过程会建立早期页表、初始化内存管理，并逐步启动时钟和调度器；
- 内存管理负责地址映射、物理页分配、内核对象分配和缺页处理；
- 时间子系统向内核提供时间，并安排周期性或一次性的事件；
- 调度器根据任务状态、运行时间和优先级选择下一个任务；
- Kexec/Kdump 在当前内核之外准备另一套内核，用于快速切换或保存崩溃现场。

## Network 专题

[`network/`](network/) 已从“后续占位专题”转为正式学习专题，当前从 **Netfilter/nftables** 切入。

当前入口：

- [`network/README.md`](network/)：网络专题总纲和当前进度；
- [`network/docs/nftables/00-learning-plan.md`](network/docs/nftables/00-learning-plan.md)：NF00～NF13 学习计划；
- [`network/docs/nftables/01-ruleset-evaluation-and-control-flow.md`](network/docs/nftables/01-ruleset-evaluation-and-control-flow.md)：已学 ruleset evaluator 与控制流；
- [`network/docs/nftables/02-counter-log-and-rule-operations.md`](network/docs/nftables/02-counter-log-and-rule-operations.md)：已学 counter/log/handle；
- [`network/source-paths/nftables-v6.12.md`](network/source-paths/nftables-v6.12.md)：Linux v6.12 源码闭环；
- [`network/labs/nftables/01-counter-log/README.md`](network/labs/nftables/01-counter-log/README.md)：counter/log 最小实验。

当前 nftables 进度：

```text
ruleset evaluation                 已完成
jump/goto/return/verdict           已完成
counter/log/handle                 已完成
nft monitor trace                  下一课
Netfilter hooks + packet path      待学习
conntrack/NAT                      待学习
sets/maps/verdict maps             待学习
mark + policy routing              待学习
route chain                        待学习
families/stateful objects          待学习
flowtable                          待学习
v6.12 evaluator 深入               持续推进
```

Network 专题当前内核事实基线：

```text
Linux tag: v6.12
upstream commit: adc218676eef25575469234709c2d87185ca223a
```

具体核验规则见 [`network/AGENTS.md`](network/AGENTS.md)。

## 版本与实验基线

基础课程历史基线：

```text
内核版本：Linux kernel 5.10
主要架构：x86-64
汇编器：GNU assembler
主要汇编语法：AT&T
用户态 ABI：System V AMD64 ABI
```

Network 专题：

```text
内核版本：upstream Linux v6.12
主要架构：x86-64（架构相关内容）
Netfilter/nftables 实现结论必须回到 v6.12 源码核验
```

如果未来要把现有 5.10 基础课程整体迁移到 6.12，应作为独立迁移任务逐章重做源码、实验和自动检查核验，而不是仅修改文档版本号。

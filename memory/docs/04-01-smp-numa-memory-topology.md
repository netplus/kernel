# M04-01：SMP、NUMA 与物理拓扑

本节先从硬件和体系结构层建立 NUMA 心智模型，避免进入源码后把 CPU topology、socket 和 memory node 混为一谈。

## 1. 本章目标

回答：

```text
SMP 解决什么问题？
NUMA 描述什么问题？
CPU、core、socket、NUMA node、memory controller 如何关联？
为什么 socket 不等于 NUMA node？
```

完成后应能从硬件拓扑自然过渡到 Linux 所需要的软件拓扑。

## 2. 核心问题

1. SMP 与 NUMA 为什么不是互斥概念？
2. UMA 与 NUMA 的根本差异是什么？
3. local memory 与 remote memory 的性能差异来自哪里？
4. 为什么现代多路服务器需要分布式 memory controller？
5. 一个 socket 为什么可能包含多个 NUMA node？
6. Linux 为什么既需要 CPU topology，又需要 memory topology？

## 3. 基本模型

```text
SMP：描述多个逻辑 CPU 如何作为对等执行资源参与系统运行。
NUMA：描述这些 CPU 访问不同物理内存区域时的 locality 与代价差异。
```

示例：

```text
Node 0                         Node 1
CPU0 CPU1 CPU2 CPU3            CPU4 CPU5 CPU6 CPU7
        │                              │
 memory controller              memory controller
        │                              │
     RAM 0-16G                      RAM 16-32G
        └──────── interconnect ────────┘
```

需要建立的关键关系：

```text
logical CPU
    ↓
core / package topology
    ↓
NUMA node affinity
    ↓
local/remote memory distance
```

## 4. 必须区分的概念

```text
logical CPU
core
SMT sibling
socket / package
NUMA node
memory node
memory controller
local memory
remote memory
```

重点澄清：

```text
socket != NUMA node
SMP != UMA
NUMA system 通常仍然是 SMP system
```

## 5. Linux 视角下需要保存的信息

硬件模型最终必须转换成 Linux 可以查询的关系：

```text
CPU → node ID
node ID → CPU mask
physical address / PFN range → node ID
node → distance to other nodes
```

这一节只说明需求，不深入映射实现。

## 6. 相关配置

后续源码阅读时关注：

```text
CONFIG_SMP
CONFIG_NUMA
CONFIG_X86_64
```

并说明 UMA 构建与 NUMA 构建在抽象接口上的差别。

## 7. 示例机器推演

贯穿后续章节的机器保持为：

```text
Node 0
├── CPU0-3
└── RAM 0-16 GiB

Node 1
├── CPU4-7
└── RAM 16-32 GiB
```

本章先只回答：

```text
CPU0 访问 0-16 GiB 为什么视为 local？
CPU0 访问 16-32 GiB 为什么可能视为 remote？
```

后续章节再回答 Linux 如何知道这些事实。

## 8. 源码定位

本章以概念为主，只做源码入口预览：

```text
arch/x86/mm/numa.c
arch/x86/include/asm/numa.h
include/linux/numa.h
include/linux/cpumask.h
include/linux/nodemask.h
```

## 9. 当前启动状态

本章仍停留在“Linux 需要获得什么拓扑信息”的层次：

| 对象 | 当前认识 |
|---|---|
| CPU topology | 硬件概念已建立 |
| NUMA node | 硬件/固件概念已建立 |
| CPU → node | 尚未分析如何建立 |
| memory range → node | 尚未分析如何建立 |
| pg_data_t | 尚未进入 |
| zone | 尚未进入 |

## 10. 与上一章的连接

M04-00 给出了完整软件结构：

```text
NUMA node → pg_data_t → zone → page
```

本节向前追问：

```text
NUMA node 这个信息最初从哪里来？
```

## 11. 与下一章的连接

下一节进入 x86-64 启动路径，研究固件尤其是 ACPI SRAT 如何把：

```text
Processor Affinity
Memory Affinity
```

提供给 Linux，并最终形成初始 NUMA topology。
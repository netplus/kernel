# M04-00：Page、Zone、Node 总览

本节是 M04 的导航章。目标不是立即进入具体函数，而是先建立 Linux 5.10 启动期物理内存管理对象之间的关系，并明确后续七个子章节分别解决什么问题。

## 1. 本章目标

完成本章后，应先建立下面这条主线：

```text
Firmware / Hardware
        ↓
physical memory map + NUMA affinity
        ↓
memblock
        ↓
NUMA node
        ↓
pg_data_t
        ↓
zone
        ↓
struct page
        ↓
buddy allocator
```

重点不是记住结构体字段，而是理解每一层为什么存在、上一层向下一层提供什么信息。

## 2. 核心问题

本章围绕以下问题建立导航：

1. Linux 为什么不能只维护一个全局物理页数组？
2. NUMA node、`pg_data_t`、zone、PFN、`struct page` 分别描述什么？
3. `node` 与 `zone` 为什么是两个层次？
4. 一个 PFN 是在什么时候获得 node 和 zone 归属的？
5. `NODE_DATA(nid)` 与 `pfn_to_page()` 分别解决什么查找问题？
6. memblock 与 buddy allocator 的职责边界在哪里？

## 3. 抽象模型

贯穿 M04 使用下面的示例机器：

```text
2 sockets / 8 logical CPUs / 32 GiB RAM

Node 0
├── CPU0-3
└── RAM: 0-16 GiB

Node 1
├── CPU4-7
└── RAM: 16-32 GiB
```

在典型 x86-64 zone 边界下，可先抽象为：

```text
Node 0 → pg_data_t
├── ZONE_DMA
├── ZONE_DMA32
└── ZONE_NORMAL

Node 1 → pg_data_t
└── ZONE_NORMAL
```

注意：这是用于推演的简化模型，不意味着 `socket == NUMA node`，也不意味着每个 node 必然拥有所有 zone。

## 4. 关键对象

后续会逐步深入：

```text
NUMA node
pg_data_t / struct pglist_data
struct zone
PFN
struct page
memblock.memory
memblock.reserved
zonelist
```

本章只建立职责边界。

## 5. 源码导航

后续主要会进入：

```text
arch/x86/mm/numa.c
arch/x86/mm/numa_64.c
arch/x86/mm/srat.c
arch/x86/kernel/acpi/boot.c
mm/memblock.c
mm/page_alloc.c
include/linux/mmzone.h
include/linux/memblock.h
include/linux/numa.h
```

## 6. 整个 M04 的概念调用链

```text
x86 early boot
    ↓
firmware memory / NUMA information
    ↓
memblock records physical ranges
    ↓
NUMA discovery establishes node affinity
    ↓
CPU ↔ node mapping
    ↓
node memory ranges
    ↓
pg_data_t initialization
    ↓
zone sizing and initialization
    ↓
struct page initialization
    ↓
free pages enter buddy allocator
```

正式教程中会进一步区分：

- 直接调用；
- 间接调用；
- architecture-specific path；
- generic MM path。

## 7. 启动阶段状态表

M04 会持续维护下面这张表：

| 阶段 | memblock | NUMA topology | pg_data_t | zone | struct page | buddy |
|---|---|---|---|---|---|---|
| 早期物理内存发现 | 可用/建立中 | 未完成 | 未完成 | 未完成 | 未完成 | 不可用 |
| NUMA 发现后 | 可用 | 已建立主体 | 建立中 | 未完成 | 未完成 | 不可用 |
| zone 初始化后 | 可用 | 已建立 | 已建立 | 已建立 | 建立中 | 未完全可用 |
| page 初始化后 | 可用 | 已建立 | 已建立 | 已建立 | 已建立 | 准备交接 |
| buddy 接管后 | 逐步退出主舞台 | 已建立 | 已建立 | 已建立 | 已建立 | 可用 |

具体时点和函数边界将在后续章节按 Linux 5.10 源码校正。

## 8. 本章与前后章节的关系

上一章 M03 已经回答：

```text
普通页分配器还不可用时，Linux 如何记录和预留物理内存？
```

M04 接着回答：

```text
这些物理内存如何获得 NUMA、node、zone 和 page 元数据？
```

下一章 M05 再回答：

```text
这些已经完成建模的空闲物理页如何进入伙伴系统并被 alloc_pages() 使用？
```

## 9. M04 子章节地图

```text
M04-00  总览
   ↓
M04-01  SMP、NUMA 与物理拓扑
   ↓
M04-02  x86 NUMA 拓扑发现
   ↓
M04-03  CPU → NUMA node
   ↓
M04-04  memory range → node → pg_data_t
   ↓
M04-05  pg_data_t → zone
   ↓
M04-06  PFN → struct page
   ↓
M04-07  memblock → buddy
```

下一节从硬件模型开始，先把 SMP、socket、NUMA node、local/remote memory 的边界彻底厘清。
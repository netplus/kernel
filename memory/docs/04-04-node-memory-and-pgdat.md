# M04-04：Node Memory Range 与 pg_data_t

本节沿物理内存支线继续，从“某段物理内存属于哪个 NUMA node”推进到 Linux MM 的 per-node 描述对象 `pg_data_t / struct pglist_data`。

## 1. 本章目标

建立下面的转换链：

```text
physical address range
        ↓
memblock region + nid
        ↓
node memory ranges
        ↓
pg_data_t
        ↓
NODE_DATA(nid)
```

完成后应理解“硬件 NUMA node”如何变成“Linux memory node”。

## 2. 核心问题

1. e820 memory map 与 NUMA memory affinity 分别提供什么信息？
2. memblock region 如何携带 node ID？
3. node 的 `start_pfn`、`spanned_pages`、`present_pages` 如何从物理范围推导？
4. `pg_data_t` 为什么必须是 per-node？
5. `NODE_DATA(nid)` 背后依赖什么存储关系？
6. UMA 系统与 NUMA 系统在 `pg_data_t` 抽象上有什么共同点？
7. node 中存在 memory hole 时，范围与实际存在页数为什么不同？

## 3. 关键数据结构

正式教程重点分析：

```c
struct memblock
struct memblock_type
struct memblock_region

struct pglist_data
pg_data_t

node_data[]
NODE_DATA(nid)
```

其中 `struct pglist_data` 至少关注：

```text
node_id
node_start_pfn
node_spanned_pages
node_present_pages
node_zones[]
node_zonelists[]
```

本章重点解释字段存在的原因，而不是只翻译字段名。

## 4. 关键源码文件

正式展开时重点核验：

```text
include/linux/memblock.h
mm/memblock.c
include/linux/mmzone.h
mm/page_alloc.c
arch/x86/mm/numa.c
arch/x86/mm/numa_64.c
```

`pg_data_t` 的静态、早期或动态放置方式需要以 Linux 5.10 + x86-64 + CONFIG_NUMA 的实际代码为准。

## 5. 输入与输出

本章输入：

```text
已发现的 NUMA node IDs
物理 memory ranges
每段 range 的 nid
memblock early allocation 能力
```

本章输出：

```text
每个 memory node 对应的 pg_data_t
node 的 PFN 范围和 page 数量统计
后续 zone 初始化可使用的 per-node 容器
```

## 6. 概念调用链

```text
NUMA memory affinity
        ↓
numa memory blocks
        ↓
memblock / nid-aware ranges
        ↓
calculate node PFN span
        ↓
prepare pg_data_t
        ↓
NODE_DATA(nid) becomes meaningful
```

正文必须核实真正的函数边界，并区分“node range 计算”和“pgdat 初始化”是否发生在同一个函数中。

## 7. Memory hole 的意义

示例：

```text
Node0 span: PFN 0 ... PFN X

其中：
[0 ... A]       RAM
[A ... B]       hole / reserved / absent
[B ... X]       RAM
```

因此需要区分：

```text
node_spanned_pages
node_present_pages
```

这一差异将在下一章 zone 的 `spanned/present/managed` 中进一步展开。

## 8. 示例机器推演

对示例机器：

```text
Node0 memory: 0-16 GiB
Node1 memory: 16-32 GiB
```

目标形成：

```text
NODE_DATA(0) → pg_data_t for Node0
NODE_DATA(1) → pg_data_t for Node1
```

并在其中记录各自：

```text
node_start_pfn
node_spanned_pages
node_present_pages
```

正文中加入一个存在 memory hole 的变体，验证 `span != present`。

## 9. 当前启动状态

本章结束时：

| 对象 | 状态 |
|---|---|
| memblock | 可用，并携带物理范围信息 |
| CPU → node | 已建立 |
| memory range → node | 已建立并可解释 |
| pg_data_t | 已建立/初始化到足以承载 node MM 状态 |
| zone | 容器存在但具体 sizing/初始化是下一章重点 |
| struct page | 尚未完整初始化 |
| buddy | 不可用 |

## 10. 容易混淆的问题

正文至少区分：

```text
NUMA node vs pg_data_t
physical address vs PFN
node span vs actual RAM
memblock.memory vs node memory accounting
node_data[] vs node_zones[]
```

## 11. 与上一章的连接

上一章完成：

```text
CPU → node
```

本章完成另一半：

```text
memory range → node → pg_data_t
```

两条支线到这里第一次在同一个 Linux node ID 上汇合。

## 12. 与下一章的连接

有了 `pg_data_t` 这个 per-node 容器，下一步需要回答：

```text
一个 node 内部为什么还要切成 ZONE_DMA / DMA32 / NORMAL？
这些 zone 的 PFN 边界如何计算并写入 struct zone？
```

下一节进入 zone sizing 与初始化。
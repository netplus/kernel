# M04-05：Zone 边界计算与初始化

本节研究 `pg_data_t` 内部的物理内存如何进一步划分为 zone，并解释 zone 的范围统计为什么必须区分 `spanned_pages`、`present_pages` 和 `managed_pages`。

## 1. 本章目标

建立：

```text
node PFN range
      +
architecture zone limits
      ↓
ZONE_DMA / ZONE_DMA32 / ZONE_NORMAL
      ↓
struct zone
```

并理解 zone 是“物理页分配约束域”，而不是 NUMA node 的同义词。

## 2. 核心问题

1. 为什么有了 NUMA node 还需要 zone？
2. x86-64 的 DMA、DMA32、NORMAL 边界从哪里来？
3. 一个 node 为什么可能没有某些 zone？
4. zone 的 `zone_start_pfn` 如何确定？
5. `spanned_pages`、`present_pages`、`managed_pages` 为什么必须分开？
6. reserved pages 为什么可能 present 但暂时不 managed？
7. zone 初始化与 buddy free list 初始化是什么关系？

## 3. 关键数据结构

正式教程重点：

```c
struct zone
pg_data_t.node_zones[]
```

关注字段：

```text
zone_start_pfn
spanned_pages
present_pages
managed_pages
free_area[]
watermark[] / _watermark
```

watermark 与 free_area 在本章只定位其初始化关系，详细分配行为留到 M05。

## 4. 关键 zone 类型

针对 Linux 5.10 x86-64：

```text
ZONE_DMA
ZONE_DMA32
ZONE_NORMAL
ZONE_MOVABLE
```

需要说明：

- 哪些由架构物理寻址/DMA 约束产生；
- `ZONE_MOVABLE` 与普通硬件地址边界的性质不同；
- 当前主线以 DMA/DMA32/NORMAL 为核心。

## 5. 关键源码文件

正式展开时重点核验：

```text
mm/page_alloc.c
include/linux/mmzone.h
arch/x86/mm/init.c
arch/x86/mm/init_64.c
arch/x86/include/asm/page_types.h
```

如 zone boundary 的 5.10 实际定义位于其他 x86 文件，正文按源码校正。

## 6. 关键函数候选

重点核验：

```text
free_area_init()
free_area_init_node()
calculate_node_totalpages()
free_area_init_core()
zone_sizes_init()
```

不得默认这些函数在 x86-64 5.10 主路径中的调用关系；正式正文必须从 `setup_arch()`/MM 初始化路径反向确认。

## 7. 三种 page count

本章必须用具体 PFN 区间解释：

```text
spanned_pages
    zone 起止 PFN 覆盖的整个跨度，可能含 hole。

present_pages
    其中实际存在的物理 RAM 页。

managed_pages
    最终交由 page allocator 管理的页；会排除仍被保留或不可交付的页。
```

示例：

```text
zone span     : 1000 pages
memory holes  : 100 pages
reserved      : 50 pages

概念上：
spanned = 1000
present = 900
managed ≈ 850
```

具体计算必须以 Linux 5.10 初始化过程为准。

## 8. 示例机器推演

示例：

```text
Node0: 0-16 GiB
Node1: 16-32 GiB
```

根据 x86 zone limits，形成类似：

```text
Node0
├── DMA
├── DMA32
└── NORMAL

Node1
└── NORMAL
```

正文要强调：zone boundary 是系统物理地址边界与 node memory range 的交集。

## 9. 当前启动状态

本章结束后：

| 对象 | 状态 |
|---|---|
| memblock | 可用 |
| NUMA topology | 已建立 |
| pg_data_t | 已建立 |
| struct zone | 已完成主要 sizing / 初始化 |
| zone free_area | 结构存在，但空闲页尚未完成最终交接 |
| struct page | 下一章完成主体初始化 |
| buddy | 尚未正式接管全部可用页 |

## 10. 容易混淆的问题

正文至少澄清：

```text
node boundary != zone boundary
present != managed
reserved != absent
ZONE_NORMAL != “所有普通 RAM” 的简单全局集合
zone index 在不同 node 上代表同类约束，但实际 PFN 范围不同
```

## 11. 与上一章的连接

M04-04 已得到：

```text
node → pg_data_t
```

本章进一步填充：

```text
pg_data_t.node_zones[]
```

让每个 node 具备可以被页分配器使用的 zone 层次。

## 12. 与下一章的连接

zone 只描述一组 PFN 的分配域；真正对每个物理页进行状态管理，还需要：

```text
PFN → struct page
```

下一节研究 `struct page` 元数据在普通 page allocator 尚未完全可用时如何建立。
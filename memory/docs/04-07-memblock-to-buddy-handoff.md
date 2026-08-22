# M04-07：从 Memblock 交接到 Buddy

本节是 M04 的收束章，研究 Linux 如何从启动期 memblock 管理模型切换到运行期 buddy allocator，并把前面建立的 NUMA node、pg_data_t、zone 和 struct page 全部串成一条完整启动链。

## 1. 本章目标

最终解释：

```text
early boot
memblock owns physical-memory bookkeeping
        ↓
NUMA / pg_data_t / zone / struct page ready
        ↓
release usable physical pages
        ↓
buddy free lists populated
        ↓
normal page allocation becomes available
```

并明确 memblock 与 buddy 并不是两个同时承担相同职责的分配器。

## 2. 核心问题

1. 为什么 Linux 启动时不能直接使用 buddy allocator？
2. buddy 接管前必须具备哪些数据结构？
3. `memblock.reserved` 中哪些区域不能进入 buddy？
4. 可用物理页是在什么路径中被转换成 buddy free pages？
5. `managed_pages` 在交接过程中如何变得有意义？
6. memblock metadata 本身何时可以释放或不再承担主分配职责？
7. buddy 可用与 `kmalloc()` 完全可用是否是同一个时点？
8. M03 中的 early allocation 与 M05 中的 `alloc_pages()` 在语义上如何交接？

## 3. 前置条件清单

进入交接前，系统应已经拥有：

```text
NUMA nodes
CPU ↔ node mapping
node memory ranges
pg_data_t
zone boundaries and metadata
PFN ↔ struct page mapping
reserved-memory knowledge
```

本章要逐项确认这些前置条件是由 M04 哪一节建立的。

## 4. 关键源码文件

正式展开时重点核验：

```text
mm/memblock.c
mm/page_alloc.c
init/main.c
arch/x86/kernel/setup.c
arch/x86/mm/init_64.c
```

同时追踪 `mem_init()`、free boot memory 相关架构路径与 generic MM helper 的真实调用关系。

## 5. 关键函数候选

正式教程需在 Linux 5.10 源码中核验：

```text
mem_init()
memblock_free_all()
free_low_memory_core_early()
__free_memory_core()
__free_pages_core()
```

以及 x86-64 架构层实际进入 generic free path 的函数。

这里特别要求区分：

- 初始化 page allocator 的函数；
- 把具体 page 释放进 buddy 的函数；
- 释放 memblock metadata 的函数；
- architecture-specific wrapper。

## 6. 概念交接过程

```text
memblock.memory
  - memblock.reserved
        ↓
usable PFN ranges
        ↓
for each usable page/range
        ↓
initialize/validate struct page state
        ↓
free into buddy by order/path
        ↓
zone managed/free accounting updated
```

正式正文需避免把“从 memblock 遍历可用范围”简化成单个函数调用；应按源码展示真实层次。

## 7. 为什么 reserved memory 不能交出去

需要用 M03 已经出现的对象验证：

```text
kernel image
initrd（具体时点视路径而定）
page tables / boot metadata
ACPI / firmware reservations
crashkernel
other architecture reservations
```

本章重点回答：

```text
这些范围在 memblock 中如何被排除？
什么时候可能被后续释放？
哪些会长期保持 reserved？
```

不展开各 reserved 子系统本身。

## 8. Managed pages 的最终意义

M04-05 已经区分：

```text
spanned
present
managed
```

本章要把 `managed_pages` 与真实交付 buddy 的页联系起来：

```text
present RAM
  - pages not available to allocator
        ↓
managed pages
```

并核验 5.10 中 managed page accounting 的具体更新时间点。

## 9. 示例机器推演

假设：

```text
Node0 RAM: 0-16 GiB
Node1 RAM: 16-32 GiB
```

其中包含：

```text
kernel image
firmware reserved ranges
crashkernel reserved range
memory holes
```

最终推演：

```text
Node0/DMA, DMA32, NORMAL free pages
        ↓
对应 zone free_area[]

Node1/NORMAL free pages
        ↓
对应 zone free_area[]
```

并明确哪些 PFN 没有进入 free lists 以及原因。

## 10. 启动状态最终表

本章结束时形成 M04 最终状态：

| 对象 | 状态 |
|---|---|
| memblock | 已完成启动期核心使命，后续不再作为普通页分配器 |
| NUMA topology | 已建立 |
| CPU → node | 已建立 |
| memory range → node | 已建立 |
| pg_data_t | 已建立 |
| zone | 已建立 |
| struct page | 已建立 |
| buddy | 已获得可管理空闲页并可进入正常物理页分配阶段 |

## 11. 完整启动主线复盘

M04 最终需要能够从头解释：

```text
Firmware / ACPI / e820
        ↓
memblock
        ↓
NUMA discovery
        ├── CPU → node
        └── memory range → node
                    ↓
                 pg_data_t
                    ↓
                   zone
                    ↓
                struct page
                    ↓
       free usable pages to buddy
```

同时回答每一步：

```text
输入是什么？
输出是什么？
修改了什么全局状态？
下一阶段为什么依赖它？
```

## 12. 容易混淆的问题

正文至少澄清：

```text
memblock free != buddy free 的所有语义都相同
memblock 不等于 buddy 的“早期模式”
zone initialized != 所有 free pages 已进入 free_area
buddy available != slab/kmalloc 所有层次已经完全初始化
reserved != 永远不会释放
```

## 13. 与上一章的连接

M04-06 已完成：

```text
PFN → struct page
```

所以运行期页分配器需要的静态描述已经具备。

本章完成最后一步：

```text
可用页 → buddy free lists
```

## 14. 与 M05 的连接

M04 到此结束。

M05 不再讨论“buddy 是怎么被建立出来的”，而从已经可用的 buddy allocator 出发，深入：

```text
order
free_area
split
merge
alloc_pages()
GFP
PCP
fast path / slow path
fragmentation
```

这样 M03、M04、M05 形成完整连续课程：

```text
M03：启动期如何暂存和预留物理内存
        ↓
M04：如何把物理拓扑转换成 page allocator 数据结构并完成交接
        ↓
M05：运行期 buddy allocator 如何真正分配和回收物理页
```
# M04-06：struct page 初始化

本节研究 Linux 如何为物理页建立 `struct page` 元数据，并解决一个关键启动依赖问题：普通页分配器尚未可用时，管理物理页所需的元数据本身从哪里获得内存。

## 1. 本章目标

建立：

```text
physical memory / PFN
        ↓
page metadata storage
        ↓
PFN → struct page
        ↓
page state initialization
```

并理解 `struct page` 是运行期 page allocator 能工作的基础元数据，而不是 buddy allocator 启动之后才临时创建的对象。

## 2. 核心问题

1. 为什么每个可管理 PFN 都需要 `struct page`？
2. `pfn_to_page()` 的映射依赖什么内存模型？
3. `CONFIG_SPARSEMEM` 在本课程需要理解到什么程度？
4. `struct page` 数组/section metadata 自身占用的内存从哪里分配？
5. memblock 在 page metadata 建立过程中扮演什么角色？
6. `struct page` 在什么时候获得 node/zone 相关初始化状态？
7. reserved、hole、normal RAM 对应的 page metadata 是否完全相同？

## 3. 关键数据结构与接口

正式教程重点：

```c
struct page
pfn_to_page()
page_to_pfn()
page_zone()
page_to_nid()
```

根据 Linux 5.10 x86-64 默认/目标配置，补充：

```text
SPARSEMEM
memory section
mem_section
vmemmap（若实际配置路径使用）
```

本章只深入到理解 PFN/page 映射所需程度，不展开 memory hotplug。

## 4. 关键源码文件

正式展开时重点核验：

```text
include/linux/mm_types.h
include/linux/mm.h
include/linux/mmzone.h
include/linux/memory_model.h
mm/page_alloc.c
mm/sparse.c
arch/x86/mm/init_64.c
```

如果目标配置使用 `SPARSEMEM_VMEMMAP`，还应核对对应 vmemmap 初始化路径。

## 5. 启动期循环依赖

本章要明确解释：

```text
要使用 buddy 管理 page
        ↓
需要 struct page 元数据
        ↓
建立 struct page 元数据本身需要内存
        ↓
但 buddy 此时尚未可用
```

Linux 的基本解决思路是：

```text
early allocator / memblock
        ↓
为必要 MM metadata 提供物理内存
        ↓
建立 page metadata
        ↓
之后才让普通 page allocator 接管
```

正式正文必须以真实 Linux 5.10 初始化调用链校正细节。

## 6. PFN 到 page 的软件映射

本章要建立：

```text
physical address
    ↓ >> PAGE_SHIFT
PFN
    ↓
pfn_to_page()
    ↓
struct page *
```

反向：

```text
struct page *
    ↓
page_to_pfn()
    ↓
PFN
```

并说明该映射为什么与具体 memory model 配置有关。

## 7. Page 与 Node/Zone 的联系

最终 `struct page` 不应被理解为孤立对象。

运行期需要能够从 page 推导：

```text
page
 ↓
zone
 ↓
pg_data_t / node
```

本章重点定位这些关系在 page flags、section metadata、zone 初始化中的来源，具体实现以 5.10 源码为准。

## 8. 示例机器推演

对于示例：

```text
Node0: PFN range A
Node1: PFN range B
```

最终需要形成：

```text
PFN x in Node0 NORMAL
    ↓
pfn_to_page(x)
    ↓
struct page
    ↓
page_zone(page) → Node0 ZONE_NORMAL
```

正文中再加入 hole/reserved page 对比。

## 9. 当前启动状态

本章结束后：

| 对象 | 状态 |
|---|---|
| memblock | 仍可为 early metadata 服务 |
| NUMA topology | 已建立 |
| pg_data_t | 已建立 |
| zone | 已建立 |
| struct page | 主体初始化完成 |
| PFN ↔ page | 可解释 |
| buddy | 已具备接管前提，下一章完成交接 |

## 10. 容易混淆的问题

正文至少区分：

```text
PFN != struct page
struct page != 物理页内容本身
page metadata memory != 被描述的 RAM 内容
memory hole != 普通 free page
reserved page != 不存在的 page
SPARSEMEM != NUMA
```

## 11. 与上一章的连接

M04-05 已经建立：

```text
node → zone → PFN range
```

本章给这些 PFN 建立逐页元数据：

```text
PFN → struct page
```

至此 page allocator 所依赖的核心静态拓扑已经基本齐备。

## 12. 与下一章的连接

最后还差“谁真正拥有这些空闲页”的切换：

```text
memblock world
      ↓
release / free boot-time usable pages
      ↓
buddy world
```

下一章完整分析这次启动期内存管理权力交接。
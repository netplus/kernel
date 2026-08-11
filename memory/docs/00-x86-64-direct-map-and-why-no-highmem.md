# x86-64 Direct Map：为什么通常不再需要 ZONE_HIGHMEM

本文专门回答一个问题：

> **为什么 Linux x86-64 系统通常不需要通过 `ZONE_HIGHMEM` 解决“物理 RAM 存在，但 kernel virtual address 不够为其建立永久映射”的问题？**

这不是简单因为“指针从 32 位变成了 64 位”，而是因为 **x86-64 可用的 kernel virtual-address budget、Linux 的 kernel VA layout、direct-map window 与硬件支持的 physical-address range 之间的比例关系发生了根本变化**。

理解这件事，需要沿下面的因果链展开：

```text
CPU virtual-address width
        ↓
kernel 能取得多少 virtual address space
        ↓
kernel 能拿多少 VA 建立 permanent direct map
        ↓
这个 direct-map window 能否覆盖全部 ordinary RAM
        ↓
如果不能：LOWMEM / HIGHMEM
如果能：不需要经典 HIGHMEM
```

---

## 1. HIGHMEM 首先是一个“kernel VA 不够”的问题

不要先把 `HIGHMEM` 理解成某种特殊物理内存。

它真正解决的问题是：

```text
系统中存在 physical RAM
        ↓
kernel 想直接访问这些 physical pages
        ↓
CPU load/store 必须使用 virtual address
        ↓
因此 kernel 需要一个 kernel VA 指向这些 pages
```

Linux 最理想的做法是：

> **为 ordinary physical RAM 中的每个 page 都长期保留一个 kernel virtual address。**

这就是 direct mapping，也常称 direct map / linear map。

概念上：

```text
Kernel Direct-Map VA              Physical RAM

DIRECT_MAP_BASE + 0x0000  ----->  PA 0x0000
DIRECT_MAP_BASE + 0x1000  ----->  PA 0x1000
DIRECT_MAP_BASE + 0x2000  ----->  PA 0x2000
...
```

对 direct-mapped page 来说，kernel 不需要在每次访问前重新找 VA、改页表、再释放这个映射。

因此可以先定义两个量：

```text
R = kernel 需要覆盖的 physical-address / RAM range
D = kernel VA layout 为 permanent direct mapping 提供的容量
```

问题就变成一个非常简单的不等式。

### 情况 A：`R <= D`

```text
all ordinary RAM
        ↓
全部能够 permanent direct map
        ↓
不存在“剩余 RAM 没有永久 kernel VA”的问题
        ↓
不需要经典 HIGHMEM
```

### 情况 B：`R > D`

```text
前 D 范围 RAM
        ↓
permanent direct mapped
        ↓
LOWMEM

剩余 RAM
        ↓
没有足够 kernel VA 永久映射
        ↓
HIGHMEM
```

因此 HIGHMEM 的核心定义可以抽象成：

> **physical RAM whose permanent kernel virtual mapping cannot be afforded。**

“high” 经常对应较高 PFN/物理地址，只是因为 direct map 通常从低物理地址开始覆盖；真正的因果根源仍然是 **kernel VA scarcity**。

---

## 2. 为什么经典 32-bit x86 会遇到这个问题

### 2.1 整个 virtual address space 只有 4 GiB

32-bit virtual address 的理论范围是：

```text
2^32 = 4 GiB
```

经典 Linux 3G/1G split 可以抽象为：

```text
Virtual Address Space

0x00000000
│
│ user VA
│ ~3 GiB
│
0xC0000000  PAGE_OFFSET
├────────────────────────────
│ kernel VA
│ ~1 GiB
│
0xFFFFFFFF
```

所以 kernel 一共只有大约 1 GiB virtual-address budget。

### 2.2 这 1 GiB 不能全给 direct map

Kernel VA 还承担很多职责，例如：

```text
vmalloc
modules
ioremap
fixmap
kmap / temporary mappings
其他 architecture-specific mappings
```

因此经典 3G/1G x86 中，经常以约 896 MiB 来说明可用于 permanent lowmem mapping 的数量级：

```text
kernel VA total       ≈ 1 GiB

其中：
direct map            ≈ 896 MiB
other kernel mappings ≈ remaining VA
```

这个 `896 MiB` 是经典教学模型中的典型值，不应理解成所有 32-bit kernel 配置都固定具有同一边界。

### 2.3 RAM 很容易超过 direct-map capacity

假设：

```text
Physical RAM = 4 GiB
Direct-map VA capacity ≈ 896 MiB
```

那么显然：

```text
R > D
```

于是：

```text
Physical RAM

0
│
│ permanent kernel mapping
│ LOWMEM
│
~896 MiB
├────────────────────────────
│
│ no permanent kernel direct mapping
│ HIGHMEM
│
RAM end
```

这就是经典 32-bit HIGHMEM 的设计背景。

---

## 3. HIGHMEM page 为什么需要特殊处理

如果一个 physical page 属于 LOWMEM：

```text
physical page
     ↕
permanent kernel direct-map VA
```

kernel 随时都有稳定的地址访问它。

而 HIGHMEM page 没有 permanent kernel direct-map VA：

```text
HIGHMEM physical page
        ↑
        │
        × no permanent direct-map VA
```

当 kernel 确实需要解引用这个 page 的内容时，就需要临时获得一个 kernel VA，例如传统 highmem API 中的：

```text
kmap(page)
    ↓
取得/建立临时 kernel mapping
    ↓
访问 page
    ↓
kunmap(...)
```

因此 HIGHMEM 带来的成本主要不是 DRAM 本身更慢，而是：

- kernel 不能假设 page 永久具有直接可解引用的 VA；
- 某些内核数据结构不能简单放到 HIGHMEM；
- kernel 访问 highmem page 时需要映射管理；
- kernel VA 本身成为需要精细管理的稀缺资源。

---

## 4. x86-64 真正改变的是 VA 的数量级

进入 x86-64 后，最关键的变化并不是“C 指针变成 8 字节”本身，而是 CPU 能够提供的有效 virtual-address range 大幅扩大。

x86-64 并不意味着所有实现都真正使用完整 64-bit VA。典型 Linux 5.10 x86-64 需要重点理解两种分页模式：

```text
4-level paging
5-level paging (LA57)
```

### 4.1 4-level paging

经典 x86-64 4-level paging 使用 48-bit canonical virtual addresses。

总 canonical VA 数量级为：

```text
2^48 = 256 TiB
```

通常分成两个 canonical halves：

```text
lower canonical range  -> user space
upper canonical range  -> kernel space
```

因此 kernel 不再面对“总共只有约 1 GiB VA”的局面，而是拥有 **TiB 级别**的虚拟地址资源。

### 4.2 5-level paging

5-level paging 将有效 virtual-address width 进一步扩大到 57 bit 的数量级，使 virtual-address capacity 进入 PiB 级别。

因此，从 VA resource budget 的角度看：

```text
32-bit kernel:
    kernel VA ≈ GiB level

x86-64 kernel:
    kernel VA ≈ TiB / PiB level
```

这是结构性变化，而不是简单的“两倍地址宽度”。

---

## 5. Linux x86-64 专门为 physical RAM 预留巨大 direct-map window

Linux 并没有只是“拥有很多 VA”，而是主动在 kernel VA layout 中切出一个巨大区域专门做 physical memory direct mapping。

对于 Linux 5.10 的典型 4-level x86-64 layout，可以建立下面的概念图：

```text
x86-64 Kernel Virtual Address Space

upper canonical addresses
│
│ ... architecture-specific regions ...
│
├─────────────────────────────────────────
│ Direct Mapping of Physical Memory
│ very large VA window
│
├─────────────────────────────────────────
│ vmalloc / ioremap
│
├─────────────────────────────────────────
│ vmemmap / other regions
│
├─────────────────────────────────────────
│ kernel image / modules / fixmap ...
│
virtual-address top
```

在 Linux 5.10 典型 4-level x86-64 layout 中，direct mapping 区域的数量级达到约 **64 TiB**。

这与经典 32-bit x86 的约 896 MiB direct-map budget 是完全不同的数量级：

```text
classic 32-bit x86:
    direct-map capacity ≈ 896 MiB

x86-64 4-level:
    direct-map VA window ≈ 64 TiB
```

因此核心变化是：

> **kernel 已经有能力非常“奢侈”地拿出几十 TiB VA，专门给 ordinary physical memory 建立长期 direct mapping。**

---

## 6. 预留 64 TiB VA 并不意味着消耗 64 TiB RAM

这点必须与前面的 mapping / allocation 概念保持一致。

假设机器只有：

```text
RAM = 64 GiB
```

kernel VA layout 可以仍然为 direct map 规划：

```text
64 TiB VA range
```

这并不表示：

```text
系统需要 64 TiB physical RAM
```

也不表示：

```text
kernel 占用了 64 TiB RAM
```

它只表示：

> **这段 virtual-address range 被指定用于表达 physical-memory direct mapping。**

实际存在的 RAM 才会按照物理内存地图和页表建立有效映射。

因此必须继续牢记：

```text
virtual-address reservation
        ≠
physical allocation
        ≠
physical ownership
```

64-bit 架构的一个巨大优势，就是 virtual address 本身足够宽裕，可以用大范围 VA 换取简单、稳定的 mapping model。

---

## 7. 为什么 direct-map capacity 足以覆盖 x86-64 ordinary RAM

这是整个逻辑真正闭环的地方。

经典 4-level x86-64 的 physical-address capability 也是有限的，并不是任意 64-bit physical address 都可用。

在 Linux 5.10 所讨论的经典 4-level x86-64 模型中，可以建立下面的数量级认识：

```text
virtual-address capacity:
    256 TiB canonical VA total

physical-address capacity:
    up to roughly 64 TiB in the traditional model

Linux direct-map VA window:
    roughly 64 TiB
```

于是从设计上：

```text
supported ordinary physical-address range
             ≈
direct-map virtual-address capacity
```

也就是说，Linux 可以给可支持的 ordinary physical RAM 准备对应的永久 kernel VA。

因此不再出现经典 32-bit 模式下的：

```text
RAM = several GiB
kernel direct-map window < 1 GiB
```

这种根本性失配。

---

## 8. 以一台 128 GiB x86-64 机器为例

假设：

```text
Physical RAM = 128 GiB
Direct-map VA window = TiB-level
```

显然：

```text
128 GiB << direct-map capacity
```

因此 ordinary RAM 可以全部落入 direct map：

```text
Physical RAM

0
│
│ page 0
│ page 1
│ page 2
│ ...
│ page N
│
128 GiB
```

对应 kernel VA：

```text
Kernel Direct Map

DIRECT_MAP_BASE + PA(page 0)
DIRECT_MAP_BASE + PA(page 1)
DIRECT_MAP_BASE + PA(page 2)
...
DIRECT_MAP_BASE + PA(page N)
```

于是系统中的 ordinary physical page 不再需要分成：

```text
有 permanent kernel VA 的部分
+
没有 permanent kernel VA 的部分
```

也就失去了经典 `LOWMEM / HIGHMEM` 二分的必要性。

---

## 9. 用户页仍然可以同时拥有 kernel direct mapping

“所有 ordinary RAM 都 permanent direct mapped”并不意味着所有 RAM 都归 kernel 使用。

假设某个 physical page 被分配给进程 A：

```text
Process A user VA
        │
        ▼
+-------------------+
| physical page P   |
+-------------------+
        ▲
        │
Kernel direct-map VA
```

同一个 physical page 同时可以：

- 作为某个进程的 anonymous page；
- 被 user page table 映射到用户 VA；
- 同时具有一个 kernel direct-map VA。

因此：

```text
permanent kernel direct mapping
        ≠
kernel owns the page
```

这与 32-bit LOWMEM 中的规则完全一致，只不过 x86-64 把这种 permanent direct-map 能力扩展到了几乎全部 ordinary RAM。

---

## 10. 为什么 x86-64 的普通 RAM 主要进入 ZONE_NORMAL

经典 32-bit 中可以建立：

```text
LOWMEM
├── ZONE_DMA
└── ZONE_NORMAL

HIGHMEM
└── ZONE_HIGHMEM
```

其中 `ZONE_HIGHMEM` 的成立条件是：

```text
physical page exists
        +
no permanent kernel mapping
```

x86-64 上，第二个条件通常不再成立。

因此 ordinary RAM 不需要因为“kernel VA 不够”被切成 HIGHMEM zone。

典型 x86-64 更常见：

```text
Physical RAM

low physical addresses
│
├── ZONE_DMA
│      legacy / special low-address constraints
│
├── ZONE_DMA32
│      32-bit DMA-addressability constraints
│
└── ZONE_NORMAL
       ordinary RAM
       permanent kernel direct mapping
```

如果启用了相关布局，还可能有：

```text
ZONE_MOVABLE
```

但 `ZONE_MOVABLE` 的设计目标是 page migration、memory hotplug/offline、控制不可迁移页分布等，不是对 `ZONE_HIGHMEM` 的替代。

---

## 11. ZONE_DMA / ZONE_DMA32 为什么没有随着 x86-64 一起消失

这反过来可以帮助验证我们的模型。

如果所有 zone 都只是因为 kernel VA 不够而产生，那么 x86-64 上理论上所有特殊 zone 都应该消失。

但实际并不是。

原因是：

```text
ZONE_HIGHMEM
    <- kernel virtual-address constraint

ZONE_DMA / ZONE_DMA32
    <- device DMA-address constraint
```

x86-64 CPU 拥有巨大 VA，并不意味着所有外设都拥有同样大的 DMA addressing capability。

某设备可能仍然要求 buffer 落在较低 physical-address range 中。

所以 x86-64 消除的是：

```text
“kernel VA 不足”造成的 zone 区分
```

而不是：

```text
所有 physical-address constraints
```

这也是为什么现代 x86-64 仍然需要 zone 这一层 physical-page capability 分类。

---

## 12. kmap 在没有 HIGHMEM 的架构上为什么会变得简单

在真正存在 HIGHMEM 的 32-bit 架构上：

```text
kmap(highmem_page)
        ↓
需要获得 kernel VA
        ↓
必要时建立临时 mapping
        ↓
kernel 才能直接访问 page content
```

而在没有经典 HIGHMEM 的 x86-64 上，ordinary page 本来就位于 permanent direct map 中：

```text
page
 ↓
已有 direct-map VA
 ↓
kernel 可直接访问
```

因此 highmem mapping API 在这类架构上的底层语义可以大幅简化。

这不是 API 偶然变简单，而是 architecture address-space condition 已经改变。

---

## 13. kernel image mapping 与 direct mapping 必须分开

x86-64 kernel VA layout 中常见两个很容易混淆的区域：

```text
kernel image mapping
```

和：

```text
physical-memory direct mapping
```

它们不是同一件事。

### Kernel image mapping

主要用于：

```text
kernel .text
kernel .rodata
kernel .data
kernel .bss
```

即 Linux kernel image 本身。

### Direct mapping

主要用于：

> **为 ordinary physical RAM 提供长期稳定的 kernel VA。**

因此不能因为 kernel image 本身只有几百 MiB，就认为 kernel 只能映射几百 MiB RAM。

真实 kernel VA layout 可以同时拥有：

```text
huge direct-map region
vmalloc/ioremap region
vmemmap
kernel image
modules
fixmap
other architecture-specific regions
```

这些区域承担不同职责。

---

## 14. 5-level paging 又进一步扩大了这个余量

当 x86-64 使用 5-level paging 时：

```text
virtual-address width
        ↑
57-bit level
```

VA capacity 进入 PiB 级别。

Linux 对 kernel VA layout 和 direct-map capacity 也可以进一步扩大。

因此从设计趋势看：

```text
32-bit:
VA 是非常稀缺的资源

x86-64 4-level:
VA 极大丰富

x86-64 5-level:
VA budget 进一步扩大
```

这使“为所有 ordinary RAM 建立 permanent kernel mapping”成为合理的基本策略。

---

## 15. 为什么不能简单总结成“64 位系统一定没有 HIGHMEM”

更严谨的条件不是：

```text
sizeof(void *) == 8
```

而是：

```text
permanent direct-map VA capacity
        >=
需要管理的 ordinary physical-memory range
```

只要这个条件成立，就不需要经典 HIGHMEM workaround。

所以真正应该说：

> **Linux x86-64 的地址空间能力和 kernel VA layout 使其能够为支持的 ordinary physical memory 提供足够大的 permanent direct-map 区域，因此通常不需要经典 `ZONE_HIGHMEM`。**

理论上，如果某个架构即便使用 64-bit pointer，但 kernel 可用 VA layout 仍然无法 permanent-map 其需要管理的 physical memory，它仍可能需要类似 HIGHMEM 的设计。

因此 HIGHMEM 是 architecture + kernel VA layout 的结果，不是 C 语言指针宽度本身直接决定的。

---

## 16. 32-bit 与 x86-64 的完整对照

### 16.1 经典 32-bit x86

```text
32-bit VA
   ↓
整个 virtual-address space 只有 4 GiB
   ↓
kernel 典型只占约 1 GiB
   ↓
direct-map budget 约 896 MiB 数量级
   ↓
实际 RAM 可以超过这个范围
   ↓
无法 permanent-map 所有 physical RAM
   ↓
LOWMEM + HIGHMEM
   ↓
ZONE_NORMAL + ZONE_HIGHMEM
   ↓
highmem page 需要特殊 mapping API
```

### 16.2 Linux 5.10 x86-64

```text
48-bit / 57-bit effective VA
   ↓
kernel VA 从 GiB 级跃升到 TiB / PiB 级
   ↓
Linux 为 physical RAM 规划巨大 direct-map window
   ↓
direct-map capacity 足够覆盖 ordinary RAM
   ↓
所有 ordinary RAM 都可以 permanent direct mapped
   ↓
不存在“剩余 RAM 没有 kernel VA”的经典问题
   ↓
不需要经典 HIGHMEM / ZONE_HIGHMEM
   ↓
ordinary RAM 主要由 ZONE_NORMAL 管理
```

---

## 17. 最终应该建立的统一模型

以后不要把问题记成：

```text
32-bit 有 HIGHMEM
64-bit 没 HIGHMEM
```

而应该记成：

```text
                 Physical RAM
                       │
                       ▼
Kernel 是否有足够 permanent VA 覆盖它？
              │                 │
             YES               NO
              │                 │
              ▼                 ▼
       permanent direct map    部分 RAM 无永久 mapping
              │                 │
              ▼                 ▼
       不需要经典 HIGHMEM     LOWMEM / HIGHMEM
```

然后再追问：

```text
是什么决定“足够”与“不足”？
```

答案是：

```text
hardware virtual-address capability
        +
Linux kernel VA layout
        +
direct-map window size
        +
hardware physical-address capability
        +
actual RAM topology
```

这五个因素共同决定 HIGHMEM 是否有存在的必要。

---

## 18. 与后续 Linux 5.10 源码学习的连接点

理解完本专题后，下一步不应该继续停留在抽象图，而应沿 Linux 5.10 x86-64 源码验证下面几个问题：

```text
1. x86-64 kernel virtual layout 在哪里定义？

2. PAGE_OFFSET / page_offset_base 在 5.10 中如何使用？

3. physical RAM 的 direct mapping 在启动阶段如何建立？

4. __va() / __pa()、phys_to_virt() / virt_to_phys()
   为什么只对特定 mapping 类型成立？

5. max_pfn / max_low_pfn 在 x86-64 中分别意味着什么？

6. arch/x86 如何计算 DMA、DMA32、NORMAL 的 zone PFN 边界？

7. 为什么 x86-64 的 ZONE_NORMAL 能覆盖大量 ordinary RAM，
   而经典 32-bit 需要额外的 ZONE_HIGHMEM？
```

建议后续沿下面的源码目录继续：

```text
arch/x86/include/asm/page_types.h
arch/x86/include/asm/page_64_types.h
arch/x86/mm/init_64.c
arch/x86/mm/init.c
mm/page_alloc.c
include/linux/mmzone.h
```

到这一步，HIGHMEM 就不应该再被视为一个孤立的“zone 名称”，而应该被理解为：

> **32-bit 时代 kernel virtual-address resource 不足在 physical-page allocator 中留下的一种架构性结果。**

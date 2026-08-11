# 地址空间、LOWMEM/HIGHMEM 与 Memory Zone：统一概念模型

本文建立一个统一模型，用来回答下面几个容易混淆的问题：

```text
kernel 为什么位于高虚拟地址？
LOWMEM 为什么又位于低物理地址？
物理内存已经被 kernel direct map 后，用户进程还使用什么内存？
ZONE_DMA、ZONE_NORMAL、ZONE_HIGHMEM 分别为什么存在？
LOWMEM/HIGHMEM 与 ZONE_* 到底是不是同一个概念？
x86-64 下哪些结论仍然成立，哪些已经成为历史背景？
```

核心原则只有两个：

1. **Virtual mapping 不等于 physical allocation，也不等于 ownership。**
2. **Zone 是对 physical pages 的分组；不同 zone 的划分原因可能来自不同类型的地址约束。**

本文先以经典 32-bit x86 Linux 的 3G/1G 布局建立概念，再回到 Linux 5.10 x86-64。

---

## 1. 第一层：先分清三种 address space

讨论 Linux 内存管理时，至少要区分三种地址空间。

### 1.1 CPU virtual address space

CPU 执行普通 load/store 时，软件提供的是虚拟地址：

```text
Virtual Address
      │
      │ MMU + page tables
      ▼
Physical Address
```

32-bit x86 的一个虚拟地址空间最多有 `2^32 = 4 GiB` 地址编号。

经典 3G/1G Linux 布局可以抽象为：

```text
Virtual Address Space

0x00000000
    │
    │ user virtual address space
    │ ~3 GiB
    │
0xC0000000  PAGE_OFFSET
    ├────────────────────────────
    │ kernel virtual address space
    │ ~1 GiB
    │
0xFFFFFFFF
```

因此“kernel 在高地址”中的“高”，首先指的是：

> **kernel 使用高端 virtual address range。**

它并没有说明 kernel 对应的 physical address 是高还是低。

### 1.2 CPU physical address space

物理 RAM 由 physical address / PFN 定位。例如：

```text
PA = 0x02000000
```

表示物理地址 32 MiB 附近。

Virtual address 和 physical address 是两个不同坐标系。页表负责建立二者关系。

因此：

```text
VA 0xC2000000
      │
      │ page-table translation
      ▼
PA 0x02000000
```

完全正常。

不能因为 VA 很高，就推断 PA 也很高。

### 1.3 Device DMA address space

设备执行 DMA 时还有自己的可寻址范围。例如某设备只有 32-bit DMA addressing capability，它能够使用的 DMA 地址范围受到 32-bit 限制。

因此：

```text
CPU virtual-address constraint
CPU physical-address capability
Device DMA-address capability
```

是三个需要分别考虑的问题。

后面的 `ZONE_HIGHMEM` 主要与 **kernel virtual-address scarcity** 有关；而 `ZONE_DMA` / `ZONE_DMA32` 主要与 **device DMA addressability** 有关。

---

## 2. 第二层：kernel 为什么需要 direct mapping

Kernel 自己执行 load/store 时也使用 virtual address。

假设系统存在一个物理页：

```text
PA = 32 MiB
```

kernel 如果需要频繁访问它，最方便的办法不是每次动态建立映射，而是提前建立一块长期存在的线性映射窗口。

经典 32-bit x86 中可以用下面的简化模型理解：

```text
Kernel Virtual Address              Physical Address

0xC0000000  --------------------->  0x00000000
0xC0001000  --------------------->  0x00001000
0xC0002000  --------------------->  0x00002000
...
```

概念上：

```text
kernel_va ≈ PAGE_OFFSET + physical_addr
```

例如：

```text
PA = 0x02000000
VA = 0xC0000000 + 0x02000000
   = 0xC2000000
```

于是同一块 RAM 同时具有：

```text
物理坐标：PA 0x02000000      ← 低物理地址
虚拟坐标：VA 0xC2000000      ← 高 kernel 虚拟地址
```

这就是理解“kernel 在高地址、LOWMEM 却在低地址”时最关键的一步。

两句话分别描述两个不同坐标系：

```text
kernel lives at high virtual addresses

LOWMEM occupies low physical memory
```

二者通过页表/direct mapping 连接起来，并不矛盾。

---

## 3. 第三层：LOWMEM/HIGHMEM 是什么

在经典 32-bit x86 语境下，`LOWMEM` / `HIGHMEM` 首先描述的是 **physical pages 与 kernel permanent mapping 的关系**。

### 3.1 LOWMEM

可以把 LOWMEM 理解为：

> **具有永久 kernel direct mapping 的那部分 physical RAM。**

如果一个 lowmem page 的 PA 是已知的，kernel 通常能够得到一个长期有效的 direct-map VA，并随时解引用。

经典 3G/1G 配置下，kernel 虽然拥有约 1 GiB VA，但这 1 GiB 不能全部拿来 direct-map RAM，因为还需要给 `vmalloc`、`ioremap`、fixmap、模块以及其他特殊映射留出 VA。

因此典型教材经常用“约 896 MiB direct-mapped physical memory”来建立直觉：

```text
Physical RAM

0
│
│ LOWMEM
│ permanently mapped into kernel VA
│
~896 MiB       （经典示意值，并非所有配置的固定常数）
```

对应到 kernel VA：

```text
Kernel Virtual Address

0xC0000000
│
│ direct-map window for LOWMEM
│
~0xF8000000
│
│ vmalloc / fixmap / other mappings
│
0xFFFFFFFF
```

这里 `LOWMEM` 的 `LOW` 是在描述 **physical-memory side**，不是 kernel virtual address 的高低。

### 3.2 HIGHMEM

如果机器的 RAM 大于 kernel 能够永久 direct-map 的物理范围，就会出现剩余 physical pages：

```text
Physical RAM

0
│ LOWMEM
│ permanent kernel mapping
│
~896 MiB
├────────────────────────
│ HIGHMEM
│ no permanent kernel direct mapping
│
RAM end
```

因此 HIGHMEM 的本质不是“CPU 访问不到”，也不是“更慢的 DRAM”，而是：

> **这些 physical pages 没有永久 kernel virtual mapping。**

Kernel 要直接访问 highmem page 时，需要临时建立 kernel mapping，例如历史上的 `kmap()` 一类接口。

所以 HIGHMEM 的根本成因是：

```text
32-bit VA 总量有限
        ↓
kernel 只能取得其中一部分 VA
        ↓
kernel VA 还要承担 direct-map 以外的用途
        ↓
无法永久映射全部 physical RAM
        ↓
LOWMEM / HIGHMEM 分化
```

---

## 4. 一个最容易犯的错误：mapping ≠ allocation

假设机器只有 896 MiB RAM，并且这些 RAM 都属于 LOWMEM、都已经建立 kernel direct mapping。

这不表示：

```text
896 MiB RAM 全部被 kernel 占用了
```

它只表示：

```text
kernel 对这些 physical pages 都有可用的 virtual mapping
```

必须严格区分：

```text
mapping
allocation
ownership / current use
```

### 4.1 Free page 也可以已经被 kernel 映射

Buddy allocator 中一个 `FREE` physical page，仍然可以具有 permanent kernel direct-map VA。

因此：

```text
FREE page             -> 可以有 kernel direct mapping
anonymous user page   -> 可以有 kernel direct mapping
page-cache page       -> 可以有 kernel direct mapping
kernel-owned page     -> 可以有 kernel direct mapping
```

`direct mapping` 是“kernel 如何到达这个 physical page”的属性，而不是“这个 page 当前归谁使用”的属性。

---

## 5. User space 到底使用哪些 physical pages

答案是：

> **用户进程与 kernel 使用的是同一个 physical-page pool；区别在于这些 physical pages 如何被分配、以及映射到哪些 VA。**

假设一个 LOWMEM physical page：

```text
PA = 0x01234000
```

因为它属于 LOWMEM，kernel 已经有 permanent direct-map VA：

```text
Kernel VA
    │
    ▼
PA 0x01234000
```

随后进程 A 发生匿名页缺页。Page allocator 可以把这个 physical page 分配给进程 A，并建立用户页表项：

```text
Process A user VA
        │
        │ user page table
        ▼
+-------------------+
| physical page     |
| PA 0x01234000     |
+-------------------+
        ▲
        │ kernel direct map
        │
Kernel VA
```

于是：

> **同一个 physical page 可以同时被一个 user VA 和一个 kernel VA 映射。**

如果是共享内存，还可能有多个用户 VA 同时指向同一页：

```text
Process A VA ───┐
Process B VA ───┼──> same physical page
Process C VA ───┘
Kernel direct VA ──> same physical page
```

所以：

```text
one physical page
        ↕
can have multiple virtual mappings
```

这也是为什么“一个进程拥有 3 GiB user VA”完全不意味着系统需要为它准备 3 GiB 独立物理 RAM。

VA 是地址编号空间；只有真正建立有效映射、并实际驻留的页面才消耗相应 physical pages。

---

## 6. 第四层：Memory Zone 是另一层抽象

到这里才应该引入 `ZONE_*`。

Zone 是 page allocator 用来组织 **physical page frames** 的结构化分类：

```text
Physical Pages
      │
      │ classified by constraints/capabilities
      ▼
Memory Zones
```

关键点是：

> **不同 zone 并不是因为同一个原因而存在。**

### 6.1 ZONE_DMA：来自设备寻址约束

某些设备只能 DMA 到低物理地址范围。

如果普通 allocation 把这些稀缺的低地址页全部消耗掉，可能出现：

```text
系统还有大量 free RAM

但是

符合该设备 DMA addressing constraint 的 page = 0
```

因此 Linux 将这类特殊低地址 physical pages 单独管理，这就是 `ZONE_DMA` 的主要设计动机。

它的根本约束来自：

> **device DMA address space / DMA addressing capability。**

它不是因为 kernel VA 不够才产生的。

### 6.2 ZONE_NORMAL：普通 kernel-direct-mapped physical pages

经典 32-bit x86 中，除特殊 DMA 低地址区域以外，那些能够由 kernel permanent direct map 正常访问的 ordinary physical pages，主要组成 `ZONE_NORMAL`。

因此 `NORMAL` 的含义可以理解为：

> **对普通 kernel allocation 来说，它们是正常、永久可寻址的 physical pages。**

大量需要长期 kernel pointer 的对象必须依赖这一类可直接访问的内存。

### 6.3 ZONE_HIGHMEM：来自 kernel VA 不足

当 physical RAM 超过 permanent direct-map capacity 后，那些没有永久 kernel mapping 的 physical pages 被组织为 `ZONE_HIGHMEM`。

它的根本约束来自：

> **kernel virtual address space scarcity。**

因此 `ZONE_HIGHMEM` 与 `ZONE_DMA` 的历史成因完全不同：

```text
ZONE_DMA
    <- device addressing constraint

ZONE_HIGHMEM
    <- kernel virtual-address constraint
```

---

## 7. LOWMEM/HIGHMEM 与 ZONE_* 的关系

不能简单写成：

```text
LOWMEM == ZONE_NORMAL
```

因为经典 x86 中，低地址的 `ZONE_DMA` 通常也属于 permanent kernel direct-map 范围。

更好的抽象是：

```text
Mapping property

LOWMEM
├── ZONE_DMA
└── ZONE_NORMAL

HIGHMEM
└── ZONE_HIGHMEM
```

这里：

- `LOWMEM/HIGHMEM` 关注 **physical page 是否有 permanent kernel mapping**；
- `ZONE_*` 关注 **page allocator 如何按照能力和约束管理 physical pages**。

在经典布局中二者边界高度相关，因此教材经常一起讲，但它们不是同一层概念。

---

## 8. 为什么 HIGHMEM 会被称为“cheap”，DMA 会被称为“costly”

一些经典资料会把不同 zone 描述成一种 memory hierarchy：优先消耗“cheap memory”，保护“costly memory”。

这里的 cost 不是 DRAM latency，而是：

> **消耗某类 physical pages 后，对未来 allocation constraints 造成的机会成本。**

在经典 32-bit x86 语境中：

- HIGHMEM 不能承担很多要求 permanent kernel VA 的内核对象，因此用途相对受限；
- NORMAL 可以满足更多 kernel allocations，因此更值得保护；
- DMA pages 还能满足特殊设备的低地址 DMA constraint，因此更加稀缺。

可以理解为：

```text
constraint-specific capability / opportunity cost

HIGHMEM  <  NORMAL  <  DMA
```

但这不是说“所有 allocation 都固定按照 HIGHMEM -> NORMAL -> DMA 搜索”。

真正的页分配过程首先由 GFP flags 等约束决定 **哪些 zone 合法**，再在允许的 zonelist 中进行搜索和 fallback。

因此正确模型是：

```text
allocation requirement / GFP mask
            ↓
确定允许使用的 zone 范围
            ↓
zonelist / NUMA / watermark 等约束
            ↓
在合法候选中寻找 physical pages
```

---

## 9. 将经典 32-bit x86 的完整模型放在一张图里

```text
                      32-bit x86 Linux

1. Virtual-address view
----------------------------------------------------------------
0x00000000
│
│  user virtual address space
│
0xC0000000  PAGE_OFFSET
├──────────────────────────────────────────────────────────────
│
│  kernel virtual address space
│  ┌─────────────────────────────────────┐
│  │ permanent direct map of LOWMEM      │
│  └─────────────────────────────────────┘
│  vmalloc / fixmap / other mappings
│
0xFFFFFFFF

                    │ MMU + page tables
                    ▼

2. Physical-memory view
----------------------------------------------------------------
0
│ ZONE_DMA
│
├──────────────────────────────────────────────────────────────
│ ZONE_NORMAL
│
~ classic LOWMEM limit (often illustrated around 896 MiB)
├──────────────────────────────────────────────────────────────
│ ZONE_HIGHMEM
│
RAM end

3. Mapping-property view
----------------------------------------------------------------
ZONE_DMA + ZONE_NORMAL
        -> LOWMEM
        -> permanent kernel direct mapping

ZONE_HIGHMEM
        -> HIGHMEM
        -> no permanent kernel direct mapping
```

最关键的是：上面第一张图和第二张图使用不同地址坐标系。

---

## 10. x86-64 下哪些东西发生了变化

Linux 5.10 x86-64 的核心变化是 kernel virtual address space 大幅扩大。

因此在典型 x86-64 系统上：

> **经典 32-bit HIGHMEM 问题基本消失。**

系统通常不需要通过 `ZONE_HIGHMEM` 解决“RAM 存在但 kernel VA 不够永久映射”的问题。

更常见的 zone 是：

```text
ZONE_DMA
ZONE_DMA32
ZONE_NORMAL
ZONE_MOVABLE      （取决于配置和内存布局）
```

其中：

- `ZONE_DMA` / `ZONE_DMA32` 仍然体现设备 DMA addressing constraints；
- `ZONE_NORMAL` 成为普通 RAM 的主要 zone；
- `ZONE_MOVABLE` 主要服务于 page migration、memory hotplug/offline、减少不可迁移页对物理内存布局的长期约束，它不是经典 HIGHMEM 的替代物。

因此现代 x86-64 下仍然必须保留的思想是：

> **physical pages 并非完全可互换；page allocator 必须保护具有特殊能力或特殊地址约束的内存。**

但不要把经典教材中的：

```text
HIGHMEM -> NORMAL -> DMA
```

机械套到 x86-64。

Linux 5.10 x86-64 更应该沿下面的路径理解：

```text
allocation request
      ↓
GFP constraints
      ↓
zone eligibility
      ↓
NUMA/node preference
      ↓
zonelist
      ↓
watermark / reclaim / fragmentation constraints
      ↓
buddy allocator
```

---

## 11. 概念层次总结

以后遇到这组概念，可以严格按照下面四层来判断。

### Layer 1：Address spaces

回答：

```text
CPU 当前使用什么 virtual address？
它最终翻译成哪个 physical address？
设备能够 DMA 到哪些地址？
```

### Layer 2：Kernel mapping policy

回答：

```text
哪些 physical pages 有 permanent kernel direct mapping？
```

经典 32-bit x86 因此出现：

```text
LOWMEM / HIGHMEM
```

### Layer 3：Physical-page allocation state

回答：

```text
这个 physical page 当前是 free，
还是 anonymous page、page cache、slab、page table、kernel stack ...？
```

这与“有没有 kernel mapping”不是同一个问题。

### Layer 4：Memory zones

回答：

```text
这个 physical page 能满足哪些 allocation constraints？
Page allocator 应该把它归入哪个 zone 管理？
```

于是才有：

```text
ZONE_DMA
ZONE_DMA32
ZONE_NORMAL
ZONE_HIGHMEM
ZONE_MOVABLE
```

---

## 12. 必须牢记的四句话

```text
1. Virtual address 和 physical address 是两个不同坐标系。

2. Kernel permanent mapping 不等于 kernel ownership。

3. 一个 physical page 可以同时拥有多个 virtual mappings。

4. Zone 是 physical-page allocator 的分类；不同 zone 的成因可能来自不同地址约束。
```

如果这四句话成立，那么下面几件事就同时成立，而且互不矛盾：

```text
kernel 位于高 virtual address；
ZONE_NORMAL 位于较低 physical address；
用户进程可以使用已经被 kernel direct-map 的 physical pages；
32-bit HIGHMEM 来自 kernel VA 稀缺；
DMA zone 来自设备 DMA addressability；
x86-64 可以没有经典 HIGHMEM，但仍然需要 DMA/DMA32 等 zone。
```

这套模型是后续学习 `struct page`、PFN、`pg_data_t`、zone、zonelist、GFP flags、buddy allocator 和 NUMA allocation path 的前置基础。

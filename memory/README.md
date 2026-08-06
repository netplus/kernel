# Linux Kernel 5.10 内存管理课程

本目录研究“虚拟地址如何映射到物理内存、物理页如何分配、对象如何缓存，以及内存不足时如何回收”。

## 课程主线

```text
启动阶段发现物理内存
→ 建立页表和虚拟地址空间
→ 管理物理页
→ 为内核对象和用户进程分配内存
→ 处理缺页
→ 缓存文件数据
→ 回收、压缩或 OOM
```

## 课程大纲

### M00：内存管理全景

- 虚拟地址与物理地址；
- 用户空间与内核空间；
- page、folio 概念在 5.10 前后的关系；
- 页表、物理页分配器、对象分配器、VMA、page cache 的职责边界。

### M01：x86-64 多级页表

- PGD、P4D、PUD、PMD、PTE；
- 虚拟地址拆分；
- page offset；
- present、RW、US、NX、accessed、dirty；
- CR3、TLB、PCID；
- huge page；
- 与 [`assembly/`](../assembly/) 中控制寄存器和异常入口的联系。

### M02：内核虚拟地址布局

- direct mapping；
- kernel text/data；
- vmalloc；
- modules；
- fixmap；
- per-CPU；
- KASLR；
- `virt_to_phys` 的适用边界。

### M03：启动期 Memblock

- firmware/bootloader 提供的内存地图；
- `memblock.memory` 与 `memblock.reserved`；
- region 合并和裁剪；
- early allocation；
- 将可用内存交给伙伴系统。

### M04：Page、Zone、Node 与 NUMA

- `struct page`；
- PFN；
- zone；
- `ZONE_DMA`、`ZONE_DMA32`、`ZONE_NORMAL`；
- `pglist_data`；
- NUMA node；
- zonelist；
- watermarks。

### M05：伙伴系统

- order；
- free area；
- split 与 merge；
- `alloc_pages`；
- GFP flags；
- per-CPU page lists；
- fragmentation；
- slow path。

### M06：SLAB/SLUB 对象分配

- 为什么不能所有小对象都按页分配；
- `kmem_cache`；
- slab、page、object；
- per-CPU freelist；
- partial list；
- `kmalloc` size class；
- redzone、poison、KASAN。

### M07：vmalloc、ioremap 与非连续内存

- 物理连续与虚拟连续；
- `vmalloc`；
- 页表映射；
- `ioremap`；
- MMIO；
- TLB flush；
- `kmalloc` 与 `vmalloc` 的选择。

### M08：进程地址空间与 VMA

- `mm_struct`；
- `vm_area_struct`；
- mmap region；
- code、data、heap、stack、shared library；
- `mmap`、`munmap`、`mprotect`；
- VMA 查找与合并。

### M09：缺页异常

核心路径：

```text
CPU memory access
→ #PF
→ exc_page_fault
→ handle_page_fault
→ do_user_addr_fault
→ handle_mm_fault
```

重点：

- demand paging；
- anonymous fault；
- file fault；
- protection fault；
- stack growth；
- SIGSEGV；
- exception table。

### M10：匿名内存与 Copy-on-Write

- zero page；
- anonymous page；
- fork；
- read-only shared mapping；
- write fault；
- page copy；
- refcount 与 mapcount。

### M11：文件映射与 Page Cache

- address_space；
- radix tree/XArray；
- buffered I/O；
- read fault；
- dirty page；
- writeback；
- readahead；
- mmap 与 read/write 的统一缓存基础。

### M12：内存回收

- LRU；
- active/inactive；
- anonymous/file；
- direct reclaim；
- kswapd；
- shrinker；
- writeback；
- reclaim 与延迟抖动。

### M13：内存压缩与 THP

- external fragmentation；
- compaction；
- migration；
- transparent huge page；
- khugepaged；
- huge fault；
- split huge page。

### M14：NUMA 策略与自动平衡

- local/remote memory；
- NUMA policy；
- first touch；
- automatic NUMA balancing；
- page migration；
- CPU affinity 与内存 locality。

### M15：DMA 与设备内存

- DMA address；
- coherent 与 streaming DMA；
- scatter-gather；
- IOMMU；
- bounce buffer；
- page pinning；
- 网络驱动 RX/TX ring 与 DMA。

### M16：网络栈内存

- `sk_buff`；
- head/data/tail/end；
- page frag；
- `napi_alloc_skb`；
- socket memory accounting；
- TCP send/receive queue；
- zero-copy；
- 与 [`network/`](../network/) 的交叉关系。

### M17：OOM 与内存故障分析

- allocation failure；
- OOM killer；
- badness；
- memcg OOM；
- leak；
- fragmentation；
- `slabtop`、`vmstat`、`buddyinfo`、`pagetypeinfo`；
- crash 中分析 page、slab 和进程地址空间。

## 推荐源码入口

```text
arch/x86/mm/
mm/memblock.c
mm/page_alloc.c
mm/slub.c
mm/vmalloc.c
mm/memory.c
mm/mmap.c
mm/filemap.c
mm/vmscan.c
mm/compaction.c
mm/huge_memory.c
mm/oom_kill.c
include/linux/mm_types.h
include/linux/mm.h
```

## 推荐实验

```text
手工拆解一个虚拟地址的页表索引
查看 /proc/<pid>/maps 与 pagemap
跟踪一次匿名缺页和 COW
观察伙伴系统 order 分布
比较 kmalloc 与 vmalloc
制造 page cache 与回收压力
观察 NUMA locality
分析 skb 和 page frag 的内存布局
```

## 与其他维度的关系

- 汇编：页表、CR3、TLB 和 #PF 入口；
- 调度：NUMA 迁移、内核栈、阻塞回收；
- 时钟：回收、writeback、定时统计与超时；
- 网络：skb、DMA、socket 缓冲区和零拷贝。
# Linux Kernel 5.10 内存管理基础

本目录学习虚拟地址如何映射到物理内存、物理页如何分配、内核对象如何管理，以及内存不足时如何回收。

## 课程主线

```text
启动阶段获得物理内存信息
→ 建立早期页表和内核地址空间
→ 使用 memblock 管理启动期内存
→ 将空闲页交给伙伴系统
→ 使用 SLUB 分配内核对象
→ 建立进程地址空间和 VMA
→ 处理缺页和 Copy-on-Write
→ 回收内存或触发 OOM
```

本阶段重点研究内存管理的基础机制。NUMA 自动平衡、设备 DMA、网络缓冲区、memory cgroup 和复杂的大页优化不在本阶段系统展开。

## 课程大纲

### M00：内存管理概览

- 虚拟地址与物理地址；
- 用户空间与内核空间；
- 页表、物理页分配器、对象分配器、VMA 和 page cache 的职责；
- 启动期内存管理与运行期内存管理的区别。

### M01：x86-64 多级页表

- PGD、P4D、PUD、PMD 和 PTE；
- 虚拟地址拆分；
- 页大小和页内偏移；
- present、RW、US、NX、accessed 和 dirty；
- CR3；
- TLB；
- PCID 只建立基本认识；
- 大页只说明页表层级上的差异。

### M02：内核虚拟地址布局

- kernel text 和 data；
- direct mapping；
- vmalloc 区域；
- modules 区域；
- fixmap；
- per-CPU 区域；
- KASLR；
- 虚拟地址与物理地址转换的适用范围。

### M03：启动期 Memblock

- 固件或引导程序提供的内存地图；
- `memblock.memory`；
- `memblock.reserved`；
- region 合并、裁剪和预留；
- early allocation；
- `crashkernel` 等保留区域；
- 将可用内存交给伙伴系统。

### M04：Page、Zone 和 Node

- `struct page`；
- PFN；
- `ZONE_DMA`、`ZONE_DMA32` 和 `ZONE_NORMAL`；
- `pglist_data`；
- node 和 zone 的关系；
- zonelist；
- watermark；
- NUMA 只讲解理解这些结构所需的基本概念。

### M05：伙伴系统

- order；
- free area；
- block split；
- buddy merge；
- `alloc_pages()`；
- GFP flags；
- per-CPU page lists；
- fragmentation；
- allocation fast path 和 slow path。

### M06：SLUB 对象分配

- 为什么小对象不直接按页分配；
- `kmem_cache`；
- slab、page 和 object；
- per-CPU freelist；
- partial list；
- `kmalloc` size class；
- 对象构造和释放；
- redzone、poison 和 KASAN 只作调试关联说明。

### M07：Vmalloc 和非连续内存

- 物理连续与虚拟连续；
- `vmalloc()`；
- 为非连续物理页建立连续虚拟映射；
- 页表建立和 TLB 刷新；
- `kmalloc` 与 `vmalloc` 的选择；
- `ioremap` 只说明与普通内存映射的区别。

### M08：进程地址空间和 VMA

- `mm_struct`；
- `vm_area_struct`；
- code、data、heap、stack 和 mmap region；
- VMA 查找；
- VMA 合并和拆分；
- `mmap()`、`munmap()` 和 `mprotect()` 只围绕地址空间变化展开。

### M09：缺页异常

核心路径：

```text
CPU 内存访问
→ 页表遍历失败或权限检查失败
→ #PF
→ exc_page_fault
→ handle_page_fault
→ do_user_addr_fault
→ handle_mm_fault
```

重点包括：

- demand paging；
- anonymous fault；
- file-backed fault 的基本过程；
- protection fault；
- stack growth；
- SIGSEGV；
- exception table；
- 缺页处理完成后为什么能够重新执行原指令。

### M10：匿名内存和 Copy-on-Write

- zero page；
- anonymous page；
- fork 后共享只读 PTE；
- write fault；
- 分配新页；
- 复制旧内容；
- 更新 PTE；
- refcount 和 mapcount。

### M11：Page Cache 基础

- `address_space`；
- page cache 的作用；
- buffered read；
- file-backed page fault；
- dirty page；
- writeback；
- readahead 只建立基本认识；
- 本阶段不展开 VFS 和具体文件系统实现。

### M12：内存回收

- anonymous 与 file page；
- active 与 inactive；
- LRU；
- direct reclaim；
- kswapd；
- shrinker；
- dirty page 与 writeback；
- 回收为何可能造成较长延迟。

### M13：分配失败、OOM 和故障分析

- allocation failure；
- watermark 和 reclaim 失败；
- fragmentation；
- OOM killer；
- badness；
- 内存泄漏；
- `vmstat`；
- `buddyinfo`；
- `pagetypeinfo`；
- `slabtop`；
- crash 中查看 page、slab、VMA 和进程地址空间。

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
mm/oom_kill.c
include/linux/mm_types.h
include/linux/mm.h
```

## 推荐实验

```text
手工拆解一个虚拟地址的页表索引
查看进程地址空间布局
跟踪一次匿名缺页
跟踪一次 Copy-on-Write
观察伙伴系统各 order 的空闲页
比较 kmalloc 与 vmalloc
制造可控内存压力并观察回收
使用 crash 查看 page、slab 和 VMA
```

## 与其他主题的关系

- 汇编：CR3、页表、TLB 和缺页异常入口；
- 启动：早期页表、内存地图、memblock 和 crashkernel 预留；
- 调度：缺页、回收和内存等待可能使任务阻塞；
- 时钟：回收和写回中的时间统计与延迟观测；
- Kdump：捕获内核如何访问旧内核物理内存并生成 vmcore。

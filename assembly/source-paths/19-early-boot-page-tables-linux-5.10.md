# A19 源码事实核验：Linux 5.10 x86-64 early boot page tables

本文只核验 A19“早期启动汇编阅读基础”所需的页表事实：compressed kernel 的 `startup_32` 为什么必须在打开 `CR0.PG` 之前构造一套临时页表，这套页表在 Linux v5.10 中如何由汇编逐项写出，以及这些 entry 与物理地址、identity mapping、2 MiB large page 的关系。完整页表机制放在 `memory/`，完整启动流程放在 `boot-crash/`。

## 1. 版本与源码基线

版本：upstream Linux v5.10。

主要文件：

```text
arch/x86/boot/compressed/head_64.S
arch/x86/include/asm/boot.h
```

前置核验见：

- [`19-long-mode-transition-linux-5.10.md`](19-long-mode-transition-linux-5.10.md)

该前置单元已经确认 `startup_32` 在 `CR4.PAE=1` 后先建立 early page tables、把其根地址写入 `CR3`，随后才设置 `EFER.LME` 和 `CR0.PG`。

## 2. 为什么这里必须先有页表

进入 IA-32e paging 不是“先打开 PG，再慢慢准备映射”。当 `CR0.PG` 被置位时，CPU 随后的 instruction fetch 和 data access 已经受 paging structures 控制。因此在打开 paging 之前，`CR3` 必须指向一套能够继续执行当前启动代码的有效页表。

Linux v5.10 compressed `startup_32` 为此建立一套临时的 early 4 GiB identity mapping。它的目的不是表达最终内核虚拟地址布局，而是给模式切换和 decompressor 的早期执行提供足够简单、可预测的地址转换环境。

这里要严格区分：

```text
页表 entry 中保存的 frame/table address
    是 CPU paging walker 使用的物理地址语义

startup_32 当前用来填写这些 entry 的 %edi/%eax
    是当前 32-bit 启动环境中的地址计算结果

identity mapping
    表示被映射范围内 linear address == translated physical address
```

不能因为 identity mapping 数值相同，就把“虚拟地址”和“物理地址”概念合并。

## 3. 页表缓冲区大小：6 个 4 KiB page

`arch/x86/include/asm/boot.h` 在 `CONFIG_X86_64` 下定义：

```c
#define BOOT_INIT_PGT_SIZE (6*4096)
```

`startup_32` 先定位 `pgtable`，然后以：

```asm
movl $(BOOT_INIT_PGT_SIZE/4), %ecx
rep stosl
```

把整个区域清零。

后面的构造正好使用：

```text
pgtable + 0x0000 : 1 page  Level 4 table
pgtable + 0x1000 : 1 page  Level 3 table
pgtable + 0x2000 : 4 pages Level 2 tables
-----------------------------------------
总计                         6 pages = 24 KiB
```

这不是偶然的常量：四个 Level-2 table 每个有 512 个 8-byte entry，每个 table 能用 2 MiB leaf 覆盖 1 GiB，四个 table 合计覆盖 4 GiB。

## 4. Level 4：只建立一个通向 Level 3 的入口

v5.10 `head_64.S` 的 Level-4 构造为：

```asm
leal rva(pgtable + 0)(%ebx), %edi
leal 0x1007(%edi), %eax
movl %eax, 0(%edi)
addl %edx, 4(%edi)
```

核心关系是：

```text
L4[0] -> pgtable + 0x1000
```

低 12 bit 中的 `0x007` 提供该 non-leaf entry 所需的 Present、Read/Write、User 位组合；地址部分指向下一层 Level-3 table。

`%edx` 在此前由 `get_sev_encryption_bit` 路径准备。如果 SEV 未启用，它保持为 0；如果 SEV 启用，代码把高于 bit 31 的 encryption mask 放到 entry 的高 32 bit。因此不能把这里所有 entry 的高 32 bit 无条件写成 0。

## 5. Level 3：四个入口分别指向四张 Level-2 table

Level-3 构造为：

```asm
leal rva(pgtable + 0x1000)(%ebx), %edi
leal 0x1007(%edi), %eax
movl $4, %ecx
1:
    movl %eax, 0x00(%edi)
    addl %edx, 0x04(%edi)
    addl $0x00001000, %eax
    addl $8, %edi
    decl %ecx
    jnz 1b
```

因此四个 entry 的地址部分依次指向：

```text
L3[0] -> pgtable + 0x2000
L3[1] -> pgtable + 0x3000
L3[2] -> pgtable + 0x4000
L3[3] -> pgtable + 0x5000
```

每次 `%eax += 0x1000` 是移动到下一张 4 KiB Level-2 table；每次 `%edi += 8` 是移动到下一个 64-bit page-table entry。

这四个 L3 entry 本身不是 1 GiB leaf。真正的 leaf 在下一层 Level 2。

## 6. Level 2：2048 个 2 MiB leaf 建立 4 GiB identity mapping

Level-2 构造是本单元最重要的循环：

```asm
leal rva(pgtable + 0x2000)(%ebx), %edi
movl $0x00000183, %eax
movl $2048, %ecx
1:
    movl %eax, 0(%edi)
    addl %edx, 4(%edi)
    addl $0x00200000, %eax
    addl $8, %edi
    decl %ecx
    jnz 1b
```

这里有三个需要分别核验的事实。

### 6.1 `2048 × 2 MiB = 4 GiB`

循环执行 2048 次，每次 leaf physical base 增加 `0x00200000`，即 2 MiB：

```text
entry 0    -> physical 0x00000000
entry 1    -> physical 0x00200000
entry 2    -> physical 0x00400000
...
entry 2047 -> physical 0xffe00000
```

因此总覆盖范围是 `[0, 4 GiB)`。

### 6.2 `0x183` 表示这是 2 MiB leaf

`0x183` 的低位包含：

```text
bit 0   Present
bit 1   Read/Write
bit 7   Page Size
bit 8   Global
```

其中 Page Size 位使 Level-2 entry 成为 2 MiB leaf，而不是再指向 Level-1/PT。于是这套 early mapping 不需要额外 2048 张 4 KiB PTE table。

A19 只需要理解这种“用 large page 减少早期页表层级和内存占用”的直接效果；PSE/PAT、TLB、global-page 生命周期等完整机制不在这里展开。

### 6.3 地址值本身形成 identity mapping

leaf 的 address field 从 0 开始，每次正好增加 2 MiB。与此同时 L4[0]、L3[0..3] 覆盖的是低 canonical linear-address range。因此 linear `0..4 GiB` 被映射回同值 physical `0..4 GiB`。

identity mapping 是“转换前后的数值关系”，不是“paging 没有发生”。打开 paging 后，CPU 仍然执行完整 page walk，只是最终 physical address 与 linear address 数值相等。

## 7. 为什么只需要四张 Level-2 table

在四级 IA-32e paging 中，本路径只使用 L4[0]。一个 Level-3 entry 配合一张包含 512 个 2 MiB leaf 的 Level-2 table，可以覆盖：

```text
512 × 2 MiB = 1 GiB
```

因此：

```text
L3[0] -> L2 #0 -> 0..1 GiB
L3[1] -> L2 #1 -> 1..2 GiB
L3[2] -> L2 #2 -> 2..3 GiB
L3[3] -> L2 #3 -> 3..4 GiB
```

这解释了源码中的三个常量为什么彼此一致：

```text
4       Level-3 entries
2048    Level-2 leaf entries
6 pages BOOT_INIT_PGT_SIZE
```

## 8. `CR3` 接收的是 early root 的地址

构造完成后源码执行：

```asm
leal rva(pgtable)(%ebx), %eax
movl %eax, %cr3
```

这里写入 `CR3` 的是 Level-4 root 的地址。随后 `EFER.LME` 和 `CR0.PG` 被设置时，CPU 才开始使用这套 paging structures 进行地址转换。

因此时间关系必须写成：

```text
clear/build tables
    -> CR3 = early L4 root
    -> EFER.LME = 1
    -> CR0.PG = 1
    -> paging translation becomes active
    -> far control transfer reloads CS
    -> .code64 startup_64
```

不能把“页表已经写到内存”“CR3 已经装载”“paging 已经启用”写成同一个时刻。

## 9. SEV encryption bit 是 entry 地址域的条件修饰

在清表之前，`startup_32` 调用 `get_sev_encryption_bit`。如果 SEV active，源码把 encryption bit 转换为高 32-bit mask 保存在 `%edx`，随后对 L4/L3/L2 entry 都执行：

```asm
addl %edx, 4(%edi)
```

因此 v5.10 的实际 early-table 构造并不是永远只写低 32 bit。A19 不展开 SEV 的加密内存机制，但源码事实必须记录这个条件路径，否则对 64-bit entry 写入过程的描述是不完整的。

## 10. 这套页表不是最终 kernel page table

这套 `pgtable` 的教学意义是“让 compressed startup 能安全跨过 paging/long-mode 切换并继续早期执行”。不能由此推出：

- Linux 最终只 identity-map 低 4 GiB；
- Linux 最终只使用 2 MiB page；
- kernel 最终虚拟地址等于物理地址；
- 这里已经建立了完整 direct map；
- 这里已经完成 KASLR、decompressor 或最终 `init_top_pgt` 的所有映射。

这些属于后续 boot/memory 主线。

## 11. 与 5-level paging 的边界

本单元描述的是 `startup_32` 为进入 long mode 建立的四级形式 early mapping。v5.10 后续 `startup_64` 还包含针对 4-level/5-level paging 状态的处理，并可能借助 trampoline 改变 `CR4.LA57`。

因此不能把本单元的 L4/L3/L2 三层实际使用方式泛化成“Linux v5.10 永远只使用四级页表”。A19 只要求能够读懂当前汇编片段。

## 12. 最小源码执行模型

```text
startup_32
    |
    |-- CR4.PAE = 1
    |
    |-- get_sev_encryption_bit()
    |       -> optional high-bit mask in %edx
    |
    |-- zero BOOT_INIT_PGT_SIZE = 6 pages
    |
    |-- L4[0] -> L3
    |
    |-- L3[0..3] -> four L2 tables
    |
    |-- L2[0..2047]
    |       -> 2048 x 2 MiB leaf
    |       -> identity map [0, 4 GiB)
    |
    |-- CR3 = pgtable root
    |
    |-- EFER.LME = 1
    |-- CR0.PG = 1
    v
CPU starts using the early mapping
```

## 13. 后续教程必须避免的误区

1. 不把 `pgtable` 当前地址计算表达式直接称为“虚拟地址写进 CR3”；CR3/page-table address field 是物理地址语义。
2. 不把 identity mapping 解释成“没有页表转换”。
3. 不把 L3 的四个 entry 误写成四个 1 GiB huge-page leaf；它们指向四张 L2 table。
4. 不把 `0x183` 只解释为地址常量；其低位包含 page-table flags，其中 PS 使 L2 entry 成为 2 MiB leaf。
5. 不忽略每个 entry 是 64 bit，而 32-bit startup 用两个 32-bit 写操作构造它；高 32 bit 还可能包含 SEV encryption mask。
6. 不把 `BOOT_INIT_PGT_SIZE=6*4096` 当成无来源的 magic number；它与 1 L4 + 1 L3 + 4 L2 的布局严格对应。
7. 不把这套 early 4 GiB identity mapping 当成最终 kernel address-space layout。
8. 不在 assembly 课程扩展完整 page-table API、页表生命周期、direct map 或 KASLR；这里只保留读懂 `head_64.S` 所需的汇编基础。

## 14. 本次核验结论

Linux v5.10 compressed `startup_32` 的 early page table 可以精确概括为：用 24 KiB 连续空间构造 `1×L4 + 1×L3 + 4×L2`，L2 中写入 2048 个 2 MiB leaf，从而 identity-map 低 4 GiB；完成后把 L4 root 装入 CR3，再进入 EFER/CR0 的 long-mode 激活阶段。SEV active 时 entry 的高位还会加入 encryption mask。

这一单元已经足以支撑 A19 后续教程解释“早期汇编如何手工构造 page-table entries”；完整页表设计仍留在 memory 课程。

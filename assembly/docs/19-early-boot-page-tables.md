# A19 第二部分：早期页表的汇编构造

本节解决一个很具体的问题：Linux 5.10 compressed kernel 的 `startup_32` 在打开 `CR0.PG` 之前，为什么必须先准备页表，以及汇编代码如何用一小段连续内存手工构造出足以跨过 long-mode 切换的映射。

完整页表机制属于 `memory/`，完整启动过程属于 `boot-crash/`。这里仅保留读懂 `arch/x86/boot/compressed/head_64.S` 所需的地址计算、entry 布局、循环和控制寄存器关系。

Linux 5.10 源码事实基线见：[`../source-paths/19-early-boot-page-tables-linux-5.10.md`](../source-paths/19-early-boot-page-tables-linux-5.10.md)。前置模式切换教程见：[`19-long-mode-transition-basics.md`](19-long-mode-transition-basics.md)。

## 1. 为什么打开 paging 之前页表必须已经可用

`CR0.PG` 不是“允许以后再使用页表”的准备位。它生效后，处理器后续的 instruction fetch 和 data access 就会按照当前 paging state 做地址转换。

因此 Linux 不能采用下面的顺序：

```text
CR0.PG = 1
-> 再创建页表
```

因为第二步本身就需要继续取指和访问内存，而 CPU 此时已经要求一套有效的 paging structures。

正确的依赖关系是：

```text
先在内存中构造有效页表
-> CR3 指向页表根
-> 设置 EFER.LME
-> 设置 CR0.PG
-> CPU 开始通过该页表继续取指
-> far control transfer 重新装载 CS
-> startup_64
```

所以 early page table 首先是一个“让 CPU 在模式切换期间还能继续执行”的过渡设施，而不是最终 kernel virtual address layout。

## 2. Linux 5.10 为什么只准备 24 KiB

在 `CONFIG_X86_64` 下，Linux v5.10 定义：

```text
BOOT_INIT_PGT_SIZE = 6 * 4096 = 24 KiB
```

`startup_32` 将这块区域清零，然后按如下方式使用：

```text
pgtable + 0x0000   1 x L4 table
pgtable + 0x1000   1 x L3 table
pgtable + 0x2000   L2 table #0
pgtable + 0x3000   L2 table #1
pgtable + 0x4000   L2 table #2
pgtable + 0x5000   L2 table #3
```

关键在于 L2 使用 2 MiB leaf。每张 L2 table 有 512 个 8-byte entry，因此一张表能够覆盖：

```text
512 * 2 MiB = 1 GiB
```

四张 L2 table 就能覆盖 4 GiB，所以不需要为这一临时映射继续分配大量 L1/PTE table。

## 3. 先把层级关系画出来

这套页表真正使用的层级很简单：

```text
L4[0]
  |
  v
L3
  |-- L3[0] -> L2 #0 ->   0 .. 1 GiB
  |-- L3[1] -> L2 #1 -> 1 GiB .. 2 GiB
  |-- L3[2] -> L2 #2 -> 2 GiB .. 3 GiB
  `-- L3[3] -> L2 #3 -> 3 GiB .. 4 GiB
```

这里必须注意：四个 L3 entry **不是四个 1 GiB leaf**。它们仍然是 non-leaf entry，分别指向四张 L2 table。真正结束 page walk 的 leaf 是 L2 entry。

## 4. 为什么 L2 可以直接结束 page walk

L2 leaf 的初始低位值是 `0x183`。把它拆开：

```text
bit 0   P   Present
bit 1   RW  writable
bit 7   PS  page size
bit 8   G   global
```

对本节最重要的是 bit 7，也就是 PS。它告诉 CPU：这个 L2 entry 直接描述一个 2 MiB mapping，不要继续走到 L1/PT。

因此第一个 leaf 可以抽象成：

```text
physical base = 0x00000000
flags         = 0x183
entry         = 0x0000000000000183
```

第二个 leaf 的 physical base 增加 2 MiB：

```text
physical base = 0x00200000
entry low     = 0x00200183
```

以后每个 entry 都按相同规律递增。

## 5. 2048 个 leaf 为什么恰好覆盖 4 GiB

`startup_32` 的 L2 循环执行 2048 次，每次 physical base 增加 `0x00200000`：

```text
leaf 0       -> 0x00000000
leaf 1       -> 0x00200000
leaf 2       -> 0x00400000
...
leaf 2047    -> 0xffe00000
```

因此覆盖长度为：

```text
2048 * 2 MiB = 4096 MiB = 4 GiB
```

最后一个 leaf 从 `0xffe00000` 开始，覆盖到 `0xffffffff` 所在的最后一个 2 MiB 区间；整个映射范围可以写成 `[0, 4 GiB)`。

这也把源码中的三个数字联系起来了：

```text
4 个 L3 entry
2048 个 L2 leaf
6 个 4 KiB page 的页表缓冲区
```

它们不是三个独立 magic number，而是同一个映射设计的不同结果。

## 6. identity mapping 到底意味着什么

这些 L2 leaf 的 physical base 从 0 开始，按 2 MiB 顺序增长；上层 L4/L3 又覆盖低 linear-address range。因此得到：

```text
linear 0x00000000 -> physical 0x00000000
linear 0x00200000 -> physical 0x00200000
...
```

这叫 identity mapping。

但 identity mapping **不表示 paging 没有发生**。`CR0.PG=1` 后 CPU 仍然进行正常 page walk：

```text
linear address
-> L4 index
-> L3 index
-> L2 entry
-> 2 MiB page offset
-> physical address
```

只是最终 physical address 的数值恰好等于输入 linear address。

## 7. 手工推导一个地址

假设访问：

```text
linear = 0x12345678
```

它位于低 1 GiB，所以经过 `L4[0] -> L3[0]`。

先求它属于第几个 2 MiB region：

```text
0x12345678 / 0x200000 = 0x91，余数 0x145678
```

因此使用 L2 #0 中的 entry `0x91`。该 leaf 的 physical base 是：

```text
0x91 * 0x200000 = 0x12200000
```

再加 2 MiB page 内 offset：

```text
0x12200000 + 0x145678 = 0x12345678
```

这正是 identity mapping。

读 `head_64.S` 时，能够做这种手算比背诵页表术语更重要：你可以直接检查汇编循环生成的 entry 是否真的覆盖了当前执行地址。

## 8. 汇编为什么每次让 `%edi` 增加 8

IA-32e page-table entry 是 64 bit，即 8 bytes。虽然 `startup_32` 此时运行的是 32-bit code，但页表格式仍然要求 64-bit entry。

因此循环中：

```text
%edi += 8
```

表示前进到下一个 entry，而不是前进到下一个 4-byte integer。

源码分别写 entry 的低 32 bit 和高 32 bit。这一点很重要：不能因为当前汇编使用 `movl`，就把 entry 错看成 32 bit。

## 9. SEV 条件路径为什么会修改 entry 高 32 bit

Linux v5.10 在构造这些 entry 前会取得 SEV encryption bit。未启用 SEV 时，对应 mask 为 0；启用时，entry 的高 32 bit 会加入 encryption mask。

所以源码中对 64-bit entry 的构造可以抽象为：

```text
low 32 bits  = table/leaf address low part + flags
high 32 bits = address high part + optional SEV encryption mask
```

A19 不展开 SEV 的内存加密机制，但阅读汇编时必须知道为什么代码还会写 `4(%edi)`；不能把这条写操作当成无意义清零。

## 10. `CR3` 是页表构造与 paging 生效之间的交接点

页表写完后，`startup_32` 把 early L4 root 的地址写入 `CR3`。

三个时刻必须分开：

```text
T1: tables built
    内存中已有有效 entry，但 CPU 尚未因此自动使用它们

T2: CR3 loaded
    CPU 已知道 paging root 在哪里，但 CR0.PG 尚未打开

T3: CR0.PG set
    后续取指和数据访问开始受 paging translation 控制
```

这也是为什么第一部分的 long-mode 教程把 page-table construction 放在 `EFER.LME` 和 `CR0.PG` 之前。

## 11. 这套映射为什么适合 early startup

它有三个直接优点。

第一，结构小。只用 24 KiB，就覆盖低 4 GiB。

第二，地址关系简单。identity mapping 让模式切换前后的早期代码不需要立即处理复杂的虚实地址差异。

第三，构造容易。L2 leaf physical base 只是一个从 0 开始、每次增加 2 MiB 的等差序列，适合在 `startup_32` 中用简单循环写出。

这些都是 early bootstrap 的设计取舍，不代表 Linux 最终页表也采用同样布局。

## 12. 不要把 early mapping 当成最终 kernel address space

从这一段汇编不能推出：

- Linux 最终只映射低 4 GiB；
- kernel virtual address 永远等于 physical address；
- Linux 最终全部使用 2 MiB page；
- direct map 已经在这里完整建立；
- KASLR 或最终 kernel page table 已经完成。

本节只解释 compressed `startup_32` 为模式切换建立的临时映射。最终页表布局和生命周期应在 `memory/` 与 `boot-crash/` 中学习。

## 13. 与 5-level paging 的边界

本节分析的具体片段使用的是这套 early 四级形式结构。Linux 5.10 后续还需要处理 4-level/5-level paging 状态，并可能涉及 `CR4.LA57` 的转换。

因此这里的结论是：

> v5.10 compressed `startup_32` 在当前模式切换阶段用 `1 x L4 + 1 x L3 + 4 x L2` 建立低 4 GiB early identity mapping。

而不是：

> Linux 5.10 永远只使用四级页表。

## 14. 把整个执行过程串起来

现在可以把 A19 第一、第二部分连接起来：

```text
startup_32
  |
  |-- establish protected-mode prerequisites
  |-- CR4.PAE = 1
  |
  |-- reserve/clear 24 KiB pgtable area
  |-- L4[0] -> L3
  |-- L3[0..3] -> four L2 tables
  |-- L2[0..2047] -> 2048 x 2 MiB leaf
  |-- identity map [0, 4 GiB)
  |-- CR3 = early L4 root
  |
  |-- EFER.LME = 1
  |-- CR0.PG = 1
  |     CPU now uses the early mapping
  |
  |-- lret reloads CS
  v
startup_64
```

这里最重要的不是记住每条 `movl`，而是看懂每条汇编指令正在建立哪一个 CPU 后续执行所依赖的状态。

## 15. 本节检查点

学完本节，应能够独立回答：

1. 为什么 `CR0.PG` 置位前必须已经有有效页表？
2. 为什么 `BOOT_INIT_PGT_SIZE` 恰好是 6 个 page？
3. L4、L3、L2 在这套 early mapping 中分别用了多少 entry？
4. 为什么 L3 entry 不是 1 GiB leaf，而 L2 entry 是 2 MiB leaf？
5. `0x183` 中哪些 bit 对本节最关键？
6. 为什么 2048 个 leaf 恰好覆盖 4 GiB？
7. identity mapping 为什么仍然需要 page walk？
8. 为什么 32-bit `startup_32` 仍然要按 8-byte entry 前进？
9. SEV 为什么会让 entry 高 32 bit 的写入不能被忽略？
10. 页表写完、CR3 装载和 CR0.PG 生效为什么是三个不同时间点？

如果这些问题都能从源码中的地址计算和循环直接推导出来，就已经具备继续阅读 `head_64.S` 早期页表汇编的基础。
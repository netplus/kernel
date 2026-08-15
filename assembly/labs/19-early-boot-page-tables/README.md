# A19 实验：静态验证 early boot page tables

本实验验证 Linux 5.10 compressed `startup_32` 早期页表构造中的**可由源码和算术直接确认**的事实。正文见 [`../../docs/19-early-boot-page-tables.md`](../../docs/19-early-boot-page-tables.md)，Linux 5.10 源码事实基线见 [`../../source-paths/19-early-boot-page-tables-linux-5.10.md`](../../source-paths/19-early-boot-page-tables-linux-5.10.md)。

完整页表机制属于 `memory/`。这里不验证最终 kernel address space，只验证读懂 `arch/x86/boot/compressed/head_64.S` 所需的 early mapping 算术和 entry 布局。

## 1. 要验证什么

本实验有五个独立检查点：

1. `BOOT_INIT_PGT_SIZE = 6 * 4096 = 24 KiB` 与 `1 x L4 + 1 x L3 + 4 x L2` 的布局一致；
2. 每张 4 KiB table 有 `4096 / 8 = 512` 个 64-bit entry，四张 L2 table 共 2048 个 leaf；
3. `2048 * 2 MiB = 4 GiB`，因此能够覆盖 `[0, 4 GiB)`；
4. `0x183` 的 P/RW/PS/G 位与 2 MiB L2 leaf 语义一致，US 为 0；
5. 对低 4 GiB 的若干 linear address，按 L3 index、L2 index 和 2 MiB offset 手工推导后，最终 physical address 与 linear address 相同。

实验还检查四个 L3 entry 指向相对于 `pgtable` 基址的 `+0x2000/+0x3000/+0x4000/+0x5000` 四张连续 L2 page。

## 2. 运行脚本

需要 Python 3：

```bash
cd assembly/labs/19-early-boot-page-tables
python3 verify_early_pgtable.py
```

脚本内部使用 `assert` 做硬验收，并打印布局、flag 解码和若干地址的 page-walk 算术。

本实验不把脚本输出当作 Linux 运行时页表 dump。它只是把 v5.10 源码中的常量和循环转换成可重复计算的验证。

## 3. 手工复核 `0x183`

可以不用脚本，直接计算：

```text
0x183 = 0x100 + 0x80 + 0x2 + 0x1
```

因此：

```text
bit 0  P  = 1
bit 1  RW = 1
bit 2  US = 0
bit 7  PS = 1
bit 8  G  = 1
```

本实验只使用这些与当前 early mapping 直接相关的位。不要由此扩展成完整 x86 page-table flag 教程。

## 4. 手工复核地址 `0x12345678`

2 MiB leaf 的 offset 是低 21 bit。对：

```text
linear = 0x12345678
```

应得到：

```text
L3 index = 0
L2 index = 0x91
2 MiB offset = 0x145678
leaf physical base = 0x12200000
physical = 0x12200000 + 0x145678 = 0x12345678
```

这验证的是 identity mapping 的数值关系，而不是“没有 paging”。

## 5. 边界地址

脚本还检查：

```text
0x00000000
0x001fffff
0x00200000
0x40000000
0xffe00000
0xffffffff
```

其中 `0x001fffff -> 0x00200000` 跨过第一个 2 MiB leaf 边界；`0x3fffffff -> 0x40000000` 对应从 L3[0] 覆盖范围进入 L3[1]；`0xffffffff` 位于最后一个 leaf 中。

## 6. 与 Linux 5.10 源码对照

在可用的 v5.10 checkout 中，至少核对：

```bash
grep -n 'BOOT_INIT_PGT_SIZE' arch/x86/include/asm/boot.h
grep -n -A80 -B20 'startup_32:' arch/x86/boot/compressed/head_64.S
```

重点找出：

```text
rep stosl                 清 6-page pgtable area
L4[0]                     指向 +0x1000
4-entry loop              L3[0..3] -> +0x2000..+0x5000
2048-entry loop           L2 2 MiB leaves
addl $0x00200000, %eax    leaf physical base 每次增加 2 MiB
addl $8, %edi             前进一个 64-bit entry
movl %eax, %cr3           装载 early root
```

还应注意 `get_sev_encryption_bit` 与 `addl %edx, 4(%edi)`：脚本按 SEV mask 为 0 的基础情况做地址算术，不声称高 32 bit 在所有配置下恒为 0。

## 7. 当前执行状态

本实验文件已完成静态设计。当前维护环境只有 GitHub 内容接口，没有仓库 checkout 或 shell，因此本次无法实际执行 `python3 verify_early_pgtable.py`，也无法对本地 v5.10 tree 执行 `grep/objdump`。这些结果不得写成实测值。

脚本只使用 Python 标准语法和整数运算；下一单元的 `expected-analysis.md` 将固定输出关系、边界地址与 SEV 条件路径的验收标准，并在有可执行 checkout 的环境中补实际运行记录。

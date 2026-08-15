# A19 early boot page tables 实验预期分析

本文给 [`README.md`](README.md) 中的静态实验提供独立验收基线。它验证的是 Linux 5.10 compressed `startup_32` 为进入长模式准备的临时页表结构和地址算术，不把它扩展为完整的 x86 页表课程。

正文见 [`../../docs/19-early-boot-page-tables.md`](../../docs/19-early-boot-page-tables.md)，Linux 5.10 源码事实基线见 [`../../source-paths/19-early-boot-page-tables-linux-5.10.md`](../../source-paths/19-early-boot-page-tables-linux-5.10.md)。

## 1. 六页布局必须同时满足容量和层级关系

基础配置下：

```text
BOOT_INIT_PGT_SIZE = 6 * 4096 = 24576 bytes = 24 KiB
```

六张 4 KiB page 的角色应解释为：

```text
pgtable + 0x0000 : L4
pgtable + 0x1000 : L3
pgtable + 0x2000 : L2 #0
pgtable + 0x3000 : L2 #1
pgtable + 0x4000 : L2 #2
pgtable + 0x5000 : L2 #3
```

每张表有 `4096 / 8 = 512` 个 64-bit entry。四张 L2 因此共有：

```text
4 * 512 = 2048 leaf entries
```

每个 L2 leaf 映射 2 MiB，所以覆盖范围必须为：

```text
2048 * 2 MiB = 4096 MiB = 4 GiB
```

硬验收关系是 `[0, 4 GiB)`，不是“包含地址 4 GiB”。`0xffffffff` 仍在映射内，而 `0x100000000` 已超出该临时 identity map 的覆盖范围。

## 2. L3 到 L2 的四个目标必须连续

相对于 `pgtable` 基址，四个 L3 entry 应分别指向：

```text
+0x2000
+0x3000
+0x4000
+0x5000
```

这四个 entry 本身不是 1 GiB leaf。它们继续指向 L2 table；真正承担大页 leaf 语义的是后面的 L2 entries。

因此不能只根据“每个 L3 entry 覆盖 1 GiB linear range”就把它们解释成 1 GiB huge-page entries。层级覆盖范围与 entry 是否为 leaf 是两个问题。

## 3. `0x183` 的最小 flag 解码

对本实验需要的位：

```text
0x183 = 0x100 + 0x80 + 0x2 + 0x1
```

应得到：

```text
P  (bit 0) = 1
RW (bit 1) = 1
US (bit 2) = 0
PS (bit 7) = 1
G  (bit 8) = 1
```

其中最关键的是 `PS=1`：在 L2 层它使 entry 直接描述 2 MiB leaf，因此 page walk 不再继续到 L1/PTE。

本实验不从 `0x183` 推导未参与当前结论的其他页表属性。

## 4. 地址推导必须使用 2 MiB leaf 的位宽

对于低 4 GiB linear address：

```text
L3 index     = (linear >> 30) & 0x1ff
L2 index     = (linear >> 21) & 0x1ff
2 MiB offset = linear & ((1 << 21) - 1)
leaf number  = L3_index * 512 + L2_index
leaf base    = leaf_number * 2 MiB
physical     = leaf base + offset
```

基础 identity-map 情况下，最终必须满足：

```text
physical == linear
```

这里的“identity”只表示 linear 与 physical 的数值相同；CPU 在 `CR0.PG=1` 后仍然执行正常的 page walk。

### `0x12345678` 的验收值

应得到：

```text
L3 index     = 0
L2 index     = 0x91
2 MiB offset = 0x145678
leaf base    = 0x12200000
physical     = 0x12345678
```

脚本和手工计算必须一致。

## 5. 边界地址的预期关系

下列地址用于检查 index 进位，而不只是检查一般样本：

```text
0x001fffff : L3=0, L2=0,   offset=0x1fffff
0x00200000 : L3=0, L2=1,   offset=0
0x3fffffff : L3=0, L2=511, offset=0x1fffff
0x40000000 : L3=1, L2=0,   offset=0
0xffe00000 : L3=3, L2=511, offset=0
0xffffffff : L3=3, L2=511, offset=0x1fffff
```

因此：

- `0x001fffff -> 0x00200000` 必须体现 L2 index 从 0 进到 1；
- `0x3fffffff -> 0x40000000` 必须体现 L2 从 511 回到 0，同时 L3 从 0 进到 1；
- `0xffffffff` 必须落在第四张 L2 table 的最后一个 leaf 中。

当前 `verify_early_pgtable.py` 已把上述六个边界地址全部纳入自动断言。对边界样本不仅要求 `physical == linear`，还会分别断言 `(L3 index, L2 index, offset)`，因此不能再由 identity-address 相等掩盖 index 进位错误。

## 6. 三个时间点不能混为一谈

源码阅读时必须分别记录：

```text
A. page-table entries 已经写入内存
B. early root physical address 已写入 CR3
C. CR0.PG 已置位，paging 开始参与地址翻译
```

A 不意味着 CPU 已使用这些表；B 也不意味着 paging 已经开启。只有到 C，当前取指和数据访问才真正受该 page-table hierarchy 约束。

这也是本实验与 A19 第一部分长模式切换实验的交接点：early mapping 必须在打开 paging 前已经准备好，但“paging 已生效”仍不等于“当前 instruction stream 已经使用 64-bit code segment”。

## 7. SEV 条件路径的验收边界

基础脚本只验证 encryption mask 为 0 时的地址算术。Linux 5.10 compressed startup 还存在 SEV 条件路径：源码会取得 encryption bit/mask，并可能修改 64-bit page-table entry 的高 32 bit。

因此验收时只能说：

```text
基础地址布局和 index/coverage 算术保持成立；
entry 的高 32 bit 不能被概括为所有配置下恒为 0。
```

不能把基础脚本输出推广成 SEV active 环境下完整 entry 的运行时值。

## 8. 脚本自身的验收标准

运行：

```bash
python3 verify_early_pgtable.py
```

硬验收条件包括：

```text
pgtable size == 24 KiB
entries per table == 512
L2 leaves == 2048
coverage == 4 GiB
0x183 -> P=1,RW=1,US=0,PS=1,G=1
L3 targets == +0x2000,+0x3000,+0x4000,+0x5000
所有 samples 的 physical == linear
六个边界 samples 的 L3/L2/offset 与第 5 节逐项一致
```

脚本使用 `assert`，任一硬关系失败都应视为实验失败并回到源码/算术重新核对。

## 9. 当前验证状态

2026-08-15 已把仓库中的 `verify_early_pgtable.py` 按原逻辑实际执行一遍，所有断言通过。关键样本结果为：

```text
0x00000000 : L3=0, L2=0,   offset=0x000000, physical=0x00000000
0x001fffff : L3=0, L2=0,   offset=0x1fffff, physical=0x001fffff
0x00200000 : L3=0, L2=1,   offset=0x000000, physical=0x00200000
0x12345678 : L3=0, L2=145, offset=0x145678, physical=0x12345678
0x3fffffff : L3=0, L2=511, offset=0x1fffff, physical=0x3fffffff
0x40000000 : L3=1, L2=0,   offset=0x000000, physical=0x40000000
0xffe00000 : L3=3, L2=511, offset=0x000000, physical=0xffe00000
0xffffffff : L3=3, L2=511, offset=0x1fffff, physical=0xffffffff
```

这次执行验证了脚本自身的 Python 算术、flag 解码和边界断言；它**没有**替代 Linux v5.10 tree 的 Kbuild/`objdump` 或 QEMU/GDB 早期启动现场验证。特别是 SEV encryption mask、真实页表物理地址以及 CR3/CR0 的运行时值仍不能由该脚本推出。

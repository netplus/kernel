# B06 upstream Linux v5.10 source audit — 2026-08-24

本记录是 B06 在自动验收仍待执行期间的一次独立源码事实复核。它只建立 **upstream source provenance / manual L1 evidence**，不能替代 `verify_source_contract.py` 的真实 7/7 执行，也不能替代当前 exact 22-case fixture 的 `22 tests / OK`。

## 固定事实基线

```text
repository: torvalds/linux
ref:        v5.10
commit:     2c85ebc57b3e1817b6ce1a6b703928e113a90442
```

本次按精确 commit 重新读取 B06 checker 涉及的四个 upstream 文件，Git blob 与既有基线一致：

```text
kernel/kexec.c
  c82c6c06f0518f3591de33431904d60175e69bc2
kernel/kexec_file.c
  e21f6b9234f7a2dbcfe17df61d1611b5d3bbb9d7
kernel/kexec_core.c
  8798a8183974e3b3d52ac53dc4b981f4055f0b52
arch/x86/kernel/machine_kexec_64.c
  a29a44a98e5bef10751af769bd198d783e23b9fd
```

## 本次重新核验的实现事实

1. `kernel/kexec.c` 的 `kexec_load` 仍通过 `do_kexec_load()` 进入 traditional loader 主线；源码注释明确区分 generic load、设备收缩和 machine-specific transition 三部分。
2. `kernel/kexec_file.c::kimage_file_alloc_init()` 由 `KEXEC_FILE_ON_CRASH` 形成 `kexec_on_panic`；crash image 设置 `image->type = KEXEC_TYPE_CRASH`，而 `image->swap_page` 只在 `!kexec_on_panic` 时分配。`kexec_file_load()` 默认选择 `&kexec_image`，crash flag 下改为 `&kexec_crash_image`。
3. `kernel/kexec_core.c::sanity_check_segment_list()` 在 `image->type == KEXEC_TYPE_CRASH` 时逐 segment 检查目标范围，要求 `mstart >= phys_to_boot_phys(crashk_res.start)` 且 `mend <= phys_to_boot_phys(crashk_res.end)`，否则返回 `-EADDRNOTAVAIL`。
4. `arch/x86/kernel/machine_kexec_64.c::init_pgtable()` 仍通过 `kernel_ident_mapping_init()` 为已有 `pfn_mapped` 范围以及 image segments 建立 transition 所需 identity mappings；页表页分配回调仍由 `alloc_pgt_page()` 调用 `kimage_alloc_control_pages(image, 0)`。

## 证据边界

本次读取来自精确 upstream commit，并重新确认四个 blob identity，因此可以证明 B06 当前人工源码事实基线没有因上游引用漂移而改变。但这些文件没有被 materialize 成可供课程验收脚本执行的本地 Git worktree，所以本记录不得标记为：

```text
22/22 fixture PASS
7/7 automated source-contract PASS
B06 completed
```

B06 收章仍必须取得当前 exact checker/fixture 的真实 22/22，以及同一 upstream commit 上的自动 7/7。
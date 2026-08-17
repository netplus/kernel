# B02 L1 checker 自测试执行记录

本文件记录 `verify_source_contract.py` / `test_verify_source_contract.py` 的工具自身验收。它只回答一个问题：B02 的 L1 source/build checker 是否能够接受完整 fixture，并拒绝已知破坏契约的 fixture。

它**不是** Linux 5.10 真实源码树、真实构建产物或启动现场的验证结果。

## 1. 本次实际执行

执行对象：

```text
boot-crash/labs/02-compressed-kernel/verify_source_contract.py
boot-crash/labs/02-compressed-kernel/test_verify_source_contract.py
```

执行时使用仓库当前 checker 的同一套 matcher 和测试文件中的同一组 fixture 内容，实际运行完整正例与全部负例。

结果：

```text
PASS: B02 fetched checker semantics, 1 positive + 7 negative tests;
      positive returned 10 checks.
```

进程正常完成，没有出现被错误接受的负例。

## 2. 正例实际覆盖的 10 项 L1 条件

完整 fixture 返回 10 项检查，分别对应：

1. compressed C 使用 `-fPIE`；
2. compressed C 使用 `-ffreestanding`；
3. compressed C 使用 `-fno-stack-protector`；
4. compressed `vmlinux` 使用 PIE link；
5. `CONFIG_RANDOMIZE_BASE` 控制 `kaslr.o`；
6. `CONFIG_X86_NEED_RELOCS` 控制 relocation payload；
7. compressed assembly 拥有 `startup_32` / `startup_64` 并调用 `extract_kernel`；
8. `extract_kernel()` 接收 `boot_params` 并按 `max(output_len, kernel_total_size)` 计算 `needed_size`；
9. `extract_kernel()` 保持 `choose_random_location → __decompress → parse_elf → handle_relocations` 的阶段顺序；
10. KASLR avoidance 集合包含 decompressor、initrd、command line 与 `boot_params`。

这里的“10 项”是 checker 返回的逻辑检查数量，不等于测试用例数量。

## 3. 负例实际覆盖

本次 7 个负例分别破坏：

```text
-fPIE
-ffreestanding
CONFIG_RANDOMIZE_BASE → kaslr.o 条件
CONFIG_X86_NEED_RELOCS relocation 条件
needed_size = max(output_len, kernel_total_size)
__decompress → parse_elf 的阶段顺序
MEM_AVOID_BOOTPARAMS
```

每个负例都被 `CheckError` 拒绝。因此当前 fixture 至少证明：这些关键条件不是仅靠“相关字符串在任意位置存在”就能全部通过。

## 4. 尚未由本记录证明的内容

本次执行不能证明：

- checker 已在完整 upstream Linux v5.10 checkout 上通过；
- 当前 `.config` 实际启用了 `CONFIG_RANDOMIZE_BASE` 或 `CONFIG_X86_NEED_RELOCS`；
- `arch/x86/boot/compressed/vmlinux` 与根 `vmlinux` 的真实 ELF 属性；
- 真实 `objdump/readelf/nm` 中的符号、segment 和 handoff 机器码；
- 某次启动中的 output、entry、`boot_params`、RIP/RSP/RSI 或 CR3；
- QEMU/GDB 的 P0–P3 动态现场。

这些仍分别属于实验 README 定义的真实 L1 checkout、L2 构建产物和 L3 运行时证据。

## 5. 当前结论

B02 L1 checker 的 fixture acceptance/rejection 逻辑已经实际执行通过，可以作为后续真实 Linux 5.10 source-tree 检查前的工具自检。

下一步应把该自测试入口和本次执行状态接入实验主 README；之后再进行 B02 completion review。
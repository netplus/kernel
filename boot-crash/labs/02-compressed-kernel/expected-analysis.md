# B02 实验预期分析：compressed kernel 的构建、解压与 handoff

本文件是 [B02 实验](README.md) 的验收基线。它说明在 Linux kernel 5.10、x86-64 下，各层证据应该支持什么结论，以及哪些结论不能由较低层证据推出。

对应正文：[压缩内核与早期 64 位环境](../../docs/02-compressed-kernel-and-early-64bit.md)。源码事实以 [Linux 5.10 源码核验](../../source-paths/02-compressed-kernel-linux-5.10.md) 为准。

## 1. 首先固定两个映像的边界

实验中必须始终区分：

```text
arch/x86/boot/compressed/vmlinux   compressed kernel / decompressor ELF
vmlinux                            formal kernel ELF
```

它们不是同一个 ELF 的两个名称。compressed ELF 包含早期入口、decompressor 和 `piggy.o` 中的压缩 payload；formal `vmlinux` 是最终被恢复并交接执行的正式内核映像。

因此两个文件中即使都出现 `startup_64`，符号值也只在各自的链接地址空间中有意义。不能比较两个数值的大小来推导启动先后，也不能把 compressed `startup_64` 的反汇编当成 formal `startup_64` 的机器码。

## 2. PIE 与 relocation 解决的是两个不同问题

B02 至少要区分：

```text
compressed PIE
    解决 decompressor 自身可能从不同合法位置运行的问题

formal-kernel relocation
    解决正式内核实际 placement 改变后，需要修正的地址引用问题
```

Linux 5.10 compressed C 构建使用 `-fPIE`、`-ffreestanding`，compressed `vmlinux` 以 PIE 方式链接。这是 compressed execution environment 的构建属性。

`handle_relocations()` 和压缩输入中的 relocation payload 则受 `CONFIG_X86_NEED_RELOCS` 控制。它们服务于 formal kernel 的 placement，不应被称为“compressed PIE 的另一部分”。

## 3. KASLR 必须写出配置条件和约束

`CONFIG_RANDOMIZE_BASE` 控制 compressed KASLR 相关代码是否进入构建。启用后，正确模型不是“生成一个随机物理地址”，而是：

```text
读取 memory map / boot_params
→ 排除 compressed image、initrd、command line、boot_params 等占用区
→ 按 image size 与 CONFIG_PHYSICAL_ALIGN 形成合法 slots
→ 从合法 slots 中随机选择 output
```

因此一次启动观察到的 output 地址只是一次运行结果，不是 Linux 5.10 的固定地址。关闭 `CONFIG_RANDOMIZE_BASE` 时，B02 的解压、ELF placement 和 handoff 仍然存在，只是不执行随机选址路径。

## 4. `needed_size` 的预期解释

`extract_kernel()` 不能只按“解压后文件有多大”寻找目标区。Linux 5.10 计算：

```text
kernel_total_size = VO__end - VO__text
needed_size = max(output_len, kernel_total_size)
```

x86-64 下还要按 `MIN_KERNEL_ALIGN` 对齐。

预期解释是：目标范围不仅要容纳解压得到的文件内容，还要容纳 formal kernel 的运行时 footprint，例如不以相同文件字节形式存在的 `.bss`、`.brk` 等区域。若实验报告把 `needed_size` 等同于 compressed size 或单纯 `output_len`，则结论不合格。

## 5. `extract_kernel()` 主线的阶段语义

源码层至少应确认以下先后关系：

```text
接管 boot_params
→ sanitize_boot_params()
→ 建立 decompressor 所需的 console / heap 状态
→ 计算 needed_size
→ choose_random_location()
→ 校验 output / virt_addr
→ __decompress()
→ parse_elf()
→ handle_relocations()
→ return formal entry
```

这里三个后半阶段不能合并：

### `__decompress()`

把 compressed payload 恢复成解压后的 ELF 内容。此时不能据此声称 formal kernel 已经形成最终运行布局。

### `parse_elf()`

读取 ELF program headers，处理 `PT_LOAD` segment，并把文件内容移动到相应目标位置。`FileSiz` 与 `MemSiz` 可以不同；后者描述运行时 segment 所需内存范围，因此解压字节完成与运行时布局完成是两个时刻。

### `handle_relocations()`

在 `CONFIG_X86_NEED_RELOCS` 条件成立时修正需要随实际 placement 改变的地址。没有该配置时应按空实现理解，不能把 relocation 写成无条件启动步骤。

## 6. `extract_kernel()` 返回不等于进入 formal kernel

这是 B02 的硬验收边界。

正确控制流模型是：

```text
compressed assembly
    call extract_kernel()
        |
        | C ABI return: 返回 formal entry address
        v
compressed assembly
    后续跨映像 control transfer
        |
        v
formal-kernel entry
```

因此：

- `extract_kernel()` 的 `return` 目标仍属于 compressed image；
- 返回值描述下一阶段入口；
- 真正进入 formal kernel 由 compressed assembly 的后续控制转移完成。

如果 L2 反汇编可用，应以真实机器码确认 `call extract_kernel` 之后仍有 compressed assembly 指令，再定位最终 handoff 指令。具体寄存器和跳转形式必须以当前构建产物为准，不从记忆补写。

## 7. L1：源码/构建契约能够证明什么

只读取 Linux 5.10 的 Makefile、`head_64.S`、`misc.c`、`kaslr.c`、`vmlinux.lds.S`，可以支持：

- compressed image 是独立构建的早期 ELF；
- compressed C/ELF 的 PIE/freestanding 构建约束；
- KASLR 与 relocation 的编译配置条件；
- `extract_kernel()` 的源码阶段顺序；
- KASLR 候选区域的避让模型；
- handoff 在源码设计上发生于 compressed assembly 与 formal entry 之间。

L1 **不能**证明当前 `.config` 实际启用了 KASLR，也不能证明某个具体 binary 中的指令、ELF type、segment 地址或某次启动的 output 地址。

## 8. L2：实际构建产物应增加哪些证据

具备成功构建的 Linux 5.10 tree 时，应分别检查：

```text
arch/x86/boot/compressed/vmlinux
vmlinux
```

### `readelf -h`

预期证明它们是两个独立 ELF，并记录各自 ELF header。不要只凭文件名下结论。

### `nm`

预期分别定位 compressed `startup_32/startup_64`、`extract_kernel` 和 formal `startup_64`、`x86_64_start_kernel`。同名符号必须连同 ELF 文件名一起记录。

### `objdump -dr`

预期确认当前构建机器码中的 `extract_kernel()` 调用、返回后的 compressed assembly 和最终 handoff。源码关系与机器码关系应分开记录。

### `readelf -lW vmlinux`

预期记录 formal kernel 的 `PT_LOAD` segment，并把 `Offset/VirtAddr/PhysAddr/FileSiz/MemSiz/Align` 与 `parse_elf()` 的职责对应起来。

L2 仍不能证明某次真实启动最终选择了哪个 KASLR 地址。

## 9. L3：运行时应观察什么

QEMU/GDB 可用时，至少观察：

```text
P0  compressed startup_64
P1  extract_kernel() 入口
P2  extract_kernel() 返回后、跨映像 handoff 前
P3  formal startup_64
```

预期的阶段变化是：

- P0/P1/P2 的 RIP 仍属于 compressed execution environment；
- P1 能关联到本次启动传入的 `boot_params`；
- P2 能取得本次实际选择/形成的 formal entry；
- P3 才能声明 CPU 已经开始执行 formal kernel entry。

若记录 `%rsi`、`%rsp`、CR3 或其他寄存器，必须以实际路径和反汇编解释其语义。尤其不能把“boot protocol 在某入口规定 `%rsi` 携带 boot_params”扩展成“整个 decompressor 期间 `%rsi` 永远保持不变”。

## 10. CONFIG 条件检查

实验报告至少记录：

```text
CONFIG_X86_64
CONFIG_RELOCATABLE
CONFIG_RANDOMIZE_BASE
CONFIG_X86_NEED_RELOCS
```

解释源码时必须区分：

- `CONFIG_X86_64` 下的 64-bit 特有对齐和路径；
- `CONFIG_RELOCATABLE` 对 formal placement/ELF placement 的影响；
- `CONFIG_RANDOMIZE_BASE` 是否启用随机选址；
- `CONFIG_X86_NEED_RELOCS` 是否存在 relocation payload 与有效 `handle_relocations()`。

不要因为源码树中存在某个 `#ifdef` 分支，就声称当前构建一定执行该分支。

## 11. 常见错误及判定

以下结论均应判为不合格：

1. “compressed `vmlinux` 就是解压前的 formal `vmlinux` 文件名。”
2. “两个 `startup_64` 地址谁小谁先执行。”
3. “KASLR 随机生成一个地址然后把 kernel 解压过去。”
4. “`__decompress()` 返回后 formal kernel 已经完成最终布局。”
5. “relocation 是 compressed PIE 的同义词。”
6. “`handle_relocations()` 每次 x86-64 启动都会实际修正地址。”
7. “`extract_kernel()` 直接 C-call formal kernel。”
8. “源码中存在 KASLR 代码，所以本次构建一定启用了 KASLR。”
9. “fixture/source checker 通过就等于真实 ELF 或运行时已经验证。”

## 12. 当前验证状态

截至本验收基线写入仓库时：

- Linux 5.10 的 B02 源码事实已经完成核验；
- B02 正式教程和实验方法已经建立；
- 本文件固定了 L1/L2/L3 的预期结果和错误判定；
- 当前仓库维护环境没有可执行的 Linux 5.10 build tree，因此尚未记录真实 `readelf`、`nm`、`objdump` 结果；
- 当前也没有 QEMU/GDB 启动现场，因此 P0–P3 尚未执行。

未执行的 L2/L3 项目仍是增强验证，不能用推测结果填充。

## 13. B02 收章前的下一步

下一最小单元应把本文件中可由源码静态判定的 L1 条件转换为自动 checker，并为 checker 增加正/负 fixture 自测试。至少应自动拒绝：PIE/freestanding 构建契约缺失、KASLR/relocation 配置边界丢失、`extract_kernel()` 主线顺序破坏，以及 compressed/formal 映像归属被混淆。

# B02 实验：compressed kernel 的构建、解压与 handoff

本实验对应 [B02：压缩内核与早期 64 位环境](../../docs/02-compressed-kernel-and-early-64bit.md)。目标不是重复验证 long-mode 指令细节，而是把 compressed kernel 作为一个独立执行映像来观察：它如何构建、从哪里取得输入、怎样选择和形成 formal kernel 的目标布局，以及最终如何跨映像交接控制权。

实验基线为 Linux kernel 5.10、x86-64。源码事实以 [B02 Linux 5.10 源码核验](../../source-paths/02-compressed-kernel-linux-5.10.md) 为准。

## 1. 要验证的问题

完成实验后，应能够用证据回答：

1. `arch/x86/boot/compressed/vmlinux` 为什么是独立于根目录 `vmlinux` 的 ELF 映像；
2. compressed C 代码和最终 compressed ELF 使用了哪些 freestanding/PIE 构建约束；
3. `CONFIG_RANDOMIZE_BASE` 与 `CONFIG_X86_NEED_RELOCS` 分别控制哪一部分构建或运行逻辑；
4. compressed `startup_64` 怎样把 `boot_params` 与临时运行环境交给 `extract_kernel()`；
5. 为什么 `extract_kernel()` 的职责不能简化成 `__decompress()`；
6. `__decompress()`、`parse_elf()`、`handle_relocations()` 分别处于什么阶段；
7. `extract_kernel()` 返回后，为什么还需要 compressed assembly 执行真正的跨映像 handoff。

## 2. 证据分层

本实验严格区分三层证据：

```text
L1  源码/构建契约
    Makefile、head_64.S、misc.c、kaslr.c、vmlinux.lds.S

L2  实际构建产物
    arch/x86/boot/compressed/vmlinux、根 vmlinux、objdump/readelf/nm 输出

L3  运行时现场
    QEMU/GDB 中 compressed startup_64、extract_kernel() 与 formal entry 前后的寄存器和地址
```

L1 可以证明 Linux 5.10 源码如何设计；L2 才能证明某个实际配置生成了什么 ELF/机器码；L3 才能证明某次启动实际采用了什么地址和控制流。不得用较低层证据替代较高层结论。

## 3. L1：核验 compressed image 的构建边界

在 Linux 5.10 源码树中执行：

```bash
cd /path/to/linux-5.10

grep -nE 'fPIE|ffreestanding|fno-stack-protector|LDFLAGS_vmlinux.*pie' \
    arch/x86/boot/compressed/Makefile

grep -nE 'CONFIG_RANDOMIZE_BASE|kaslr\.o|CONFIG_X86_NEED_RELOCS|vmlinux\.relocs' \
    arch/x86/boot/compressed/Makefile
```

记录：

- compressed C 编译是否使用 `-fPIE`、`-ffreestanding`；
- compressed `vmlinux` 是否以 PIE 方式链接；
- `kaslr.o` 是否受 `CONFIG_RANDOMIZE_BASE` 控制；
- relocation 数据是否只在 `CONFIG_X86_NEED_RELOCS` 条件下进入 compressed payload。

这里验证的是构建规则，不要仅凭 Makefile 就声称当前 `.config` 一定启用了 KASLR 或 relocation。

## 4. L1：核验入口与 `extract_kernel()` 主线

先定位两个 compressed 入口和 C decompressor：

```bash
git grep -n 'startup_32' -- arch/x86/boot/compressed/head_64.S
git grep -n 'startup_64' -- arch/x86/boot/compressed/head_64.S
git grep -n 'extract_kernel' -- arch/x86/boot/compressed/head_64.S arch/x86/boot/compressed/misc.c
```

然后阅读 `extract_kernel()`，逐项确认下列关系，而不是只搜索函数名：

```text
boot_params = rmode
sanitize_boot_params()
needed_size = max(output_len, kernel_total_size)
[CONFIG_X86_64] needed_size alignment
choose_random_location()
__decompress()
parse_elf()
handle_relocations()
return entry
```

特别记录 `choose_random_location()` 在关闭 `CONFIG_RANDOMIZE_BASE` 时的实现边界，以及 `handle_relocations()` 在关闭 `CONFIG_X86_NEED_RELOCS` 时是否退化为空实现。

## 5. L1：核验 KASLR 的“约束内随机”模型

在 `arch/x86/boot/compressed/kaslr.c` 中定位：

```bash
git grep -n 'MEM_AVOID_' -- arch/x86/boot/compressed/kaslr.c
git grep -n 'mem_avoid_init' -- arch/x86/boot/compressed/kaslr.c
git grep -n 'choose_random_location' -- arch/x86/boot/compressed
```

至少确认候选位置会避让 compressed image 自身、initrd、command line 与 `boot_params`，并受 image size 与 alignment 约束。

实验报告中不要写“随机生成一个物理地址”。应写清：先根据 memory map 和占用区形成合法候选，再从候选 slots 中随机选择。

## 6. L2：分别检查 compressed 与 formal 两个 ELF

需要一棵已经成功构建的 Linux 5.10 tree。先确认两个文件都存在：

```bash
ls -l vmlinux arch/x86/boot/compressed/vmlinux
file vmlinux arch/x86/boot/compressed/vmlinux
```

分别检查 ELF header：

```bash
readelf -h vmlinux
readelf -h arch/x86/boot/compressed/vmlinux
```

再分别检查符号：

```bash
nm -n arch/x86/boot/compressed/vmlinux | \
    grep -E 'startup_(32|64)|extract_kernel|input_data|input_len'

nm -n vmlinux | grep -E 'startup_64|x86_64_start_kernel'
```

观察重点不是比较两个 `startup_64` 谁的数值更大，而是证明它们属于两个独立 ELF/链接上下文。跨 ELF 的符号地址不能直接拿来推导启动先后。

## 7. L2：检查真实机器码中的调用与 handoff

对 compressed ELF 反汇编：

```bash
objdump -dr arch/x86/boot/compressed/vmlinux > /tmp/compressed-vmlinux.dis

grep -n -A30 -B20 'extract_kernel' /tmp/compressed-vmlinux.dis
```

结合 `head_64.S` 确认：

1. compressed assembly 调用 `extract_kernel()`；
2. C 函数返回的是下一阶段 entry address；
3. `extract_kernel()` 返回后仍回到 compressed assembly；
4. 真正进入 formal kernel 是后续控制转移，不是 C ABI 的普通 `return`。

具体寄存器和指令必须以当前构建产物为准，不要从源码记忆补全反汇编。

## 8. L2：核验 formal kernel 的 `PT_LOAD` 布局

`parse_elf()` 处理的是解压后 formal kernel 的 ELF program headers。对根 `vmlinux` 执行：

```bash
readelf -lW vmlinux
```

记录所有 `LOAD` segment 的：

```text
Offset
VirtAddr
PhysAddr
FileSiz
MemSiz
Align
```

然后回到 `parse_elf()`，解释为什么 `FileSiz` 与 `MemSiz` 可以不同，以及为什么“`__decompress()` 已结束”仍不等于“formal kernel 的全部运行时内存布局已经完成”。

## 9. L3：QEMU/GDB 动态观察点

只有在隔离的测试虚拟机中执行。建议至少设置三个观察点：

```text
P0  compressed startup_64
P1  call extract_kernel() 前 / extract_kernel() 入口
P2  extract_kernel() 返回后、跨映像 handoff 前
P3  formal-kernel startup_64
```

每个观察点至少记录：

```text
RIP
RSP
RSI（若当前路径按 boot protocol 携带 boot_params）
boot_params 地址
compressed image 当前地址范围
extract_kernel() 的 output / 返回 entry
CR3（只记录阶段变化；页表机制本身留给 memory/assembly）
```

若启用了 KASLR，还应记录实际 output/entry，并与未启用 KASLR 的构建对比。不要把一次启动观察到的随机地址写成 Linux 5.10 的固定地址。

## 10. 结果记录模板

```text
Kernel version / commit:
.config relevant options:
  CONFIG_X86_64=
  CONFIG_RELOCATABLE=
  CONFIG_RANDOMIZE_BASE=
  CONFIG_X86_NEED_RELOCS=

L1 source/build contract:
  PIE/freestanding:
  kaslr.o condition:
  relocation payload condition:
  extract_kernel mainline:

L2 artifacts:
  compressed ELF:
  formal ELF:
  compressed startup_64:
  extract_kernel:
  formal startup_64:
  PT_LOAD summary:

L3 runtime:
  P0:
  P1:
  P2:
  P3:

Not executed / environment limits:
```

## 11. 通过标准

本实验的最低通过条件是：

- 能从 Linux 5.10 源码解释 compressed image 与 formal image 的构建和所有权边界；
- 能准确写出 `extract_kernel()` 中位置选择、解压、ELF placement、relocation 的先后关系；
- 能说明 KASLR 和 relocation 的配置条件，不能写成无条件路径；
- 能解释为什么两个 ELF 中的 `startup_64` 不能直接比较地址；
- 能解释为什么 `extract_kernel()` 返回并不等于已经执行到 formal kernel；
- 若有 build tree，实际执行 `readelf`、`nm`、`objdump` 并保存结果；
- 若有 QEMU/GDB，记录 P0–P3；若环境缺失，明确写“未执行”，不得生成虚构输出。

当前仓库维护环境没有可执行 Linux 5.10 build tree 或 QEMU/GDB 启动现场，因此本文件只建立可复现的实验方法与验收标准；L2/L3 结果尚未执行。
# B02 Linux 5.10 源码核验：compressed kernel 与早期 64 位环境

本文件固定 B02 使用的 Linux kernel 5.10 源码事实。重点不是再次解释 GDT、CR0/CR3/CR4、EFER 或 long-mode transition 的机器机制；这些已经由 `assembly/` 负责。这里要回答的是：**compressed kernel 为什么是一个独立执行阶段，它接收什么输入，怎样选择解压目标，怎样产生正式内核映像，最后把什么状态交给 formal kernel。**

## 1. 构建边界：compressed kernel 是独立的早期执行映像

Linux 5.10：

```text
arch/x86/boot/compressed/Makefile
```

该 Makefile 明确说明 compressed `vmlinux` 由 decompression code 与 `piggy.o` 等对象组成；`piggy.S` 又封装压缩后的 `vmlinux.bin.*`。正式 `vmlinux` 先经过 `objcopy` 形成 `vmlinux.bin`，在需要时附加 relocation 数据，再按所选算法压缩，最后被放进 compressed image。

关键构建关系：

```text
formal vmlinux
  → vmlinux.bin
  → [vmlinux.relocs]
  → vmlinux.bin.all
  → vmlinux.bin.{gz,bz2,lzma,xz,lzo,lz4,zst}
  → piggy.S / piggy.o
  → arch/x86/boot/compressed/vmlinux
```

Linux 5.10 的 compressed C 代码使用 `-fPIE`、`-ffreestanding`、`-fno-stack-protector`；compressed `vmlinux` 以 PIE 方式链接，因为 boot loader 可以把它放到不同物理位置。sanitizer runtime 也明确不可用于这一早期启动环境。

因此 compressed kernel 不是“formal kernel 已经正常运行后调用的一个解压函数”，而是正式内核出现之前的自包含启动环境。

## 2. 两个入口：`startup_32` 与 compressed `startup_64`

源码：

```text
arch/x86/boot/compressed/head_64.S
```

Linux 5.10 同时提供：

```text
startup_32   32-bit entry，入口 offset 0
startup_64   64-bit entry，入口 offset 0x200
```

`startup_32` 可以从 32-bit boot loader 进入，并负责建立进入 long mode 所需的最小状态；`startup_64` 也可以由已经满足 boot protocol 要求的 64-bit loader 直接进入。

对 B02 更重要的是两条路径最终必须收敛到同一个 compressed-kernel 工作模型：建立 compressed image 自己能够安全运行的栈、映射和位置关系，然后调用 C 侧 `extract_kernel()`。

### 与 assembly A19 的边界

`startup_32` 中的 GDT、`verify_cpu()`、PAE、early page tables、CR3、EFER.LME、CR0.PG/PE 与 far `lret` 已在 `assembly/` 解释。B02 只把这些状态视为 compressed kernel 进入后续 64-bit 解压阶段所需的前置条件。

## 3. compressed `startup_64` 不能假设固定装载地址

Linux 5.10 `startup_64` 的注释明确指出，它可能来自 `startup_32`，也可能直接来自 64-bit boot loader。直接进入时，loader 必须提供 identity mapping，使 compressed kernel、zero page 与 command line 可访问。

在 `CONFIG_RELOCATABLE` 下，代码从运行时 `startup_32` 地址计算 image base，并按 `boot_params.hdr.kernel_alignment` 对齐；如果结果低于 `LOAD_PHYSICAL_ADDR`，则回退到 `LOAD_PHYSICAL_ADDR`。随后结合 `BP_init_size` 与 compressed image `_end` 计算用于安全解压的目标/搬移位置。

这说明这里至少存在三个不同概念，后续正文不得混写：

```text
compressed image 当前运行位置
用于 compressed image 自身安全运行/搬移的区域
formal kernel 的最终解压物理位置 output
```

## 4. 栈与页表属于 compressed kernel 自己的临时运行环境

`head_64.S` 在 compressed `startup_64` 中以 `boot_stack_end` 建立 `%rsp`。这不是进入 formal kernel 后的正常内核栈。

同一文件还处理 compressed stage 所需的 early page-table 状态，包括来自 32-bit path 的临时映射，以及 64-bit path 对当前 paging mode、identity mapping 和可访问范围的修正。这里的目标是让 decompressor、boot parameters、command line 和解压目标在正式内核接管之前可访问。

因此 B02 只记录这些页表的**阶段责任**：它们服务于 decompressor 的临时执行环境；完整页表结构与 long-mode 开启机制分别引用 `memory/` 与 `assembly/`，不在本章重复展开。

## 5. `extract_kernel()` 是 compressed C 阶段的中心入口

源码：

```text
arch/x86/boot/compressed/misc.c
```

Linux 5.10 定义：

```c
asmlinkage __visible void *extract_kernel(...)
```

其第一个重要动作是保存从 `startup_32/64` 传来的 boot parameters 指针：

```text
boot_params = rmode
```

随后执行的主线包括：

```text
接管 boot_params
→ sanitize_boot_params()
→ 初始化早期输出/heap
→ 计算 needed_size
→ choose_random_location()
→ 检查 output / virt_addr 对齐和范围
→ __decompress()
→ parse_elf()
→ handle_relocations()
→ 返回 formal kernel entry
```

这条链比“解压 bzImage”更准确：compressed stage 不只是运行压缩算法，还负责选择可用位置、解析解压后的 ELF `PT_LOAD`、处理必要 relocation，并产生下一阶段可跳转的入口。

## 6. `needed_size` 不是单纯的压缩后或解压后文件大小

`extract_kernel()` 计算：

```text
kernel_total_size = VO__end - VO__text
needed_size = max(output_len, kernel_total_size)
```

在 `CONFIG_X86_64` 下再按 `MIN_KERNEL_ALIGN` 向上对齐。

原因是目标区域既要容纳解压 payload/relocation 所需范围，也要容纳 formal kernel 运行时 `.bss`、`.brk` 等形成的完整运行范围。后续 KASLR 选择目标地址时必须以能够容纳这一整体范围为前提。

## 7. KASLR：选择的是满足约束的可用槽位，不是任意随机地址

源码：

```text
arch/x86/boot/compressed/kaslr.c
```

该文件的职责是为 KASLR 生成随机性，并扫描物理内存图，寻找能够容纳完整 kernel image 且满足对齐要求的位置。

Linux 5.10 的 `mem_avoid` 明确排除：

```text
MEM_AVOID_ZO_RANGE      compressed image 与 decompressor 自身使用范围
MEM_AVOID_INITRD        initrd
MEM_AVOID_CMDLINE       kernel command line
MEM_AVOID_BOOTPARAMS    boot_params
MEM_AVOID_MEMMAP_*      memmap/EFI 等额外不可覆盖范围
```

`mem_avoid_init()` 还从 `boot_params` 重建 initrd 的高低 32-bit 地址/大小，并把 `boot_params` 自身作为禁止覆盖区域。

候选区域最终按 `CONFIG_PHYSICAL_ALIGN` 对齐并形成 slot；随机数是在合法 slot 集合中选择一个。因此更准确的模型是：

```text
先由 boot protocol / memory map 给出约束
→ 排除 decompressor 与启动数据占用区域
→ 形成满足 image_size 和 alignment 的候选 slots
→ 再随机选择
```

`kaslr.o` 只有在 `CONFIG_RANDOMIZE_BASE` 下加入 compressed `vmlinux`。后续正文必须明确这个配置条件。

## 8. 解压后的数据仍要经过 ELF 装载语义

`misc.c` 的 `parse_elf()` 读取解压结果的 ELF header 与 program headers，只处理 `PT_LOAD` 段。x86-64 下还检查 LOAD segment alignment 是否为 2 MiB 的倍数。

在 `CONFIG_RELOCATABLE` 下，目标地址相对于 `output` 和 `LOAD_PHYSICAL_ADDR` 计算；否则使用 ELF `p_paddr`。然后用 `memmove()` 把各 `PT_LOAD` 的文件内容放到目标位置。

所以：

```text
__decompress() 完成
```

并不等价于：

```text
formal kernel 已经处于最终可执行布局
```

两者之间还有 ELF segment placement 和 relocation 处理。

## 9. relocation 的配置条件

`handle_relocations()` 由 `CONFIG_X86_NEED_RELOCS` 控制。Linux 5.10 compressed Makefile 也只在该配置条件下把 `vmlinux.relocs` 附加到 `vmlinux.bin.all`。

x86-64 下，如果 KASLR 使 kernel 的实际 virtual placement 与默认链接/装载关系不同，relocation 数据用于修正相应地址。没有该配置条件时 `handle_relocations()` 是空 inline 实现。

因此不能把 relocation 描述成所有 compressed boots 都无条件执行的地址修正过程。

## 10. handoff：`extract_kernel()` 返回下一阶段入口

在 Linux 5.10 中，`extract_kernel()` 完成解压、ELF placement 和 relocation 后返回正式 kernel 的入口地址；`head_64.S` 随后从 compressed execution environment 把控制权转移到该返回地址。

阶段交接可以概括为：

```text
输入：
  boot_params / zero page
  compressed payload
  当前 CPU/paging 可执行环境

compressed stage 负责：
  建立自己的临时栈和可访问映射
  确定安全解压目标
  可选 KASLR 选址
  解压 payload
  按 ELF PT_LOAD 放置正式 kernel
  处理需要的 relocations

输出：
  formal kernel 已放置在选定位置
  boot_params 仍作为跨阶段启动数据
  CPU 仍处于可执行 64-bit kernel entry 的状态
  控制权跳转到 formal kernel entry
```

这里的 handoff 不是普通 C 函数“返回到正式内核”。`extract_kernel()` 只是先返回给 compressed assembly；真正跨映像的控制权转移由汇编入口代码完成。

## 11. B02 后续实验应核验什么

后续实验至少分三层：

1. **源码/构建层**：确认 compressed Makefile 的 PIE/freestanding 约束、`CONFIG_RANDOMIZE_BASE`/`CONFIG_X86_NEED_RELOCS` 条件，以及 `startup_64 → extract_kernel()` 主线；
2. **构建产物层**：对 `arch/x86/boot/compressed/vmlinux` 使用 `readelf`、`nm`、`objdump`，确认 compressed ELF 与 formal `vmlinux` 是不同映像，并定位 `startup_64`、`extract_kernel`、payload symbols；
3. **运行时层**：在 QEMU/GDB 中记录进入 compressed `startup_64`、调用 `extract_kernel()` 前后、以及跳转 formal kernel entry 前的 `%rsi/%rsp/%rip`、关键地址与页表状态。

当前源码事实核验不等于上述构建产物或运行时实验已经执行。

## 12. 本章源码入口

```text
arch/x86/boot/compressed/Makefile
arch/x86/boot/compressed/head_64.S
arch/x86/boot/compressed/misc.c
arch/x86/boot/compressed/kaslr.c
arch/x86/boot/compressed/vmlinux.lds.S
arch/x86/boot/compressed/mkpiggy.c
arch/x86/boot/header.S
```

下一单元基于这些已核验事实编写 B02 正式教程，先建立 compressed kernel 作为“formal kernel 之前的独立加载/解压执行环境”的模型，再展开位置选择、KASLR、ELF placement 与 handoff。
# B01 Linux boot protocol 与 `boot_params`：Linux 5.10 源码事实核验

本文件只固定 B01 后续教程需要依赖的 Linux 5.10 事实。完整启动阶段模型见 B00；GDT、控制寄存器和 long-mode transition 仍由 `assembly/` 解释。

## 1. 问题边界

x86 boot loader 不能只把一段机器码放入内存然后跳转。它还需要知道映像怎样拆分、protected-mode payload 可以放在哪里、内核支持哪个 boot protocol 版本，以及 command line、initrd、内存映射等启动信息应放在哪里。Linux/x86 boot protocol 因而同时承担两类契约：

1. kernel image 向 loader 暴露的自描述 header；
2. loader/setup 向后续 kernel 传递的 `struct boot_params` 参数块。

这两者有关联，但不是同一个结构。

## 2. Linux 5.10 protocol 版本

`Documentation/x86/boot.rst` 的版本表显示 Linux 5.10 已包含 protocol 2.15。2.15 从 Linux 5.5 引入 `kernel_info` / `kernel_info.setup_type_max`，并明确指出：protocol version 只应在 `setup_header` 改变时递增；`boot_params` 或 `kernel_info` 的变化本身不要求修改 protocol version。

`arch/x86/boot/header.S` 中实际写入：

```text
"HdrS"
version = 0x020f
```

因此 B01 后续正文以 **Linux 5.10 header version 2.15 (`0x020f`)** 为版本基线，而不是依据更新内核的 header 字段补全。

## 3. bzImage 的两个基本区域

boot protocol 文档把 real-mode code 描述为 boot sector + setup code；对现代 bzImage，protected-mode kernel 通常加载到 `0x100000`，setup/boot sector 则位于低内存中的可重定位区域。

这里的“real-mode/setup 部分”和“protected-mode kernel 部分”是映像/协议层面的分区。后续 compressed kernel 自己建立 long-mode 环境属于 B02/A19 的执行机制，不能反向把整个 bzImage 简化成“一个 64 位 ELF 直接入口”。

`arch/x86/boot/header.S` 也保留 legacy boot-sector 入口，但该入口会打印 `Use a boot loader.`；正常 loader 应解析 boot protocol，而不是把 bzImage 当传统裸 boot sector 使用。

## 4. `setup_header`：映像给 loader 的协议头

Linux 5.10 `arch/x86/include/uapi/asm/bootparam.h` 定义 packed `struct setup_header`。关键字段包括：

- `setup_sects`：setup code 的 512-byte sector 数；值为 0 时按兼容规则解释为 4；
- `boot_flag`：legacy `0xAA55`；
- `header`：`HdrS` signature；
- `version`：boot protocol version；
- `type_of_loader`：loader 标识；
- `loadflags`：包括 `LOADED_HIGH`、`CAN_USE_HEAP` 等；
- `code32_start`：32-bit code 的 loader hook/default start；
- `ramdisk_image` / `ramdisk_size`：initrd 的低 32-bit 地址和长度；
- `cmd_line_ptr`：command line 的低 32-bit 指针；
- `kernel_alignment` / `relocatable_kernel` / `min_alignment`：protected-mode kernel 的装载/重定位约束；
- `xloadflags`：64-bit kernel、above-4G loading、EFI handover、5-level paging 等能力位；
- `cmdline_size`：command line 最大长度；
- `setup_data`：可扩展 setup-data 链表的 64-bit physical pointer；
- `pref_address` / `init_size`：preferred load address 与初始化期线性内存需求；
- `kernel_info_offset`：2.15 引入的 `kernel_info` 偏移。

`header.S` 中部分值由源码静态给出，另一些明确标注由 `arch/x86/boot/tools/build.c` 在构建 bzImage 时填写。因此“header 是编译期 C 结构常量”也不准确；它最终是构建后映像中的协议数据。

## 5. `boot_params`：zeropage 参数块

同一 UAPI header 定义 packed `struct boot_params`，源码注释直接称其为 **zeropage**。Linux 5.10 的关键布局包括：

```text
0x000  screen_info
0x070  acpi_rsdp_addr
0x0c0  ext_ramdisk_image
0x0c4  ext_ramdisk_size
0x0c8  ext_cmd_line_ptr
0x1c0  efi_info
0x1e8  e820_entries
0x1ef  sentinel
0x1f1  struct setup_header hdr
0x2d0  e820_table[128]
```

`arch/x86/boot/main.c` 定义：

```c
struct boot_params boot_params __attribute__((aligned(16));
```

并在 `copy_boot_params()` 中用 `BUILD_BUG_ON(sizeof(boot_params) != 4096)` 固定 setup 阶段所用参数块为 4096 bytes，然后把映像中的 `hdr` 复制到 `boot_params.hdr`。

所以应建立如下模型：

```text
bzImage 内的 setup header
        ↓ copy_boot_params()
setup 阶段 4 KiB boot_params / zeropage
        ↓ BIOS/setup 探测 + loader 已填写字段
后续 compressed/formal kernel 继续接收
```

不能把 `setup_header` 和整个 4 KiB `boot_params` 当成同义词。

## 6. command line：指针而不是内嵌字符串

protocol 2.02+ 使用 `setup_header.cmd_line_ptr` 传递 32-bit physical pointer；Linux 5.10 又在 `boot_params.ext_cmd_line_ptr` 保存高 32 bit 扩展。

`arch/x86/boot/main.c:copy_boot_params()` 还保留 old-style command-line protocol 的兼容逻辑：只有新式 `cmd_line_ptr` 为空且 old magic 有效时，才从旧 segment/offset 形式推导新的 linear pointer。

因此 command line 本体并不存放在 `setup_header` 中；header/boot_params 保存的是地址元数据。正式内核后续再根据这些字段复制命令行。

## 7. initrd：地址和长度，64 位地址由扩展字段拼接

`setup_header` 中有 `ramdisk_image` 与 `ramdisk_size` 两个 32-bit 字段；`boot_params` 另有 `ext_ramdisk_image` 与 `ext_ramdisk_size`。protocol 2.12 引入的扩展允许 64-bit bzImage/ramdisk 地址超过 4 GiB，具体是否允许还受 `xloadflags` 能力位约束。

因此 B01 只把它解释为 loader→kernel 的物理位置/大小契约；initramfs 的展开和 rootfs 使用留到 B05。

## 8. E820：setup 阶段会主动探测并填充 zeropage

`arch/x86/boot/main.c:main()` 在 `copy_boot_params()`、CPU 检查等步骤后调用 `detect_memory()`。`boot_params` 中用 `e820_entries` 给出有效 entry 数，并内嵌 `e820_table[E820_MAX_ENTRIES_ZEROPAGE]`；Linux 5.10 将 zeropage 内固定容量定义为 128 项。

因此“所有 boot_params 字段都由 boot loader 填写”是错误模型。它是一个跨阶段参数块：一部分来自映像 header，一部分由 loader 按 protocol 填写，一部分由 setup/BIOS 探测产生，另有 EFI/平台专用字段。

完整 E820→memblock→伙伴系统转换属于 `memory/`；B01 只解释交接格式。

## 9. `sentinel` 与坏 loader 防护

Linux 5.10 `boot_params.sentinel` 位于 `0x1ef`。`header.S` 把 header 前的 sentinel bytes 初始化为 `0xff`；`bootparam.h` 注释解释了目的：规范 loader 应只把 `setup_header` 复制进一个干净的 `boot_params` buffer。如果 loader 粗暴复制过多数据，sentinel 仍为 `0xff`，kernel 可以据此判断某些 `boot_params` 区域不可信并清理。

这说明 boot protocol 不只是字段列表，也包含“哪些字节由谁拥有/初始化”的 ABI 约束。

## 10. setup `main()` 如何继续完善参数块

Linux 5.10 `arch/x86/boot/main.c:main()` 的主线是：

```text
copy_boot_params()
→ console_init()
→ init_heap()
→ validate_cpu()
→ set_bios_mode()        [CONFIG_X86_64 内部路径]
→ detect_memory()
→ keyboard / IST / optional APM / optional EDD
→ set_video()
→ go_to_protected_mode()
```

这里的重点是：进入 protected mode 之前，setup 已经把后续启动需要的一组平台信息收集进 `boot_params`。`go_to_protected_mode()` 的机器级切换过程不是 B01 主体。

## 11. 必须保持的四个边界

### 11.1 protocol header ≠ `boot_params`

前者是映像内的自描述协议头；后者是 4 KiB zeropage 参数块，并在 `0x1f1` 内嵌一个 `setup_header`。

### 11.2 loader input ≠ setup-discovered state

command line、initrd 装载位置等通常由 loader 提供；E820、键盘、视频等还会由 setup 代码探测/补充。字段所有权应按 protocol 文档逐项判断。

### 11.3 bzImage layout ≠ CPU execution mode

“setup + protected-mode kernel”描述的是 boot image/protocol 布局；CPU 从 real mode 到 protected/long mode 的状态转换是另一层机制。

### 11.4 protocol capability ≠ 当前 loader 一定使用

`xloadflags`、relocatable kernel、EFI handover 等字段描述 kernel/loader 能力契约。字段存在不代表某次启动一定选择对应路径。

## 12. B01 后续教程应采用的主模型

```text
kernel build
    ↓
bzImage embeds setup_header / protocol capabilities
    ↓
boot loader parses header, chooses legal placement
    ↓
loader fills command line / initrd / loader-owned boot parameters
    ↓
setup main copies hdr into 4 KiB boot_params and supplements platform data
    ↓
go_to_protected_mode()
    ↓
compressed/formal kernel continues consuming the same boot information
```

B01 正式教程应围绕“为什么需要一个跨 loader/kernel 边界的自描述 ABI”展开，而不是逐字段背诵 `struct boot_params`。

## 13. Linux 5.10 核验文件

- `Documentation/x86/boot.rst`
- `arch/x86/boot/header.S`
- `arch/x86/boot/main.c`
- `arch/x86/include/uapi/asm/bootparam.h`

本次事实核验使用 upstream Linux tag `v5.10` 的上述文件；未使用 master 分支字段补全 v5.10 结构。
# B01 Linux boot protocol 与 `boot_params`

B00 已经建立了 x86_64 Linux 启动的阶段图。本章把其中 boot loader 到 setup/compressed kernel 之间的交接放大来看：为什么一个内核映像不能只是“一段可执行代码”，以及 loader 怎样知道它应该把内核、命令行和 initrd 放在哪里，又怎样把机器信息交给后续内核。

本章以 Linux 5.10 x86 boot protocol 为准。重点不是背字段，而是建立一个跨阶段 ABI 模型：**bzImage 用 `setup_header` 描述自己；boot loader 按协议选择合法装载方式并提供启动输入；setup 再把这些输入和平台探测结果汇入 4 KiB `boot_params`，交给后续启动阶段。**

## 1. 为什么需要 boot protocol

如果 loader 只拿到一个二进制文件，它至少还需要回答下面几个问题：

- 文件的 setup 部分有多长，protected-mode payload 从哪里开始；
- kernel 是否要求高地址装载，是否可以重定位；
- kernel 支持哪个协议版本和哪些扩展能力；
- command line 放在哪里、最多多长；
- initrd 放在哪里、大小是多少；
- 后续 kernel 从哪里取得 BIOS/EFI、内存映射等启动信息。

这些信息不能靠 loader 猜测。Linux/x86 因此定义 boot protocol，让 kernel image 与 loader 共享一套稳定的二进制接口。

这里有两个方向不同但相互连接的对象：

```text
kernel image ──setup_header──> boot loader
boot loader/setup ──boot_params──> later kernel
```

`setup_header` 主要回答“这个映像怎样被合法启动”；`boot_params` 主要回答“这一次启动实际带来了什么参数和机器状态”。二者不能混为一个结构。

## 2. Linux 5.10 的协议基线

Linux 5.10 `arch/x86/boot/header.S` 中的 boot protocol header 使用：

```text
signature: "HdrS"
version:   0x020f
```

也就是 protocol 2.15。`Documentation/x86/boot.rst` 的版本历史说明 2.15 引入了 `kernel_info` 相关能力。

这里需要注意协议版本的含义。它不是“Linux 内核版本号”，也不是每次 `boot_params` 增加内部信息都必须变化。它描述的是 boot loader 与 kernel 之间的 `setup_header` 协议版本。后续阅读字段时，应始终以 Linux 5.10 的 2.15 布局为基线，不能从新内核的 header 反推 5.10。

## 3. 从 bzImage 看两个基本区域

对本章需要的抽象，可以先把现代 x86 bzImage 看成：

```text
+------------------------------+
| boot sector / setup area     |
| setup_header 位于其中         |
+------------------------------+
| protected-mode kernel payload|
| 后续包含 compressed kernel   |
+------------------------------+
```

`setup_sects` 等字段帮助 loader 找到这些边界。现代 boot loader 会读取 `HdrS`、protocol version 和相关字段，然后按协议装载，而不是把 bzImage 当成传统裸 boot sector 直接执行。Linux 5.10 `header.S` 中保留的 legacy boot-sector 路径本身就会提示 `Use a boot loader.`。

这里的“setup 部分”“protected-mode kernel 部分”首先是**映像与协议布局**。CPU 当前处于 real mode、protected mode 还是 long mode，是另一层机器状态问题。不要因为映像里叫 protected-mode payload，就把整个 bzImage 描述成一个直接从 64 位入口执行的 ELF。

## 4. `setup_header`：内核映像怎样描述自己

Linux 5.10 在 `arch/x86/include/uapi/asm/bootparam.h` 中定义 packed `struct setup_header`。它的字段很多，但可以按用途分组理解。

第一组描述映像身份和基本布局，例如：

- `boot_flag`；
- `header` (`HdrS`)；
- `version`；
- `setup_sects`。

第二组描述装载约束和入口能力，例如：

- `loadflags`；
- `code32_start`；
- `kernel_alignment`；
- `relocatable_kernel`；
- `min_alignment`；
- `pref_address`；
- `init_size`。

第三组建立 loader 输入的位置契约，例如：

- `cmd_line_ptr` / `cmdline_size`；
- `ramdisk_image` / `ramdisk_size`；
- `setup_data`。

第四组表达扩展能力，例如 `xloadflags` 和 2.15 的 `kernel_info_offset`。

因此 `setup_header` 的核心作用不是保存“一次启动的全部参数”，而是让 loader 能够判断：**这个 kernel image 支持什么，我应该怎样装载它，以及某些启动输入应该通过什么字段传递。**

另一个实现细节也很重要：`header.S` 中有些值是静态汇编数据，有些字段由 `arch/x86/boot/tools/build.c` 在构建 bzImage 时补写。最终协议对象是构建后映像里的二进制 header，而不是一个运行时才创建的普通 C 对象。

## 5. `boot_params`：这一次启动的 4 KiB 参数块

同一个 UAPI header 定义 `struct boot_params`，源码注释称它为 zeropage。Linux 5.10 setup 代码还用：

```c
BUILD_BUG_ON(sizeof(boot_params) != 4096);
```

固定其大小为 4 KiB。

它的关键布局可以先记住几个锚点：

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

最重要的不是偏移本身，而是 `0x1f1` 处的关系：**`boot_params` 内嵌一个 `setup_header`，但 `boot_params` 并不等于 `setup_header`。**

Linux 5.10 `arch/x86/boot/main.c:copy_boot_params()` 会把映像 header 复制到 `boot_params.hdr`。随后 setup 代码继续补充本次启动需要的平台信息。因此可以把对象演化理解为：

```text
bzImage 中的 setup_header
        │
        │ copy_boot_params()
        v
4 KiB boot_params
        + loader 已提供的启动输入
        + setup/BIOS/平台探测得到的信息
        │
        v
后续 compressed/formal kernel
```

这也是为什么“`boot_params` 全部由 boot loader 填写”是不准确的。

## 6. command line：传的是地址元数据

现代协议并不把命令行字符串直接塞进 `setup_header`。protocol 2.02+ 使用 `cmd_line_ptr` 传递低 32 位物理地址；Linux 5.10 的 `boot_params.ext_cmd_line_ptr` 可以提供高 32 位扩展。

因此逻辑关系是：

```text
boot_params/header
    │
    └── pointer metadata ──> command-line string elsewhere in memory
```

`copy_boot_params()` 还保留旧式 command-line protocol 的兼容处理：只有新的 `cmd_line_ptr` 没有提供、旧 magic 又有效时，setup 才从旧 segment/offset 形式推导新的 linear pointer。

这里体现了 boot protocol 的一个典型设计原则：新字段可以逐步替代旧接口，但启动早期仍需要兼容历史 loader。

## 7. initrd：位置和长度也是协议输入

initrd 的基本传递方式类似：`setup_header.ramdisk_image` 与 `ramdisk_size` 保存低 32 位地址和长度，`boot_params` 还提供 `ext_ramdisk_image` / `ext_ramdisk_size` 扩展高位。

能否把相关对象放到 4 GiB 以上还受 kernel/loader 的协议能力约束，例如 `xloadflags`。所以“字段可以表达 64 位地址”和“当前 loader 一定会选择 4 GiB 以上装载”是两个不同结论。

B01 只关注 loader 把 initrd 的**物理位置与大小**交给 kernel。initramfs 如何展开、何时成为 rootfs 的一部分，留到 B05。

## 8. E820 说明 `boot_params` 是跨阶段对象

Linux 5.10 `arch/x86/boot/main.c:main()` 会调用 `detect_memory()`。zeropage 中有：

```text
e820_entries
e820_table[128]
```

因此 E820 是理解 `boot_params` 所有权的好例子：参数块并非某一个参与者一次性写完。

可以把字段来源分成三类：

```text
映像自身
    setup_header 中的 protocol/version/capability/layout 信息

boot loader
    loader identity、command line、initrd placement 等启动输入

setup/platform detection
    E820、video、部分 BIOS/平台信息等
```

具体字段仍应以 boot protocol 文档规定为准，但这个模型比“loader 填一个结构体，kernel 读取”更接近真实实现。

完整的 E820 规范化以及 E820 → memblock → buddy 的过程属于 `memory/`。本章只关注信息怎样越过启动阶段边界。

## 9. `sentinel`：协议还规定字节所有权

`boot_params.sentinel` 位于 `0x1ef`。Linux 5.10 的注释说明，它用于识别某些不遵守约定、把过多 setup-header 邻近字节复制进 `boot_params` 的 loader。

这个细节很有价值，因为它说明 ABI 不只是“字段的名字和含义”。ABI 还包括：

- 哪一段内存由谁初始化；
- loader 可以复制多少字节；
- 哪些保留区域必须保持干净；
- kernel 怎样识别历史实现造成的不可信内容。

所以学习 boot protocol 时，字段布局、版本协商和所有权规则必须一起看。

## 10. setup `main()`：把协议输入变成下一阶段可用状态

Linux 5.10 setup 主线可以简化为：

```text
copy_boot_params()
→ console_init()
→ init_heap()
→ validate_cpu()
→ set_bios_mode()       [x86_64 路径]
→ detect_memory()
→ keyboard / IST / optional APM / optional EDD
→ set_video()
→ go_to_protected_mode()
```

这条路径说明 setup 不是一个只负责“跳转”的薄壳。它在进入 protected-mode handoff 前完成三类工作：

1. 接管映像/loader 已提供的协议数据；
2. 检查当前 CPU/启动条件；
3. 补充后续内核需要的平台信息。

到 `go_to_protected_mode()` 时，`boot_params` 已经成为后续阶段的重要输入对象。

`go_to_protected_mode()` 内部怎样建立机器级 protected-mode 环境不是本章主体；相关汇编机制由 assembly 课程负责，B02 再从启动阶段责任继续向 compressed kernel 推进。

## 11. 一次完整的 B01 数据流

把前面的内容压缩成一条数据流：

```text
kernel build
    │
    ├── header.S + build.c
    v
bzImage with setup_header (protocol 2.15)
    │
    │ loader parses capabilities/layout
    v
legal kernel/setup placement
    + command-line location
    + initrd location/size
    + loader-owned parameters
    │
    v
setup main()
    │ copy_boot_params()
    │ platform/BIOS detection
    v
4 KiB boot_params / zeropage
    │
    v
go_to_protected_mode()
    │
    v
compressed kernel and later formal kernel continue consuming boot information
```

这条链同时有两个方向的信息流：kernel image 先通过 header 告诉 loader “我怎样被启动”；loader/setup 再通过 `boot_params` 告诉后续 kernel “这一次实际怎样启动、机器是什么状态”。这就是 boot protocol 存在的核心原因。

## 12. 四个必须保持的边界

### 12.1 `setup_header` 不等于 `boot_params`

前者是 bzImage 自描述协议头；后者是 4 KiB zeropage，并内嵌一个 `setup_header`。

### 12.2 protocol capability 不等于本次启动选择

`relocatable_kernel`、`xloadflags`、above-4G loading 等表达能力和约束；它们不证明当前 loader 实际采用了对应路径。

### 12.3 image layout 不等于 CPU mode

setup/protected-mode payload 是映像与协议概念；real/protected/long mode 是 CPU 执行状态。二者有关联，但不是同一层事实。

### 12.4 `boot_params` 的来源不只有 loader

映像 header、loader 输入和 setup/platform detection 都会贡献状态。判断具体字段时必须回到 Linux 5.10 protocol 文档和源码。

## 13. Linux 5.10 源码阅读入口

本章对应的主要文件是：

- `Documentation/x86/boot.rst`：boot protocol ABI 和版本历史；
- `arch/x86/boot/header.S`：映像中的 setup header；
- `arch/x86/boot/main.c`：`boot_params`、`copy_boot_params()` 与 setup 主线；
- `arch/x86/include/uapi/asm/bootparam.h`：`setup_header`、`boot_params` 和字段布局；
- `arch/x86/boot/tools/build.c`：构建阶段补写的 header 信息。

源码事实与字段核验记录见 [`../source-paths/01-linux-boot-protocol-linux-5.10.md`](../source-paths/01-linux-boot-protocol-linux-5.10.md)。

下一步实验应验证三类事实：Linux 5.10 的协议版本和关键偏移；`setup_header` 与 4096-byte `boot_params` 的包含关系；`main()` 中 `copy_boot_params()`、`detect_memory()` 和 `go_to_protected_mode()` 的实际阶段顺序。
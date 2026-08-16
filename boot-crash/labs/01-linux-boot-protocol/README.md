# B01 实验：Linux boot protocol 与 `boot_params` 静态验证

本实验服务于 B01《Linux boot protocol 与 `boot_params`》。目标不是背诵字段，而是把正文中的几个 ABI 结论落实为可以从 Linux 5.10 源码和构建产物复核的证据。

## 1. 要验证的问题

至少回答下面六个问题：

1. Linux 5.10 x86 boot protocol header 是否确实使用 `HdrS` 和 version `0x020f`；
2. `struct boot_params` 是否固定为 4096 bytes，并在 `0x1f1` 内嵌 `struct setup_header hdr`；
3. `e820_entries`、`sentinel`、`hdr`、`e820_table` 的关键 ABI offset 是否分别为 `0x1e8`、`0x1ef`、`0x1f1`、`0x2d0`；
4. command line 与 initrd 是否通过地址/长度元数据传递，而不是把字符串或 initrd 内容内嵌进 `setup_header`；
5. setup `main()` 是否先执行 `copy_boot_params()`，随后经过 CPU/平台探测并执行 `detect_memory()`，最后才进入 `go_to_protected_mode()`；
6. 哪些结论属于源码/ABI 静态事实，哪些只有在真实 bzImage 或启动现场中才能证明。

## 2. Linux 5.10 源码基线

使用 Linux tag `v5.10`，重点文件：

```text
Documentation/x86/boot.rst
arch/x86/boot/header.S
arch/x86/boot/main.c
arch/x86/include/uapi/asm/bootparam.h
arch/x86/boot/tools/build.c
```

不要使用当前 master 的字段反推 5.10。

## 3. 验证 `HdrS` 与 protocol 2.15

先从源码定位协议签名和版本：

```bash
git grep -n 'HdrS' v5.10 -- arch/x86/boot/header.S Documentation/x86/boot.rst
git grep -n '0x020f' v5.10 -- arch/x86/boot/header.S
```

硬验收条件：Linux 5.10 `header.S` 的 setup header 必须能够定位到 `HdrS`，version 必须是 `0x020f`，即 protocol 2.15。

这里验证的是 **kernel image 暴露给 loader 的协议版本**，不是 Linux 版本号，也不是 `boot_params` 自身的版本号。

## 4. 验证 `boot_params` 的 4 KiB 契约

阅读：

```bash
git show v5.10:arch/x86/include/uapi/asm/bootparam.h | less
git show v5.10:arch/x86/boot/main.c | less
```

至少定位：

```text
struct setup_header
struct boot_params
BUILD_BUG_ON(sizeof(boot_params) != 4096)
copy_boot_params()
```

硬验收条件：

```text
sizeof(struct boot_params) == 4096
boot_params.hdr offset == 0x1f1
```

注意：`BUILD_BUG_ON` 是 Linux 5.10 setup 代码对结构大小的编译期约束；不能因为看到 `struct setup_header` 也出现在 `bootparam.h` 中，就把两个结构当成同一个对象。

## 5. 用一个小程序验证 UAPI 布局

如果本地有 Linux 5.10 源码树，可以建立临时程序 `check_layout.c`：

```c
#include <stddef.h>
#include <stdio.h>
#include "arch/x86/include/uapi/asm/bootparam.h"

int main(void)
{
    printf("sizeof(boot_params) = %#zx\n", sizeof(struct boot_params));
    printf("e820_entries        = %#zx\n", offsetof(struct boot_params, e820_entries));
    printf("sentinel            = %#zx\n", offsetof(struct boot_params, sentinel));
    printf("hdr                 = %#zx\n", offsetof(struct boot_params, hdr));
    printf("e820_table          = %#zx\n", offsetof(struct boot_params, e820_table));
    return 0;
}
```

由于直接包含 kernel UAPI header 时还依赖同一源码树的 UAPI include 路径，推荐先生成 headers：

```bash
make -C /path/to/linux-5.10 headers_install INSTALL_HDR_PATH=/tmp/linux510-uapi
```

然后按实际安装后的 header 路径调整 include，并编译运行。也可以在完整 kernel build 环境中写一个只做 `offsetof`/`BUILD_BUG_ON` 的辅助编译单元。

预期 ABI 锚点：

```text
sizeof(boot_params) = 0x1000
offsetof(e820_entries) = 0x1e8
offsetof(sentinel)     = 0x1ef
offsetof(hdr)          = 0x1f1
offsetof(e820_table)   = 0x2d0
```

这些是结构布局验收值，不是运行时物理地址。

## 6. 验证 command line 与 initrd 的元数据模型

在 `struct setup_header` / `struct boot_params` 中定位：

```text
cmd_line_ptr
ext_cmd_line_ptr
cmdline_size
ramdisk_image
ramdisk_size
ext_ramdisk_image
ext_ramdisk_size
```

观察点不是“字段存在”本身，而是它们保存的是地址、长度或能力元数据。

因此应得到：

```text
setup_header / boot_params
        ├── address metadata ──> command-line bytes elsewhere
        └── address + size    ──> initrd bytes elsewhere
```

不要把 `cmd_line_ptr` 解释为 C 字符数组，也不要把 `ramdisk_image` 解释为 initrd 内容本身。

## 7. 验证 setup `main()` 的阶段顺序

从 Linux 5.10 `arch/x86/boot/main.c` 读取 `main()`，记录下面几个事件的源码顺序：

```text
copy_boot_params()
validate_cpu()
detect_memory()
set_video()
go_to_protected_mode()
```

其中 `CONFIG_X86_64` 路径还会出现 `set_bios_mode()`。

硬验收条件不是要求这些函数彼此直接调用，而是要求在 setup `main()` 主线上确认：

```text
接管 protocol/header 输入
        ↓
检查 CPU/初始化 setup 环境
        ↓
补充内存与平台信息
        ↓
进入 protected-mode handoff
```

因此 `boot_params` 是跨阶段逐步形成的参数块，而不是 loader 一次性填写后 setup 完全只读的对象。

## 8. 可选：从真实 bzImage 验证 header

如果已经构建 Linux 5.10 x86 `arch/x86/boot/bzImage`，可进一步检查实际映像，而不只检查源码。

Linux 内核源码自带 `tools`/构建逻辑会生成最终 boot image；也可以用十六进制工具观察 protocol 固定 offset。操作前必须以 `Documentation/x86/boot.rst` 中的 offset 定义为准，不要靠搜索字符串猜字段边界。

建议至少记录：

```text
bzImage SHA256
HdrS 所在 offset
version bytes
setup_sects
loadflags/xloadflags
```

真实映像验证能够证明“构建产物确实携带这些字段”，但仍不能证明某个 boot loader 在一次具体启动中实际采用了哪种 placement/capability 路径。

## 9. 证据等级

本实验把证据分为三层：

```text
L1 源码/UAPI 证据
header.S、bootparam.h、main.c 中的定义和顺序。

L2 构建产物证据
真实 Linux 5.10 bzImage 中的 header bytes、最终 build-time 填充值。

L3 运行时证据
boot loader 实际选择的装载地址、command line/initrd 位置、传入 zeropage 内容。
```

L1 通过不能写成 L2/L3 已验证。某个 capability bit 存在，也不能推出本次启动一定使用对应能力。

## 10. 结果记录模板

```text
Linux source/tag:
compiler/toolchain:

[源码]
HdrS:
version:
sizeof boot_params:
hdr offset:
e820_entries offset:
sentinel offset:
e820_table offset:
setup main order:

[构建产物，可选]
bzImage SHA256:
header bytes/offset:

[运行时，可选]
boot loader:
boot_params physical address:
command line physical address:
initrd physical address/size:

未执行项及原因:
```

## 11. 当前环境状态

本实验说明依据已经完成的 Linux 5.10 source-path 核验编写。当前维护环境没有可执行的 Linux v5.10 checkout/完整 kernel build tree，因此本次没有伪造 `headers_install`、C `offsetof` 程序、bzImage 十六进制或 boot-loader 运行结果。

下一步应补 `expected-analysis.md`，把上述 ABI offset、setup 顺序、证据等级以及常见误判固定为独立验收基线。
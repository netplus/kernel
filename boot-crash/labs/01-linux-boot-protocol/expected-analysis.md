# B01 实验预期分析：Linux boot protocol 与 `boot_params`

本文件是 `README.md` 中 B01 静态验证实验的验收基线。它固定 Linux 5.10 下必须成立的 ABI 事实、setup 主线顺序和证据边界；尚未在真实 checkout、bzImage 或 boot-loader 现场执行的项目不能写成实测结果。

## 1. 验收目标

B01 实验通过后，应能够用证据回答三个层次的问题：

1. Linux 5.10 的 x86 boot image 对 loader 暴露了什么协议；
2. loader、setup 与后续 kernel 如何通过 `boot_params` 交接本次启动的信息；
3. 哪些结论只由源码/UAPI 即可证明，哪些必须继续检查真实 bzImage 或运行现场。

本章不验证 real/protected/long mode 的机器级切换；该机制属于 assembly。这里验证的是 boot protocol ABI 和阶段交接。

## 2. protocol header 的硬验收值

Linux 5.10 `arch/x86/boot/header.S` 中必须能够定位到：

```text
signature: "HdrS"
version:   0x020f
```

`0x020f` 表示 boot protocol 2.15。它是 `setup_header` 的协议版本，不是 Linux kernel 版本号，也不是 `struct boot_params` 的版本号。

若实际检查的源码不是 tag `v5.10`，不能直接用本文件的版本值作为通过条件。

## 3. `setup_header` 与 `boot_params` 的关系

必须得到下面的对象关系，而不是把两个名字当成同义词：

```text
bzImage 中的 setup_header
        ↓ copy_boot_params()
boot_params.hdr
        ↓
4 KiB boot_params / zeropage 的一个内嵌成员
```

硬验收条件：

```text
sizeof(struct boot_params) == 0x1000
offsetof(struct boot_params, hdr) == 0x1f1
```

因此：

- `setup_header` 是 kernel image 向 boot loader 暴露的自描述协议头；
- `boot_params` 是跨 loader/setup/kernel 阶段传递的 4096-byte 参数块；
- `boot_params` 包含 `setup_header`，但不等于 `setup_header`。

`arch/x86/boot/main.c` 中的 `BUILD_BUG_ON(sizeof(boot_params) != 4096)` 是 Linux 5.10 setup 对这一大小契约的编译期保护。

## 4. `boot_params` 关键布局

UAPI 布局检查至少必须得到：

```text
e820_entries = 0x1e8
sentinel     = 0x1ef
hdr          = 0x1f1
e820_table   = 0x2d0
```

这些值是 **结构内 byte offset**，不是运行时物理地址。

`e820_table` 的 zeropage 固定容量为 128 entries。B01 只验证其作为 boot-time handoff 数据的布局；E820 后续如何进入 memblock 和正式内存管理留在 memory 领域。

## 5. command line 的预期模型

必须把 command line 理解为“参数块中的地址元数据指向参数块外的字符串字节”。Linux 5.10 相关字段包括：

```text
setup_header.cmd_line_ptr
boot_params.ext_cmd_line_ptr
setup_header.cmdline_size
```

因此正确模型是：

```text
boot_params/header
    └── command-line address metadata
            └──> command-line bytes elsewhere in memory
```

错误模型包括：

- 把 `cmd_line_ptr` 当成字符数组；
- 认为 command-line 字符串内嵌在 `setup_header`；
- 看到 `cmdline_size` 就把它解释为本次字符串实际长度。它首先是协议能力/长度约束字段，具体语义应按 boot protocol 文档判断。

## 6. initrd 的预期模型

Linux 5.10 使用低位字段与扩展字段描述 initrd：

```text
ramdisk_image
ramdisk_size
ext_ramdisk_image
ext_ramdisk_size
```

B01 应得到的模型是：

```text
boot parameters
    ├── initrd physical-address metadata
    └── initrd size metadata
            └──> initrd bytes elsewhere in memory
```

这些字段不是 initrd 内容本身。能否使用超过 4 GiB 的地址还受 boot protocol 版本和 `xloadflags` 能力约束；“字段存在”不能推出某次启动实际采用 above-4G placement。

## 7. E820 与字段所有权

必须拒绝“boot loader 一次性填好整个 `boot_params`，setup 只读”的模型。

Linux 5.10 setup `main()` 会调用 `detect_memory()`，因此至少存在：

```text
image/build 提供的 header 信息
        +
loader 按 protocol 填写的输入
        +
setup/BIOS 探测和补充的平台状态
        ↓
boot_params
```

字段的具体所有权必须逐项依据 protocol 和源码判断，不能从“字段位于 boot_params”推出其唯一生产者。

## 8. `sentinel` 的验收含义

`sentinel` 位于 `0x1ef`。它服务于坏 loader/过量复制的防护语义：规范 loader 应把需要的 `setup_header` 数据复制到干净的 `boot_params`，而不是把 header 前后不属于自己的字节粗暴覆盖过去。

实验只需确认这一 ABI 字节所有权/防护模型。不要把 sentinel 解释成 boot protocol 版本标志、E820 终止项或普通 padding。

## 9. setup `main()` 的阶段顺序

Linux 5.10 `arch/x86/boot/main.c:main()` 的主线必须与下面的阶段关系一致：

```text
copy_boot_params()
→ console_init()
→ init_heap()
→ validate_cpu()
→ set_bios_mode()       [x86_64 路径]
→ detect_memory()
→ 其他平台探测
→ set_video()
→ go_to_protected_mode()
```

实验的硬条件不是要求这些函数形成彼此直接调用链，而是确认它们在 `main()` 主线中的相对顺序。

因此可以得到：

```text
接管 image/loader 的 protocol 输入
→ 建立 setup 自身可运行环境并检查 CPU
→ 补充 memory/platform 信息
→ protected-mode handoff
```

`go_to_protected_mode()` 之后的寄存器、GDT、CR0/CR4/EFER 等机器状态不属于本实验的通过条件。

## 10. `bzImage` 布局与 CPU mode 必须分层

B01 中“setup 部分 / protected-mode kernel 部分”描述 boot image 和 protocol 布局。它不能单独证明 CPU 当前已经处于 protected mode 或 long mode。

因此以下推理不成立：

```text
映像中存在 protected-mode kernel
⇒ 当前 CPU 已进入 protected mode
```

CPU execution mode 必须由实际控制寄存器、segment state 和控制流等机器证据判断；相关机制由 assembly 课程负责。

## 11. L1 / L2 / L3 证据等级

### L1：源码与 UAPI

能够证明：

- `HdrS` 和 `0x020f` 的源码定义；
- `boot_params` 结构布局；
- setup `main()` 的源码顺序；
- command line/initrd/E820 字段的接口形式。

不能据此证明某个实际 bzImage 的最终 build-time 字节，也不能证明某次 boot-loader 运行采用了哪条 capability 路径。

### L2：真实 Linux 5.10 bzImage

应至少记录：

```text
bzImage SHA256
HdrS offset/bytes
version bytes
setup_sects
loadflags/xloadflags
```

L2 能证明构建产物实际携带什么 header 值，但仍不能证明 loader 在一次具体启动中的 placement 和输入。

### L3：运行现场

运行时观察才能证明：

```text
boot_params physical address
command-line physical address/content
initrd physical address/size
实际 loader 标识和本次选择的能力路径
```

L1/L2 通过不能写成 L3 已验证。

## 12. 常见误判的失败条件

出现下面任一结论时，本实验不能判定通过：

1. `setup_header == boot_params`；
2. `boot_params` 全部由 boot loader 一次性生成；
3. command line 或 initrd 内容内嵌在 `setup_header`；
4. 把 `0x1f1`、`0x2d0` 等 offset 当成物理地址；
5. 把 protocol capability bit 当成本次启动一定采用该路径；
6. 把 bzImage 的“protected-mode kernel”布局名称当成 CPU mode 的动态证据；
7. 没有真实 bzImage/运行现场，却填写 L2/L3 的伪造结果。

## 13. 当前验证状态

已经完成：

- Linux 5.10 `Documentation/x86/boot.rst`、`header.S`、`main.c`、`bootparam.h` 的源码事实核验；
- B01 正式教程；
- 静态实验流程和本验收基线。

当前维护环境尚未执行：

- Linux v5.10 checkout 中的 UAPI `offsetof`/`sizeof` 编译运行；
- 真实 v5.10 bzImage header bytes 检查；
- boot-loader/QEMU 运行时 zeropage、command line、initrd 位置观察。

因此目前的结论属于 L1 源码事实与实验设计，不冒充 L2/L3 实测结果。下一步可把 L1 的 header/layout/setup-order 条件转换成自动 source/layout checker，再在具备完整 v5.10 checkout 时执行。
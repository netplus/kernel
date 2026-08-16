# B01 收章复核：Linux boot protocol 与 `boot_params`

本文件用于确认 B01 已经形成一个可以独立验收的课程单元。复核范围包括正式教程、Linux 5.10 source-path、实验 README、`expected-analysis.md` 以及自动 source-contract checker。复核基线固定为 upstream Linux tag `v5.10`；未在真实 checkout、bzImage 或 boot-loader 现场执行的项目继续保持为增强证据，不写成已实测结果。

## 1. 本章解决的问题

B01 解释 boot loader 与 Linux kernel 之间为什么需要稳定的 boot protocol，以及两类容易混淆的对象如何分工：

```text
bzImage / setup_header
        │ kernel image 向 loader 描述映像和能力
        v
boot loader
        │ 按协议选择装载方式并提供本次启动输入
        v
setup + 4 KiB boot_params / zeropage
        │ 汇合 header、loader 输入和 setup/platform 探测结果
        v
protected-mode handoff / 后续启动阶段
```

因此本章的核心结论不是字段列表，而是一个双向 ABI 模型：`setup_header` 主要描述“这个映像怎样被合法启动”，`boot_params` 主要携带“这一次启动实际带来了什么信息”。

## 2. Linux 5.10 事实复核

### 2.1 protocol 版本

Linux 5.10 `arch/x86/boot/header.S` 使用 `HdrS` signature，boot protocol version 为 `0x020f`，即 2.15。这里的 version 是 `setup_header` 协议版本，不是 Linux kernel 版本，也不是 `boot_params` 自身版本。

### 2.2 `setup_header` 与 `boot_params`

Linux 5.10 `arch/x86/include/uapi/asm/bootparam.h` 定义 packed `struct setup_header` 与 packed `struct boot_params`。后者是 zeropage，并在 `0x1f1` 内嵌 `struct setup_header hdr`。

Linux 5.10 `arch/x86/boot/main.c:copy_boot_params()` 同时提供两个关键事实：

```text
BUILD_BUG_ON(sizeof(boot_params) != 4096)
memcpy(&boot_params.hdr, &hdr, sizeof(hdr))
```

所以必须保持：

```text
setup_header != boot_params
boot_params contains setup_header
sizeof boot_params == 4096 bytes
```

### 2.3 关键 ABI 布局

本章使用并在实验中固定的 zeropage 锚点与 Linux 5.10 UAPI 一致：

```text
e820_entries  0x1e8
sentinel      0x1ef
hdr           0x1f1
e820_table    0x2d0
```

`E820_MAX_ENTRIES_ZEROPAGE` 为 128。上述值是结构内 byte offset，不是运行时物理地址。

### 2.4 command line 与 initrd

教程和实验都把 command line 与 initrd 解释为参数块中的地址/长度元数据指向其他内存，而不是把字符串或 initrd 内容内嵌进 `setup_header`。这与 Linux 5.10 的 `cmd_line_ptr`、`ext_cmd_line_ptr`、`ramdisk_image`、`ramdisk_size` 以及扩展字段模型一致。

同时保持一个重要边界：字段或 capability bit 能表达某种装载能力，不等于某一次启动实际采用了该 placement。

### 2.5 setup `main()` 主线与 CONFIG 条件

Linux 5.10 `arch/x86/boot/main.c:main()` 的相关主线为：

```text
copy_boot_params()
→ console_init()
→ init_heap()
→ validate_cpu()
→ set_bios_mode()
→ detect_memory()
→ keyboard / IST / optional APM / optional EDD
→ set_video()
→ go_to_protected_mode()
```

`set_bios_mode()` 这个函数本身会被调用，但其中 BIOS mode notification 的实际 `int 0x15` 代码受 `CONFIG_X86_64` 条件保护；APM 与 EDD 查询也分别受对应配置条件控制。正文、source-path 和实验没有把这些条件路径写成所有配置都无条件执行的事实。

这条主线支持本章的对象所有权模型：`boot_params` 不是 loader 一次性填写后 setup 只读的结构；setup 会继续探测并补充平台状态。

## 3. 架构规则、ABI、内核设计与具体实现的分层

B01 已保持下面四层边界：

- x86 CPU 的 real/protected/long mode 切换属于机器执行机制，由 assembly 课程完整解释；
- Linux x86 boot protocol 是 loader 与 kernel 之间的 ABI；
- “自描述映像 + 跨阶段参数块”是 Linux 启动设计；
- `0x020f`、4096-byte zeropage、具体字段 offset、`copy_boot_params()` 和 `main()` 顺序是 Linux 5.10 的具体实现事实。

因此“protected-mode kernel”作为 bzImage/protocol 布局名称不能被用作 CPU 当前 mode 的动态证据。

## 4. 实验闭环复核

B01 实验已经提供：

```text
labs/01-linux-boot-protocol/README.md
labs/01-linux-boot-protocol/expected-analysis.md
labs/01-linux-boot-protocol/verify_source_contract.py
labs/01-linux-boot-protocol/test_verify_source_contract.py
```

自动 checker 固定 11 项 L1 source-contract 条件；fixture self-test 已实际执行，一个完整正例与七个负例全部通过。负例覆盖 protocol version、`HdrS`、ABI offset、E820 capacity、4 KiB 大小契约、header copy 和 setup `main()` 顺序破坏。

这证明的是 matcher 自身能够接受/拒绝预期 fixture，而不是证明真实 Linux checkout 或真实机器已经通过验证。

## 5. 证据等级复核

本章当前证据状态分为：

```text
已完成
- upstream Linux v5.10 源码事实人工核验
- 正式教程
- source-path
- 实验与 expected analysis
- source-contract checker
- checker fixture self-test 实际执行

尚未执行的增强证据
- checker 对真实 Linux v5.10 checkout 的 CLI 运行
- 实际编译的 sizeof/offsetof 布局验证
- 真实 Linux v5.10 bzImage header bytes 检查
- boot-loader/QEMU 现场的 zeropage、command line、initrd 地址观察
```

后四项需要相应 source/build/boot 环境。它们能增强证据强度，但当前材料没有把它们伪装成已完成结果。

## 6. 跨领域边界复核

B01 没有重复展开以下主题：

- GDT、CR0/CR4/EFER 和 mode transition：属于 `assembly/`；
- E820 如何规范化并进入 memblock/buddy：属于 `memory/`；
- initramfs/rootfs 如何展开并进入用户空间：留到 B05；
- compressed kernel 自己的临时运行环境和解压：进入 B02。

因此本章只负责 boot protocol 与参数交接，不越界扩展成 CPU mode、完整内存管理或 rootfs 专题。

## 7. 常见误区验收

读完 B01 后应能够拒绝以下说法：

1. `setup_header` 就是整个 `boot_params`；
2. `boot_params` 完全由 boot loader 一次性填写；
3. command line 字符串和 initrd 内容直接内嵌在 `setup_header`；
4. `0x1f1`、`0x2d0` 是运行时物理地址；
5. capability bit 存在就证明当前启动使用了该路径；
6. bzImage 中存在“protected-mode kernel”就证明 CPU 此刻处于 protected mode；
7. fixture self-test 通过就等于真实 Linux 5.10 checkout、bzImage 或启动现场已经验证。

如果仍接受其中任一说法，说明本章的 ABI/阶段模型尚未建立。

## 8. 收章结论

B01 已经能够回答本课程的章节完成标准：为什么需要 boot protocol、核心对象如何分工、Linux 5.10 的具体入口和布局在哪里、setup 如何继续完善参数块、哪些路径受配置影响、如何通过实验验证，以及静态事实与构建/运行时事实的边界是什么。

因此 B01 内容层面可以收章。下一章 B02 应从 compressed kernel 为什么需要独立的早期执行环境开始，沿 `arch/x86/boot/compressed/head_64.S`、`misc.c` 和 `kaslr.c` 核验临时栈、CPU/页表前置条件、解压与 KASLR/物理放置，再说明它如何把控制权交给 formal kernel；GDT、控制寄存器和 long-mode transition 的机器级原理继续引用 assembly，不在 B02 重复展开。
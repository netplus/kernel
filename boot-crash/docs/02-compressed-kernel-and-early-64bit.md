# B02：压缩内核与早期 64 位环境

B01 解决了 boot loader 与 Linux kernel 之间如何通过 boot protocol 交付映像信息和本次启动参数的问题。接下来还有一个容易被名字掩盖的阶段：boot loader 并不是直接把最终的 `vmlinux` 放到它正常运行的位置，然后调用一个普通的“解压函数”。x86 的 bzImage 中存在一个能够独立执行的 **compressed kernel**。它先获得 CPU 控制权，建立只够自己工作的早期环境，选择正式内核的放置位置，解压 payload，按 ELF 装载语义整理 `PT_LOAD` 段，处理需要的 relocation，最后才把控制权交给 formal kernel。

本章以 Linux kernel 5.10、x86-64 为基线。GDT、控制寄存器、long-mode transition 的机器机制已经在 `assembly/` 中完整解释；页表项本身的结构和通用页表机制属于 `memory/`。这里关注的是这些状态在 **compressed stage** 中承担什么职责，以及 compressed kernel 与 formal kernel 如何交接。

对应源码核验记录：[B02 Linux 5.10 源码核验](../source-paths/02-compressed-kernel-linux-5.10.md)。

## 1. 为什么需要一个独立的 compressed stage

内核映像希望同时满足两个目标：

1. 启动介质上的映像尽量小，因此正式 kernel payload 被压缩；
2. 启动时又必须在通用内核基础设施尚不存在的情况下把它恢复成可执行布局。

第二点决定了解压器不能依赖“已经启动好的 Linux”。此时没有正常进程上下文，没有伙伴系统和 SLUB，也不能假定正式内核的虚拟地址空间已经接管 CPU。解压代码必须带着自己的入口汇编、栈、早期页表、简单 heap、解压算法和必要的输出/错误处理代码运行。

Linux 5.10 的 `arch/x86/boot/compressed/Makefile` 正体现了这个边界：compressed C 代码使用 `-fPIE`、`-ffreestanding`、`-fno-stack-protector` 等选项，compressed `vmlinux` 使用 `-pie` 链接；KASAN、KCSAN、KCOV 等依赖正常 runtime 的设施被禁用。原因不是性能优化，而是这一阶段还没有正常 kernel runtime 可以依赖。

因此应先建立下面的模型：

```text
boot loader / setup
        |
        | boot_params + CPU entry state
        v
compressed kernel (独立早期执行映像)
        |
        | 选择位置、解压、ELF placement、relocation
        v
formal kernel
```

这里有两个不同的 kernel image 语境。后面看到同名入口或相近地址时，首先要问“它属于哪个映像”。

## 2. 从 formal `vmlinux` 到 compressed `vmlinux`

Linux 5.10 的构建关系可以简化为：

```text
formal vmlinux
  -> vmlinux.bin
  -> [vmlinux.relocs]
  -> vmlinux.bin.all
  -> vmlinux.bin.{gz,bz2,lzma,xz,lzo,lz4,zst}
  -> piggy.S / piggy.o
  -> arch/x86/boot/compressed/vmlinux
```

`vmlinux.bin` 是从正式 `vmlinux` 去掉调试和注释等内容后形成的 binary；如果 `CONFIG_X86_NEED_RELOCS` 生效，`vmlinux.relocs` 会附加到 `vmlinux.bin.all`。选定的压缩算法再压缩这份输入，`piggy.o` 将压缩 payload 封装进 compressed `vmlinux`。

因此：

```text
arch/x86/boot/compressed/vmlinux
```

不是 formal `vmlinux` 的另一个文件名。它是包含 decompressor 与 compressed payload 的独立 ELF 映像。实际调试时，应分别对 compressed `vmlinux` 和根目录 formal `vmlinux` 使用 `nm`、`readelf`、`objdump`，不能把两个 ELF 的符号地址放进同一个地址空间直接比较。

## 3. compressed kernel 可以从两种入口状态进入

Linux 5.10 `arch/x86/boot/compressed/head_64.S` 同时提供：

```text
startup_32   32-bit entry
startup_64   64-bit entry
```

32-bit loader 可以从 `startup_32` 进入，compressed assembly 再建立进入 long mode 所需的最小状态。符合 boot protocol 要求的 64-bit loader 也可以直接进入 compressed `startup_64`。

这一区别很重要，因为它说明 compressed `startup_64` 不能依赖“前面一定执行过本文件的 `startup_32`”。如果由 64-bit loader 直接进入，loader 必须已经提供满足协议要求的 CPU/paging 环境，包括让 compressed image、zero page 和 command line 可访问的映射。

两条入口路径最终要收敛到同一个目标：让 compressed C decompressor 可以安全执行。

## 4. 位置问题：不要只问“kernel 被加载到哪里”

这一阶段至少要区分三个地址概念：

```text
A. compressed image 当前实际运行的位置
B. compressed image 为避免覆盖自己而使用的安全运行/搬移区域
C. formal kernel 最终选择的 output 物理位置
```

它们可能不同。

在 `CONFIG_RELOCATABLE` 下，compressed assembly 不能把当前装载地址写死。它会利用运行时位置计算 image base，并结合 `boot_params.hdr.kernel_alignment`、`LOAD_PHYSICAL_ADDR`、`BP_init_size` 和映像末端等信息，为后续解压建立不会过早覆盖自身的布局。

这也是 compressed image 采用位置无关构建方式的直接原因之一：boot loader 允许把它放在不同的合法物理位置，而 decompressor 必须先弄清“我现在在哪里”，再决定“formal kernel 应该去哪里”。

## 5. 临时栈和早期页表只服务于当前阶段

compressed `startup_64` 会建立以 `boot_stack_end` 为基础的栈。这个栈属于 decompressor 的临时执行环境，并不是 formal kernel 后续任务使用的正常内核栈。

同样，`head_64.S` 中建立或调整的早期映射，目标是让当前 compressed stage 能访问：

```text
compressed code/data
boot_params / zero page
command line
临时 heap / stack
解压输入
解压 output
```

这些页表的阶段责任比具体页表项位定义更值得在 B02 记住：**formal kernel 尚未接管地址空间，因此 decompressor 必须先为自己提供足够的可执行映射。**

完整的 long-mode 开启过程引用 `assembly/`；完整页表机制引用 `memory/`。B02 不重复展开这些机制。

## 6. `boot_params` 如何继续穿过 compressed stage

B01 中建立的 4 KiB `boot_params` 并不会在进入 decompressor 后失效。compressed assembly 把它作为关键输入传给 C 侧 `extract_kernel()`。

Linux 5.10 `extract_kernel()` 的第一个关键状态接管是：

```text
boot_params = rmode
```

随后它会调用 `sanitize_boot_params()`，并继续从 `boot_params` 中取得屏幕信息、命令行、initrd、memory map 等启动数据。KASLR 的避让逻辑也需要这些信息，以避免把 formal kernel 放到仍被启动数据占用的区域。

因此 `boot_params` 是一个真正的跨阶段对象：

```text
boot loader / setup
        -> compressed kernel
        -> formal kernel early boot
```

它不是 setup 阶段结束后就可以丢弃的临时结构。

## 7. `extract_kernel()` 不只是“调用解压算法”

Linux 5.10 的中心入口位于：

```text
arch/x86/boot/compressed/misc.c
asmlinkage __visible void *extract_kernel(...)
```

其主线可概括为：

```text
接管 boot_params
-> sanitize_boot_params()
-> 初始化早期 console / heap
-> 计算 needed_size
-> choose_random_location()
-> 校验 output / virt_addr
-> __decompress()
-> parse_elf()
-> handle_relocations()
-> 返回 formal-kernel entry
```

把这一过程只称为“解压”会漏掉三个关键问题：formal kernel 放在哪里、解压后的 ELF 怎样形成最终 segment 布局、地址发生变化时哪些引用需要修正。

## 8. 为什么 `needed_size` 大于“解压文件大小”这个概念

`extract_kernel()` 计算：

```text
kernel_total_size = VO__end - VO__text
needed_size = max(output_len, kernel_total_size)
```

x86-64 下还会按 `MIN_KERNEL_ALIGN` 向上对齐。

这里要避免一个常见误解：解压器需要的目标区域不能只容纳压缩算法输出的文件内容。formal kernel 运行时还需要 `.bss`、`.brk` 等不一定以同样形式占据压缩 payload 的范围。因此位置选择必须保证整个 kernel runtime footprint 可以安全落下。

这也是 KASLR 搜索候选区域时使用 `needed_size` 一类完整范围，而不是只拿压缩文件长度找空洞的原因。

## 9. KASLR 是“约束内随机”，不是任意地址随机

Linux 5.10 的 KASLR 位置选择主要位于：

```text
arch/x86/boot/compressed/kaslr.c
```

并且 `kaslr.o` 只有在 `CONFIG_RANDOMIZE_BASE` 下才加入 compressed `vmlinux`。

位置选择的正确模型是：

```text
memory map / boot protocol 给出可用范围
        |
        v
排除不能覆盖的区域
        |
        v
按 image size 和 CONFIG_PHYSICAL_ALIGN 形成合法 slots
        |
        v
从合法 slots 中随机选择
```

Linux 5.10 的避让对象包括 compressed image/decompressor 自身、initrd、command line、`boot_params` 以及 `memmap`/EFI 等额外保留范围。

因此 KASLR 不能被描述为“生成随机物理地址然后解压过去”。随机性只负责在已经满足内存图、大小、对齐和占用约束的候选集合中做选择。

如果 `CONFIG_RANDOMIZE_BASE` 没有启用，本章仍然存在位置与对齐问题，只是不执行这套随机位置选择。

## 10. `__decompress()` 结束时 formal kernel 还没有完成最终布局

压缩算法通过 `__decompress()` 把 payload 恢复到 output buffer。但 Linux 5.10 随后还调用：

```text
parse_elf(output)
```

`parse_elf()` 读取 ELF header 和 program headers，只处理 `PT_LOAD` 段。x86-64 下还检查 LOAD segment alignment 是否是 2 MiB 的倍数。

在 `CONFIG_RELOCATABLE` 下，各段的目标位置根据 `output` 与 `LOAD_PHYSICAL_ADDR` 的关系计算；非 relocatable 情况则使用 ELF 的 `p_paddr`。随后通过 `memmove()` 将各个 LOAD segment 的文件内容放到相应位置。

所以应把过程分成两个动作：

```text
__decompress()
    得到解压后的 ELF 内容

parse_elf()
    按 PT_LOAD 语义形成 formal kernel 的装载布局
```

“字节已经解压出来”和“正式内核已经处于最终可执行布局”不是同一时刻。

## 11. relocation 为什么是有条件的

Linux 5.10 的 `handle_relocations()` 受：

```text
CONFIG_X86_NEED_RELOCS
```

控制。compressed Makefile 也只有在这一条件成立时才把 `vmlinux.relocs` 附加进压缩输入。

因此不能把 relocation 写成每次启动都无条件执行的修正过程。没有该配置时，`handle_relocations()` 是空 inline 实现。

在 x86-64 relocatable/KASLR 场景中，formal kernel 的实际 placement 可能与默认链接/装载关系不同，relocation 数据用于修正需要调整的地址。这里要区分：

```text
PIE：让 compressed kernel 自己能够在不同位置运行
relocation：修正 formal kernel 中需要随实际 placement 改变的地址
```

两者服务于不同对象，不应混成同一个“重定位”。

## 12. 从 compressed kernel 到 formal kernel 的 handoff

`extract_kernel()` 完成解压、ELF placement 和需要的 relocation 后，会返回 formal kernel 的入口地址。

但这不意味着 formal kernel 是由 C 语言 `extract_kernel()` 直接调用的。控制流是：

```text
compressed assembly
    call extract_kernel()
            |
            | 返回 entry address
            v
compressed assembly
    跨映像转移控制权
            |
            v
formal kernel entry
```

因此这里存在两个不同的“返回/跳转”语义：`extract_kernel()` 的返回仍然发生在 compressed image 内部；真正结束 compressed stage 的，是随后汇编代码把 CPU 控制权转移到解压后的 formal kernel entry。

在这个交接点，可以从输入/输出角度理解状态：

| 状态 | compressed stage 接收 | formal kernel 接收 |
| --- | --- | --- |
| `boot_params` | loader/setup 已形成的启动参数 | 继续沿用同一启动信息 |
| kernel bytes | compressed payload | 已解压并按 ELF 布局放置的 formal image |
| CPU mode | 能执行 compressed 64-bit path 的状态 | 能进入 formal 64-bit entry 的状态 |
| stack | compressed 临时栈 | 后续由 formal kernel 建立自己的启动/运行栈 |
| page tables | 服务 decompressor 的早期映射 | 后续由 formal kernel 继续调整和接管 |

这张表比“decompressor 跳到 kernel”更准确，因为它说明了哪些状态被继承，哪些只是上一阶段的临时设施。

## 13. 三组容易混淆的概念

第一组是 **compressed `vmlinux` 与 formal `vmlinux`**。它们是不同 ELF，拥有不同构建职责和符号空间。

第二组是 **compressed image 的运行位置与 formal kernel 的 output 位置**。前者回答 decompressor 当前在哪里执行，后者回答正式内核最终放在哪里。

第三组是 **compressed PIE 与 formal-kernel relocation**。PIE 解决 decompressor 自身可移动执行；relocation 解决正式 kernel placement 改变后需要修正的地址。

如果这三组边界清楚，B02 后面的 KASLR、ELF placement 和 handoff 就不会退化成一串难以解释的地址计算。

## 14. 如何验证本章

本章后续实验应分三个证据层次。

源码/构建层首先核验 `arch/x86/boot/compressed/Makefile` 的 `-fPIE`、`-ffreestanding`、`-pie`，`CONFIG_RANDOMIZE_BASE` 与 `CONFIG_X86_NEED_RELOCS` 条件，并核验 `head_64.S → extract_kernel()` 的主线。

构建产物层应对真实 Linux 5.10 build tree 中的 compressed `vmlinux` 和 formal `vmlinux` 分别执行 `readelf`、`nm`、`objdump`，证明它们是两个不同 ELF，并定位 compressed `startup_64`、`extract_kernel`、payload symbols 和跨映像 handoff 附近的机器指令。

运行时层则应在隔离的 QEMU/GDB 环境中观察进入 compressed `startup_64`、调用 `extract_kernel()` 前后以及转移到 formal kernel entry 前的 `%rip`、`%rsp`、`%rsi`、output 地址和必要的 paging 状态。

在没有真实 build tree 或 QEMU 现场时，只能声称完成源码级核验，不能把预期寄存器值、ELF 地址或 KASLR 结果写成实测数据。

## 15. 本章工作模型

把 B02 压缩成一条主线，可以得到：

```text
boot protocol 已交付 boot_params 和入口状态
        |
        v
compressed startup_32 / startup_64
        |
        | 建立 decompressor 自己的临时执行环境
        v
extract_kernel()
        |
        | needed_size + memory constraints
        | [CONFIG_RANDOMIZE_BASE] choose_random_location()
        v
__decompress()
        |
        v
parse_elf() / PT_LOAD placement
        |
        | [CONFIG_X86_NEED_RELOCS] relocation
        v
formal kernel entry address
        |
        v
compressed assembly 跨映像 handoff
        |
        v
formal kernel
```

B03 将从这个交接点继续：formal `arch/x86/kernel/head_64.S` 接管 CPU 后，怎样建立正式内核早期地址空间并进入 `x86_64_start_kernel()`。
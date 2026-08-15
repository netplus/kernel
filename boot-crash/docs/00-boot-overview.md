# B00：x86_64 Linux 启动过程概览

本章先建立 Linux 5.10 x86-64 启动过程的整体模型。这里的目标不是立即展开每一条汇编指令或每一个初始化函数，而是先回答三个问题：当前是谁在执行、它拥有什么运行环境、它完成什么工作后把控制权和状态交给下一阶段。

启动过程不能简单理解成一条很长的 C 函数调用链。固件、引导程序、setup、压缩内核、正式内核和第一个用户空间程序属于不同执行环境；阶段之间可能通过协议入口、汇编跳转、解压后的入口地址或 `exec` 完成交接。

Linux 5.10 的具体源码交接点见 [`../source-paths/00-boot-overview-linux-5.10.md`](../source-paths/00-boot-overview-linux-5.10.md)。

## 1. 启动过程真正要解决什么问题

机器刚开始执行时，并不存在一个已经初始化完成的 Linux 内核。后续内核代码依赖的许多条件都必须逐步建立，例如：

- CPU 必须进入内核期望的执行模式；
- 内核映像必须位于可执行的位置；
- 必须有可用的栈和地址映射；
- 引导程序获得的命令行、内存布局和 initrd 等信息必须传给内核；
- 正式内核必须从只能使用少量早期设施的环境，逐步进入可以使用内存分配、调度、中断和其他通用基础设施的环境；
- 最终还要从内核任务跨越 `exec` 边界，开始执行用户空间 init。

因此可以把启动理解为一系列“能力逐步增加的执行环境”。每一阶段只依赖前一阶段已经建立的最小条件，并为下一阶段增加新的能力。

## 2. 一条适合阅读源码的主线

对 Linux 5.10 x86-64 `bzImage`，本课程采用下面的主线：

```text
firmware
    ↓
boot loader
    ↓  Linux x86 boot protocol
setup / boot_params
    ↓
compressed kernel
    ↓
extract_kernel()
    ↓
formal kernel startup_64
    ↓
x86_64_start_kernel()
    ↓
start_kernel()
    ↓
rest_init()
    ↓
kernel_init / kthreadd / idle
    ↓
exec init
    ↓
user space
```

图中的箭头表示控制权或状态的交接，并不都表示普通的 `call` 指令。

下面逐层解释这些阶段。

## 3. 固件：让机器达到可以装载下一阶段的状态

固件位于 Linux 之前。传统 BIOS 与 UEFI 的具体启动方式不同，但从本章的抽象层次看，它们承担的是平台初始化和寻找可启动对象等前置责任。

Linux 内核不能假定自己从 CPU reset vector 开始执行，也不应该把所有平台固件工作重新实现一遍。固件最终把执行机会交给引导程序或兼容的 Linux 启动路径。

这里要保持一个边界：BIOS、UEFI 的内部实现不是 B00 的重点。后续只在它们影响 Linux boot protocol 入口条件时讨论差异。

## 4. 引导程序：装载 Linux，并满足 boot protocol

引导程序的任务不是“初始化 Linux 内核”，而是把 Linux 映像和相关启动材料放到约定位置，并按照 Linux x86 boot protocol 提供内核能够理解的输入。

典型输入包括：

- kernel image；
- kernel command line；
- initrd/initramfs 的位置和大小；
- 内存与平台相关信息；
- boot protocol 定义的其他字段。

这些信息最终汇入以 `boot_params` 为核心的启动参数结构。B01 会详细解释 boot protocol 和 `boot_params`；B00 只需要记住：**引导程序与内核之间首先是协议交接，而不是任意约定的一次函数调用。**

## 5. setup：整理启动参数并准备进入保护模式内核部分

Linux `bzImage` 自己还包含 setup 阶段。Linux 5.10 中的重要源码包括：

```text
arch/x86/boot/header.S
arch/x86/boot/main.c
```

`arch/x86/boot/main.c` 中也有一个 `main()`，但它不是通常意义上的内核主函数。它运行在 boot/setup 环境，负责整理启动参数、执行必要探测，并为后续 protected-mode kernel payload 做准备。

这说明阅读启动代码时，仅凭函数名判断阶段是不可靠的。必须同时看文件路径、映像归属和当前 CPU/内存环境。

## 6. compressed kernel：为什么正式内核之前还有一套小环境

`bzImage` 中的正式内核主体经过压缩。CPU 不能直接执行压缩数据，因此必须先运行一段独立的解压器代码。

Linux 5.10 x86-64 的关键路径位于：

```text
arch/x86/boot/compressed/head_64.S
arch/x86/boot/compressed/misc.c
```

这一阶段需要自己建立足以运行解压器的机器环境，包括必要的 GDT、栈、早期页表以及长模式条件。assembly A19 已经从机器执行角度分析这些机制；本章只关心它们在启动主线中的职责：**为解压正式内核提供一个临时但自洽的执行环境。**

随后汇编进入 `extract_kernel()`。它负责处理压缩映像，并结合重定位/KASLR 等条件得到正式内核可以开始执行的位置。

因此 compressed kernel 不是正式内核初始化的一部分简单前缀。它本身是一套生命周期很短的启动环境，完成任务后就把控制权交出去。

## 7. 两个 `startup_64` 必须分清

Linux 5.10 x86-64 启动源码中有一个非常容易造成误解的同名符号：

```text
arch/x86/boot/compressed/head_64.S : startup_64
arch/x86/kernel/head_64.S          : startup_64
```

前者属于 compressed kernel；后者属于已经解压得到的正式内核。

二者虽然都叫 `startup_64`，但执行环境和责任不同：

```text
compressed startup_64
    服务于解压器自己的早期环境

formal-kernel startup_64
    服务于正式内核的早期入口和地址空间准备
```

以后阅读启动调用图时，看到 `startup_64` 必须同时问“它在哪个文件、属于哪个映像”。只写“然后进入 `startup_64`”是不充分的。

## 8. 正式内核入口：从早期汇编进入架构 C 代码

解压完成并跳转到正式内核后，主线进入：

```text
arch/x86/kernel/head_64.S
arch/x86/kernel/head64.c
```

正式内核的 `startup_64` 继续建立正式内核所需的早期机器状态，然后进入 `x86_64_start_kernel()`。

这里发生了一次重要的责任变化：前面的 compressed kernel 关心的是“怎样把正式内核准备出来”；从这里开始，代码关心的是“怎样把正式内核本身初始化到可以进入通用内核初始化”。

`x86_64_start_kernel()` 仍然是 x86-64 架构侧的早期 C 入口。它不是 `start_kernel()` 的别名。

Linux 5.10 主线可以概括为：

```text
x86_64_start_kernel()
    ↓
x86_64_start_reservations()
    ↓
start_kernel()
```

前两者仍承担架构早期准备；`start_kernel()` 才进入通用初始化主线。

## 9. `start_kernel()`：通用内核开始逐步建立完整运行环境

`start_kernel()` 位于：

```text
init/main.c
```

到这里，CPU 已经远离最初只能依赖少量汇编设施的环境，但也不能理解为“所有内核服务已经可用”。恰恰相反，`start_kernel()` 的主要工作之一就是按照严格顺序把这些基础设施建立起来。

后续 B04 会分析初始化顺序。B00 只需要建立一个重要认识：

> `start_kernel()` 是初始化过程的主体入口，而不是初始化完成后的普通内核函数。

例如内存、调度、时钟、中断、RCU 等子系统都有自己的初始化依赖关系。某个阶段能否分配内存、能否调度、能否依赖普通中断语义，都必须根据当时已经完成的初始化判断，不能把运行期内核的能力倒推到早期启动阶段。

## 10. `rest_init()`：从单一启动执行流进入任务世界

`start_kernel()` 完成关键基础初始化后，经 `arch_call_rest_init()` 进入 `rest_init()`。

主干关系可以先记为：

```text
rest_init()
    ├─ 创建 PID 1 的 kernel_init
    ├─ 创建 kthreadd
    └─ 让 boot CPU 进入 idle 任务的正常运行语义
```

这是启动过程中另一个重要边界。在此前很长一段时间里，可以把启动理解为一个特殊的早期执行流；到 `rest_init()` 附近，调度器管理的任务关系开始成为正常内核运行模型的一部分。

但这里还不能说“用户空间已经启动”。

## 11. PID 1 的创建不等于已经执行 `/sbin/init`

`rest_init()` 创建的 PID 1 首先执行内核函数 `kernel_init()`。它仍处于内核执行环境中，还要完成 `kernel_init_freeable()` 等工作。

随后内核尝试执行配置或约定的 init 程序。具体候选路径、initramfs 和根文件系统关系留到 B05。

概念上必须区分：

```text
创建 PID 1
    ↓
PID 1 执行 kernel_init() 内核代码
    ↓
完成剩余初始化
    ↓
exec init program
    ↓
同一个任务开始执行新的用户空间映像
```

所以“PID 1 已存在”和“PID 1 已经在用户态执行 `/sbin/init`”是两个不同时间点。

## 12. 什么叫“可以使用普通内核基础设施”

启动代码最容易出现的阅读错误之一，是把成熟运行期的规则套到过早的阶段。

可以把能力增长粗略理解为：

```text
boot/setup
    可用设施极少，受 boot protocol 和早期环境约束

compressed kernel
    有自己的临时栈/页表/解压环境，但不是正式内核运行环境

formal kernel early entry
    正在建立正式地址空间和架构状态

start_kernel
    按依赖关系初始化通用子系统

rest_init 之后
    任务、idle、kthreadd 等逐渐进入正常运行模型

exec init
    用户空间正式开始持续运行
```

这不是一张“某函数之后所有 API 都立即可用”的精确表。判断一个具体 API 能否使用，仍应检查对应子系统在 Linux 5.10 中的实际初始化位置和执行上下文。

## 13. 与 assembly 和 memory 课程怎样分工

B00 只建立启动阶段和交接关系，不重复完整机器机制。

assembly A19 已经负责解释 compressed `startup_32` 中的：

- GDT 与 segment state；
- scratch/boot stack；
- early page tables；
- CR4.PAE、CR3、EFER.LME、CR0.PG；
- far transfer 和真正进入 64-bit execution 的条件。

memory 课程则负责完整解释页表、物理内存描述和后续内存管理。

boot-crash 关心的是这些机制在启动过程中为什么此时发生，以及完成后把什么状态交给下一阶段。

## 14. 不同启动方式的边界

本章采用 Linux 5.10 x86-64 `bzImage` 的主线作为阅读框架，但不能把它写成所有启动方式唯一逐指令相同的路径。

需要保留的条件包括：

- BIOS 与 UEFI 的前置路径不同；
- x86 boot protocol 存在 32-bit 和满足条件的 64-bit 入口方式；
- `CONFIG_RELOCATABLE`、KASLR 会影响正式内核物理位置和重定位；
- command line、initrd/initramfs 是否存在取决于启动配置；
- 最终 init 程序也不是无条件固定为一个路径。

后续章节在进入相应机制时再逐项展开。

## 15. 用五个问题检查自己是否真正理解 B00

读完本章，应能够回答：

1. 为什么 Linux 启动不能画成从 boot loader 到 `/sbin/init` 的普通 C 调用链？
2. `arch/x86/boot/compressed/head_64.S:startup_64` 与 `arch/x86/kernel/head_64.S:startup_64` 有什么本质区别？
3. `x86_64_start_kernel()` 与 `start_kernel()` 分别处在哪一层？
4. 为什么进入 `start_kernel()` 仍不能假定所有普通内核基础设施已经可用？
5. 为什么 `rest_init()` 创建 PID 1 不等于已经开始执行用户空间 init？

如果这五个问题能够按“执行环境、责任主体、输入/输出和交接点”回答，就已经具备继续阅读 B01–B05 的整体框架。

## 16. 下一步

下一最小单元应为 B00 建立源码/符号定位实验，验证以下名称实际属于哪个文件和阶段：

```text
arch/x86/boot/main.c:main
arch/x86/boot/compressed/head_64.S:startup_64
arch/x86/boot/compressed/misc.c:extract_kernel
arch/x86/kernel/head_64.S:startup_64
arch/x86/kernel/head64.c:x86_64_start_kernel
init/main.c:start_kernel
init/main.c:rest_init
init/main.c:kernel_init
```

实验的重点不是运行完整启动过程，而是先训练“看到符号时先确定映像和执行阶段”的源码阅读习惯。
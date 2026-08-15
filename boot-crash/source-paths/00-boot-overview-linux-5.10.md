# B00 源码事实核验：x86_64 启动主线的交接点（Linux 5.10）

本文只为 B00“启动过程概览”固定 Linux 5.10 中几个必须准确区分的交接点。它不是完整启动教程；后续 B01–B05 会分别展开 boot protocol、compressed kernel、正式 64 位入口、`start_kernel()` 和第一个用户空间进程。

## 1. 为什么先核验交接点

“固件 → 引导程序 → 内核 → 用户空间”这个概览如果直接写成一条函数调用链，很容易把不同映像阶段、不同 CPU 状态和不同责任主体混在一起。

B00 先固定四条边界：

1. boot loader 交给 Linux boot protocol 的入口，不等于正式 64 位内核入口；
2. compressed kernel 的 `startup_64` 不等于正式内核 `arch/x86/kernel/head_64.S` 中的 `startup_64`；
3. `x86_64_start_kernel()` 是 x86 架构早期 C 入口，`start_kernel()` 才进入通用内核初始化主线；
4. `rest_init()` 创建/启动的内核任务与最终执行用户态 init 是两个阶段。

## 2. 本次核验的 Linux 5.10 路径

### 2.1 Boot protocol 与 setup 阶段

主要文件：

```text
Documentation/x86/boot.rst
arch/x86/boot/header.S
arch/x86/boot/main.c
arch/x86/include/uapi/asm/bootparam.h
```

`arch/x86/boot/header.S` 定义 boot protocol header 和 setup 入口所需的低级布局；`arch/x86/boot/main.c` 中的 `main()` 属于 setup 阶段。这个阶段仍负责收集/整理启动参数、探测必要平台信息，并准备进入 protected-mode kernel 部分。

因此 B00 不应把 `arch/x86/boot/main.c:main()` 写成内核通用初始化的 `main`；它属于 boot/setup 环境。

### 2.2 Compressed kernel

x86-64 `bzImage` 的保护模式 payload 首先进入 compressed kernel 自己的早期入口。关键文件：

```text
arch/x86/boot/compressed/head_64.S
arch/x86/boot/compressed/misc.c
```

`head_64.S` 负责 compressed kernel 所需的早期机器状态，包括 32/64 位入口、临时 GDT/栈/页表以及进入长模式的准备。汇编随后调用 `extract_kernel()`；该函数位于 `arch/x86/boot/compressed/misc.c`，负责解压正式内核映像并返回可跳转的入口地址。

这里必须保留一个命名陷阱：

```text
arch/x86/boot/compressed/head_64.S : startup_64
arch/x86/kernel/head_64.S          : startup_64
```

二者是不同映像阶段中的符号。前者运行在解压器环境，后者属于解压后的正式内核。教程中不能仅写“进入 startup_64”而不说明文件/阶段。

### 2.3 正式 64 位内核入口

解压完成并完成必要跳转后，正式内核的早期入口位于：

```text
arch/x86/kernel/head_64.S
arch/x86/kernel/head64.c
```

`arch/x86/kernel/head_64.S` 的 64 位 `startup_64` 继续处理正式内核自己的早期页表和入口状态，然后进入 C 侧的 `x86_64_start_kernel()`（`arch/x86/kernel/head64.c`）。

这一阶段和 compressed kernel 的临时映射职责不同。完整页表机制属于 `memory/`；B00 只记录“解压器的地址空间 → 正式内核早期地址空间”是一次明确交接。

### 2.4 `x86_64_start_kernel()` 到 `start_kernel()`

主要文件：

```text
arch/x86/kernel/head64.c
init/main.c
```

`x86_64_start_kernel()` 是 x86-64 架构早期 C 初始化的重要入口。它完成进入通用初始化前必须由架构代码处理的工作，随后进入 `x86_64_start_reservations()`，最终调用通用 `start_kernel()`。

B00 应将这两个层次分开：

```text
x86_64_start_kernel()
    架构早期 C 环境
        ↓
x86_64_start_reservations()
        ↓
start_kernel()
    通用内核初始化主线
```

不能把 `x86_64_start_kernel()` 与 `start_kernel()` 当成同一个入口的两个名字。

### 2.5 `start_kernel()` 到 init 进程

`init/main.c` 是这一段的主要文件。B00 只固定主干：

```text
start_kernel()
    ↓
arch_call_rest_init()
    ↓
rest_init()
    ├─ kernel_thread(kernel_init, ...)
    └─ kernel_thread(kthreadd, ...)

kernel_init()
    ↓
kernel_init_freeable()
    ↓
尝试执行 ramdisk/init 或系统 init
```

`rest_init()` 还让 boot CPU 进入 idle 任务的正常调度语义。`kernel_init` 起初是内核线程上下文；真正执行 init 程序时才通过 exec 边界进入第一个长期运行的用户空间 init 映像。因此“创建 PID 1”和“已经开始执行 `/sbin/init` 用户态指令”不是同一时刻。

具体 initcall、根文件系统、initramfs 和 init 候选路径留到 B05。

## 3. B00 可采用的阶段模型

基于上述源码边界，B00 的主线应写成阶段交接，而不是一条伪调用链：

```text
firmware
    ↓  （平台/固件责任）
boot loader
    ↓  Linux x86 boot protocol
setup / boot_params
    ↓
compressed kernel entry
    ↓  建立解压器所需机器状态
extract_kernel()
    ↓  解压得到正式 kernel image
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

箭头表示“控制权或状态交接”，并不都表示普通 C ABI `call`。

## 4. 与 assembly 课程的边界

`assembly/A19` 已经讲解 compressed `startup_32` 的 GDT、segment state、early page tables、CR4/CR3/EFER/CR0 和 far transfer。这些机器状态不在 B00 重复展开。

boot-crash 的职责是回答：这些早期汇编阶段在完整启动流程中位于哪里、接收什么输入、产生什么输出，以及如何把控制权交给解压器和正式内核。

## 5. 配置与启动方式边界

本文件固定的是 Linux 5.10 x86-64 `bzImage` 的主线阅读框架，不声称所有启动方式都逐条经过完全相同的前置路径。

需要在后续章节分别处理的条件包括：

- EFI 与传统 BIOS/boot loader 的前置入口差异；
- 64-bit boot protocol 允许 boot loader 满足入口条件后进入相应 64 位入口；
- `CONFIG_RELOCATABLE` / KASLR 对物理装载与重定位的影响；
- initrd/initramfs 和命令行是否存在；
- init 程序的实际候选路径。

这些条件不能在 B00 中被简化成无条件事实。

## 6. 本次核验结论

B00 后续正文必须至少保持以下事实边界：

- setup `main()`、compressed kernel、正式 kernel 是不同执行阶段；
- compressed 与 formal kernel 都可能出现 `startup_64` 名称，引用时必须带源码路径；
- `extract_kernel()` 是解压阶段的核心 C 交接点；
- 正式内核先进入架构侧 `x86_64_start_kernel()`，再进入通用 `start_kernel()`；
- `rest_init()` 建立 PID 1、kthreadd 与 idle 的运行基础，但 PID 1 随后还要经过 `kernel_init()` 的初始化和 exec 才成为用户空间 init；
- 阶段图中的箭头不应全部解释成普通函数调用。

下一最小单元应基于这些边界编写 B00 正式教程，并用符号/源码定位实验验证同名 `startup_64`、`extract_kernel`、`x86_64_start_kernel`、`start_kernel`、`rest_init` 和 `kernel_init` 的阶段归属。
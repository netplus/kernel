# x86_64 启动、Kexec 与 Kdump

本目录学习 x86_64 Linux kernel 5.10 的正常启动、Kexec、Kdump 与 vmcore。课程始终围绕一个问题组织：**当前是谁在执行、依赖什么运行环境、留下什么状态、如何把控制权交给下一阶段。**

```text
正常启动
firmware / boot loader → setup → compressed kernel → formal kernel → start_kernel → user space

Kexec
当前内核准备新映像 → 收缩运行环境 → relocation / purgatory → 新内核

Kdump
生产内核 panic → crash_kexec → 捕获内核 → /proc/vmcore → 持久化与离线分析
```

Kdump 使用 Kexec 的内核切换能力，但运行条件更恶劣：生产内核已经发生严重故障，因此锁、调度、设备和部分内存状态都可能不可信。课程会明确区分正常路径与 crash path，不把二者写成同一条调用链。

## 学习目标

完成本领域后，应能够说明：

1. x86_64 Linux 从 boot loader 进入 `start_kernel()` 并最终执行用户态 init 的主要阶段；
2. boot protocol、`boot_params`、compressed kernel、early page tables、long mode 和正式内核入口分别解决什么问题；
3. Kexec 的加载阶段与真正切换阶段为何分离；
4. Kdump 中生产内核、捕获内核、`crashkernel=` 保留内存和旧内核物理内存之间的关系；
5. panic 后如何进入 `crash_kexec()`，以及崩溃上下文为何不能继续依赖正常内核基础设施；
6. `elfcorehdr`、`VMCOREINFO` 和 `/proc/vmcore` 如何把旧内核现场暴露给捕获内核；
7. 如何使用匹配的 `vmlinux`、模块符号、Build ID、`makedumpfile` 和 `crash` 建立可复核的故障证据链；
8. Kdump 在 NMI、死锁、DMA、内存损坏、CPU 停止失败和捕获内核启动失败等场景中的能力边界。

---

# 第一部分：x86_64 内核启动

## B00：启动过程概览【已完成】

建立完整阶段模型：

```text
firmware → boot loader / Linux boot protocol → setup / boot_params
→ compressed kernel → extract_kernel() → formal-kernel startup_64
→ x86_64_start_kernel() → x86_64_start_reservations()
→ start_kernel() → rest_init() → kernel_init / kthreadd / idle
→ exec init → user space
```

重点区分 setup、compressed image、formal kernel、架构早期 C 初始化、通用初始化以及 PID 1 越过 exec 边界；两个 `startup_64` 属于不同映像和链接上下文。

已完成内容：

- [正式教程：x86_64 Linux 启动过程概览](docs/00-boot-overview.md)
- [Linux 5.10 源码路径与阶段交接核验](source-paths/00-boot-overview-linux-5.10.md)
- [实验：启动阶段源码与符号归属](labs/00-boot-overview/)
- [B00 收章复核](docs/00-b00-completion-review.md)

实验已建立 source-contract checker，并实际执行通过 8-case fixture self-test。真实 Linux v5.10 checkout、ELF/反汇编和 QEMU/GDB 动态观察仍属于增强证据。

## B01：Linux boot protocol 与内核映像【已完成】

本章建立 boot loader 与 kernel 之间的双向 ABI 模型：`setup_header` 描述 bzImage 自身及其装载能力；4 KiB `boot_params` / zeropage 汇合映像 header、loader 输入和 setup/platform 探测结果，并把本次启动状态交给后续阶段。

核心范围：

- `bzImage`、setup 与 protected-mode payload 的协议布局；
- `HdrS` 与 Linux 5.10 boot protocol 2.15 (`0x020f`)；
- `setup_header` 与 `boot_params` 的包含关系；
- command line、initrd、E820 的地址/长度与所有权语义；
- `copy_boot_params()`、平台探测与 `go_to_protected_mode()` 的阶段关系；
- ABI/source、真实构建产物与 boot-loader 运行现场三层证据边界。

已完成内容：

- [正式教程：Linux boot protocol 与 `boot_params`](docs/01-linux-boot-protocol-and-boot-params.md)
- [Linux 5.10 boot protocol 源码事实核验](source-paths/01-linux-boot-protocol-linux-5.10.md)
- [实验：boot protocol 与 `boot_params` 静态验证](labs/01-linux-boot-protocol/)
- [B01 收章复核](docs/01-b01-completion-review.md)

实验已建立 source/layout checker，并实际执行通过 1 个完整正例和 7 个负例 fixture；完整正例返回 11 项 L1 source-contract 检查。真实 Linux v5.10 checkout 上的 checker、实际 `sizeof/offsetof`、真实 bzImage header bytes 和 boot-loader/QEMU zeropage 现场仍属于增强证据，不冒充为已执行结果。

建议源码：

```text
Documentation/x86/boot.rst
arch/x86/boot/header.S
arch/x86/boot/main.c
arch/x86/include/uapi/asm/bootparam.h
```

## B02：压缩内核与早期 64 位环境【已完成】

本章把 compressed kernel 作为 formal kernel 之前的独立执行映像来理解，重点说明它如何接收 `boot_params`、选择 formal-kernel output、解压 payload、按 ELF `PT_LOAD` 形成布局、按配置处理 relocation，并最终把控制权交给 formal kernel。

核心范围：

- compressed `vmlinux` 与 formal `vmlinux` 是两个独立 ELF/链接上下文；
- compressed PIE/freestanding 构建约束与 formal-kernel relocation 的职责边界；
- `CONFIG_RELOCATABLE`、`CONFIG_RANDOMIZE_BASE`、`CONFIG_X86_NEED_RELOCS` 等配置条件；
- `needed_size`、KASLR 合法候选与 `MEM_AVOID_*` 覆盖规避；
- `choose_random_location() → __decompress() → parse_elf() → handle_relocations()` 的阶段语义；
- `extract_kernel()` 的 C ABI return 与后续跨映像 handoff 是两个不同控制流事件。

已完成内容：

- [正式教程：压缩内核与早期 64 位环境](docs/02-compressed-kernel-and-early-64bit.md)
- [Linux 5.10 compressed-kernel 源码事实核验](source-paths/02-compressed-kernel-linux-5.10.md)
- [实验：compressed kernel 的构建、解压与 handoff](labs/02-compressed-kernel/)
- [B02 收章复核](docs/02-b02-completion-review.md)

实验已建立 L1 source/build contract checker，并实际执行通过 1 个完整正例和 7 个负例 fixture；完整正例覆盖 10 组 L1 contract。真实 Linux v5.10 checkout、compressed/formal ELF 的 `readelf/nm/objdump` 和 QEMU/GDB P0–P3 动态现场仍属于增强证据，不冒充为已执行结果。

建议源码：

```text
arch/x86/boot/compressed/Makefile
arch/x86/boot/compressed/head_64.S
arch/x86/boot/compressed/misc.c
arch/x86/boot/compressed/kaslr.c
```

GDT、控制寄存器、long-mode transition 等机器执行机制由 [`assembly/`](../assembly/) 完整解释；本领域关注这些状态在启动阶段之间如何交接。

## B03：formal `head_64.S` 与早期页表【已完成】

本章解释 formal kernel 已经在 64-bit mode 且已有 identity mapping 时，为什么仍需要根据实际物理装载位置修正 early page tables、形成并切换 CR3，再显式转入 kernel virtual-address execution，最后建立进入 `x86_64_start_kernel()` 所需的机器状态。

核心范围：

- formal `startup_64` 的入口前提：64-bit mode、identity mapping、`%rsi` 中的 `boot_params` / `real_mode_data` 物理指针；
- link-time high-half VA、默认 physical position、实际 `physaddr` 与 `load_delta` 的关系；
- `early_top_pgt`、`early_dynamic_pgts`、`phys_base` 与 switchover identity mapping 的职责；
- `__startup_64()` 返回 SME modifier，而 assembly 随后才形成实际 CR3；
- `mov %cr3` 与 indirect virtual-address jump 是两个不同状态变化；
- kernel GDT、`initial_stack`、early IDT、RFLAGS、`%rsi → %rdi` 与 `lretq → x86_64_start_kernel()`；
- BSP `early_top_pgt` 与 secondary CPU `init_top_pgt` 的 ownership 边界，以及 LA57/SEV-ES 条件路径。

已完成内容：

- [正式教程：formal `head_64.S` 与早期页表](docs/03-formal-head64-and-early-paging.md)
- [Linux 5.10 formal entry 与 early paging 源码事实核验](source-paths/03-formal-head64-early-paging-linux-5.10.md)
- [实验：formal `head_64.S` 与 early paging 状态交接](labs/03-formal-head64-early-paging/)
- [B03 收章复核](docs/03-b03-completion-review.md)

实验已建立 6 组 L1 source-contract checker，并实际执行通过 8 个 unittest（1 个完整正例 + 7 个负例，exit code 0）。真实 Linux v5.10 checkout 上的 checker、匹配构建的 `vmlinux`/`nm`/`readelf`/`objdump` 和 QEMU/GDB P0–P3 动态现场仍属于增强证据，不冒充为已执行结果。

建议源码：

```text
arch/x86/kernel/head_64.S
arch/x86/kernel/head64.c
arch/x86/include/asm/pgtable_64_types.h
arch/x86/include/asm/page_64_types.h
```

Linux 5.10 BSP formal-entry 的 switchover identity mapping 直接在 `head64.c::__startup_64()` 中构造；`arch/x86/mm/ident_map.c` 不属于这条主调用链，因此不再把它列为 B03 主源码入口。完整页表机制放在 [`memory/`](../memory/)；本章只讲启动所需的页表状态和交接点。

## B04：从 `x86_64_start_kernel()` 到 `start_kernel()`

主要内容：早期 BSS 和启动状态、早期异常处理、`boot_params`/命令行/内存信息接管、`setup_arch()`、架构初始化与通用 `start_kernel()` 的边界，以及页分配器、调度器、时钟、中断和 RCU 初始化的顺序约束。

建议源码：

```text
arch/x86/kernel/head64.c
arch/x86/kernel/setup.c
init/main.c
```

## B05：从 `start_kernel()` 到用户空间

```text
start_kernel() → arch_call_rest_init() → rest_init()
→ kernel_init() → run_init_process() → user-space init
```

重点说明 idle 任务、`kthreadd`、initcall、initramfs/rootfs，以及“创建 PID 1”与“PID 1 成功 exec 用户态 init”为什么是两个不同时间点。

---

# 第二部分：Kexec

## B06：Kexec 解决什么问题

建立普通 reboot 与 Kexec 的差异，并区分 normal kexec 与 crash kexec。重点理解为什么“不重新经过 firmware”意味着旧内核必须主动为新内核准备可接受的 CPU、内存和映像状态。

## B07：Kexec 映像的加载

学习 `kexec_load` / `kexec_file_load`、kernel/initramfs/command line、segment 目标物理内存、加载与切换分离，以及签名验证和安全限制。

建议源码：`kernel/kexec.c`、`kernel/kexec_core.c`、`kernel/kexec_file.c`、`arch/x86/kernel/kexec-bzimage64.c`。

## B08：从当前内核切换到新内核

```text
trigger kexec → stop ordinary activity → quiesce / isolate CPUs and devices
→ relocation code → establish new-kernel entry state → transfer control
```

重点说明切换阶段为何不能继续依赖当前内核的大部分服务，以及 normal/crash Kexec 在 shutdown 假设上的差异。

建议源码：`kernel/kexec_core.c`、`arch/x86/kernel/machine_kexec_64.c`、`arch/x86/kernel/relocate_kernel_64.S`。

## B09：Purgatory 的作用

学习 Purgatory 作为旧内核与新内核之间独立过渡代码的原因、执行约束、映像校验、入口参数准备及其与正式新内核入口的边界。建议源码：`arch/x86/purgatory/`。

---

# 第三部分：双内核 Kdump

## B10：生产内核与捕获内核

建立双内核模型：生产内核正常承载业务并留下崩溃现场；捕获内核预先放入保留内存，在 panic 后启动并负责保存 vmcore。捕获内核必须尽量少依赖生产内核仍然正常工作。

## B11：`crashkernel=` 与保留内存

学习 crash kernel 内存为何必须在生产内核启动时预留、为何不能再交给普通页分配器、常见预留形式，以及捕获内核/initramfs/Purgatory/控制结构如何使用保留区。

与 [`memory/`](../memory/) 的交接点：`boot parameter → memblock reservation → ordinary memory initialization excludes crashkernel region`。

## B12：捕获内核的预加载

学习捕获内核和 initramfs 的加载、capture-kernel command line、CPU/内存约束、必要存储或网络驱动，以及如何确认 crash kernel 已成功加载。

## B13：从 panic 到 `crash_kexec()`

```text
fatal error → panic → stop / notify other CPUs → save crash CPU state
→ crash_kexec → machine_crash_shutdown → capture kernel
```

重点说明 panic path 与正常 reboot path 的区别，以及为什么崩溃上下文中的锁、调度、设备和内存状态不能按正常路径假设。

建议源码：`kernel/panic.c`、`kernel/crash_core.c`、`kernel/kexec_core.c`、`arch/x86/kernel/crash.c`、`arch/x86/kernel/machine_kexec_64.c`。

## B14：捕获内核如何访问旧内核内存

学习旧内核物理内存的保留语义、`elfcorehdr`、`/proc/vmcore`、`VMCOREINFO`，以及保留区、不可导出区域和过滤区域。

建议源码：`fs/proc/vmcore.c`、`kernel/crash_core.c`、`include/linux/crash_core.h`。

## B15：保存 `vmcore`

区分 `/proc/vmcore` 这一捕获内核提供的崩溃内存视图，与从它复制、过滤或压缩后得到的持久化 saved vmcore。学习直接复制、`makedumpfile`、dump level、存储目标、空间/时间约束和保存失败定位。

## B16：使用 Crash 分析 `vmcore`

分析前准备匹配的 `vmcore`、带调试信息的 `vmlinux`、模块调试文件、内核版本/配置和 Build ID。证据链为：`kernel identity → panic/log → CPU/current task → stack → registers/faulting instruction → relevant objects → reconstruct execution path`。

## B17：符号匹配与调用栈展开

学习 `vmlinux`、`System.map`、kallsyms、模块符号、Build ID、KASLR 地址修正、函数/模块/相对偏移，以及 frame pointer、DWARF、ORC unwinder、inline、tail call 和 stack corruption 对栈展开的影响。

## B18：Kdump 的限制与失效场景

分析 CPU 无法继续执行、严重内存损坏、IOMMU/DMA 继续破坏内存、多 CPU 停止失败、捕获内核缺驱动、存储不可用、捕获内核自身启动失败，以及 firmware/BMC/hardware reset 先于 crash kexec 等场景。Kdump 应与 serial console、pstore、BMC event log、hardware watchdog 和 remote logging 配合使用。

---

# 实验主线

1. **正常启动**：保存完整 `dmesg`，把可观察事件与 B00–B05 阶段边界对应起来；
2. **普通 Kexec**：加载第二个测试内核，比较 normal reboot 与 Kexec 的入口状态和日志；
3. **双内核 Kdump**：配置 `crashkernel=`、构建捕获内核 initramfs、加载 crash kernel；
4. **受控 panic**：只在隔离测试环境中触发 panic，观察生产内核 → crash kexec → 捕获内核；
5. **vmcore 分析**：使用匹配符号分析 panic CPU、task、stack、registers、faulting RIP 和相关对象；
6. **失败注入**：验证预留不足、驱动缺失、符号不匹配、存储空间不足等问题，并判断失败发生阶段。

故障定位统一使用：`reservation → image loading → panic/crash switch → capture-kernel boot → vmcore export → persistent storage → offline analysis`。

# 与其他课程的关系

- [`assembly/`](../assembly/)：完整解释早期入口、寄存器、栈、控制寄存器、异常入口和 Kexec 跳转所需的机器执行基础；
- [`memory/`](../memory/)：完整解释页表、memblock、物理页分配，以及 crashkernel 保留区和 vmcore 内存映射所依赖的内存机制；
- [`scheduler/`](../scheduler/)：解释任务、CPU、调度和上下文切换，帮助理解 panic 后为何不能再假设正常调度环境；
- [`timekeeping/`](../timekeeping/)：解释 watchdog、lockup detection 和崩溃时间线所依赖的时间机制；
- [`integrated-paths/`](../integrated-paths/)：最终把正常启动和 panic→vmcore 路径与其他基础子系统串联起来。

本阶段不展开网络协议栈。通过网络保存 vmcore 时，只说明当前实验所需的存储通道，不在本目录重复网络机制。

# 建议学习顺序

进入本目录前，应先掌握 assembly 中的寄存器、取址、栈、ABI 和控制流；正常启动 B00–B05 与 memory 中的早期页表、内存布局和 memblock 可以交叉学习。

```text
B00～B05  x86_64 正常启动
B06～B09  Kexec
B10～B15  双内核 Kdump 与 vmcore 生成
B16～B18  vmcore 分析、符号和失效场景
```

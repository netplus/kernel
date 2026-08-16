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

先建立完整阶段模型：

```text
firmware
→ boot loader / Linux boot protocol
→ setup / boot_params
→ compressed kernel
→ extract_kernel()
→ formal-kernel startup_64
→ x86_64_start_kernel()
→ x86_64_start_reservations()
→ start_kernel()
→ rest_init()
→ kernel_init / kthreadd / idle
→ exec init
→ user space
```

本章重点不是背一条伪 C 调用链，而是区分 setup、compressed image、formal kernel、架构早期 C 初始化、通用初始化以及 PID 1 越过 exec 边界这几个不同执行阶段。尤其必须区分 `arch/x86/boot/compressed/head_64.S:startup_64` 与 `arch/x86/kernel/head_64.S:startup_64`：它们属于不同映像和链接上下文。

已完成内容：

- [正式教程：x86_64 Linux 启动过程概览](docs/00-boot-overview.md)
- [Linux 5.10 源码路径与阶段交接核验](source-paths/00-boot-overview-linux-5.10.md)
- [实验：启动阶段源码与符号归属](labs/00-boot-overview/)
- [B00 收章复核](docs/00-b00-completion-review.md)

实验已经建立 source-contract checker，并实际执行通过 8-case fixture self-test。真实 Linux v5.10 checkout 上的 checker、compressed/formal ELF 的 `nm/readelf/objdump` 和 QEMU/GDB 动态启动观察仍属于增强证据，不冒充为已执行结果。

## B01：Linux boot protocol 与内核映像

主要内容：

- `bzImage` 的基本组成；
- setup 部分与保护模式内核部分；
- boot protocol header 与版本协商；
- `boot_params` 的角色和布局；
- 内核命令行、initrd 和内存映射如何由 boot loader 传入；
- 为什么内核映像需要自描述的引导协议。

建议源码：

```text
Documentation/x86/boot.rst
arch/x86/boot/header.S
arch/x86/boot/main.c
arch/x86/include/uapi/asm/bootparam.h
```

## B02：压缩内核与早期 64 位环境

主要内容：

- compressed kernel 为什么需要独立启动环境；
- 临时栈、CPU 能力检查和临时页表；
- 内核解压；
- KASLR 与物理装载位置；
- 解压完成后如何把控制权交给正式内核。

建议源码：

```text
arch/x86/boot/compressed/head_64.S
arch/x86/boot/compressed/misc.c
arch/x86/boot/compressed/kaslr.c
```

其中 GDT、控制寄存器、long-mode transition 等机器执行机制由 [`assembly/`](../assembly/) 课程完整解释；本领域关注这些状态在启动阶段之间如何交接。

## B03：formal `head_64.S` 与早期页表

主要内容：

- 解压后的 64 位内核入口；
- 内核虚拟地址与物理地址的关系；
- 为什么进入正式内核后还要继续调整早期地址空间；
- 内核映像重定位；
- BSP 与 AP 入口的边界；
- 何时具备进入更完整内存管理初始化的条件。

建议源码：

```text
arch/x86/kernel/head_64.S
arch/x86/kernel/head64.c
arch/x86/mm/ident_map.c
```

完整页表机制放在 [`memory/`](../memory/)；本章只讲启动所需的页表状态和交接点。

## B04：从 `x86_64_start_kernel()` 到 `start_kernel()`

主要内容：

- 早期 BSS 和启动状态处理；
- 早期异常处理；
- `boot_params`、命令行和内存信息的接管；
- `setup_arch()`；
- 架构初始化与通用 `start_kernel()` 的边界；
- 页分配器、调度器、时钟、中断和 RCU 等初始化为何存在顺序约束。

建议源码：

```text
arch/x86/kernel/head64.c
arch/x86/kernel/setup.c
init/main.c
```

## B05：从 `start_kernel()` 到用户空间

主要主线：

```text
start_kernel()
→ arch_call_rest_init()
→ rest_init()
→ kernel_init()
→ run_init_process()
→ user-space init
```

重点说明 idle 任务、`kthreadd`、initcall、initramfs/rootfs，以及“创建 PID 1”与“PID 1 成功 exec 用户态 init”为什么是两个不同时间点。

---

# 第二部分：Kexec

## B06：Kexec 解决什么问题

建立普通 reboot 与 Kexec 的差异，并区分：

```text
normal kexec
为了快速启动另一个正常内核。

crash kexec
为了在当前内核崩溃后启动捕获内核。
```

重点理解为什么“不重新经过 firmware”意味着旧内核必须主动为新内核准备可接受的 CPU、内存和映像状态。

## B07：Kexec 映像的加载

主要内容：

- `kexec_load` 与 `kexec_file_load`；
- kernel、initramfs、command line 如何组成待启动映像；
- segment 如何放入目标物理内存；
- 加载阶段与真正切换阶段为什么分离；
- 签名验证和安全限制的基本作用。

建议源码：

```text
kernel/kexec.c
kernel/kexec_core.c
kernel/kexec_file.c
arch/x86/kernel/kexec-bzimage64.c
```

## B08：从当前内核切换到新内核

主要主线：

```text
trigger kexec
→ stop ordinary activity
→ quiesce / isolate CPUs and devices
→ enter relocation code
→ establish new-kernel entry state
→ transfer control
```

重点说明切换阶段为何不能继续依赖当前内核的大部分服务，以及正常 Kexec 与 crash Kexec 在 shutdown 假设上的差异。

建议源码：

```text
kernel/kexec_core.c
arch/x86/kernel/machine_kexec_64.c
arch/x86/kernel/relocate_kernel_64.S
```

## B09：Purgatory 的作用

主要内容：

- Purgatory 位于旧内核和新内核之间的原因；
- 独立过渡代码的执行约束；
- 映像校验；
- 入口参数准备；
- Purgatory 与正式新内核入口的边界。

建议源码：

```text
arch/x86/purgatory/
```

---

# 第三部分：双内核 Kdump

## B10：生产内核与捕获内核

建立双内核模型：生产内核正常承载业务并留下崩溃现场；捕获内核预先放入保留内存，在 panic 后启动并负责保存 vmcore。捕获内核必须尽量少依赖生产内核仍然正常工作。

## B11：`crashkernel=` 与保留内存

主要内容：

- 为什么生产内核启动时就必须预留 crash kernel 内存；
- 保留区为何不能再交给普通页分配器；
- 固定大小、范围选择和高低端预留的基本形式；
- 捕获内核、initramfs、Purgatory 和控制结构如何使用保留区；
- 预留过小和过大的影响。

与 [`memory/`](../memory/) 的交接点：

```text
boot parameter
→ memblock reservation
→ ordinary memory initialization excludes crashkernel region
```

## B12：捕获内核的预加载

主要内容：捕获内核和 initramfs 的加载、捕获内核 command line、常见 CPU/内存约束、必要存储或网络驱动，以及如何确认 crash kernel 已经成功加载。

## B13：从 panic 到 `crash_kexec()`

主要路径：

```text
fatal error
→ panic
→ stop / notify other CPUs
→ save crash CPU state
→ crash_kexec
→ machine_crash_shutdown
→ capture kernel
```

重点说明 panic path 与正常 reboot path 的区别，以及为什么崩溃上下文中的锁、调度、设备和内存状态不能按正常路径假设。

建议源码：

```text
kernel/panic.c
kernel/crash_core.c
kernel/kexec_core.c
arch/x86/kernel/crash.c
arch/x86/kernel/machine_kexec_64.c
```

## B14：捕获内核如何访问旧内核内存

主要内容：

- 为什么旧内核物理内存不能被捕获内核当作普通可分配内存；
- `elfcorehdr` 如何描述导出的物理内存和 CPU 状态；
- `/proc/vmcore` 如何呈现 ELF core 视图；
- `VMCOREINFO` 为什么需要记录符号和结构布局信息；
- 保留区、不可导出区域和过滤区域。

建议源码：

```text
fs/proc/vmcore.c
kernel/crash_core.c
include/linux/crash_core.h
```

## B15：保存 `vmcore`

重点区分：

```text
/proc/vmcore
捕获内核提供的崩溃内存视图。

saved vmcore
从 /proc/vmcore 复制、过滤或压缩后得到的持久化转储。
```

学习直接复制、`makedumpfile` 的过滤/压缩、dump level、存储目标、空间与时间约束，以及保存失败的分层定位方法。

## B16：使用 Crash 分析 `vmcore`

分析前必须准备匹配的 `vmcore`、带调试信息的 `vmlinux`、模块调试文件、内核版本/配置和 Build ID。基础证据链为：

```text
kernel identity
→ panic/log
→ CPU and current task
→ stack
→ registers and faulting instruction
→ relevant objects
→ reconstruct execution path
```

常用命令包括 `sys`、`log`、`bt`、`bt -a`、`ps`、`task`、`regs`、`dis`、`kmem`、`vm`、`struct` 和 `list`。具体命令必须服务于证据链，而不是命令罗列。

## B17：符号匹配与调用栈展开

主要内容：

- `vmlinux`、`System.map`、kallsyms 与模块符号；
- Build ID 与版本/配置匹配；
- KASLR 地址修正；
- 函数名、模块名与相对偏移；
- frame pointer、DWARF 与 ORC unwinder；
- inline、tail call 和 stack corruption；
- 为什么错误符号可能产生“看似合理”的错误栈。

## B18：Kdump 的限制与失效场景

Kdump 不能保证在所有故障中成功。重点分析 CPU 无法继续执行、严重内存损坏、IOMMU/DMA 继续破坏内存、多 CPU 停止失败、捕获内核缺驱动、存储不可用、捕获内核自身启动失败，以及 firmware/BMC/hardware reset 先于 crash kexec 等情况。

Kdump 应与 serial console、pstore、BMC event log、hardware watchdog 和 remote logging 配合使用，而不是被视为唯一崩溃取证手段。

---

# 实验主线

课程实验按故障链分层，而不是按工具堆叠：

1. **正常启动**：保存完整 `dmesg`，把可观察事件与 B00–B05 的阶段边界对应起来；
2. **普通 Kexec**：加载第二个测试内核，比较 normal reboot 与 Kexec 的入口状态和日志；
3. **双内核 Kdump**：配置 `crashkernel=`、构建捕获内核 initramfs、加载 crash kernel；
4. **受控 panic**：只在隔离测试环境中触发 panic，观察生产内核 → crash kexec → 捕获内核；
5. **vmcore 分析**：使用匹配符号分析 panic CPU、task、stack、registers、faulting RIP 和相关对象；
6. **失败注入**：验证预留不足、驱动缺失、符号不匹配、存储空间不足等问题，并判断失败发生在哪个阶段。

故障定位统一使用下面的阶段模型：

```text
reservation
→ image loading
→ panic / crash switch
→ capture-kernel boot
→ vmcore export
→ persistent storage
→ offline analysis
```

---

# 与其他课程的关系

- [`assembly/`](../assembly/)：完整解释早期入口、寄存器、栈、控制寄存器、异常入口和 Kexec 跳转所需的机器执行基础；
- [`memory/`](../memory/)：完整解释页表、memblock、物理页分配，以及 crashkernel 保留区和 vmcore 内存映射所依赖的内存机制；
- [`scheduler/`](../scheduler/)：解释任务、CPU、调度和上下文切换，帮助理解 panic 后为何不能再假设正常调度环境；
- [`timekeeping/`](../timekeeping/)：解释 watchdog、lockup detection 和崩溃时间线所依赖的时间机制；
- [`integrated-paths/`](../integrated-paths/)：最终把正常启动和 panic→vmcore 路径与其他基础子系统串联起来。

本阶段不展开网络协议栈。通过网络保存 vmcore 时，只说明当前实验所需的存储通道，不在本目录重复网络机制。

# 建议学习顺序

进入本目录前，应先掌握 assembly 中的寄存器、取址、栈、ABI 和控制流；正常启动 B00–B05 与 memory 中的早期页表、内存布局和 memblock 可以交叉学习。之后按以下顺序推进：

```text
B00～B05  x86_64 正常启动
B06～B09  Kexec
B10～B15  双内核 Kdump 与 vmcore 生成
B16～B18  vmcore 分析、符号和失效场景
```

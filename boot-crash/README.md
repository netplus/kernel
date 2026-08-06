# x86_64 启动、Kexec 与 Kdump

本目录学习 x86_64 Linux 内核的启动过程，以及 `kexec`、`kdump` 和 `vmcore` 的工作原理。源码以 Linux kernel 5.10 为主要基线。

这几部分内容关系紧密：

```text
正常启动
固件或引导程序 → 内核早期入口 → start_kernel → 用户空间

Kexec
当前内核准备新内核 → 停止当前系统 → 直接跳转到新内核

Kdump
生产内核发生 panic → crash_kexec → 捕获内核启动 → 导出 vmcore
```

Kdump 可以看作 Kexec 的一个特殊用途。它预先保留一段内存并加载第二套内核。当生产内核崩溃时，不再经过固件和普通引导程序，而是直接切换到这套捕获内核。捕获内核随后读取生产内核留下的内存，并把它保存为 `vmcore`。

## 学习目标

完成本部分后，应能够说明：

1. x86_64 Linux 从引导程序进入 `start_kernel()` 的主要过程；
2. 压缩内核、早期页表、长模式和内核重定位分别解决什么问题；
3. `kexec` 如何在不重新经过固件的情况下启动另一个内核；
4. Kdump 中生产内核、捕获内核和保留内存的关系；
5. `crashkernel=` 为什么必须在生产内核启动时预留内存；
6. panic 之后如何进入 `crash_kexec()`；
7. 捕获内核如何通过 `elfcorehdr` 和 `/proc/vmcore` 访问崩溃现场；
8. `vmcore`、`vmlinux`、调试符号、Build ID 和内核模块之间如何匹配；
9. 如何使用 `makedumpfile` 和 `crash` 保存并分析内核转储；
10. Kdump 在 NMI、死锁、设备失控和内存损坏场景中的能力与限制。

---

# 第一部分：x86_64 内核启动

## B00：启动过程概览

先建立完整主线：

```text
固件
→ 引导程序
→ Linux boot protocol
→ 压缩内核入口
→ 解压和重定位
→ 64 位内核早期入口
→ x86_64_start_kernel
→ start_kernel
→ rest_init
→ kernel_init
→ 第一个用户空间程序
```

本章重点区分：

- 固件负责什么；
- 引导程序负责什么；
- 内核自己的早期启动代码负责什么；
- 什么时候可以使用普通的内核基础设施。

## B01：Linux boot protocol 与内核映像

主要内容：

- `bzImage` 的基本组成；
- setup 部分与保护模式内核部分；
- 引导参数和 `boot_params`；
- 内核命令行、initrd 和内存映射如何传入内核；
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

- 压缩内核为什么需要单独的启动环境；
- 临时栈和临时页表；
- CPU 模式检查；
- 内核解压；
- KASLR 与物理装载位置；
- 解压完成后如何跳转到正式内核。

建议源码：

```text
arch/x86/boot/compressed/head_64.S
arch/x86/boot/compressed/misc.c
arch/x86/boot/compressed/kaslr.c
```

## B03：`head_64.S` 与早期页表

主要内容：

- 64 位内核入口；
- 内核虚拟地址和物理地址的关系；
- 早期页表为什么还要继续调整；
- 内核映像重定位；
- BSP 与 AP 启动入口的区别；
- 何时建立较完整的内核地址空间。

建议源码：

```text
arch/x86/kernel/head_64.S
arch/x86/kernel/head64.c
arch/x86/mm/ident_map.c
```

## B04：从 `x86_64_start_kernel()` 到 `start_kernel()`

主要内容：

- 清理早期 BSS 和启动状态；
- 早期异常处理；
- 命令行和内存信息；
- `setup_arch()`；
- 页分配器、调度器、时钟、中断和 RCU 的初始化顺序；
- 为什么初始化顺序不能任意改变。

建议源码：

```text
arch/x86/kernel/head64.c
arch/x86/kernel/setup.c
init/main.c
```

## B05：从 `start_kernel()` 到用户空间

主要内容：

```text
start_kernel
→ arch_call_rest_init
→ rest_init
→ kernel_init
→ run_init_process
```

重点说明：

- idle 任务如何形成；
- `kthreadd` 如何启动；
- initcall 如何初始化各子系统和驱动；
- initramfs 与根文件系统；
- `/sbin/init` 或其他 init 程序如何成为第一个用户空间进程。

---

# 第二部分：Kexec

## B06：Kexec 解决什么问题

普通重启通常会重新经过固件和引导程序。Kexec 允许当前 Linux 内核直接启动另一个内核，可以减少重启路径，也为 Kdump 提供内核切换机制。

需要区分：

```text
正常 kexec
为了快速启动另一个正常内核。

crash kexec
为了在当前内核崩溃后启动捕获内核。
```

## B07：Kexec 镜像的加载

主要内容：

- `kexec_load` 与 `kexec_file_load`；
- 内核、initramfs 和命令行如何组成待启动映像；
- segment 如何放入目标物理内存；
- 加载阶段与真正切换阶段为什么分开；
- 签名验证和安全限制的基本作用。

建议源码：

```text
kernel/kexec.c
kernel/kexec_core.c
kernel/kexec_file.c
arch/x86/kernel/kexec-bzimage64.c
```

## B08：从当前内核切换到新内核

主要内容：

```text
触发 kexec
→ 停止普通任务和设备活动
→ 关闭或隔离其他 CPU
→ 保存必要状态
→ 执行重定位代码
→ 建立新内核要求的入口状态
→ 跳转到新内核
```

重点说明：

- 为什么不能继续依赖当前内核的大部分服务；
- 为什么切换代码必须小而独立；
- CPU、页表、中断和设备状态如何影响切换；
- 正常 Kexec 与 crash Kexec 在关闭流程上的区别。

建议源码：

```text
kernel/kexec_core.c
arch/x86/kernel/machine_kexec_64.c
arch/x86/kernel/relocate_kernel_64.S
```

## B09：Purgatory 的作用

主要内容：

- Purgatory 位于旧内核和新内核之间；
- 为什么需要一段独立执行的过渡代码；
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

Kdump 使用两套内核：

```text
生产内核
正常承载业务。发生 panic 时提供崩溃现场。

捕获内核
预先加载到保留内存中。生产内核崩溃后启动，负责保存 vmcore。
```

捕获内核应尽量小，并使用较少的驱动和内存。它不能依赖生产内核仍然正常工作。

## B11：`crashkernel=` 与保留内存

主要内容：

- 为什么必须在生产内核启动时预留内存；
- 保留区为什么不能再交给普通页分配器；
- 固定大小、范围选择和高低端预留的基本形式；
- 捕获内核、initramfs、Purgatory 和控制结构如何使用保留区；
- 预留过小和过大的影响。

与内存课程的联系：

```text
启动参数
→ memblock 预留
→ 普通内存初始化时排除 crashkernel 区域
```

## B12：捕获内核的预加载

主要内容：

- kdump 服务如何加载捕获内核；
- 捕获内核命令行；
- `nr_cpus=1`、内存限制等常见配置的目的；
- initramfs 中为什么需要存储、网络或文件系统驱动；
- 如何确认 crash kernel 已经加载。

## B13：从 panic 到 `crash_kexec()`

主要路径：

```text
严重错误
→ panic
→ 停止或通知其他 CPU
→ 保存崩溃 CPU 状态
→ crash_kexec
→ machine_crash_shutdown
→ 跳转到捕获内核
```

重点说明：

- panic 路径与普通重启路径的区别；
- 为什么崩溃环境中锁、调度和设备状态都不可信；
- 各 CPU 寄存器和崩溃注释如何保存；
- NMI、watchdog 和多 CPU 停止过程；
- 哪些情况下 `crash_kexec()` 可能无法执行。

建议源码：

```text
kernel/panic.c
kernel/crash_core.c
kernel/kexec_core.c
arch/x86/kernel/crash.c
arch/x86/kernel/machine_kexec_64.c
```

## B14：捕获内核如何访问旧内核内存

捕获内核启动后，看到的主要内存内容仍然来自生产内核崩溃时的物理内存。课程重点解释：

- 捕获内核为什么不能把旧内存当作普通可分配内存；
- `elfcorehdr` 如何描述需要导出的物理内存和 CPU 状态；
- `/proc/vmcore` 如何以 ELF core 文件形式呈现崩溃现场；
- `VMCOREINFO` 为什么需要记录符号、结构体偏移和页大小等信息；
- 保留区、不可导出区域和过滤区域。

建议源码：

```text
fs/proc/vmcore.c
kernel/crash_core.c
include/linux/crash_core.h
```

## B15：保存 `vmcore`

主要内容：

- 直接复制 `/proc/vmcore`；
- `makedumpfile` 的过滤和压缩；
- 文件系统、本地磁盘、网络和远程存储；
- dump 级别；
- 磁盘空间和写入时间；
- 保存失败时应检查哪些环节。

重点区分：

```text
/proc/vmcore
捕获内核提供的崩溃内存视图。

保存后的 vmcore 文件
从 /proc/vmcore 复制或过滤得到的持久化转储。
```

## B16：使用 Crash 分析 `vmcore`

分析前必须准备匹配的：

```text
vmcore
带调试信息的 vmlinux
对应的内核模块调试文件
内核版本、Build ID 和配置
```

基础分析流程：

```text
确认崩溃内核版本
→ 查看 panic 信息
→ 查看当前任务和各 CPU
→ 展开调用栈
→ 查看寄存器和故障指令
→ 检查 task、内存、锁或网络对象
→ 还原故障发生前的执行路径
```

重点命令可包括：

```text
sys
log
bt
bt -a
ps
task
regs
dis
kmem
vm
files
net
struct
list
```

## B17：符号匹配与调用栈展开

主要内容：

- `vmlinux`、`System.map`、kallsyms 和模块符号；
- Build ID；
- KASLR 地址修正；
- 函数名、模块名和相对偏移；
- frame pointer、DWARF 和 ORC unwinder；
- 内联函数、尾调用和栈损坏；
- 为什么错误的符号文件可能生成看似合理但实际错误的结果。

## B18：Kdump 的限制与失效场景

需要客观看待 Kdump。它不能保证在所有故障中成功。

常见限制：

- CPU 已无法继续执行指令；
- 严重内存损坏破坏了 Kexec 映像或保留区；
- IOMMU 或设备仍在 DMA，继续破坏内存；
- 多 CPU 停止失败；
- 捕获内核缺少必要驱动；
- 存储目标不可用；
- 捕获内核自身启动失败；
- 固件、BMC 或硬件复位先于 crash kexec 发生。

因此，Kdump 应与串口日志、pstore、BMC 事件日志、硬件 watchdog 和远程日志配合使用。

---

# 第四部分：实验安排

## 实验 1：观察正常 x86_64 启动

- 保存完整 `dmesg`；
- 标记内核解压、内存发现、SMP、调度器、时钟和驱动初始化阶段；
- 将启动日志与 `start_kernel()` 初始化顺序对应起来。

## 实验 2：普通 Kexec 切换

- 加载第二个测试内核；
- 检查待启动映像；
- 执行 Kexec；
- 对比普通重启与 Kexec 的日志和耗时；
- 验证新内核命令行和 initramfs。

## 实验 3：配置双内核 Kdump

- 配置 `crashkernel=`；
- 检查保留内存；
- 构建捕获内核 initramfs；
- 加载 crash kernel；
- 检查服务状态和加载结果。

## 实验 4：受控触发 panic

在隔离的测试环境中：

- 使用 SysRq 或测试模块触发 panic；
- 观察生产内核进入 crash kexec；
- 确认捕获内核启动；
- 保存 vmcore；
- 记录失败时的控制台和串口日志。

## 实验 5：分析 vmcore

- 使用匹配的 `vmlinux` 打开 vmcore；
- 查看 panic CPU、当前任务、调用栈和寄存器；
- 反汇编故障 RIP 附近代码；
- 查看故障对象；
- 输出一份包含证据链的分析报告。

## 实验 6：模拟常见失败

可选择验证：

- crashkernel 预留不足；
- 捕获内核缺少存储驱动；
- vmlinux 与 vmcore 不匹配；
- 模块调试符号缺失；
- 保存目录空间不足。

实验重点是学会判断故障发生在：

```text
预留阶段
加载阶段
panic 切换阶段
捕获内核启动阶段
vmcore 导出阶段
持久化保存阶段
离线分析阶段
```

---

# 与其他课程的关系

```text
assembly
理解早期入口、寄存器、页表切换、异常和 Kexec 跳转代码。

memory
理解 crashkernel 保留区、物理内存、页表和 vmcore 内存映射。

scheduler
理解 panic 时其他 CPU 和任务为何不能再按正常调度路径处理。

timekeeping
理解 watchdog、lockup 检测和崩溃时间线。

network
理解通过网络保存 vmcore，以及分析网络故障现场。

integrated-paths
从 panic 一直跟踪到 vmcore 根因分析。
```

# 建议学习顺序

在进入本目录前，建议先掌握：

1. 汇编课程中的寄存器、取址、栈和控制流；
2. 内存课程中的物理内存、页表和 memblock；
3. 调度课程中的任务、CPU 和上下文切换基础。

之后按照下面的顺序学习：

```text
B00～B05  x86_64 正常启动
B06～B09  Kexec
B10～B15  双内核 Kdump 与 vmcore 生成
B16～B18  vmcore 分析、符号和失效场景
```

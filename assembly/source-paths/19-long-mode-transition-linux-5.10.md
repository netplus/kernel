# A19 源码事实核验：Linux 5.10 x86-64 长模式切换基础

本文只核验 A19“早期启动汇编阅读基础”所需的最小事实：32-bit protected mode 如何准备 PAE/page table/EFER，如何通过 CR0.PG 激活 IA-32e mode，以及为什么还需要一次 far control transfer 才进入 64-bit code segment。完整 Linux 启动流程仍放在 `boot-crash/`。

## 1. 版本与源码基线

版本：upstream Linux v5.10。

主要文件：

```text
arch/x86/boot/compressed/head_64.S
arch/x86/include/asm/processor-flags.h
arch/x86/include/asm/msr-index.h
arch/x86/include/asm/segment.h
```

本节以 compressed kernel 的 `startup_32 -> startup_64` 路径作为可读的模式切换样本。它不是“所有 bootloader 都必须从 startup_32 进入”的声明：`startup_64` 本身也支持满足入口条件的 64-bit bootloader 直接进入。

## 2. 先区分四个状态

阅读模式切换代码时不能把下面四件事写成一个动作：

1. `CR0.PE=1`：protected mode 基础状态；
2. `CR4.PAE=1`：选择 IA-32e paging 所需的 PAE paging structure 语义；
3. `IA32_EFER.LME=1`：允许在 paging 被打开后激活 long mode；
4. 当前 code segment 的 `CS.L=1`：决定当前代码是否真正按 64-bit mode 执行。

Linux v5.10 的 compressed `startup_32` 正好按这个依赖关系准备环境，而不是通过一条“进入 64 位”的单独指令完成全部状态变化。

## 3. GDT 先准备 64-bit code segment

`startup_32` 先根据当前实际装载地址修正本地 GDT descriptor，然后执行：

```text
lgdt
```

并把 data selectors 装入 `DS/ES/FS/GS/SS`。

这里的关键点不是“lgdt 会切换到 long mode”。`lgdt` 只是让后续 far control transfer 能够使用包含 64-bit code descriptor 的 GDT。真正决定后续 code-segment execution mode 的是重新装载 `CS`。

## 4. CR4.PAE 在 page-table 激活之前设置

Linux v5.10 `startup_32` 在“Prepare for entering 64 bit mode”阶段执行：

```asm
movl %cr4, %eax
orl  $X86_CR4_PAE, %eax
movl %eax, %cr4
```

因此 A19 教程可以把 `CR4.PAE` 作为进入 IA-32e paging 的必要准备条件讲解，但不能把它解释成“PAE 位一设置 CPU 就已经进入 long mode”。

## 5. 建立 early 4G boot page tables 并写 CR3

随后代码清零并建立 compressed boot path 使用的 early page tables，再执行：

```asm
leal rva(pgtable)(%ebx), %eax
movl %eax, %cr3
```

这一阶段解决的是：一旦打开 paging，CPU 必须已经能够从 CR3 找到有效的 paging structures。

需要保留两个边界：

- 这里是 compressed boot path 的具体 early mapping，不代表 Linux 后续最终页表布局；
- A19 只解释“为什么模式切换前必须先有可用映射”，完整早期页表建立与启动地址空间继续由 `boot-crash/` / `memory/` 展开。

## 6. EFER.LME 通过 MSR 设置

v5.10 随后读取 `MSR_EFER`：

```asm
movl $MSR_EFER, %ecx
rdmsr
btsl $_EFER_LME, %eax
wrmsr
```

因此这里涉及两个不同概念：

- `IA32_EFER` 是 MSR，不是 CR0/CR4 这样的 control register；
- `LME` 是 long-mode enable 条件，但在此时 paging 尚未由这段代码打开，不能把 `wrmsr` 后的现场直接描述成已经执行 64-bit instructions。

## 7. CR0.PG 与 CR0.PE 激活 paged protected mode / IA-32e

在 far transfer 的 selector 和 target 都已压入 mini stack 后，代码执行：

```asm
movl $(X86_CR0_PG | X86_CR0_PE), %eax
movl %eax, %cr0
```

v5.10 源码注释明确把这里描述为 enabling paging and protected mode，并指出此时 long mode 已激活，但当前仍处于 32-bit compatibility execution context，直到新的 `CS` 被加载。

这给 A19 一个很重要的教学边界：

```text
EFER.LME + CR4.PAE + valid CR3 + CR0.PG
```

建立 IA-32e 的 paging/mode 条件；而“当前指令按 64-bit mode 解码执行”还依赖 code segment 的 `CS.L`。

## 8. `lret` 是这里的 far control transfer

Linux 在 mini stack 上准备：

```asm
pushl $__KERNEL_CS
pushl %eax              # startup_64 target
```

随后在设置 CR0 后执行：

```asm
lret
```

这里 `lret` 的作用不是普通近 `ret`：它同时取得新的 instruction pointer 和 code-segment selector，从 GDT 装入具有 64-bit 属性的 `__KERNEL_CS`，从而进入 `startup_64` 的 `.code64` 代码。

因此 A19 后续教程应把“far jump”按更准确的 **far control transfer / reload CS** 来讲；v5.10 这个具体路径实际使用的是 `lret`，不应为了教材叙述而改写成源码并未执行的 `ljmp`。

## 9. `startup_64` 的入口边界

`startup_64` 位于 `.code64`，源码同时说明两种来源：

```text
startup_32 完成模式切换后进入
或
满足 64-bit boot protocol 前提的 64-bit bootloader 直接进入
```

直接 64-bit 入口要求 bootloader 已提供能覆盖 kernel/zero page/command line 等所需对象的 identity-mapped page table。因此不能把 `startup_32` 的 CR0/CR4/EFER 序列错误地描述成每一次 Linux x86-64 启动都会由 kernel 自己执行。

## 10. 与 5-level paging 的边界

v5.10 `startup_64` 后续还可能处理 4-level/5-level paging 转换。源码明确指出：处于 long mode 时不能直接设置或清除 `CR4.LA57`，否则会触发 `#GP`，所以必要时需要 trampoline 暂时关闭 paging/long mode 再切换。

这说明 control-register 的修改存在架构状态依赖。A19 第一部分只记录这一事实作为边界，不在本单元展开 LA57 trampoline。

## 11. 本次事实核验得到的最小执行模型

对 v5.10 compressed `startup_32`，可以用下面的顺序阅读：

```text
32-bit protected-mode startup_32
    |
    |-- prepare GDT containing 64-bit code segment
    |-- CR4.PAE = 1
    |-- build early paging structures
    |-- CR3 = early page-table root
    |-- IA32_EFER.LME = 1
    |-- prepare far-return target: __KERNEL_CS:startup_64
    |-- CR0.PE | CR0.PG = 1
    |       IA-32e active, but current CS is not yet 64-bit CS
    |-- lret
    |       reload CS from 64-bit descriptor
    v
.code64 startup_64
```

## 12. 后续教程必须避免的误区

1. 不说“设置 EFER.LME 就进入 64 位”。
2. 不说“设置 CR0.PG 后下一条普通指令天然就是 64-bit instruction”。
3. 不说“`lgdt` 会切换 CPU mode”。
4. 不把 CR3 中的地址误写成“页表本身的虚拟地址”；这里 CPU 需要的是 paging-structure root 的物理地址语义。
5. 不把 v5.10 compressed `startup_32` 路径泛化成所有 bootloader 的唯一入口。
6. 不把源码实际使用的 `lret` 写成 `ljmp`；应先讲 far control transfer 的原理，再说明该路径用 far return 实现。
7. 不在 assembly 课程重复展开完整 boot protocol、KASLR、decompressor、最终内核页表或 `start_kernel()`；这些属于 `boot-crash/` 主线。

## 13. 下一最小单元

基于本核验编写 A19 第一部分正式教程：先从 real mode / protected mode / compatibility mode / 64-bit mode 的状态关系建立背景，再解释 CR0、CR3、CR4、EFER、GDT/CS 与 paging 的依赖，最后用 v5.10 `startup_32 -> startup_64` 逐条映射；配套实验优先采用一个最小 QEMU boot stub 或静态反汇编验证，而不是直接复制完整 Linux 启动过程。

# A19 第一部分：x86-64 长模式切换基础

本节只解决一个问题：CPU 从 32 位 protected-mode 执行环境进入真正的 64-bit mode，需要哪些状态彼此配合，以及 Linux 5.10 的 compressed kernel 如何把这些条件组织成一条可读的汇编路径。

完整 Linux 启动协议、解压、KASLR、最终内核页表和 `start_kernel()` 不在本节展开；这些内容属于 `boot-crash/`。这里把 `arch/x86/boot/compressed/head_64.S` 的 `startup_32 -> startup_64` 当作模式切换的具体样本。

Linux 5.10 源码事实基线见：[`../source-paths/19-long-mode-transition-linux-5.10.md`](../source-paths/19-long-mode-transition-linux-5.10.md)。

## 1. 为什么“进入 64 位”不是一个开关

初学时很容易把 long mode 想成某个控制位：把一个 bit 置 1，CPU 就开始执行 64 位指令。x86-64 实际不是这样。

至少要同时回答四个问题：

1. CPU 是否已经处于 protected-mode 基础状态；
2. paging 是否使用 IA-32e 所要求的页表机制；
3. EFER 是否允许 long mode；
4. 当前 `CS` 是否指向一个 64-bit code segment。

因此模式切换更适合写成一组依赖关系：

```text
protected-mode foundation
        +
CR4.PAE
        +
valid paging structures selected by CR3
        +
IA32_EFER.LME
        +
CR0.PG
        +
load a code segment with CS.L = 1
        |
        v
64-bit execution
```

其中任何一步都不能单独代表完整切换。

## 2. 先区分 real mode、protected mode、compatibility mode 与 64-bit mode

### 2.1 real mode

real mode 是 x86 启动历史模型中的早期执行状态。它使用传统分段语义，没有 protected mode 的 descriptor-based protection，也不是本节 Linux `startup_32` 的直接起点。

A19 需要知道 real mode 的存在，是为了理解为什么启动代码最终必须逐步建立 protected mode、paging 和 64-bit execution 所需状态；但 Linux 5.10 compressed `startup_32` 本身已经是在 32-bit protected-mode 语境中阅读。

### 2.2 protected mode

当 `CR0.PE=1` 后，CPU 使用 protected-mode 的分段和 descriptor 机制。此时可以运行 32-bit code segment，但这仍不等于 long mode。

### 2.3 IA-32e 与 compatibility mode

当 long-mode 的 paging 条件被激活后，CPU 进入 IA-32e 环境。此时当前 code segment 的属性仍然重要。

如果当前 `CS` 不是 64-bit code segment，处理器可以处于 compatibility execution context：已经使用 IA-32e paging，但当前代码仍按兼容的 16/32-bit 语义执行。

这正是理解 Linux v5.10 `startup_32` 最关键的中间状态：打开 paging 后，代码还需要一次 far control transfer 来重新装载 `CS`。

### 2.4 64-bit mode

只有当当前 code segment 具有 long-mode code 属性，也就是 `CS.L=1`，当前代码才真正按 64-bit mode 执行。Linux 的目标入口 `startup_64` 位于 `.code64`。

因此：

```text
long mode enabled/active
```

和

```text
current instruction stream executes in 64-bit mode
```

不是完全相同的一句话。

## 3. CR0、CR3、CR4 与 EFER 各自负责什么

### 3.1 CR0：PE 与 PG

本节关心 CR0 中两个位：

```text
CR0.PE   protected-mode enable
CR0.PG   paging enable
```

Linux v5.10 compressed `startup_32` 在最后激活阶段写入 `X86_CR0_PE | X86_CR0_PG`。

`PE` 提供 protected-mode 基础；`PG` 让地址翻译真正开始使用 CR3 指向的 paging structures。在已经准备好 PAE 与 EFER.LME 的前提下，打开 PG 是激活 IA-32e paging/mode 条件的关键步骤。

### 3.2 CR4.PAE：选择所需 paging 语义

`CR4.PAE=1` 是进入 IA-32e paging 的必要准备之一。

它不是“64 位开关”。Linux 在打开 CR0.PG 之前就先设置它，因为 CPU 在 paging 激活时必须已经看到正确的 paging-mode 前提。

### 3.3 CR3：告诉 CPU 去哪里找页表根

CR3 保存 paging-structure root 的物理地址语义。

模式切换前必须先建立有效映射，再写 CR3。否则一旦打开 paging，CPU 连下一条指令、当前栈或目标入口都可能无法正确翻译。

因此依赖顺序是：

```text
build usable mappings
        |
        v
load CR3
        |
        v
enable paging
```

不能反过来。

### 3.4 IA32_EFER.LME：允许 long mode

EFER 是 MSR，不是 CR0/CR4 一类 control register。Linux 使用 `rdmsr/wrmsr` 修改 `IA32_EFER`，把 LME（Long Mode Enable）位置 1。

LME 表示允许在 paging 条件满足后进入 long-mode 环境。仅执行：

```text
EFER.LME = 1
```

并不会让下一条指令自动变成 64-bit instruction。

## 4. GDT 和 CS 为什么仍然重要

x86-64 经常被概括为“弱化了 segmentation”。这句话不能推导出“进入 64 位时不需要 GDT/CS”。

CPU 必须知道当前 code segment 是否是 64-bit code segment。这个属性来自 code-segment descriptor，并通过 `CS` 的装载生效。

因此 Linux 在切换前先准备包含 64-bit kernel code descriptor 的 GDT，并执行 `lgdt`。

`lgdt` 本身只加载 descriptor-table register。它不会自动改变当前 `CS`，更不会单独切换 CPU mode。

真正的关键动作是后面的 far control transfer：它同时改变 instruction pointer 和 `CS`。

## 5. Linux 5.10 `startup_32 -> startup_64` 的实际顺序

下面把原理映射到 Linux v5.10 的 `arch/x86/boot/compressed/head_64.S`。

### 5.1 准备 GDT

`startup_32` 先修正本地 GDT descriptor 的地址，然后执行 `lgdt`，并设置数据 segment selectors。

此时的目的只是为后续重新装载 `CS` 准备合法的 64-bit code descriptor。

### 5.2 设置 CR4.PAE

源码执行的核心动作可简化为：

```asm
movl %cr4, %eax
orl  $X86_CR4_PAE, %eax
movl %eax, %cr4
```

此时 CPU 仍没有因为这一位而开始执行 64-bit code。

### 5.3 建立 early page tables 并加载 CR3

compressed boot path 建立早期映射后，把页表根写入 CR3。

这里最重要的阅读问题不是页表每个 entry 的全部细节，而是：

> 打开 paging 之前，当前执行地址、栈和即将进入的 64-bit target 必须处于可翻译的映射中。

完整 early mapping 布局留给启动和内存课程。

### 5.4 设置 IA32_EFER.LME

Linux 读取 `MSR_EFER`，设置 LME，再写回：

```asm
movl $MSR_EFER, %ecx
rdmsr
btsl $_EFER_LME, %eax
wrmsr
```

这一步建立 long-mode enable 条件，但 paging 尚未由这一段代码最终打开。

### 5.5 预先准备 far-return target

Linux 5.10 这条路径没有使用教材中常见的 `ljmp` 示例，而是先把新的 code selector 和 `startup_64` target 放到一个 mini stack 上：

```text
__KERNEL_CS
startup_64 target
```

随后用 far return 完成控制转移。

### 5.6 打开 CR0.PG/PE

源码设置：

```text
CR0.PG = 1
CR0.PE = 1
```

到这里，PAE、CR3、LME 和 paging 条件已经组合起来，IA-32e 环境被激活。

但是当前 `CS` 仍是此前的 code segment，因此不能把“写 CR0 后”直接描述成“已经跳进 `.code64 startup_64`”。

### 5.7 `lret` 重新装载 CS

Linux 随后执行 `lret`。

这里的 `lret` 是 far return，不是 A07 中只恢复 RIP 的普通 near `ret`。它从准备好的栈内容中取得新的 instruction pointer 和 code-segment selector。

新的 selector 指向具有 64-bit 属性的 `__KERNEL_CS`。装载完成后，CPU 才开始在 `.code64 startup_64` 中按 64-bit mode 执行。

所以这条路径应准确写成：

```text
prepare 64-bit GDT entry
        |
CR4.PAE
        |
build page tables -> CR3
        |
EFER.LME
        |
CR0.PE | CR0.PG
        |
IA-32e active, current CS still matters
        |
lret: load __KERNEL_CS + startup_64
        |
CS.L = 1
        v
.code64 startup_64
```

## 6. 为什么源码用 `lret` 而不是必须用 `ljmp`

模式切换真正需要的是 **far control transfer that reloads CS**。

`ljmp` 是一种实现方式，far `ret` 也是一种实现方式。Linux v5.10 compressed `startup_32` 的具体实现选择 `lret`。

因此阅读内核源码时应分两层描述：

```text
架构要求：需要重新装载具有 64-bit 属性的 CS
Linux v5.10 实现：通过预构造 far-return frame + lret 完成
```

不能因为教材常用 `ljmp`，就把 Linux 实际指令改写成 `ljmp`。

## 7. 模式切换时地址为什么必须连续可用

切换过程中 CPU 不会暂停执行等待软件“修好页表”。CR0.PG 一旦生效，后续 instruction fetch 和 memory access 就必须能够通过新的 paging structures 工作。

所以 early page table 至少必须覆盖切换过程需要继续访问的对象，例如当前代码、目标代码和必要的数据/栈。

这也是为什么“先 CR3，后 PG”不是编码风格，而是执行连续性的要求。

## 8. `startup_64` 不是只能从 `startup_32` 到达

Linux v5.10 的 compressed 64-bit entry 还允许满足协议要求的 64-bit bootloader 直接进入 `startup_64`。

这种情况下，bootloader 已经完成必要的 64-bit execution 与 identity mapping 前提。

因此本节的源码路径应该表述为：

> Linux 5.10 compressed kernel 自己从 32-bit entry 切到 64-bit entry 时的一条具体路径。

而不是：

> 所有 Linux x86-64 启动都必然执行这一串 CR0/CR4/EFER 指令。

## 9. 5-level paging 是另一个状态转换问题

Linux v5.10 的 `startup_64` 后续还可能处理 4-level 与 5-level paging 的差异。

这里需要记住一个边界：处于 long mode 时不能随意修改 `CR4.LA57`。因此相关代码可能需要 trampoline 暂时改变 paging/long-mode 状态。

A19 第一部分不展开这条分支。它只说明：control-register 位之间存在状态依赖，不能把每一位当作彼此独立、任何时刻都能修改的普通配置位。

## 10. 阅读这段汇编时逐步检查什么

遇到模式切换汇编时，可以按下面的顺序检查：

1. 当前代码处于什么 execution mode；
2. 当前 `CS` 的属性是什么；
3. GDT 是否已经包含目标 code descriptor；
4. CR4.PAE 是否已经满足；
5. paging structures 是否已经建立；
6. CR3 是否已经指向正确的 root；
7. EFER.LME 是否已经设置；
8. CR0.PG 在什么时刻打开；
9. 哪条 far control transfer 真正重新装载 `CS`；
10. target 是否已经按 `.code64` 汇编，并且地址在新页表下可访问。

这比只寻找“哪一条指令进入 64 位”更接近 CPU 实际执行过程。

## 11. 常见误区

### 误区一：`EFER.LME=1` 后已经是 64-bit mode

不对。它只是必要条件之一。

### 误区二：`CR0.PG=1` 后下一条普通指令必然按 64 位解码

不对。当前 code-segment 状态仍然决定当前执行子模式，Linux 还需要 `lret` 装载 64-bit `CS`。

### 误区三：`lgdt` 完成模式切换

不对。`lgdt` 只准备 descriptor table；当前 `CS` 不会因此自动改变。

### 误区四：CR3 保存一个普通虚拟地址

不对。本节所需的基本语义是 paging-structure root 的物理地址语义。

### 误区五：Linux 5.10 这里一定执行 `ljmp`

不对。compressed `startup_32` 这条具体路径使用 `lret`。

### 误区六：`startup_32` 是所有 x86-64 Linux bootloader 的唯一入口

不对。满足 64-bit boot protocol 条件的 loader 可以直接进入 `startup_64`。

## 12. 本节完成后应能回答的问题

读完本节后，应能够解释：

- 为什么 long-mode transition 不是一个 bit 的切换；
- CR0.PE、CR0.PG、CR4.PAE、CR3 和 EFER.LME 分别承担什么角色；
- 为什么必须先建立 page tables，再打开 paging；
- 为什么 GDT/CS 在 x86-64 模式切换时仍然重要；
- compatibility execution 与真正 64-bit execution 的区别；
- Linux v5.10 为什么在这里使用 `lret`；
- `startup_32 -> startup_64` 为什么只是一个具体启动入口路径，而不是所有 bootloader 的唯一过程。

下一最小单元应为本节建立验证实验：优先使用最小 QEMU boot stub 或可控的静态汇编/反汇编样本，逐项验证 GDT descriptor、CR0/CR4/EFER 设置顺序和 far control transfer；不能在当前环境实际运行 QEMU 时，应把静态可验证项与动态 mode-state 观察明确分开。
# A19 整章一致性复核：早期启动汇编阅读基础

本文件用于在 A19 收章前检查课程大纲与已经完成的三个部分是否真正一致。A19 的目标不是讲完整 Linux 启动流程，也不是重复 memory 领域的页表课程，而是建立阅读 Linux 5.10 x86-64 早期启动汇编所需的最小机器状态模型。

复核对象：

- 第一部分：[`19-long-mode-transition-basics.md`](19-long-mode-transition-basics.md)
- 第二部分：[`19-early-boot-page-tables.md`](19-early-boot-page-tables.md)
- 第三部分：[`19-protected-mode-entry-segments-and-cpu-check.md`](19-protected-mode-entry-segments-and-cpu-check.md)
- 对应 `source-paths/19-*.md` 与 `labs/19-*/`

## 1. A19 大纲要求与现有内容的对应关系

`assembly/README.md` 对 A19 给出五项要求：

```text
实模式、保护模式和长模式
控制寄存器
早期页表
远跳转和模式切换
head_64.S 所需的汇编基础
```

现有三个部分已经覆盖这些要求，但需要准确理解覆盖边界。

### 1.1 实模式、保护模式和长模式

第一部分区分 real mode、protected mode、IA-32e compatibility execution 与 64-bit execution；第三部分进一步确认 Linux 5.10 compressed `startup_32` 已经接收一个 32-bit protected-mode 入口现场，而不是从 real mode 自己开始切换。

因此 A19 对 real mode 的要求已经达到“能够理解模式关系和 `startup_32` 的入口边界”的程度。real-mode setup、boot protocol 与前级切换过程仍属于 `boot-crash/`，不应为了让 A19 看起来更完整而复制进 assembly。

### 1.2 控制寄存器

第一部分已经围绕真实模式切换顺序解释：

```text
CR4.PAE
-> early page tables / CR3
-> IA32_EFER.LME
-> CR0.PE | CR0.PG
-> far control transfer
-> CS.L = 1
```

这里必须继续保留两个边界：

1. EFER 是 MSR，不是 control register；
2. 单独设置任意一个 bit 都不能推出当前 instruction stream 已进入 64-bit execution。

A19 不需要扩展 CR0/CR4 的全部位定义，只需要解释这条启动路径真正使用的状态。

### 1.3 早期页表

第二部分已经按 Linux 5.10 `startup_32` 的实际实现建立：

```text
BOOT_INIT_PGT_SIZE = 6 * 4096
= 1 x L4 + 1 x L3 + 4 x L2
-> 2048 x 2 MiB leaf
-> [0, 4 GiB) identity mapping
-> CR3
```

实验进一步验证 L2/L3 边界和 4 GiB 覆盖。这里讲的是“汇编如何构造足够跨过模式切换的临时页表”，而不是完整 paging subsystem。页表生命周期、最终内核地址空间与通用 page-table API 继续属于 memory/boot-crash。

### 1.4 远控制转移和模式切换

Linux 5.10 的 compressed `startup_32` 在目标栈上使用两个 `pushl` 建立 far-return frame，并通过 `lret` 重新装载 instruction pointer 与 `CS`。课程已经明确：

```text
CR0.PG 已打开
!=
当前代码已经使用 64-bit CS
```

只有 far transfer 完成、`CS` 指向具有 L bit 的 code descriptor，并进入 `.code64 startup_64` 后，才能把当前 instruction stream 描述为 64-bit execution。

这里必须坚持 Linux 5.10 的实际 `lret` 实现，不能因为教材常见示例使用 `ljmp` 就改写源码事实。

### 1.5 `head_64.S` 阅读所需汇编基础

第三部分补齐了第一、第二部分默认依赖的入口状态：

```text
.code32 entry
-> cld / cli
-> runtime base
-> lgdt
-> DS/ES/FS/GS/SS reload
-> scratch stack -> boot_stack_end
-> verify_cpu()
-> long-mode preparation
```

因此读者已经具备理解该段 `head_64.S` 所需的 segment hidden state、GDTR、stack、flags、CPU feature gate、控制寄存器和 far transfer 基础。KASLR、decompressor、boot params、最终内核入口等不属于本章目标。

## 2. 三部分必须拼成一条连续状态链

A19 的核心不是三个独立知识点，而是以下连续状态变化：

```text
已有 32-bit protected-mode entry contract
        |
        v
cld / cli
        |
        v
compressed image runtime base
        |
        v
lgdt + reload data/stack segments
        |
        v
scratch stack -> boot_stack_end
        |
        v
verify_cpu() feature gate
        |
        v
CR4.PAE
        |
        v
construct 6-page early page tables
        |
        v
CR3 = early page-table root
        |
        v
IA32_EFER.LME = 1
        |
        v
prepare 32-bit far-return frame
        |
        v
CR0.PE | CR0.PG
        |
        v
IA-32e active, but old CS still matters
        |
        v
lret -> __KERNEL_CS : startup_64
        |
        v
64-bit instruction execution
```

这条链中，“准备状态”和“状态已经生效”必须分开。例如：

- 写好 page-table entries 不等于 paging 已经开启；
- 写 CR3 不等于 CR0.PG 已经开启；
- 设置 EFER.LME 不等于已经执行 64-bit instructions；
- `lgdt` 不等于现有 segment registers 已重新装载；
- `verify_cpu()` 成功不等于后续 long-mode state 已建立。

## 3. 寄存器、栈、RFLAGS 与控制流复核

### 3.1 寄存器

A19 已经覆盖本章需要追踪的关键机器状态：

- `%cr0`：PE、PG；
- `%cr3`：early page-table root；
- `%cr4`：PAE；
- EFER MSR：LME；
- GDTR 与 segment selectors；
- `%esp`：scratch stack、boot stack、far-return mini stack；
- `%eax/%edx/%ecx`：控制寄存器/MSR 与 `verify_cpu()` 路径中的工作寄存器。

课程不应把这些寄存器的临时值写成固定地址；compressed image relocation 和运行环境会影响实际地址。

### 3.2 栈

本章有两个不同的栈问题：

1. 第三部分的 scratch stack 到 `boot_stack_end`，解决正常 early-boot 汇编调用所需的工作栈；
2. 第一部分在模式切换点构造的 far-return frame，解决 `lret` 所需的 target/selector 控制流输入。

二者不能合并成“启动栈”一个概念。

在 `startup_32` 的 32-bit operand-size 语境中，两个 `pushl` 建立两个 4-byte slot。不能套用 `retq` 或 `iretq` 的 8-byte slot 模型。

### 3.3 RFLAGS/EFLAGS

`cld` 建立 DF=0，`cli` 建立 IF=0。`verify_cpu()` 为 CPUID 等能力探测可以临时修改 flags，但通过保存/恢复 caller flags 避免把 probing 状态泄漏回调用者。返回后的 `testl %eax,%eax` 会再次更新 condition flags，因此“函数恢复 flags”不能误写成“调用点后 flags 永远与调用前完全相同”。

### 3.4 控制流

本章需要区分三类控制流：

- 普通 32-bit near call/return，例如 `verify_cpu()`；
- 普通顺序执行中的控制寄存器/MSR 更新；
- 改变 code-segment execution state 的 far `lret`。

`.code32` 和 `.code64` 是 assembler 编码上下文，不是运行时控制流指令；运行时模式结论必须结合 CR0/CR4/EFER/paging 与 CS descriptor 状态。

## 4. Linux 5.10 实现边界复核

A19 使用 `arch/x86/boot/compressed/head_64.S` 的 `startup_32 -> startup_64` 作为主样本。现有 source-path 已经记录以下 Linux 5.10 特有边界：

- compressed `startup_32` 已在 32-bit protected-mode 入口契约下运行；
- 该路径实际用 `lret` 完成最终 far transfer；
- early page-table allocation 为 24 KiB，使用四张 L2 table 建低 4 GiB identity map；
- L2 leaf 使用 2 MiB pages；
- SEV active 时 encryption mask 会影响 page-table entry 高位，不能把所有 entry 描述成恒定的纯低 32-bit 值；
- `startup_64` 还可以由满足约定的 64-bit bootloader 直接进入，因此 `startup_32` 路径不是所有 Linux x86-64 启动的唯一入口。

这些内容都属于“Linux 5.10 如何实现”的层次，不能反向写成 x86-64 架构唯一允许的实现方式。

## 5. 实验覆盖与验证状态

A19 已有三组实验：

- `labs/19-long-mode-transition/`：模式切换静态证据链和可选 QEMU/GDB 三时刻观察；
- `labs/19-early-boot-page-tables/`：6-page layout、entry flags、L3/L2 index 和 4 GiB identity map 静态计算；
- `labs/19-protected-mode-entry/`：GDT/segment/stack/`verify_cpu()` 与后续 long-mode preparation 的时间边界。

每组实验均有 expected analysis。验证状态需要按证据等级分别记录：

- 第二部分 `verify_early_pgtable.py` 已实际执行，24 KiB/6-page 布局、2048 个 2 MiB leaf、4 GiB coverage、`0x183` flags，以及 L2/L3 关键边界断言均通过；这只证明静态算术和边界计算，不等于真实 early page tables 已在 CPU 上运行。
- 第三部分已经形成 source-contract checker、正/负 fixture tests、对 upstream Linux v5.10 真实源码文本的核心匹配验证，以及独立的 objdump machine-code checker 和对应 fixture tests；这些属于源码/反汇编静态证据。
- 第三部分的 Makefile 已提供 `make test`、`make check-source KERNEL=...` 和 `make check-disassembly DISASM=...` 三个统一入口，真实 checkout/构建产物可用时应按此顺序执行并记录结果。
- 当前维护环境仍没有可执行 Linux 5.10 checkout、真实 compressed-kernel 构建产物和 QEMU early-boot debug session，因此不能把 Kbuild、真实 `objdump`、GDTR/segment hidden state、CR4/CR3/EFER、CS/RIP 等预期值写成已经动态验证的结果。

因此，“静态验证已完成的部分”和“仍需真实构建/动态现场的部分”必须分开。后续补齐真实 Kbuild、objdump 或 QEMU/GDB 数据时，应更新对应实验记录，而不是改写已经成立的架构/源码结论。

## 6. 收章判断

从课程内容覆盖看，A19 原大纲的五项要求已经全部达到：

```text
实模式/保护模式/长模式关系     已覆盖
控制寄存器与 EFER              已覆盖
早期页表                        已覆盖
far transfer 与模式切换         已覆盖
head_64.S 阅读所需汇编基础      已覆盖
```

A19 不需要再扩展完整 boot protocol、decompressor、KASLR、最终内核页表或 `start_kernel()`；这些内容应继续留在 `boot-crash/` 或 `memory/`。

因此 A19 **内容层面已经满足收章条件**。领域大纲层面的最终收口仍需要把 A18、A19 已完成的教程、实验、source-path 和 completion review 接入 `assembly/README.md`。在 README 状态同步前，不应新增 A20，也不应把 assembly 课程大纲描述成已经完全收口。
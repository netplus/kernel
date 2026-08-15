# A19：保护模式入口、GDT/段状态与 CPU 能力检查

A19 前两部分已经说明 compressed kernel 如何建立 early page tables，以及如何通过 `CR4.PAE → CR3 → EFER.LME → CR0.PG → lret` 进入 64-bit execution。本节向前补一小段：Linux 5.10 的 `startup_32` 在执行这些动作之前，CPU 到底处于什么状态，为什么已经在 protected mode 仍要重新装载 GDT、段寄存器和栈，以及 `verify_cpu()` 在这里承担什么职责。

本文只讲阅读 `arch/x86/boot/compressed/head_64.S` 所需的汇编基础。real-mode setup、boot protocol 和完整启动流程属于 `boot-crash/`。

## 1. 先建立入口模型：`startup_32` 不是 real-mode 起点

`head_64.S` 中的 `startup_32` 位于 `.code32` 环境。Linux 启动协议的前级代码已经把 CPU 带到了可以执行 32-bit protected-mode 指令的入口状态；compressed kernel 从这个契约继续执行。

因此不要把下面两件事混为一谈：

```text
前级启动代码：建立 32-bit protected-mode entry contract
                    ↓
startup_32：接收该现场，再建立 compressed kernel 自己可依赖的状态
```

`.code32` 本身只是 GNU assembler 的编码指示，它告诉汇编器如何编码后续指令；它不是一条让 CPU 进入 protected mode 的运行时指令。CPU 能否正确执行这些字节，仍取决于进入 `startup_32` 时真实的处理器模式和段状态。

Linux 5.10 的 `startup_32` 开头执行：

```asm
cld
cli
```

于是从 compressed kernel 自己的视角，后续代码首先要求：

```text
DF = 0
IF = 0
```

但此时它还没有建立自己的 GDT、data selectors 和正式 boot stack。

## 2. 为什么已经在 protected mode 还要重新建立 GDT

protected mode 并不意味着“所有 protected-mode 环境都一样”。bootloader 留下的 GDT 只属于入口契约的一部分；compressed kernel 后续还要修改控制寄存器、建立页表并进入 long mode，因此不能把外部 GDT 的具体布局当作自己的长期内部状态。

Linux 5.10 先计算 compressed image 的 runtime base，然后修正自己的 GDT descriptor 并执行 `lgdt`。

概念上可写成：

```text
bootloader/setup 留下的 GDTR
        ↓
计算当前 compressed image 的实际装载位置
        ↓
修正 compressed kernel 自己的 GDT base
        ↓
lgdt
        ↓
GDTR 指向 compressed kernel 自己的 GDT
```

这一步解决的是“CPU 去哪里查 descriptor”的问题，而不是一次性替换所有 segment register 的运行状态。

## 3. `lgdt` 为什么不等于“所有段已经切换”

理解这一点需要把一个 segment register 看成两部分：

```text
visible selector
+
hidden descriptor state/cache
```

程序能够直接看到的是 selector；CPU 在装载 selector 时，会从 GDT/LDT 读取 descriptor 的 base、limit、type、privilege 等信息，并把运行所需状态缓存起来。

`lgdt` 修改的是 GDTR：

```text
GDTR.base
GDTR.limit
```

它不会自动让现有 `CS/DS/ES/FS/GS/SS` 重新按照新 GDT 查 descriptor。因此：

> `lgdt` 改变“以后 descriptor 从哪里查”，segment-register reload 才使相应段开始采用新 descriptor。

这也是为什么 Linux 5.10 紧接着显式装载 `__BOOT_DS`：

```asm
movl $__BOOT_DS, %eax
movl %eax, %ds
movl %eax, %es
movl %eax, %fs
movl %eax, %gs
movl %eax, %ss
```

执行完成后，compressed kernel 的 data/stack segment 已经建立在自己的 GDT 上。

## 4. 为什么这里没有同时重载 `CS`

`CS` 与普通 data segment 不同，因为改变 `CS` 同时涉及 instruction stream 的控制流语义。不能用普通 `mov` 把一个 selector 写入 `%cs`。

在 `startup_32` 的这个阶段，CPU 仍然继续执行当前 32-bit code segment。真正进入 64-bit execution 时，Linux 5.10 会在栈上构造 far-return target，并使用 `lret` 装载新的 `CS` 和目标 instruction pointer。

因此时间顺序是：

```text
lgdt
  ↓
DS/ES/FS/GS/SS = __BOOT_DS
  ↓
仍在当前 32-bit CS 中执行
  ↓
PAE / early page tables / CR3 / EFER.LME / CR0.PG
  ↓
lret
  ↓
CS = __KERNEL_CS
  ↓
startup_64 / 64-bit execution
```

这条顺序非常重要。`lgdt`、data-segment reload、开启 IA-32e paging 条件和最终切换 `CS` 是四个不同事件。

## 5. scratch stack 与正式 boot stack

`startup_32` 还展示了一个很实用的早期汇编模式：在正式运行环境尚未建立时，先借用一个满足当前最小需求的临时栈，等 runtime address 已知后再切到自己的栈。

入口早期需要通过 `call`/`popl` 获得当前实际执行位置，从而计算 compressed image 的 runtime delta。此时使用的是 boot parameters scratch 区提供的临时 `%esp`。

位置关系确定、自己的段环境建立后，Linux 5.10 执行：

```asm
leal rva(boot_stack_end)(%ebp), %esp
```

从这一刻开始，普通 near `call` 的返回地址、局部栈数据等都落在 compressed kernel 自己的 boot stack 上。

所以不要把两个 `%esp` 状态写成同一个“启动栈”：

```text
scratch stack
    用途：只支撑入口最早期的位置计算

boot_stack_end
    用途：runtime base 已知后，作为 compressed kernel 的正式早期栈
```

## 6. `verify_cpu()` 为什么放在这里

接下来 Linux 要设置 PAE、构造/启用 paging、写 EFER 并进入 long mode。执行这些动作之前，必须先确认当前 CPU 满足内核要求。

Linux 5.10 的调用关系是：

```asm
call verify_cpu
testl %eax, %eax
jnz .Lno_longmode
```

返回契约很简单：

```text
EAX = 0    检查成功
EAX = 1    检查失败
```

因此 `verify_cpu()` 是后续模式转换的前置门槛，而不是模式转换本身。

## 7. `verify_cpu()` 不只是检查“long mode bit”

Linux 5.10 的 `arch/x86/kernel/verify_cpu.S` 会检查一组内核运行所要求的能力。32-bit 路径首先确认 CPUID 可用，再核验基础和扩展 CPUID feature masks，并检查所需 SSE 状态。

因此教材中如果只写：

```text
verify_cpu() 检查 CPU 是否支持 long mode
```

信息是不完整的。更准确的模型是：

```text
CPUID 是否可用
    ↓
Linux required basic feature mask
    ↓
Linux required extended feature mask
    ↓
SSE 等要求及必要兼容处理
    ↓
success / failure
```

源码中还存在 AMD SSE enable 和特定 Intel XD_DISABLE 处理。这些是 Linux 5.10 的兼容实现细节，不是 x86 架构规定的 long-mode transition 固定步骤。

## 8. `verify_cpu()` 如何保护 caller 的 EFLAGS

检查 CPUID 是否存在时，一个经典办法是尝试改变 EFLAGS.ID bit，再读回 flags 判断该位是否可修改。问题在于：feature probing 不应该无意改变调用者后续依赖的 flags 状态。

Linux 5.10 的 `verify_cpu()` 在入口保存 caller flags，内部可以临时修改 flags，退出前再恢复。

因此可以把它理解成：

```text
startup_32 caller EFLAGS
        ↓ save
verify_cpu probing state
        ↓ restore
startup_32 caller EFLAGS
```

`startup_32` 在调用前已经执行 `cld; cli`，所以正常返回后仍维持：

```text
DF = 0
IF = 0
```

这里要注意一个术语边界：`testl %eax,%eax` 会根据返回值重新设置算术 condition flags；因此“恢复 caller flags”描述的是 `verify_cpu()` 的函数边界，而不是说调用者后续任何指令都不会再改变 RFLAGS/EFLAGS。

## 9. 把第三部分与前两部分连接起来

到 `verify_cpu()` 成功返回时，可以可靠建立以下状态：

```text
32-bit protected-mode execution
GDTR -> compressed kernel GDT
DS/ES/FS/GS/SS = __BOOT_DS
ESP -> compressed boot stack
DF = 0
IF = 0
required CPU feature check passed
```

但下面这些状态仍未由这一部分建立：

```text
CR4.PAE = 1
CR3 = early page-table root
EFER.LME = 1
CR0.PG = 1
CS = __KERNEL_CS
64-bit instruction execution
```

于是 A19 三部分现在可以拼成一条连续主线：

```text
32-bit protected-mode entry
    ↓
重建 GDT / data segments / boot stack
    ↓
verify_cpu
    ↓
构造 early page tables
    ↓
CR4.PAE → CR3 → EFER.LME → CR0.PG
    ↓
lret reload CS
    ↓
startup_64
```

## 10. 四个最容易混淆的问题

### 10.1 `.code32` 是否让 CPU 进入 protected mode？

不是。它决定 assembler 如何编码指令。运行时 CPU mode 由处理器状态决定。

### 10.2 `lgdt` 后是否已经使用新 GDT 中的所有段？

不是。GDTR 更新后，已有 segment register 的 hidden state 不会因为 `lgdt` 自动全部刷新。Linux 随后显式 reload data segments；`CS` 则等 far control transfer。

### 10.3 `verify_cpu()` 是否负责开启 long mode？

不是。它验证后续路径需要的 CPU 能力。PAE、CR3、LME、paging 与 far transfer 是后续动作。

### 10.4 identity mapping 是否属于本节？

这里只需要知道后续开启 paging 前必须已有可执行映射。early page-table entry 的具体构造已经由 A19 第二部分讲解；完整 paging 机制属于 `memory/`。

## 11. Linux 5.10 源码阅读入口

本节对应：

```text
arch/x86/boot/compressed/head_64.S
    startup_32
    gdt
    boot_stack_end

arch/x86/kernel/verify_cpu.S
    verify_cpu
```

配套事实核验：

[`../source-paths/19-protected-mode-entry-segments-cpu-check-linux-5.10.md`](../source-paths/19-protected-mode-entry-segments-cpu-check-linux-5.10.md)

前置内容：

- [`19-early-boot-page-tables.md`](19-early-boot-page-tables.md)
- [`19-long-mode-transition-basics.md`](19-long-mode-transition-basics.md)

## 12. 本节应建立的最终模型

读完本节后，应能够解释下面这句话：

> Linux 5.10 compressed `startup_32` 并不是从 real mode 开始切换；它接收一个已经能够执行 32-bit protected-mode code 的入口现场，然后重新建立 compressed kernel 自己的 GDT、data segments 和 boot stack，使用 `verify_cpu()` 确认后续路径所需 CPU 能力，最后才进入 PAE、early paging、EFER 和 far control transfer 的 long-mode transition。

下一最小单元是为本节建立静态验证实验：逐项核对 `lgdt`、data-segment reload、scratch-stack/boot-stack 边界、`verify_cpu()` 的返回值和 flags 保存/恢复，并把这些观察与后续 CR4/CR3/EFER/CR0 序列分开。
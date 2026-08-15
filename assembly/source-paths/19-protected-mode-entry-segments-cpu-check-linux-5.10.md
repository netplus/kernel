# A19 源码事实核验：`startup_32` 的保护模式入口、段状态与 CPU 能力检查

本文只核验 Linux kernel 5.10 x86-64 压缩内核 `startup_32` 在准备长模式之前所依赖的**保护模式执行环境**、GDT/段寄存器重建和 `verify_cpu()` 能力检查。完整 boot protocol 属于 `boot-crash/`；长模式控制寄存器与 early page tables 已由 A19 前两个单元分别讲解。

## 1. 为什么还需要这一小节

A19 已经解释 `CR4.PAE → CR3 → EFER.LME → CR0.PG → lret → startup_64`，但这条序列不是从 real mode 直接开始执行的。Linux 5.10 的 compressed `head_64.S` 在 `startup_32` 处已经使用 `.code32`、32-bit 栈和保护模式段寄存器，并且在真正修改 PAE/paging/EFER 之前主动装载自己的 GDT、数据段和栈，再检查 CPU 是否具备后续转换所需能力。

因此必须区分：

1. bootloader/setup code 如何把 CPU 带到 32-bit protected-mode entry —— boot protocol 问题；
2. compressed `startup_32` 收到这个入口现场后如何建立自己可依赖的段环境 —— 本文范围；
3. 如何从该环境进入 IA-32e/64-bit execution —— A19 长模式切换单元。

## 2. Linux 5.10 源码位置

主文件：

```text
arch/x86/boot/compressed/head_64.S
```

CPU 能力检查实现：

```text
arch/x86/kernel/verify_cpu.S
```

`head_64.S` 在本编译上下文中包含后者，因此这里的 `verify_cpu` 运行在 32-bit code 环境。

## 3. `startup_32` 的入口不是 real-mode 指令流

Linux 5.10 `head_64.S` 在 `startup_32` 前使用 `.code32`。入口开头首先执行：

```text
cld
cli
```

随后利用 `%esi` 指向的 boot parameters scratch 区临时建立 `%esp`，通过一次近 `call`/`popl` 求出当前实际装载地址与链接时相对地址之间的 delta。

这里最重要的课程边界是：

> `.code32` 是 assembler 的编码上下文，而运行时能够正确执行这些指令还依赖调用方已经提供可用的 32-bit protected-mode 环境。`startup_32` 本身不是“从 real mode 执行 `mov %cr0` 进入 protected mode”的那段代码。

因此，A19 可以用 `startup_32` 学习 protected-mode 下的段/GDT与后续 long-mode transition，但不能把它写成 Linux 启动全过程的 real-mode 起点。

## 4. 为什么 `startup_32` 仍然重新装载 GDT

计算 runtime base 后，Linux 5.10 执行：

```text
leal rva(gdt)(%ebp), %eax
movl %eax, 2(%eax)
lgdt (%eax)
```

这里先把当前运行时的 GDT base 写入 32-bit GDTR descriptor，再由 `lgdt` 装载 GDTR。

随后：

```text
movl $__BOOT_DS, %eax
movl %eax, %ds
movl %eax, %es
movl %eax, %fs
movl %eax, %gs
movl %eax, %ss
```

即 compressed kernel 不继续把 bootloader 留下的 data selectors 当成长期契约，而是切到自己 GDT 中的 `__BOOT_DS`。

这一步要与后面的 `lret` 区分：

- `lgdt` 只更新 GDTR，不会自动重载 `CS/DS/SS/...` 的 selector/cache；
- 这里显式重载 data segment registers；
- `CS` 要到进入 64-bit execution 的 far control transfer 时，才通过栈中的 `__KERNEL_CS` 和 `lret` 更新。

因此“装载新 GDT”和“已经使用新 64-bit code segment”不是同一事件。

## 5. 正式 boot stack 在 CPU 检查前建立

完成 data segments 后，代码执行：

```text
leal rva(boot_stack_end)(%ebp), %esp
```

此后 `verify_cpu` 是普通的 32-bit near call：返回地址由当前 `%esp` 保存到这个 boot stack。

这也解释了为什么开头用于 runtime-base 计算的 scratch stack 只是临时设施：一旦位置关系确定，compressed kernel 立即切换到自己的 `boot_stack_end`。

## 6. `verify_cpu()` 的返回契约

Linux 5.10 `arch/x86/kernel/verify_cpu.S` 明确规定：

```text
EAX = 0  success
EAX = 1  failure
```

`startup_32` 对应调用：

```text
call verify_cpu
testl %eax, %eax
jnz .Lno_longmode
```

因此后续 PAE/page-table/EFER 操作只发生在检查成功之后。

### 6.1 CPUID 可用性

在 32-bit 编译上下文中，`verify_cpu()` 通过翻转 EFLAGS.ID（bit 21）并重新读取 flags，判断 CPUID 是否可用。失败直接走 `.Lverify_cpu_no_longmode`。

### 6.2 基础与扩展 CPUID feature masks

函数先检查 CPUID leaf 1 是否存在，并用 `REQUIRED_MASK0` 核验基础必需能力；再检查 extended CPUID 至少支持 `0x80000001`，并以 `REQUIRED_MASK1` 核验扩展必需能力。这里的 mask 来自 Linux x86 cpufeature 定义，不能把本文简化成“只检查一个 long-mode bit”。

### 6.3 SSE 检查

随后 `verify_cpu()` 以 `SSE_MASK` 检查所需 SSE 状态。AMD 路径还包含一次尝试通过 `MSR_K7_HWCR` 打开 SSE 的兼容处理；成功后返回 0。

### 6.4 Intel XD_DISABLE 副作用

Linux 5.10 源码注释明确说明，在满足特定 Intel family/model 条件时，函数可能清除 `MSR_IA32_MISC_ENABLE` 的 XD_DISABLE 位。这是 `verify_cpu()` 的版本实现细节，不应提升为 x86 long-mode transition 的架构步骤。

## 7. RFLAGS/EFLAGS 的处理

`verify_cpu()` 入口先保存 caller flags：

```text
pushf
push $0
popf
```

检查结束的成功与失败路径都会 `popf` 恢复 caller 传入的 flags，再设置 `%eax` 并 `ret`。

因此 CPU feature probing 中对 ID flag 等标志位的临时修改不应泄漏成 `startup_32` 的永久 EFLAGS 状态。另一方面，`startup_32` 在调用前已经执行 `cld; cli`，所以正常返回后仍保持其 caller 现场所要求的 DF=0、IF=0。

## 8. 与后续长模式切换的准确交接点

到 `verify_cpu()` 成功返回时，可以建立如下状态模型：

```text
execution encoding: 32-bit
GDTR: compressed kernel 自己的 GDT
DS/ES/FS/GS/SS: __BOOT_DS
ESP: compressed boot stack
DF: 0
IF: 0
CPU required feature check: passed
```

但此时还不能推出：

```text
CR4.PAE = 1
CR3 = early pgtable
EFER.LME = 1
CR0.PG = 1
CS.L = 1
64-bit instruction execution
```

这些状态由后续 A19 长模式切换序列逐步建立。

## 9. 与 real mode、protected mode、long mode 的边界

课程中应使用下面的表述：

```text
real mode/setup/boot protocol
    ↓  （由启动协议与前级代码建立 32-bit entry contract）
compressed startup_32
    ↓  重建自己的 GDT/data segments/stack
verify_cpu
    ↓
PAE + early page tables + CR3 + EFER.LME + CR0.PG
    ↓
lret reload CS
    ↓
startup_64
```

不要写成：

```text
startup_32 从 real mode 开始
```

也不要写成：

```text
lgdt 后 CPU 已经进入 long mode
```

## 10. 本单元核验结论

1. Linux 5.10 compressed `startup_32` 是 32-bit protected-mode 入口样本，不是 real-mode 起点。
2. 它首先重建可控的 GDTR 和 data-segment 环境，再切到自己的 boot stack。
3. `lgdt` 与 segment-register reload 是不同动作；data selectors 在这里更新，而 64-bit `CS` 要等后面的 far `lret`。
4. `verify_cpu()` 是后续 long-mode preparation 的前置门槛，成功返回值为 `%eax=0`。
5. `verify_cpu()` 检查的是一组 Linux 所需 CPU 能力，不应缩写成只测试 long-mode bit；它还包含 SSE 与厂商兼容处理。
6. feature probing 临时修改 flags，但函数在返回前恢复 caller flags；`startup_32` 自己已经通过 `cld; cli` 固定 DF/IF 的入口要求。
7. 本文只覆盖 compressed kernel 收到 32-bit entry 后的汇编状态整理；real-mode setup 与完整 bootloader contract 留在 `boot-crash/`。

## 11. 后续最小单元

基于本事实核验编写 A19 第三部分教程：以“`startup_32` 已经在 protected mode，为什么仍要重新建立 GDT/segments/stack”为问题背景，解释 GDTR 与 segment hidden state、`lgdt` 与 selector reload、临时 scratch stack 与正式 boot stack、`verify_cpu()` 的返回和 flags 契约，再与现有 long-mode transition 单元衔接。
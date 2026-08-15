# A19 实验预期分析：`startup_32` 的 GDT、段、栈与 `verify_cpu()`

本文是 `README.md` 中实验的验收基线。它只固定 Linux kernel 5.10 源码已经能够确定的关系；具体指令地址、运行时 GDT base、`ESP`、控制寄存器和 MSR 数值必须来自当前构建与 QEMU/GDB 现场，未执行动态实验时不得写成实测结果。

## 1. 入口状态：`.code32` 不是模式切换指令

在 `arch/x86/boot/compressed/head_64.S` 中，`startup_32` 位于 `.code32` 编码上下文。验收时应得到两个彼此独立的结论：

- assembler 按 32-bit code 规则编码这一段指令；
- `startup_32` 能够正确执行的运行时前提，是前级启动代码已经提供可用的 32-bit protected-mode entry contract。

因此，看到 `.code32` 或符号名 `startup_32` 都不能证明“CPU 在这里从 real mode 切到 protected mode”。本实验不把 real-mode setup 纳入 A19 assembly 主线。

入口最先执行的 `cld; cli` 分别建立 DF=0 与 IF=0。后续分析 `verify_cpu()` 的 flags 保存/恢复时，应以这个 caller 状态为基准。

## 2. `lgdt` 与 segment reload 必须分成两个事件

Linux 5.10 `startup_32` 先修正 compressed GDT 的 runtime base，再执行 `lgdt`。此时硬验收结论是：

```text
GDTR 已更新
!=
CS/DS/ES/FS/GS/SS 的 selector 与 hidden descriptor state 已全部自动刷新
```

随后源码显式把 `__BOOT_DS` 装入 `DS/ES/FS/GS/SS`。这些写操作才使对应 segment register 重新从当前 GDT 取得 descriptor state。

这一阶段没有用普通 `mov` 修改 `CS`。`CS` 的更新属于后面的 far control transfer：A19 第一部分已经核验 Linux 5.10 compressed path 使用预构造 far-return frame + `lret` 装入 `__KERNEL_CS`。所以不得把 `lgdt`、data-segment reload 和 `CS` reload 合并成一个“切换 GDT”动作。

## 3. scratch stack 与 `boot_stack_end` 的时间关系

入口早期 `%esp` 暂时借用 boot parameters scratch 区，以支持求 runtime position 的近 `call`/`popl`。runtime base 确定、GDT 与 data segments 建立后，源码执行：

```asm
leal rva(boot_stack_end)(%ebp), %esp
```

硬验收关系：

```text
早期 call/pop runtime-position calculation
    使用临时 scratch stack

ESP = boot_stack_end
    ↓
call verify_cpu
    ↓
verify_cpu 的 near-call return address
    位于 compressed kernel 自己的 boot stack
```

因此，若做 GDB 动态观察，P2 的 `%esp` 应与 `boot_stack_end` 当前运行时地址关系吻合；不能继续把它归属到最初 scratch stack。

## 4. `verify_cpu()` 的返回值契约

在 Linux 5.10 `arch/x86/kernel/verify_cpu.S` 的 32-bit 路径中，实验应确认：

```text
EAX = 0  -> success
EAX = 1  -> failure
```

调用方紧接着执行：

```asm
call verify_cpu
testl %eax, %eax
jnz .Lno_longmode
```

所以 `verify_cpu()` 成功是继续 long-mode preparation 的门槛，不是 long mode 已经建立的证据。

验收时至少要找到 CPUID availability、required basic feature mask、required extended feature mask 与 SSE 检查相关证据。AMD SSE enable 与 Intel XD_DISABLE 处理属于 Linux 5.10 的厂商兼容路径，不应提升为 x86 架构规定的 long-mode 必经步骤。

## 5. EFLAGS：函数边界恢复与返回后的再次修改

`verify_cpu()` 入口保存 caller flags，并在 probing 期间可以临时修改 EFLAGS.ID 等位；成功和失败出口都在返回前恢复 caller flags。

因此，对函数边界的正确表述是：

```text
verify_cpu 内部 probing 的临时 EFLAGS 修改
    ↓
popf
    ↓
caller 传入的 flags 状态被恢复
```

对 `startup_32` 来说，这意味着先前 `cld; cli` 建立的 DF=0、IF=0 在正常函数返回边界得到保持。

但 `ret` 后的 `testl %eax,%eax` 会立即重新写 arithmetic condition flags。因此不能把“函数恢复 caller flags”误写成“返回后整个 EFLAGS 永远保持不变”。动态实验若观察 flags，应明确记录采样点是在 `ret` 前、刚 `ret` 后还是 `testl` 后。

## 6. `verify_cpu()` 与 CR4/CR3/EFER/CR0 的硬时间边界

第三部分与 A19 前两部分的交接必须满足：

```text
startup_32 protected-mode entry
  -> runtime base
  -> lgdt
  -> DS/ES/FS/GS/SS = __BOOT_DS
  -> ESP = boot_stack_end
  -> verify_cpu() success
  -> CR4.PAE
  -> early page-table construction / CR3
  -> IA32_EFER.LME
  -> CR0.PE|PG
  -> far lret reload CS
  -> startup_64
```

在 `verify_cpu()` 成功返回、后续 CR4 write 尚未执行的观察点 P3，唯一可以确定的是 CPU feature gate 已通过以及前面的 GDT/segment/stack 状态已经建立。此时不得仅依据函数返回成功宣称：

```text
CR4.PAE = 1
CR3 已指向 early pgtable
EFER.LME = 1
CR0.PG = 1
CS.L = 1
当前 instruction stream 已是 64-bit execution
```

这些状态必须由后续指令逐项取证。

## 7. 四个动态观察点的预期关系

如果具备匹配 Linux v5.10 compressed kernel 与 QEMU/GDB 环境，建议按实验 README 的 P0-P3 记录现场。

### P0：刚进入 `startup_32`

应能执行 32-bit protected-mode 指令。`cld; cli` 执行后 DF=0、IF=0。不要从 `.code32` 本身推导 CPU mode；应结合入口契约和实际 CS/descriptor 状态判断。

### P1：`lgdt` 与 data-segment reload 完成

预期：GDTR 已指向 compressed kernel 的 GDT；`DS/ES/FS/GS/SS` 已装入 `__BOOT_DS`。`CS` 仍不是后面 long-mode far return 使用的 `__KERNEL_CS` 状态。

### P2：boot stack 已建立、`verify_cpu` 即将调用

预期：`ESP` 已切到 compressed kernel 的 `boot_stack_end` 相关位置。后续 near `call verify_cpu` 将在该栈上保存返回地址。

### P3：`verify_cpu` 成功返回、CR4.PAE 尚未写入

预期：`EAX=0` 表示 feature check 成功；函数边界已经恢复 caller flags，但若断在 `testl` 之后，算术 flags 已被 `testl` 更新。long-mode preparation 的 CR4/CR3/EFER/CR0 状态仍必须依据后续源码和实际采样判断。

## 8. 反汇编验收

实际构建可用时，AT&T 与 Intel 反汇编都应支持同一组事实：

- `startup_32` 附近存在 `cld`、`cli`；
- 存在 `lgdt`；
- 存在对 `DS/ES/FS/GS/SS` 的显式 reload；
- 存在建立 `boot_stack_end` 对应 `%esp` 的 32-bit 地址计算；
- 存在 `call verify_cpu`、`test %eax,%eax` 与失败分支；
- `verify_cpu` 中可找到 flags 保存/恢复与 CPUID probing 相关指令。

反汇编中的实际地址、relocation 结果和指令编码依赖构建产物，不写死在验收文档中。

## 9. 通过标准

A19 第三部分实验达到独立验收标准，需要同时证明：

1. `startup_32` 是 32-bit protected-mode entry sample，而不是本文负责实现的 real→protected transition；
2. `lgdt`、data-segment reload 与后续 `CS` far reload 是三个不同状态事件；
3. scratch stack 只服务入口早期位置计算，`verify_cpu` 调用已经使用 compressed boot stack；
4. `verify_cpu()` 的返回契约是 0 成功、1 失败，并检查 Linux 所需的一组 CPU feature；
5. probing 的 flags 临时变化在函数边界恢复，但 caller 随后的 `testl` 会再次更新 condition flags；
6. feature check 成功严格早于 CR4.PAE、CR3、EFER.LME、CR0.PG 和 far `lret` 的逐步建立；
7. 没有把未执行的 QEMU/GDB/Kbuild/objdump 预期值冒充实测结果。

## 10. 当前环境状态

本验收基线依据仓库中已完成的 Linux 5.10 source-path、正式教程和实验 README 交叉复核。当前维护环境没有提供可执行 Linux v5.10 checkout、compressed-kernel 构建产物或 QEMU early-boot GDB 会话，因此本文件只记录源码可确定的验收关系；动态寄存器、GDTR、控制寄存器和 MSR 数值保持待实测。
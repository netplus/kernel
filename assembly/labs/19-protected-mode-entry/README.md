# A19 实验：验证 `startup_32` 的 GDT、段、栈与 `verify_cpu()` 边界

本实验对应：

- `assembly/docs/19-protected-mode-entry-segments-and-cpu-check.md`
- `assembly/source-paths/19-protected-mode-entry-segments-cpu-check-linux-5.10.md`
- Linux kernel v5.10 `arch/x86/boot/compressed/head_64.S`
- Linux kernel v5.10 `arch/x86/kernel/verify_cpu.S`

目标不是复现完整 Linux boot protocol，而是把 A19 第三部分的几个汇编状态边界逐项变成可检查证据：`startup_32` 已经是 32-bit protected-mode 入口；`lgdt`、data-segment reload、boot-stack 切换和 `verify_cpu()` 是不同事件；CPU 检查成功后才进入 CR4/CR3/EFER/CR0 的 long-mode preparation。

## 1. 验证问题

完成实验后，应能够用源码和反汇编回答：

1. `startup_32` 为什么不能被描述成 real-mode 起点？
2. `lgdt` 更新了什么，为什么随后还要显式 reload `DS/ES/FS/GS/SS`？
3. `CS` 为什么没有在这一组 `mov` 中更新？
4. 入口 scratch `%esp` 与 `boot_stack_end` 分别服务什么阶段？
5. `verify_cpu()` 的成功/失败返回值是什么？
6. `verify_cpu()` 如何保存并恢复 caller EFLAGS，尤其不能让 CPUID probing 对 ID flag 的临时修改泄漏出去？
7. `verify_cpu()` 成功与 `CR4.PAE`、`CR3`、`EFER.LME`、`CR0.PG` 已经生效之间为什么不能画等号？

## 2. 环境

优先使用一份可构建的 upstream Linux v5.10 x86-64 checkout。建议工具：

```text
grep / sed
make
objdump
nm
readelf
可选：QEMU + GDB
```

如果没有可执行 checkout，本实验仍可做源码静态核验，但必须把未执行的构建、反汇编和动态寄存器值标为待实测。

### 2.1 自动验收入口

本目录已经提供两层自动检查和对应的正/负 fixture 自测试：

```text
verify_startup32_contract.py
verify_startup32_disassembly.py
test_verify_startup32_contract.py
test_verify_startup32_disassembly.py
```

统一入口由本目录 `Makefile` 提供：

```bash
# 先验证 checker 自身不会轻易接受错误 fixture
make test

# 对一份真实 Linux v5.10 checkout 做源码契约检查
make check-source KERNEL=/path/to/linux-5.10

# 对真实构建产物导出的 objdump -dr 文本做机器指令级检查
make check-disassembly DISASM=/path/to/startup32-and-verify-cpu.objdump
```

`check-source` 检查源码中的状态事件顺序和 `verify_cpu()` 两条返回路径；`check-disassembly` 检查真实机器指令中的 `cld/cli`、`lgdt`、segment reload、`verify_cpu` 调用/返回值测试、CR4 写入，以及 success/failure terminal path。两者都属于静态证据，不能替代第 6 节的运行时寄存器观察。

在运行 `check-disassembly` 前，应先从当前构建产物导出同时覆盖 `startup_32` 和 `verify_cpu` 的 GNU `objdump -dr` 文本。不要使用教程中的示意反汇编作为输入，也不要因为 checker 通过就宣称 GDTR hidden state、CR4/CR3/EFER 或当前 CPU execution mode 已经动态验证。

## 3. 源码静态核验

### 3.1 确认 `startup_32` 的编码上下文

在 `arch/x86/boot/compressed/head_64.S` 中定位 `.code32` 与 `startup_32`。记录：

```text
.code32 的位置
startup_32 的位置
入口最先出现的 cld / cli
```

验收重点：`.code32` 是 assembler encoding directive，不是运行时 mode-switch instruction。不要仅凭 `.code32` 反推出 CPU 是由这里从 real mode 切入 protected mode。

### 3.2 记录 GDT 装载与 data-segment reload 的顺序

定位并按实际源码顺序记录：

```text
计算/修正 compressed GDT runtime base
lgdt
mov $__BOOT_DS, ...
DS reload
ES reload
FS reload
GS reload
SS reload
```

硬验收条件：`lgdt` 与各 segment reload 必须作为两个阶段记录。`lgdt` 只改变 GDTR；现有 segment selector/hidden descriptor state 不会因为它自动全部重新装载。

同时确认这一阶段没有普通 `mov` 写 `%cs`。`CS` 的改变应与后续 long-mode transition 中的 far `lret` 联系起来。

### 3.3 找出 scratch stack 与 boot stack 的切换点

沿 `startup_32` 开头追踪 `%esp`：

1. 入口早期如何借用 boot parameters scratch 区；
2. `call`/`popl` 如何利用该临时栈求 runtime position；
3. runtime base 已知后，何处执行：

```asm
leal rva(boot_stack_end)(%ebp), %esp
```

验收重点：后续 `call verify_cpu` 的返回地址应落在 compressed kernel 自己的 boot stack，而不是继续依赖最早的 scratch stack。

### 3.4 核对 `verify_cpu()` 调用契约

在 `head_64.S` 中定位：

```asm
call verify_cpu
testl %eax, %eax
jnz .Lno_longmode
```

再到 `arch/x86/kernel/verify_cpu.S` 核对成功/失败出口。

应得到：

```text
EAX = 0 -> success
EAX = 1 -> failure
```

并确认检查至少涉及：

```text
CPUID availability
required basic feature mask
required extended feature mask
SSE requirement / compatibility handling
```

不要把函数缩写成“只检查 long-mode bit”。

### 3.5 核对 EFLAGS 保存/恢复

在 `verify_cpu()` 入口和出口定位 flags 操作，至少记录：

```asm
pushf
...
popf
```

然后定位 CPUID availability probing 对 EFLAGS.ID 的操作。

硬验收条件：必须区分：

```text
verify_cpu() 函数边界恢复 caller flags
```

与：

```text
返回后的 testl %eax,%eax 会再次更新 arithmetic condition flags
```

因此不能写成“verify_cpu 返回以后 EFLAGS 永远不再变化”。

## 4. 与 long-mode preparation 的时间边界

继续沿 `startup_32` 向后定位 CR4、CR3、EFER 和 CR0 的写入。建立下面的时间线，并在每个箭头旁写出源码证据：

```text
cld / cli
  ↓
建立 runtime base
  ↓
lgdt
  ↓
DS/ES/FS/GS/SS = __BOOT_DS
  ↓
ESP = boot_stack_end
  ↓
call verify_cpu
  ↓ success
CR4.PAE
  ↓
early page tables / CR3
  ↓
EFER.LME
  ↓
CR0.PE|PG
  ↓
far lret reload CS
  ↓
startup_64
```

关键判定：在 `verify_cpu()` 成功返回的那个时刻，不能据此声称 CR4.PAE、CR3、EFER.LME、CR0.PG 或 64-bit `CS` 已经建立。它只是允许程序继续执行后面的准备序列。

## 5. 反汇编验证

如果能够构建 Linux v5.10，构建 compressed kernel 后用实际产物确认源码与机器码对应关系。具体产物路径随构建流程而定，应先用 `find`/`nm` 确认，不要假定文件名。

建议至少检查：

```text
startup_32 附近的 cld / cli
lgdt
segment-register reload
boot_stack_end 对应的 ESP 建立
call verify_cpu / test / conditional branch
verify_cpu 中 pushf/popf 与 CPUID probing
```

同时输出 AT&T 与 Intel 两种反汇编，重点不是语法偏好，而是确认 operand width、控制流和实际生成指令。

完成手工检查后，再把同一份真实反汇编文本交给 `make check-disassembly`。自动 checker 的作用是防止后续源码/构建变化让关键顺序悄悄漂移；手工检查仍负责确认 operand width、重定位、符号归属和 checker 未覆盖的上下文。

## 6. 可选 QEMU/GDB 动态观察

只有在具备匹配 v5.10 compressed kernel、QEMU 和早期启动 GDB 环境时执行。不要在普通生产机器上尝试修改这些控制状态。

建议选择四个观察点：

```text
P0: startup_32 刚进入
P1: lgdt + data-segment reload 完成
P2: ESP 已切到 boot_stack_end、verify_cpu 即将调用
P3: verify_cpu 成功返回、CR4.PAE 尚未写入
```

每个点至少记录：

```text
EIP
EFLAGS（特别是 IF/DF；ID 仅在 probing 过程中观察）
ESP
CS/DS/ES/FS/GS/SS
GDTR（调试器支持时）
CR0 / CR3 / CR4
EFER（调试器支持 MSR 读取时）
```

预期关系：

- P0 已能执行 32-bit protected-mode code；
- P1 的 GDTR 已指向 compressed GDT，data selectors 已是 `__BOOT_DS`，但 `CS` 仍不是后续 `__KERNEL_CS` long-mode code selector；
- P2 的 `%esp` 属于 compressed boot stack；
- P3 的 CPU feature check 已成功，但 long-mode preparation 的控制寄存器状态仍应按后续源码逐项建立。

具体地址和寄存器数值必须来自当前构建，不得抄写教程中的示意值。

## 7. 结果记录模板

```text
Kernel: Linux v5.10
Config:
Build artifact:

Automated checks:
  make test:
  make check-source KERNEL=...:
  make check-disassembly DISASM=...:

startup_32:
  .code32 evidence:
  initial EFLAGS-relevant instructions:

GDT/segments:
  lgdt address:
  __BOOT_DS value:
  reload sequence:
  CS changed here? yes/no + evidence:

Stacks:
  scratch ESP evidence:
  boot_stack_end ESP evidence:

verify_cpu:
  success value:
  failure value:
  pushf/popf evidence:
  CPUID/required-mask/SSE evidence:

Long-mode boundary:
  first CR4.PAE write:
  CR3 write:
  EFER.LME write:
  CR0.PG write:
  far lret:

Dynamic QEMU/GDB:
  executed / not executed
  P0:
  P1:
  P2:
  P3:
```

## 8. 通过标准

本实验通过需要同时满足：

1. 用 v5.10 源码证明 `startup_32` 的 `.code32` 上下文，但不把它误写成 real-mode → protected-mode transition；
2. 明确 `lgdt` 与 `DS/ES/FS/GS/SS` reload 的先后和职责差异；
3. 明确 `CS` 留到后续 far control transfer 更新；
4. 区分 scratch stack 与 `boot_stack_end`，并确认 `verify_cpu` 使用后者；
5. 核对 `verify_cpu()` 的 0/1 返回契约和 flags 保存/恢复；
6. 核对 CPU feature check 成功发生在 CR4/CR3/EFER/CR0 long-mode preparation 之前；
7. `make test` 必须先通过；具备真实 v5.10 checkout/构建产物时，还必须分别运行 `check-source` 和 `check-disassembly`，并保存真实输出；
8. 若执行动态实验，只报告当前构建真实观测值；未执行时明确写明环境限制。

## 9. 本次维护环境状态

source-contract checker 已经通过 fixture 正/负测试，并已对 upstream Linux v5.10 真实源码文本完成核心契约匹配；objdump checker 已具备正/负 fixture 自测试和统一 Makefile 入口。当前维护环境仍没有可执行 Linux v5.10 checkout/QEMU 早期启动调试会话，因此本次未执行真实 Kbuild、真实构建产物上的 `check-disassembly` 或动态寄存器采样；这些项目保持为待实测，不能作为已验证数据引用。
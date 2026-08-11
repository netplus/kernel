# 第 9 课（第四部分）：DWARF CFI、CFA 与基本栈展开

A09 前三部分已经看到两种现实：有些函数保留传统 `%rbp` frame，有些优化后的函数省略 frame pointer，直接围绕 `%rsp` 组织自己的栈状态。于是出现一个关键问题：**当 `%rbp` 不再形成稳定链时，调试器或 unwinder 怎样知道 caller 的栈位置、返回地址以及被 callee 保存的寄存器在哪里？**

本节先建立最小的 DWARF Call Frame Information（CFI）模型。重点不是完整 DWARF 调试格式，而是理解三个对象：

```text
CFA                  Canonical Frame Address
CFI rule             某个 PC 范围内怎样计算 CFA、怎样恢复寄存器
FDE/CIE              这些规则在 .eh_frame 中的编码载体
```

GNU assembler 的 `.cfi_*` 指令用于向汇编器描述这些恢复规则；它们本身不是 CPU 指令，不会在运行时修改寄存器或内存。

## 1. 先区分机器执行与展开元数据

假设机器执行：

```asm
pushq %rbx
subq  $16, %rsp
```

CPU 只执行两件事：

```text
push rbx  → RSP -= 8，并把 RBX 写入 [RSP]
sub 16    → RSP -= 16
```

如果旁边写着：

```asm
.cfi_def_cfa_offset 16
.cfi_offset %rbx, -16
.cfi_def_cfa_offset 32
```

这些 `.cfi_*` 行不会产生对应的运行时算术。它们告诉汇编器：在相应机器指令执行之后，展开器应当怎样解释当前 frame。

因此必须分开理解：

```text
x86-64 指令          改变真实机器状态
DWARF CFI            描述怎样从某个机器状态恢复 caller 状态
```

## 2. CFA 是什么

Canonical Frame Address 可以先理解为：**为当前调用 frame 选择的一个规范基准地址，展开规则围绕它描述 caller 状态。**

GNU assembler 对：

```asm
.cfi_def_cfa register, offset
```

的定义是：

```text
CFA = register + offset
```

在 x86-64 普通函数刚进入时，`call` 已经把 8 字节返回地址压到栈顶，因此常见初始规则是：

```text
CFA = RSP + 8
return RIP = [CFA - 8]
```

这里的 CFA 不等于“当前 `%rsp`”。它更像是一个让 caller frame 可以稳定描述的逻辑基准。

## 3. 为什么 `%rsp` 变化时 CFI 也必须变化

看第二个实验函数入口：

```asm
cfi_rsp_sum:
    pushq %rbx
    subq  $16, %rsp
```

设刚进入时：

```text
RSP = S
CFA = S + 8
```

执行：

```asm
pushq %rbx
```

以后：

```text
RSP = S - 8
```

但我们仍希望 CFA 指向原来的 `S + 8`，因此新的关系必须是：

```text
CFA = RSP + 16
```

所以写：

```asm
.cfi_def_cfa_offset 16
```

同时旧 `%rbx` 被保存到：

```text
S - 8 = CFA - 16
```

所以：

```asm
.cfi_offset %rbx, -16
```

再执行：

```asm
subq $16, %rsp
```

真实 `%rsp` 变成 `S - 24`，CFA 仍是 `S + 8`，于是：

```text
CFA = RSP + 32
```

对应：

```asm
.cfi_def_cfa_offset 32
```

这说明 CFI 的核心工作并不是复制栈布局，而是随着机器状态变化持续维护一套“如何找到 caller 状态”的规则。

## 4. `%rbp` frame 为什么可以让 CFA 基准寄存器改变

第一个实验函数使用经典序言：

```asm
pushq %rbp
movq  %rsp, %rbp
subq  $16, %rsp
```

对应 CFI：

```asm
.cfi_def_cfa_offset 16
.cfi_offset %rbp, -16
.cfi_def_cfa_register %rbp
```

执行 `push %rbp` 后：

```text
CFA = RSP + 16
saved caller RBP = CFA - 16
```

执行：

```asm
movq %rsp, %rbp
```

以后 `%rbp` 固定在 frame 顶部，因此可以把 CFA 基准寄存器从 `%rsp` 改为 `%rbp`：

```text
CFA = RBP + 16
```

随后即使：

```asm
subq $16, %rsp
```

改变 `%rsp`，CFA 规则仍不需要再变，因为 `%rbp` 没动。

这正是 frame pointer 作为稳定 frame base 的直观价值；但 CFI 也说明，**稳定的 `%rbp` 链并不是展开的唯一方式。**

## 5. `.cfi_offset` 描述的是“caller 的旧值保存在哪里”

GNU assembler 的：

```asm
.cfi_offset register, offset
```

表示该寄存器进入当前函数之前的值，保存在：

```text
CFA + offset
```

例如：

```asm
.cfi_offset %rbx, -16
```

含义不是“当前 RBX = CFA - 16”，而是：

```text
caller 的 RBX 值保存在内存 [CFA - 16]
```

展开器如果要恢复 caller 的寄存器状态，应从那个位置取值。

这与 A09 第二部分的普通 spill 也不同。CFI 关心的是**跨函数边界需要恢复的 caller 状态**；一般临时 spill 并不天然需要写进 unwind rule。

## 6. 返回地址为什么通常表现为 `CFA - 8`

在普通 x86-64 near `call` 中，返回地址由 CPU 压入栈。

函数刚进入时：

```text
RSP       → return address
CFA       = RSP + 8
```

因此：

```text
return RIP = [CFA - 8]
```

本实验生成的 `.eh_frame` CIE 中，`readelf --debug-dump=frames` 可以观察到：

```text
DW_CFA_def_cfa: r7 (rsp) ofs 8
DW_CFA_offset: r16 (rip) at cfa-8
```

这里 `r7` 是 DWARF x86-64 寄存器编号中的 `%rsp`，`r16` 是 `%rip`。

这是 unwind 元数据对普通函数入口状态的描述，不是额外执行的一次内存读写。

## 7. CIE 与 FDE 的最小工作模型

本节只需要建立如下层次：

```text
CIE (Common Information Entry)
  保存一组可共享的基础规则，例如初始 CFA 与返回地址列

FDE (Frame Description Entry)
  覆盖某个函数/PC 区间
  描述在该区间内规则怎样随指令位置变化
```

对 `cfi_rsp_sum`，实验实际得到的 FDE 关键变化是：

```text
函数入口：                    CFA = RSP + 8
push %rbx 后：                CFA = RSP + 16
                               caller RBX 在 CFA - 16
sub $16,%rsp 后：             CFA = RSP + 32
add $16,%rsp 后：             CFA = RSP + 16
pop %rbx 后：                 CFA = RSP + 8
```

这正好与机器指令逐步改变 `%rsp` 的过程对应。

## 8. 没有 `%rbp` 链也能描述 frame

`cfi_rsp_sum` 完全没有：

```asm
push %rbp
mov  %rsp,%rbp
```

但它仍有完整的 FDE：

```text
DW_CFA_def_cfa_offset: 16
DW_CFA_offset: r3 (rbx) at cfa-16
DW_CFA_def_cfa_offset: 32
...
DW_CFA_def_cfa_offset: 16
DW_CFA_def_cfa_offset: 8
```

因此不能把：

```text
没有 frame pointer
```

错误推导为：

```text
没有 frame / 无法 unwind
```

更准确的说法是：省略 `%rbp` 后，不能再依赖传统 frame-pointer chain；若存在正确的 CFI，unwinder 仍可依据 CFA 与寄存器恢复规则工作。

## 9. `.cfi_startproc` / `.cfi_endproc` 的作用

GNU assembler 用：

```asm
.cfi_startproc
...
.cfi_endproc
```

界定一个需要生成 frame unwind 信息的函数区域。

在本实验中，这些指令最终使相关规则出现在 ELF 的：

```text
.eh_frame
.eh_frame_hdr
```

中。它们不是 ELF `.debug_info` 中的普通源码调试变量信息，职责不同。

本节使用：

```bash
readelf --debug-dump=frames cfi-demo
```

直接观察 frame 信息。

## 10. 为什么 `.eh_frame` 不等于 `%rbp` 链

传统 `%rbp` 链是一种真实的运行时内存结构：

```text
[RBP]   = saved previous RBP
[RBP+8] = return address
```

而 `.eh_frame` 是 ELF 中的元数据，它描述怎样解释不同 PC 下的 frame 状态。

两者可以配合，但没有一一绑定关系：

```text
有 RBP 链 + 有 CFI       可以同时存在
无 RBP 链 + 有 CFI       很常见
有 RBP 链 + 缺少 CFI     仍可能按 frame pointer 规则人工回溯
无 RBP 链 + 缺少可用 CFI 展开会困难得多
```

后续进入内核栈展开时，还必须再区分 Linux 内核自己的 unwinder 机制；不能把用户态 DWARF CFI 模型直接等同为 Linux 5.10 内核的唯一展开实现。

## 11. RFLAGS 与控制流

`.cfi_*` 不执行 CPU 算术，不修改 `RFLAGS`，也不产生运行时控制流。

本实验中的 `push`、`mov`、`sub`、`add`、`pop`、`leave`、`ret` 仍按 x86-64 ISA 改变机器状态；CFI 只是与相应 PC 范围关联的恢复描述。

所以分析时始终采用两条并行线：

```text
机器线：RSP/RBP/RBX/内存/控制流怎样变化
元数据线：当前 PC 对应的 CFA 与 register recovery rule 是什么
```

## 12. 本节实验

实验入口：[`../labs/09-dwarf-cfi/`](../labs/09-dwarf-cfi/)

实际验证环境：

```text
GCC 14.2.0
GNU binutils 2.44
```

运行结果：

```text
cfi_rbp_sum=42
cfi_rsp_sum=43
exit 0
```

同时实际检查：

```text
readelf -S                     .eh_frame/.eh_frame_hdr 存在
readelf --debug-dump=frames    已检查 CIE/FDE 与 CFA 变化
objdump AT&T                   已检查机器指令
objdump -Mintel                已检查机器指令
nm                             已检查函数符号
GDB                            当前环境未安装，未执行动态 backtrace
```

关键 FDE 结果与源码中的 `.cfi_*` 规则一致。

## 13. 本节完成后应能回答

1. CFI 指令与真实 x86-64 指令有什么根本区别？
2. CFA 为什么不能简单等同于当前 `%rsp`？
3. `push %rbx` 后为什么要把 CFA offset 从 8 改为 16？
4. `.cfi_offset %rbx,-16` 实际描述的是谁的 `%rbx`、保存在哪里？
5. 为什么 `mov %rsp,%rbp` 后可以把 CFA register 改成 `%rbp`？
6. CIE 与 FDE 分别承担什么基本职责？
7. 为什么没有 `%rbp` frame pointer 仍然可以存在可用 unwind 信息？
8. `.eh_frame` 与传统 frame pointer chain 为什么不是同一个东西？

下一最小单元继续 A09：在最小多层调用链上实际观察 backtrace/unwind，并进一步说明 CFI 缺失或错误时的边界。
# 第 8 课（第三部分）：寄存器耗尽后的栈上传参

A08 前两部分已经说明了 INTEGER 类参数优先使用 `%rdi/%rsi/%rdx/%rcx/%r8/%r9`，以及 caller-saved/callee-saved 的保存责任。本节继续回答一个自然问题：**当可用的 INTEGER 参数寄存器耗尽后，后续参数在哪里？**

本节只使用 8 个 64 位 `long` 参数建立最小模型，重点观察第 7、第 8 个参数与函数入口 `%rsp` 的关系。更复杂的 SSE、聚合类型和参数分类算法放到 A08 后续部分。

## 1. 问题背景

考虑函数：

```c
long abi_probe8(long a1, long a2, long a3, long a4,
                long a5, long a6, long a7, long a8);
```

前六个 INTEGER 参数已经占满通用参数寄存器：

```text
a1 → RDI
a2 → RSI
a3 → RDX
a4 → RCX
a5 → R8
a6 → R9
```

因此 `a7` 和 `a8` 不能继续使用这组寄存器，必须进入 input argument area，也就是由 caller 在栈上准备的参数区域。

## 2. 函数入口时的最小栈模型

对本节这个只有两个额外 64 位 INTEGER 参数的例子，在 `abi_probe8` **刚进入、尚未修改 `%rsp`** 时，可以建立下面的模型：

```text
高地址

RSP + 16   第 8 个参数 a8
RSP +  8   第 7 个参数 a7
RSP +  0   返回地址

低地址
```

所以手写汇编 callee 可以直接读取：

```asm
movq 8(%rsp),  %r10    # a7
movq 16(%rsp), %r11    # a8
```

关键是“函数入口、尚未修改 `%rsp`”这个条件。一旦函数执行了 `push` 或 `subq $N,%rsp`，参数相对当前 `%rsp` 的偏移也会变化。

## 3. 为什么第 7 个参数在返回地址之后

A07 已经学习：`call` 会把下一条指令地址压到栈顶，然后跳到 callee。

caller 在执行 `call` 之前已经准备好栈上传递的参数。`call` 再额外压入 8 字节返回地址，因此控制刚进入 callee 时：

```text
[RSP]      = return address
[RSP + 8]  = first stack-passed argument
[RSP + 16] = next stack-passed argument
```

这里的“first stack-passed argument”对本实验就是逻辑上的第 7 个参数。

## 4. 栈上的参数顺序不能简单理解成“从右到左 push”

在本实验的 GCC 反汇编中，确实可以看到类似：

```asm
push   $88
push   $77
call   abi_probe8
```

这会自然形成：

```text
callee 入口 [RSP+8]  = 77
callee 入口 [RSP+16] = 88
```

但是 **ABI 规定的是函数边界上的参数布局与对齐，不是强制编译器必须逐个使用 `push` 指令**。编译器也可以先一次性调整 `%rsp`，再用 `mov` 写入参数槽。

因此阅读反汇编时，应区分：

```text
ABI 语义：callee 入口看到什么布局
具体代码生成：caller 用 push、sub+mov，还是其他等价序列构造这个布局
```

## 5. 16 字节对齐与返回地址的关系

System V AMD64 psABI 规定普通调用边界的 input argument area 需要满足对齐要求。对没有更高对齐要求的普通情况，可以记住：

```text
call 执行前：RSP mod 16 = 0
callee 刚进入： (RSP + 8) mod 16 = 0
```

原因是 `call` 本身压入 8 字节返回地址。

本实验在汇编 callee 的第一条路径中记录入口 `%rsp`，并检查：

```c
(seen_entry_rsp + 8) % 16 == 0
```

这把“第 7/8 个参数的位置”和“调用边界对齐”放在同一个实际栈布局里验证。

需要注意，psABI 对某些需要更高栈对齐的参数（例如特定向量类型在栈上传递）有更高边界要求。本节只讨论普通 64 位整数场景。

## 6. 实验：C caller 直接调用手写汇编 callee

实验调用：

```c
abi_probe8(11, 22, 33, 44, 55, 66, 77, 88);
```

汇编函数入口保存：

```asm
movq %rdi, seen_regs+0(%rip)
movq %rsi, seen_regs+8(%rip)
movq %rdx, seen_regs+16(%rip)
movq %rcx, seen_regs+24(%rip)
movq %r8,  seen_regs+32(%rip)
movq %r9,  seen_regs+40(%rip)

movq 8(%rsp), %r10
movq %r10, seen_stack+0(%rip)
movq 16(%rsp), %r11
movq %r11, seen_stack+8(%rip)
```

于是程序同时验证：

```text
六个寄存器参数 = 11 22 33 44 55 66
第 7 个参数      = 77，位于入口 RSP+8
第 8 个参数      = 88，位于入口 RSP+16
```

最后 callee 将八个参数相加并通过 `%rax` 返回：

```text
11+22+33+44+55+66+77+88 = 396
```

## 7. `-O0` 下观察 caller

本次 GCC 14.2、`-O0 -fno-pie` 实验中，`call_probe` 的关键部分为：

```asm
push   $0x58        # 88
push   $0x4d        # 77
mov    $0x42,%r9d   # 66
mov    $0x37,%r8d   # 55
mov    $0x2c,%ecx   # 44
mov    $0x21,%edx   # 33
mov    $0x16,%esi   # 22
mov    $0xb,%edi    # 11
call   abi_probe8
add    $0x10,%rsp
```

`call` 返回后 caller 用 `add $0x10,%rsp` 回收两个 8 字节栈参数槽。

这也说明：**栈参数区域由 caller 建立和回收**；callee 只按 ABI 读取它自己的输入参数。

## 8. `-O2` 下布局不变，但构造方式可以变化

同一实验在 `-O2` 下，GCC 仍然保持函数边界语义：

```text
RDI..R9  = 前六个 INTEGER 参数
[RSP+8]  = 77
[RSP+16] = 88
```

实际反汇编中，编译器为满足调用点对齐先调整 `%rsp`，再压入 88 和 77，调用完成后统一回收对应栈空间。

因此优化级别可以改变：

```text
caller 的 prologue
栈空间调整方式
指令排序
清理栈空间的具体序列
```

但不能改变 ABI 边界上 callee 看到的参数位置和对齐约束。

## 9. 为什么不能把 `8(%rsp)` 写死到普通 C 函数的任意位置

`8(%rsp)` 只在特定时刻具有“第一个栈参数”的意义：

```text
函数刚进入
且函数尚未改变 RSP
```

例如 callee 如果执行：

```asm
pushq %rbp
subq $32, %rsp
```

当前 `%rsp` 已向低地址移动 40 字节，原来的 `a7` 就不再位于当前 `8(%rsp)`。

这也是为什么编译器会根据最终 frame layout 生成正确偏移，而手写汇编必须自己维护完整的 `%rsp` 变化模型。

## 10. 与 frame pointer 的关系

如果函数使用传统 frame pointer：

```asm
pushq %rbp
movq %rsp, %rbp
```

在这个 prologue 完成后：

```text
0(%rbp)  = previous RBP
8(%rbp)  = return address
16(%rbp) = first stack-passed argument
24(%rbp) = second stack-passed argument
```

因此对本实验：

```text
16(%rbp) = a7
24(%rbp) = a8
```

这是 A09 学习函数栈帧时会继续使用的布局。

## 11. 一个重要边界：并不是“第 7 个源语言参数必然上栈”

本实验使用八个纯 INTEGER 类 `long`，所以逻辑很整齐。

真实 psABI 会先对参数分类，并分别消耗通用寄存器或 SSE 寄存器资源。聚合类型还可能被拆成多个 eightbyte，或者整体归为 MEMORY。

因此准确表述是：

> 当某个 INTEGER 类参数无法再分配到 `%rdi/%rsi/%rdx/%rcx/%r8/%r9` 中的可用参数寄存器时，它按 ABI 的参数布局规则进入栈上的 input argument area。

而不是：

> 所有函数的第 7 个参数一定在栈上。

## 12. 与 Linux kernel 5.10 的关系

本节仍然讨论 **System V AMD64 用户态普通函数 ABI**。

Linux x86-64 系统调用有独立的 syscall ABI；内核内部 C 函数虽然通常由编译器按照该平台内核采用的函数调用约定生成代码，但系统调用入口保存的 `pt_regs` 布局、异常入口的硬件压栈，以及上下文切换的现场保存都不是本节这个“普通用户态函数 input argument area”模型。

后续 A13-A17 会分别学习这些边界，避免把不同层次的栈布局混在一起。

## 13. 实验与验证

配套实验：

[`../labs/08-stack-arguments/`](../labs/08-stack-arguments/)

本次实际验证环境：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
```

已验证：

```text
-O0 构建与运行             通过
-O2 构建与运行             通过
RDI..R9                   11 22 33 44 55 66
入口 [RSP+8]              77
入口 [RSP+16]             88
(RSP+8) mod 16            0
RAX 返回值                396
objdump AT&T              已检查
objdump Intel             已检查
nm                        已检查
GDB                       当前环境未安装，未执行
```

规范依据是 x86-64 psABI 的参数传递和 stack frame 规则：INTEGER 类参数优先使用六个通用参数寄存器；不能放入寄存器的参数进入栈上的参数区域；普通调用入口中，返回地址压栈后 `%rsp` 指向返回地址，并满足相应对齐关系。

## 14. 本节完成后应能回答

1. 六个 INTEGER 参数寄存器用完后，额外整数参数在哪里？
2. 为什么本实验的第 7/8 个参数位于入口 `%rsp+8/%rsp+16`？
3. 为什么 `%rsp` 一旦在 prologue 中变化，就不能继续使用相同偏移？
4. caller 为什么要负责建立和回收栈参数区域？
5. `call` 前和 callee 入口的 16 字节对齐关系是什么？
6. 为什么不能把“第 7 个源语言参数一定在栈上”当成通用规则？
7. frame pointer 建立后，第一个和第二个栈参数为什么通常变为 `16(%rbp)` 与 `24(%rbp)`？

下一部分继续学习普通函数调用边界的 **16 字节栈对齐**，重点分析为什么 caller 在 `call` 前需要对齐，以及 callee 入口为什么通常表现为 `%rsp mod 16 = 8`。
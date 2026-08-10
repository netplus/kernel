# 第 8 课（第七部分）：混合 INTEGER/SSE 聚合

上一部分已经验证纯整数聚合的 `INTEGER, INTEGER` 和较大聚合的 `MEMORY` 情况。本节继续回答一个容易被“结构体就是一块内存”这种直觉掩盖的问题：**同一个结构体的不同 eightbyte 可以属于不同 ABI 类，因此一次按值传参或返回可以同时跨越 XMM 寄存器和通用寄存器。**

## 1. 问题背景

考虑：

```c
struct mixed {
    double d;
    uint64_t n;
};
```

在本实验的 x86-64 SysV AMD64 环境中，`double` 位于前 8 字节，`uint64_t` 位于后 8 字节，结构体大小为 16 字节。ABI 不是先给整个结构体选一种寄存器，而是先按 eightbyte 分类：

```text
bytes 0..7   double    -> SSE
bytes 8..15  uint64_t  -> INTEGER
```

最终分类是 `(SSE, INTEGER)`。

## 2. 参数传递：两个寄存器序列彼此独立

SysV AMD64 为 INTEGER 类和 SSE 类维护不同的参数寄存器序列。对本节只有一个 `struct mixed` 参数的函数：

```c
struct mixed mixed_bump(struct mixed x);
```

进入 callee 时：

```text
%xmm0 = x.d
%rdi  = x.n
```

这里不能把它理解成“第一个 eightbyte 占第一个参数寄存器，所以第二个 eightbyte 必须占第二个参数寄存器”。SSE eightbyte 从 SSE 参数寄存器序列取位置，INTEGER eightbyte 从通用参数寄存器序列取位置。

这也是为什么混合结构体能够同时出现在 `%xmm0` 和 `%rdi` 中。

## 3. 返回值：分类结果再次决定返回寄存器

返回同一个 `(SSE, INTEGER)` 聚合时，返回寄存器同样按类别选择：

```text
%xmm0 = result.d
%rax  = result.n
```

因此本实验的手写汇编 callee 可以直接执行：

```asm
addsd .LCONE(%rip), %xmm0
leaq 2(%rdi), %rax
ret
```

`addsd` 把浮点字段加 1.0；`lea` 在不访问内存的情况下计算整数字段加 2。函数没有建立栈帧，也没有把结构体整体复制到某个连续的 callee 栈槽。

## 4. 设计含义：ABI 描述的是函数边界状态

CPU 并不知道 `struct mixed`。C 类型布局由编译器按照目标 ABI 实现，而函数边界最终只表现为寄存器和内存状态。

因此需要区分：

```text
C 语言层：一个 struct mixed 对象
ABI 层：   两个 eightbyte，分类为 SSE + INTEGER
机器层：   XMM0 和 RDI 中的位模式
```

某次编译器是否为了调试、spill 或优化而把字段临时写入栈，不改变 ABI 对跨函数边界的要求。

## 5. 实验验证

实验入口：[`../labs/08-mixed-aggregate/`](../labs/08-mixed-aggregate/)

实验采用 **C caller + 手写 AT&T 汇编 callee**。输入为：

```text
x.d = 1.5
x.n = 40
```

callee 只从 `%xmm0` 和 `%rdi` 取值，并通过 `%xmm0`、`%rax` 返回，预期输出：

```text
mixed=2.5,42
```

本次实际验证环境：GCC 14.2、GNU binutils 2.44。

```text
-O0：构建通过，运行输出 mixed=2.5,42，exit 0
-O2：构建通过，运行输出 mixed=2.5,42，exit 0
objdump AT&T：已确认 addsd ...,%xmm0 与 lea ...,%rax
objdump Intel：已确认 addsd xmm0,... 与 lea rax,[rdi+0x2]
nm：已确认 mixed_bump 为全局文本符号
readelf：已确认 mixed_bump 为 GLOBAL FUNC
GDB：当前环境未安装，未执行
```

## 6. 边界与常见误区

- `(SSE, INTEGER)` 是这个具体自然对齐布局的分类结果，不能推广为所有含 `double` 的结构体。
- INTEGER 与 SSE 参数寄存器序列分别分配；不要把结构体字段机械映射为“第 1、第 2 个参数寄存器”。
- XMM 寄存器中保存的是浮点字段对应的机器位模式；“XMM 寄存器保存 C double”是 ABI 层的解释，不是 CPU 的类型系统。
- 本节只验证最基础的 SSE + INTEGER 混合聚合，不展开 `SSEUP`、向量、X87、未对齐字段和可变参数规则。
- 这里讨论的是用户态 System V AMD64 ABI，不是 Linux 内核内部函数调用的完整约束，也不是 x86-64 ISA 自身规定的结构体规则。

## 7. 本节完成后应能回答

1. 为什么一个 16 字节结构体可以同时使用 `%xmm0` 和 `%rdi` 传参？
2. INTEGER 和 SSE 参数寄存器序列为什么不能混成一个统一编号？
3. `(SSE, INTEGER)` 结构体返回时为什么使用 `%xmm0` 和 `%rax`？
4. 为什么不能从某次编译器的临时栈槽反推 ABI 必须在栈上传递结构体？

完成这一单元后，A08 大纲列出的整数参数、返回值、保存责任、栈上传参、16 字节对齐、Red Zone，以及基础的小/大/混合结构体规则都已有正文与实验。下一步应先对 A08 做整章一致性复核，再决定是否标记整章完成并进入 A09。

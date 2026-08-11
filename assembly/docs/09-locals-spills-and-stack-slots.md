# 第 9 课（第二部分）：局部变量、spill/reload 与实际栈槽

A09 第一部分建立了经典 `%rbp` 栈帧模型。本节继续回答一个容易被源码表象误导的问题：**C 源码里的局部变量，什么时候真的存在于栈上？什么时候只存在于寄存器里？编译器又为什么会主动把某些寄存器值暂时写回栈中？**

理解这个问题，是后续阅读优化汇编、frame pointer omission 和栈展开信息的基础。

## 1. 先区分三种“栈上的东西”

函数栈帧中出现一个内存槽，不代表它一定对应源码中的某个局部变量。至少要区分：

```text
源码对象的内存存储
编译器 spill slot
outgoing stack arguments
```

三者形成原因不同。

### 1.1 源码对象的内存存储

某个局部对象可能因为以下原因必须具有可寻址的内存位置：

- 代码取得了它的地址；
- 对象是数组、结构体等需要按内存布局访问的实体；
- `volatile` 语义要求实际内存访问；
- 优化级别较低，编译器选择直接把中间值落栈。

### 1.2 spill slot

寄存器数量有限。若某个值当前仍然“活跃”，但编译器需要把寄存器让给别的值或需要跨越会破坏该寄存器的操作，它可以：

```text
register value
    ↓ store
stack spill slot
    ↓ later load
register value
```

前一次 store 常称为 spill，后一次重新装入称为 reload。

spill slot 是寄存器分配的产物，不一定对应任何源代码变量。

### 1.3 outgoing stack arguments

A08 已经说明：SysV AMD64 中 INTEGER 参数寄存器用尽后，后续参数通过栈传递。

caller 在 `call` 前为 callee 准备的这些参数也是栈内容，但它们属于调用接口，而不是当前函数为了保存寄存器值产生的 spill slot。

因此阅读反汇编时不能看到 `push` 或 `%rsp/%rbp` 偏移就统一称为“局部变量”。

## 2. ISA、ABI 与编译器职责要分开

### 2.1 x86-64 ISA

CPU 只看到寄存器读写和内存 load/store。它不知道某次：

```asm
movq %r8, -64(%rbp)
```

究竟是局部变量赋值、spill、保存参数还是别的临时存储。

### 2.2 SysV AMD64 ABI

ABI 规定的是函数边界，例如：

- 哪些寄存器传 INTEGER 参数；
- 哪些寄存器 caller-saved；
- 哪些寄存器 callee-saved；
- 参数寄存器耗尽后怎样走栈。

ABI 并不规定编译器必须把某个 C 局部变量放在 `-8(%rbp)`，也不规定某一次 spill 必须使用哪个偏移。

### 2.3 编译器寄存器分配

真正决定：

```text
某个值放哪个寄存器
某个值何时 spill
spill 到哪个栈槽
不同生命周期是否复用一个槽
```

的是编译器优化与寄存器分配过程。

所以具体偏移和寄存器选择只能描述为“当前编译结果”，不能写成 ABI 固定规则。

## 3. 为什么 `-O0` 常让源码变量看起来都在栈上

本节实验中的函数：

```c
long local_expr(long a, long b)
{
    long x = a + 3;
    long y = b + 5;
    long z = x * y;
    return z + x;
}
```

在本次 GCC 14.2.0、`-O0` 构建中，反汇编出现：

```asm
push   %rbp
mov    %rsp,%rbp
mov    %rdi,-0x28(%rbp)
mov    %rsi,-0x30(%rbp)
...
mov    %rax,-0x8(%rbp)
mov    %rax,-0x10(%rbp)
mov    %rax,-0x18(%rbp)
```

这里参数和若干中间值都被物化到栈上。

这种代码非常适合学习栈帧，但不能反推出“C 语言局部变量天生属于栈”。这是当前低优化代码生成策略。

## 4. 为什么 `-Og/-O2` 可以完全没有这些局部栈槽

同一个 `local_expr()` 在当前 `-Og` 构建中简化为：

```asm
lea    0x3(%rdi),%rax
add    $0x5,%rsi
imul   %rax,%rsi
add    %rsi,%rax
ret
```

`-O2` 也完全在寄存器中完成计算。

源码仍然写着 `x/y/z`，但机器代码不需要为它们分别分配内存地址。

原因是这些值：

- 生命周期短；
- 没有取地址；
- 没有 `volatile` 语义；
- 可以直接在寄存器数据流中传播。

于是源码变量可以只存在于编译器的中间表示和调试信息里，最终并不对应固定栈槽。

## 5. spill 的真正原因是“活跃值超过当前可用寄存器能力”

把一个值写到栈上只有在它随后仍然需要使用时才有保存意义。

考虑：

```text
value currently live in caller-saved register
        ↓
next operation may destroy that register
        ↓
value must still be used later
```

编译器有几种选择：

1. 把值移动到空闲的 callee-saved 寄存器；
2. 重新计算该值，如果重算更便宜；
3. 把值 spill 到栈上，稍后 reload；
4. 调整其他值的寄存器分配。

所以 spill 不是固定函数序言的一部分，而是活跃区间、寄存器压力和代价模型共同决定的结果。

## 6. 实验怎样构造一个可观察的 spill/reload

`spill_wrapper()` 接收 12 个整数参数：

```c
long spill_wrapper(long a, long b, long c, long d, long e, long f,
                   long g, long h, long i, long j, long k, long l)
{
    long marker = opaque(a);
    return marker + consume12(a, b, c, d, e, f, g, h, i, j, k, l);
}
```

设计重点是：

```text
第一次 call opaque()
        ↓
原来的 a..l 仍然要在第二次 call consume12() 中使用
```

因此一批参数必须跨越第一次 `call` 保持活跃。

按照 A08 的规则，`%rdi/%rsi/%rdx/%rcx/%r8/%r9` 属于 caller-saved。`opaque()` 返回后，caller 不能假定这些寄存器仍保存原参数。

编译器必须提前保存仍有后续用途的值。

## 7. 当前 GCC 实际如何保存这些值

实验对 `spill_wrapper()` 使用：

```text
-O2 -fno-omit-frame-pointer
```

当前 GCC 14.2.0 选择把部分参数移动到：

```text
RBX
R12
R13
R14
R15
```

这些是 callee-saved 寄存器；同时把原 `%r8/%r9` 参数保存到：

```asm
mov    %r8,-0x40(%rbp)
mov    %r9,-0x38(%rbp)
call   opaque
```

随后准备 `consume12()` 时重新装入：

```asm
mov    -0x38(%rbp),%r9
...
mov    -0x40(%rbp),%r8
```

从数据生命周期看：

```text
r8/r9 中的活跃参数
       ↓ spill
当前栈帧中的临时槽
       ↓ opaque() 执行
       ↓ reload
r8/r9，供下一次调用使用
```

这就是本实验要观察的实际 spill/reload。

## 8. 为什么不能记住 `-0x40(%rbp)` 这个偏移

这个偏移只是当前环境下的编译结果。

换成：

- 不同 GCC 版本；
- Clang；
- 不同优化级别；
- 允许省略 frame pointer；
- 修改函数体；
- 改变寄存器活跃范围；

都可能让编译器重新分配寄存器和栈槽。

应该记住的是机制：

```text
值必须继续存活
+ 当前寄存器不能可靠保留它
→ 编译器需要重新安置该值
→ 可能选择 callee-saved register，也可能 spill 到栈
```

## 9. spill slot 与栈上传参怎样区分

实验的 `consume12()` 有 12 个 INTEGER 参数。

前六个参数使用：

```text
RDI RSI RDX RCX R8 R9
```

其余参数需要放在栈上传递。因此在第二次 `call` 前还能看到多条 `push`。

这些 `push` 的目的，是构造 **callee 的输入参数区**。

而：

```asm
mov %r8,-0x40(%rbp)
mov %r9,-0x38(%rbp)
```

的目的是保存 **当前函数仍然活跃的值**。

两者都写栈，但语义完全不同。

## 10. 与 frame pointer omission 的关系

本实验为了让偏移容易观察，显式加入：

```text
-fno-omit-frame-pointer
```

这不是 spill 机制的前提。

如果允许省略 frame pointer，编译器仍然可以 spill，只是可能：

- 使用 `%rsp` 相对地址；
- 多获得一个可用于分配的 `%rbp`；
- 因可用寄存器增加而减少某些 spill；
- 产生完全不同的 frame layout。

A09 后续会专门比较保留和省略 frame pointer 的代码。

## 11. 与栈展开的关系

栈展开器关心的是怎样从当前机器状态恢复 caller 的状态。

spill slot 只是当前 frame 中保存临时值的一部分，不等于 frame 的结构边界。真实栈帧还可能同时包含：

```text
saved callee-saved registers
local objects
spill slots
alignment padding
outgoing stack arguments
return address
```

因此不能根据“看到几个负偏移”就推断调用栈结构。后续 DWARF CFI 会提供更明确的恢复规则。

## 12. 本节实验

实验入口：[`../labs/09-locals-and-spills/`](../labs/09-locals-and-spills/)

本次实际验证：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
GNU objdump 2.44

locals -O0     build/run 通过，结果 170
locals -Og     build/run 通过，结果 170
locals -O2     build/run 通过，结果 170
spill  -O2     build/run 通过，结果 178
AT&T objdump   已检查
Intel objdump  已检查
GDB            当前环境未安装，未执行
```

## 13. 本节完成后应能回答

1. 为什么 C 局部变量不一定对应栈槽？
2. spill 与 reload 分别是什么？
3. caller-saved 寄存器为什么容易形成跨调用保存压力？
4. callee-saved 寄存器和 spill slot 都可以怎样帮助值跨 `call` 存活？
5. 为什么 outgoing stack arguments 不能和 spill slot 混为一谈？
6. 为什么具体栈偏移不能当作 ABI 规则？
7. `-fno-omit-frame-pointer` 为什么会影响寄存器分配和栈布局？

下一最小单元继续 A09，进入 leaf function 与 frame pointer omission，比较没有传统 `%rbp` frame 的函数怎样组织局部状态。

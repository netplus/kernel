# 第 10 课（第一部分）：内联与函数边界消失

A09 已经从栈帧、局部变量、frame pointer omission 和 CFI 建立了“一个真实函数调用在机器层面如何存在”的模型。A10 开始学习优化后的汇编。第一个需要修正的直觉是：**C 源码中的函数边界，不一定会保留到最终机器代码中。**

内联（inlining）会把 callee 的运算并入 caller。这样做以后，源码里仍然可以看到两个函数，但最终反汇编中可能已经没有对应的 `call`、独立栈帧，甚至没有独立 helper 符号。

## 1. 先区分源码结构与机器代码结构

源码：

```c
static inline long inline_helper(long x)
{
    return x * 3 + 1;
}

long use_inline(long x)
{
    return inline_helper(x) + 5;
}
```

从 C 源码阅读角度看，`use_inline()` 调用了 `inline_helper()`。

但 CPU 不执行“C 函数”这个抽象。CPU 最终只执行链接后的机器指令。若编译器内联 helper，真实执行可以变成：

```text
use_inline
  直接完成 x * 3 + 1 + 5
  ret
```

中间没有 `call inline_helper`。

所以阅读优化代码时要分别问：

```text
源码调用关系是什么？
最终机器调用关系是什么？
```

两者可能不同。

## 2. `inline` 不是 x86-64 指令，也不是 ABI 规则

这里至少有四个层次：

```text
x86-64 ISA
    定义 call、ret、lea 等机器指令

SysV AMD64 ABI
    约束真正发生的函数调用如何传参、保存寄存器和返回

C 语言 / 编译器前端
    处理 inline 语义和函数定义

优化器
    决定某个调用点是否真的进行机器码内联
```

因此不能把：

```c
inline
```

理解成“强制产生内联机器代码”。是否真实内联取决于编译器、优化级别、函数体、属性、调用上下文等因素。

反过来，即使源码没有显式写 `inline`，优化器也可能把普通函数内联。

## 3. 内联真正消掉了什么

如果一个普通调用保留下来，A07/A08/A09 建立的边界仍然存在：

```text
caller 准备参数
→ call 压入返回地址
→ callee 建立自己的执行状态
→ callee 返回值
→ ret 回到 caller
```

如果 callee 被内联，这一层真实调用边界可以全部消失：

- 不需要为这次调用执行 `call`；
- 不会因为这次调用额外压入返回地址；
- 不需要单独满足该 callee 的寄存器保存边界；
- 不需要单独建立该 callee 的栈帧；
- 优化器可以跨原函数边界继续做常量传播、公共表达式化简和寄存器分配。

这也是内联不仅仅“省掉一条 call”的原因。真正重要的是，它把原来两个独立优化区域合并成了一个更大的优化区域。

## 4. 本实验为什么同时保留一个 `noinline` 对照

实验同时定义：

```c
static inline long inline_helper(long x)
{
    return x * 3 + 1;
}

__attribute__((noinline)) long noinline_helper(long x)
{
    return x * 3 + 1;
}
```

并分别通过：

```c
use_inline(x)
use_noinline(x)
```

调用它们。

两个 helper 的数学内容相同，所以如果最终机器代码不同，主要变量就是是否允许内联。

`noinline` 是 GCC 属性，不是 SysV ABI 的组成部分；这里仅用于建立实验控制组。

## 5. `-O0`：源码调用边界仍然存在

本次 GCC 14.2.0、`-O0` 下，`use_inline()` 的关键反汇编为：

```asm
mov    %rax,%rdi
call   inline_helper
add    $0x5,%rax
```

同时 `nm` 可以看到：

```text
inline_helper
noinline_helper
use_inline
use_noinline
```

因此在这个具体构建中，`static inline` 并没有使 helper 在 `-O0` 下消失。

这直接说明：

> 源码写了 `inline`，不等于最终机器代码一定没有函数调用。

## 6. `-Og/-O2`：helper 调用消失

同一个 `use_inline()` 在本次 `-Og` 与 `-O2` 构建中都变成：

```asm
lea    0x6(%rdi,%rdi,2),%rax
ret
```

这个地址计算可以按纯整数运算理解：

```text
RAX = RDI + 2*RDI + 6
    = 3*x + 6
    = (3*x + 1) + 5
```

于是源码中的：

```text
inline_helper(x)
+ 5
```

已经完全并入 `use_inline()`。

这里没有：

```asm
call inline_helper
```

也没有为这次 helper 调用产生新的返回地址。

`lea` 不更新算术 `RFLAGS`，而 `ret` 只恢复控制流；因此这个优化后的实现甚至不需要依赖 `add`/`imul` 产生的算术标志位。

## 7. 为什么 `inline_helper` 连符号也可以消失

本实验把 helper 声明为：

```c
static inline
```

它具有当前翻译单元内的内部链接属性。若所有需要它的调用点都已经内联，而编译器又不再需要生成一个独立可调用实体，那么最终目标中可以没有该函数体。

本次实际 `nm` 结果为：

```text
-O0: 存在局部符号 inline_helper
-O2: 不存在 inline_helper
```

因此“源码里存在函数定义”也不能推出“ELF 符号表中一定存在对应函数符号”。

## 8. `noinline` 控制组为什么重要

同一个 `-O2` 构建中的 `use_noinline()` 仍然包含：

```asm
call   noinline_helper
add    $0x5,%rax
ret
```

这时 A08 的 ABI 边界仍然真实存在：参数 `x` 通过 `%rdi` 进入 helper，结果通过 `%rax` 返回；`call`/`ret` 仍然建立和消费返回地址。

因此同一个优化级别下可以同时存在：

```text
被内联的源码调用
真实保留的机器调用
```

不能只根据“整个程序使用了 -O2”判断每个源码函数都被内联。

## 9. 内联会怎样影响 A09 学过的栈帧分析

如果一个 helper 被内联，那么分析 `use_inline()` 时不应该再凭源码想象一个 helper frame。

真实机器状态只包含最终代码实际建立的 frame。也就是说：

```text
源码函数层次
≠
运行时 frame 层次
```

这会直接影响：

- GDB 单步与源码行对应；
- backtrace 中能否看到独立调用层；
- 局部变量的 location；
- spill/reload 的归属；
- CFI 覆盖的真实 PC 区间。

优化调试困难，根本原因之一就是源码抽象与最终机器执行结构不再一一对应。

## 10. 本节实验

实验入口：[`../labs/10-inlining/`](../labs/10-inlining/)

本次实际完成：

```text
GCC 14.2.0
GNU binutils 2.44
-O0 / -Og / -O2 构建运行        通过
三个二进制运行结果              一致，exit 0
AT&T objdump                    已检查
Intel objdump                   已检查
nm                              已检查
readelf                         已检查
GDB                             当前环境未安装，未执行
```

## 11. 本节完成后应能回答

1. 为什么源码函数调用不一定对应真实 `call`？
2. 为什么 `inline` 不能理解为强制机器码内联？
3. 内联为什么不仅仅是节省 `call`/`ret` 两条指令？
4. 为什么一个源码 helper 可以在最终 ELF 中没有独立符号？
5. 为什么分析优化代码时必须以最终反汇编判断真实栈帧和调用链？
6. `noinline` 对照怎样帮助区分 ABI 调用边界是否真实存在？

下一部分继续分析尾调用（tail call / sibling call）：当 caller 的最后动作就是调用另一个函数时，编译器怎样把 `call + ret` 改写成跳转，以及这对返回地址和栈展开意味着什么。

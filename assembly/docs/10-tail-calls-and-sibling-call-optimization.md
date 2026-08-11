# 第 10 课（第二部分）：尾调用与 sibling-call 优化

A10 第一部分说明了内联如何让一个源码函数边界完全消失。第二部分学习另一种常见优化：函数本身仍保留独立入口，但 caller 不再通过普通 `call ...; ret` 完成最后一次调用，而是直接跳转到 callee。

这类优化通常称为 tail-call optimization；GCC 的实现和控制选项中常使用 sibling call 这一术语。

## 1. 问题背景：为什么最后一次调用可以少一次返回

先看两个 wrapper：

```c
long tail_wrapper(long x)
{
    return tail_target(x);
}

long non_tail_wrapper(long x)
{
    return tail_target(x) + 1;
}
```

两者的区别很小，但控制流意义完全不同。

`non_tail_wrapper()` 必须在 `tail_target()` 返回后继续执行 `+1`，所以 target 必须先返回 wrapper。

而 `tail_wrapper()` 在调用 target 后已经没有任何后续工作。target 的返回值就是 wrapper 的返回值。于是存在一个优化机会：

```text
普通形式：
caller
  call tail_wrapper
      call tail_target
      ret
  ...

优化形式：
caller
  call tail_wrapper
      jmp tail_target
  ...
```

优化形式中，`tail_target()` 可以直接返回最初的 caller。

## 2. 先区分 ISA、ABI 和编译器优化

这里有三个层次不能混在一起：

```text
x86-64 ISA
    定义 call、jmp、ret 的机器语义

SysV AMD64 ABI
    规定真实函数边界上的参数、返回值、寄存器保存和栈对齐规则

编译器优化器
    判断某个调用是否可以改写为 sibling jump
```

SysV AMD64 ABI 并没有规定“源码中的尾位置调用必须变成 `jmp`”。是否发生优化取决于编译器、优化级别、调用约定兼容性、函数属性、栈布局以及其他代码生成条件。

因此本节所有 `-O2` 结果都表示：**当前 GCC 14.2.0 在当前实验条件下做出的实际代码生成决策。**

## 3. 普通 `call + ret` 的返回地址链

设 `main()` 执行：

```asm
call tail_wrapper
```

near `call` 会把下一条指令地址压到当前栈中，然后把 `RIP` 改为 `tail_wrapper`。

进入 wrapper 后可以把栈顶抽象为：

```text
RSP -> RA_main
```

其中 `RA_main` 是 wrapper 最终应该返回的位置。

如果 wrapper 再执行：

```asm
call tail_target
```

则第二次 `call` 再压入一个返回地址：

```text
RSP -> RA_wrapper
       RA_main
```

`tail_target` 执行 `ret` 后先回到 `RA_wrapper`，然后 wrapper 的 `ret` 再消费 `RA_main`。

所以普通形式存在两次动态返回。

## 4. sibling jump 为什么可以复用原返回地址

当前 GCC 14.2.0、`-O2` 下，本实验的 `tail_wrapper()` 为：

```asm
jmp tail_target
```

near `jmp` 只改变控制流，不像 `call` 那样压入新的返回地址。这个 wrapper 本身也没有建立栈帧或调整 `RSP`。

因此跳转前后关键状态可以写成：

```text
进入 tail_wrapper：
RDI = x
RSP -> RA_main

执行 jmp tail_target：
RDI = x
RSP 不变
栈顶仍是 RA_main
RIP = tail_target
```

`tail_target()` 最终执行 `ret` 时，直接从栈顶取出 `RA_main`，于是控制流直接回到 `main()`。

这里最重要的不是“少了一条 ret”，而是：**没有为 wrapper -> target 这条边建立新的动态返回地址层次。**

## 5. 参数为什么还能满足 ABI

本实验中：

```c
long tail_wrapper(long x)
{
    return tail_target(x);
}
```

wrapper 与 target 的参数和返回类型完全兼容。

按照 SysV AMD64 ABI：

```text
第一个 INTEGER 参数 x -> RDI
整数返回值              -> RAX
```

wrapper 收到 `x` 时它已经位于 `%rdi`，而 target 也要求 `%rdi`。所以在这个具体例子中，编译器甚至不需要重新搬运参数，直接 `jmp tail_target` 即可。

如果参数位置、调用约定、栈上参数布局或返回机制不能安全复用，优化器就必须做额外调整，甚至放弃 sibling-call 优化。

## 6. 栈对齐为什么没有被破坏

A08 已经说明普通 SysV AMD64 函数调用边界的栈对齐规则。

本例的 `tail_wrapper()` 没有改变 `%rsp`。它通过 `jmp` 把自己进入时的栈状态直接交给 `tail_target()`。因此 target 所看到的入口栈状态与 wrapper 原入口状态具有相同的 ABI 对齐性质。

这也是 sibling-call 优化必须满足的条件之一：编译器不能为了消除 `call + ret` 而把 callee 放进不满足调用约定的机器状态。

## 7. `RFLAGS` 在 wrapper 中发生什么

当前优化后的 wrapper 只有：

```asm
jmp tail_target
```

这条 near jump 不执行算术运算，也不会因为跳转本身更新算术条件标志。wrapper 没有额外 `cmp`、`add`、`sub` 等会改变条件标志的指令。

但这不表示整个调用过程中 `RFLAGS` 都保持不变；`tail_target()` 内部执行的指令仍可以修改标志位。这里讨论的只是 wrapper 自身这个跳转动作。

## 8. 为什么 `non_tail_wrapper()` 不能变成同样的 `jmp`

`non_tail_wrapper()` 是：

```c
return tail_target(x) + 1;
```

当前 `-O2` 反汇编为：

```asm
call tail_target
add  $0x1,%rax
ret
```

如果把 `call` 简单改成 `jmp`，target 执行 `ret` 后会直接返回 wrapper 的 caller，`add $1,%rax` 将永远没有机会执行。

因此这里必须保留一条“target 返回到 wrapper”的真实控制流边。

这说明判断 tail position 不能只看“函数末尾附近出现了调用”，而要看：

> callee 返回之后，当前函数是否还需要执行任何影响语义的工作。

## 9. `-fno-optimize-sibling-calls` 控制组

本实验额外构建：

```bash
-O2 -fno-optimize-sibling-calls
```

此时同一个 `tail_wrapper()` 变为：

```asm
call tail_target
ret
```

这组结果很重要，因为它把两个变量分开了：

```text
源码完全相同
优化级别仍是 -O2
只关闭 sibling-call 优化
```

于是可以确认 `jmp` 不是源码、ISA 或 ABI 强制产生，而是编译器优化结果。

## 10. 对动态调用栈和 backtrace 的影响

在普通形式中：

```text
tail_target
<- tail_wrapper
<- caller
```

target 运行时存在一条真实返回到 wrapper 的动态返回链。

在 sibling jump 形式中，target 没有新的 `RA_wrapper` 可以返回。机器层面的返回链更接近：

```text
tail_target
<- caller
```

因此调试器或 unwinder 看到的调用栈不一定与源码函数嵌套关系一一对应。

需要注意：带调试信息的工具可能利用 DWARF 的 inline/tail-call 相关信息重建某些源码层级；那属于调试信息和工具行为。这里首先建立的是最基础的机器模型：**真实 `call` 是否发生、真实返回地址是否存在。**

## 11. 本节实验

实验入口：[`../labs/10-tail-calls/`](../labs/10-tail-calls/)

本次实际验证：

```text
GCC 14.2.0
GNU binutils 2.44
-O0 / -Og / -O2 构建运行                  通过
-O2 -fno-optimize-sibling-calls           通过
所有二进制运行结果                         正确，exit 0
AT&T objdump                              已检查
Intel objdump                             已检查
nm                                        已检查
readelf                                   已检查
GDB                                       当前环境未安装，未执行
```

当前最关键的反汇编结果为：

```asm
# -O2 tail_wrapper
jmp tail_target

# -O2 non_tail_wrapper
call tail_target
add  $0x1,%rax
ret

# -O2 -fno-optimize-sibling-calls tail_wrapper
call tail_target
ret
```

## 12. 常见误区

### 误区一：尾调用是 x86-64 的一种特殊指令

不是。这里使用的是普通 `jmp`。所谓 tail call / sibling call 是编译器对控制流和调用语义的判断。

### 误区二：所有 `return f(x);` 都一定优化成 `jmp`

不是。编译器还必须满足 ABI、参数、栈布局、目标可达性、优化选项等约束。

### 误区三：ELF 中还有 wrapper 符号，所以运行时一定有 wrapper frame

不是。符号表示代码入口；动态 frame 是否存在要看真实执行路径是否建立了需要返回到该函数的状态。

### 误区四：`jmp` target 后 target 的 `ret` 会回到 wrapper

不会。`jmp` 没有压入 wrapper 返回地址。在本实验的优化路径中，target 直接消费 wrapper 原 caller 的返回地址。

## 13. 本节完成后应能回答

1. 为什么真正的尾位置调用可以从 `call + ret` 变成 `jmp`？
2. `call` 与 `jmp` 对返回地址和 `%rsp` 的影响有何不同？
3. sibling jump 后 target 的 `ret` 最终从哪里取得返回地址？
4. 为什么本实验中的 `%rdi` 可以不经搬运直接交给 target？
5. 为什么 `non_tail_wrapper()` 必须保留真实 `call`？
6. 为什么 `-fno-optimize-sibling-calls` 能证明这是优化器决策而不是 ABI 规则？
7. 尾调用为什么会使源码调用层次与真实动态调用栈不一致？

下一部分继续沿 A10 的优化主线学习公共子表达式与跨源码表达式的合并，观察优化器如何减少重复计算，以及这种变化如何影响寄存器中的中间值和反汇编阅读方式。

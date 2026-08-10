# 第 7 课（第三部分）：递归调用与多层返回地址

前两部分已经分别分析了 direct `call` 和 indirect `call`。本节继续研究递归：同一个函数在尚未返回时再次调用自己，会怎样在栈上形成多层彼此独立的返回现场。

递归本身不是新的 CPU 指令。处理器看到的仍然只是普通的：

```text
call
函数体
ret
```

不同之处在于，同一个函数可以同时存在多个尚未返回的调用实例，因此栈上会同时保存多份返回地址和每一层需要保留的数据。

## 1. 一个最小递归例子

考虑：

```c
long sum(long n)
{
    if (n == 0)
        return 0;
    return n + sum(n - 1);
}
```

调用 `sum(3)` 时，逻辑过程是：

```text
sum(3)
→ sum(2)
  → sum(1)
    → sum(0)
    ← 0
  ← 1
← 3
← 6
```

关键问题不是计算结果，而是每一层怎样知道“递归调用返回以后应该继续执行哪里”。

答案仍然是 `call` 保存的返回地址。

## 2. 每一层 `call` 都保存自己的返回地址

假设函数中有：

```asm
    call recursive_sum
after_recursive_call:
    ...
```

每次执行这条 `call`，CPU 都会把本次调用的下一条指令地址压入当前栈顶。

因此，当 `recursive_sum(3)` 尚未返回就调用 `recursive_sum(2)`，随后 `recursive_sum(2)` 又调用 `recursive_sum(1)` 时，栈中会同时存在多个返回地址。

虽然它们在本实验中数值相同——因为每层都从同一个递归调用点调用自己——但它们是不同调用层分别压入的栈项，位于不同地址。

这一区分很重要：

```text
返回地址的数值可以相同
≠
栈上只有一份返回地址
```

## 3. 本节实验中的栈布局

实验函数在递归调用前先保存当前参数：

```asm
recursive_sum:
    testq %rdi, %rdi
    je recursive_base
    pushq %rdi
    subq $1, %rdi
    call recursive_sum
after_recursive_call:
    popq %rdi
    addq %rdi, %rax
    ret
```

设进入某一非基例层时：

```text
RSP = S
```

执行：

```asm
pushq %rdi
```

以后：

```text
RSP = S - 8
[RSP] = 本层 n
```

随后执行递归 `call`：

```text
RSP = S - 16
[RSP]     = after_recursive_call
[RSP + 8] = 本层 n
```

所以每一个非基例递归层在本实验中会额外占用：

```text
8 字节：本层保存的 n
8 字节：递归 call 保存的返回地址
```

也就是 16 字节。

这不是“递归固定每层占 16 字节”的通用规则。真实函数还可能保存更多寄存器、建立栈帧、分配局部变量，并受到 ABI 和编译器优化影响。这里的 16 字节只属于当前手写实验。

## 4. `sum(3)` 的逐层栈变化

忽略最外层 `_start -> recursive_sum` 的返回地址，进入第一层 `recursive_sum(3)` 后记当前 `RSP = S0`。

第一层保存 `3` 并递归调用：

```text
S0 - 16   return address for sum(2)  ← RSP
S0 - 8    saved n = 3
```

第二层保存 `2` 并递归调用：

```text
S0 - 32   return address for sum(1)  ← RSP
S0 - 24   saved n = 2
S0 - 16   return address for sum(2)
S0 - 8    saved n = 3
```

第三层保存 `1` 并递归调用基例：

```text
S0 - 48   return address for sum(0)  ← RSP
S0 - 40   saved n = 1
S0 - 32   return address for sum(1)
S0 - 24   saved n = 2
S0 - 16   return address for sum(2)
S0 - 8    saved n = 3
```

基例 `sum(0)` 不再执行 `push` 和新的递归 `call`，而是直接：

```asm
xorq %rax, %rax
ret
```

于是开始逐层展开。

## 5. 为什么返回顺序一定是后进先出

最深一层的 `ret` 首先弹出最近一次递归 `call` 保存的返回地址，因此先回到 `sum(1)` 的 `after_recursive_call`。

这一层执行：

```asm
popq %rdi
addq %rdi, %rax
ret
```

恢复 `n = 1`，得到结果 1，然后再次 `ret` 回到 `sum(2)`。

之后依次：

```text
sum(1) 返回
→ sum(2) 恢复 n=2，结果变为 3
→ sum(3) 恢复 n=3，结果变为 6
→ 返回最外层调用者
```

这个顺序来自栈的 LIFO（Last In, First Out）性质，而不是递归函数额外维护了某种“调用层编号”。

## 6. 同一个函数为什么可以有多个活动实例

递归经常容易产生一个误解：既然每层执行的是同一个函数、同一段机器代码，那么局部状态会不会互相覆盖？

答案取决于状态保存在哪里。

代码本身可以共享：

```text
所有递归层的 RIP 都会进入同一个函数地址范围
```

但每层动态状态可以分别保存在栈上的不同位置：

```text
返回地址
保存的参数
局部变量
被保存的寄存器
```

因此“函数代码只有一份”和“函数调用实例有多份”并不矛盾。

## 7. 递归深度与栈空间

每增加一层尚未返回的递归调用，就会继续向低地址方向消耗栈空间。

如果递归没有正确基例，或者深度过大：

```text
RSP 持续下降
→ 可用栈空间逐渐耗尽
→ 最终访问不可用栈地址
```

用户态通常表现为栈溢出相关故障；内核态由于内核栈大小受到严格限制，深递归尤其危险。

本节只建立“递归深度会转化为栈深度”的基础认识，不展开具体内核栈大小和异常处理。

## 8. 递归与编译器优化

源代码中的递归不保证最终机器代码中一定存在递归 `call`。

例如尾递归：

```c
return recurse(next);
```

在满足条件时可能被编译器优化成 `jmp`，从而复用当前调用层而不是再压入新的返回地址。

因此阅读反汇编时，应以真实机器指令为准：

```text
看到 call → 会建立新的返回地址
看到 jmp  → 不会按 call 的方式压入返回地址
```

后续 A10 会系统讨论编译器优化。

## 9. `RFLAGS`、`RSP` 和控制流

递归调用本身仍遵循普通 near `call/ret` 规则。

需要分别追踪：

```text
RIP：进入更深一层或返回上一层
RSP：每次 push/call 下降，每次 pop/ret 上升
栈内存：保存本层参数和返回地址
RFLAGS：由 test/sub/add 等函数体指令修改
```

不要把函数体中算术指令造成的标志位变化归因于 `call` 或 `ret`。

## 10. 实验

配套实验：

[`../labs/07-recursion/`](../labs/07-recursion/)

实验计算：

```text
recursive_sum(3) = 6
```

程序还会检查最外层递归调用完成以后 `RSP` 是否恢复到调用前值。

实际反汇编中的关键路径为：

```asm
pushq %rdi
subq $1, %rdi
call recursive_sum
popq %rdi
addq %rdi, %rax
ret
```

## 11. 本节完成后应能回答

1. 为什么递归不需要新的 CPU 指令？
2. 同一个递归调用点产生的多个返回地址为什么可以数值相同但仍属于不同调用层？
3. 本实验每个非基例层为什么额外消耗 16 字节？
4. 为什么最深层必须最先返回？
5. 同一份函数代码如何对应多个同时存在的调用实例？
6. 为什么递归深度会直接增加栈空间压力？
7. 为什么阅读优化代码时不能仅凭 C 源码判断一定存在递归 `call`？

A07 还剩最后一个最小单元：返回地址被破坏时，普通 `ret` 会产生什么直接后果。
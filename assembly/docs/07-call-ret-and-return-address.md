# 第 7 课（第一部分）：`call`、`ret` 与返回地址

A06 已经建立了栈的基本模型：`RSP` 指向当前栈顶，栈通常向低地址方向增长，`push`/`pop` 会同时修改 `RSP` 和栈内存。本节在这个基础上研究函数调用最核心的控制流机制：CPU 怎样从调用者跳到被调用者，以及被调用者怎样准确返回到原来的位置。

本节先只讨论 x86-64 的 **near direct call** 和普通 near `ret`。函数指针、间接调用、递归和返回地址破坏放到 A07 后续小节。

## 1. 为什么函数调用不能只用 `jmp`

假设调用者执行：

```asm
    jmp worker
```

CPU 可以跳到 `worker`，但 `worker` 执行完以后并不知道应该回到哪里。

函数可能从很多不同位置被调用：

```text
caller A ─┐
caller B ─┼─→ worker
caller C ─┘
```

因此，一次函数调用至少需要同时解决两个问题：

```text
1. 跳到目标函数；
2. 保存“调用完成后继续执行的位置”。
```

x86 的 `call` 指令把这两个动作结合起来。

## 2. direct `call` 的基本模型

考虑：

```asm
before_call:
    call worker
after_call:
    ...
```

对于 64 位模式中的普通 near call，可以把核心效果理解成：

```text
return_address = after_call
RSP = RSP - 8
[RSP] = return_address
RIP = worker
```

也就是说，`call` 保存的不是 `call` 指令自己的地址，而是 **紧跟在 `call` 后面的下一条指令地址**。

如果调用前：

```text
RSP = S
```

那么进入 `worker` 时：

```text
RSP     = S - 8
[RSP]   = after_call 的地址
RIP     = worker
```

这 8 字节返回地址就是随后 `ret` 能够返回调用者的依据。

## 3. 为什么是下一条指令地址

CPU 在执行完被调用函数以后，需要继续执行调用点之后的代码。

例如：

```asm
    movq $10, %rax
    call add_three
    cmpq $13, %rax
```

`add_three` 返回以后应该执行 `cmpq`，而不是再次执行 `call`。因此栈中保存的是 `call` 之后的地址。

在本节实验的实际 ELF 中：

```text
before_direct_call = 0x40100a
after_direct_call  = 0x40100f
```

反汇编为：

```asm
40100a: e8 1b 00 00 00    call 40102a <direct_target>
40100f: ...                # after_direct_call
```

这条 direct near `call` 本身占 5 字节，因此保存的返回地址正是 `0x40100f`。

不要把“5 字节”推广成所有 `call` 都固定占 5 字节。这里讨论的是当前实验中使用的 `E8 rel32` 形式。

## 4. direct near `call` 的目标地址

实验中的指令：

```asm
    call direct_target
```

反汇编显示：

```asm
40100a: e8 1b 00 00 00    call 40102a <direct_target>
```

`E8` 形式使用相对于下一条指令的有符号位移来得到目标地址。可以把它理解为：

```text
target = next_RIP + sign_extend(rel32)
```

因此 direct call 不需要在指令中保存完整 64 位目标地址。

这也是后面学习 ELF 重定位、PIC/PIE 时会再次遇到的 PC-relative 思路。

## 5. 被调用函数入口看到什么

调用：

```asm
    call direct_target
```

进入 `direct_target` 后，实验首先执行：

```asm
    movq (%rsp), %r13
    leaq after_direct_call(%rip), %r14
    cmpq %r14, %r13
```

这里：

```text
R13 = [RSP] = call 自动压入的返回地址
R14 = after_direct_call 的实际地址
```

两者相等说明：

```text
[RSP] == call 后的下一条指令地址
```

注意，这个返回地址不是由源代码显式 `push` 的，而是 `call` 指令本身的架构语义。

## 6. `ret` 的基本模型

被调用函数最后执行：

```asm
    ret
```

对于本节的普通 near `ret`，可以把核心效果理解为：

```text
RIP = [RSP]
RSP = RSP + 8
```

因此它与前面的 `call` 形成配对：

```text
调用前：        RSP = S
call 后：        RSP = S - 8, [RSP] = return_address
ret 后：         RIP = return_address, RSP = S
```

`ret` 不知道函数名，也不需要知道谁调用了当前函数。它只依赖当前栈顶保存的返回地址。

## 7. `call`/`ret` 与 `push`/`pop` 的联系和区别

从理解模型上，可以类比：

```text
call target
≈ push return_address + jump target
```

以及：

```text
ret
≈ pop RIP
```

这个类比非常有用，因为它能直接解释 `RSP` 和返回地址的变化。

但不要把它理解成处理器内部真的把一条 `call` 拆成软件可见的 `push` 和 `jmp` 指令。`call` 和 `ret` 是独立的架构指令，现代处理器还会对调用/返回控制流进行专门预测。

## 8. `RSP` 的完整变化

假设进入调用点之前：

```text
RSP = 0x...1000
```

执行：

```asm
call worker
```

进入 `worker` 时：

```text
RSP = 0x...0ff8
```

栈布局为：

```text
高地址

0x...1000   调用前栈顶以上的内容
0x...0ff8   return address   ← RSP

低地址
```

如果 `worker` 自身没有再改变栈，执行 `ret` 后：

```text
RIP = return address
RSP = 0x...1000
```

所以一个匹配的 `call` + `ret` 对返回后净栈深度的影响为 0。

## 9. 返回地址为什么必须保持完整

`ret` 会把当前 `[RSP]` 当作下一条 `RIP`。

因此，如果函数在返回前破坏了：

```text
[RSP]
```

或者让 `RSP` 指向了错误的位置，那么 `ret` 就可能跳到错误地址。

这就是为什么后面分析：

- 栈溢出；
- 返回地址覆盖；
- ROP；
- shadow stack；
- 内核调用栈损坏；

都必须先理解普通 `call`/`ret` 的栈模型。

本节暂不展开安全机制，只建立正常路径。

## 10. `RFLAGS` 和普通 near `call/ret`

本节讨论的普通 near `call` 和 near `ret` 主要改变：

```text
RIP
RSP
栈顶返回地址所在内存
```

它们不以算术/逻辑指令的方式产生新的 `ZF/CF/SF/OF` 结果。

实际函数体中的 `cmp`、`add` 等指令当然会修改标志位，因此分析调用前后 `RFLAGS` 时，要区分“控制转移指令本身”和“函数体执行的其他指令”。

## 11. 与 ABI 的边界

这里需要区分两个层次：

### x86-64 指令架构规定

`call` 保存返回地址，`ret` 从栈中取得返回地址。这属于处理器指令语义。

### System V AMD64 ABI 规定

参数放在哪些寄存器、哪些寄存器由 caller/callee 保存、函数调用边界怎样进行 16 字节栈对齐等，属于 ABI。

因此：

```text
call/ret 的返回地址机制 ≠ 完整函数调用约定
```

A08 会继续学习 ABI。

## 12. 实验观察路径

配套实验：

[`../labs/07-call-ret/`](../labs/07-call-ret/)

重点观察：

```text
调用前 RSP
→ call
→ 入口 RSP = 调用前 RSP - 8
→ [RSP] = after_direct_call
→ ret
→ RIP = after_direct_call
→ RSP 恢复
```

同时用 `objdump` 确认：

```text
E8 rel32  direct near call
C3        near ret
```

## 13. 本节完成后应能回答

1. `call` 为什么不能简单等同于 `jmp`？
2. `call` 保存的是哪一个地址？
3. 64 位模式下本实验的 near `call` 为什么让 `RSP` 减少 8？
4. 被调用函数入口处 `[RSP]` 是什么？
5. 普通 near `ret` 如何同时修改 `RIP` 和 `RSP`？
6. 为什么错误的 `RSP` 或被破坏的返回地址会使 `ret` 跳到错误位置？
7. 哪些属于指令架构语义，哪些属于后续 ABI 规则？

下一小节继续学习 direct call 之外的间接调用、函数指针与递归。
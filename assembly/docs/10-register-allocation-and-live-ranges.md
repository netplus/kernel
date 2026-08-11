# 第 10 课（第四部分）：寄存器分配与 live range

前一部分已经看到：源码变量并不与物理寄存器一一对应。本节进一步回答两个问题：**为什么同一个物理寄存器可以在不同时间承载不同 value，以及什么时候寄存器不够用会迫使编译器把 value 暂存到栈上。**

## 1. 问题背景：真正需要分配的是“当前仍然活跃的 value”

源码里可以同时出现很多变量，但只有那些“之后还会被读取”的 value 才必须继续保留。一个 value 从产生到最后一次使用之间的区间通常称为 live range。

可以先用一个简化模型理解：

```text
value 产生
   ↓
后面仍会使用   ← live
   ↓
最后一次使用
   ↓
之后不再需要   ← dead
```

当旧 value 已经 dead，保存它的物理寄存器便可以立即复用。这也是优化后机器代码经常看不到源码变量边界的原因。

## 2. 寄存器分配和 ABI 是两个层次

System V AMD64 ABI 规定函数调用边界上的寄存器职责，例如整数参数从 `%rdi/%rsi/%rdx/%rcx/%r8/%r9` 进入，返回值放在 `%rax`，并区分 caller-saved 与 callee-saved 寄存器。

但 ABI 并不规定函数体内部“变量 x 必须放哪个寄存器”。函数进入后，只要满足最终可观察语义和调用边界规则，编译器可以自由复用寄存器。

因此应区分：

```text
ABI
    约束调用边界

寄存器分配
    决定函数内部活跃 value 当前放在哪个物理寄存器或栈槽
```

## 3. 实验一：同一个 `%rdi` 连续承载多个 value

实验函数：

```c
long reuse_chain(long a, long b, long c, long d)
{
    long x = a + b;
    long y = x * c;
    long z = y + d;
    return z * 3;
}
```

本次 GCC 14.2.0、`-O2` 的关键反汇编为：

```asm
add    %rsi,%rdi
imul   %rdx,%rdi
add    %rcx,%rdi
lea    (%rdi,%rdi,2),%rax
ret
```

逐步看 `%rdi`：

```text
入口              RDI = a
add 后            RDI = a + b        = x
imul 后           RDI = x * c        = y
第二个 add 后     RDI = y + d        = z
lea 后            RAX = 3 * z
```

这里没有必要分别为 `a/x/y/z` 分配四个位置。每一步完成后，旧 value 不再需要，新的 value 可以覆盖同一个 `%rdi`。

这说明“一个寄存器属于某个源码变量”的说法通常过于静态。更准确的观察方式是：**在某条指令执行前后，这个寄存器当前承载什么 value，以及这个 value 的最后一次使用在哪里。**

## 4. live range 为什么会重叠

如果后续仍需要多个旧值，它们就不能相互覆盖。例如跨越一次普通外部函数调用时，caller 必须假设 caller-saved 寄存器可能被 callee 改写。

本实验的第二个函数接收十个整数参数，并在调用 `opaque()` 之后继续使用这些参数形成的结果。`opaque()` 被放在另一个 translation unit 中，并且不使用 LTO，因此编译 `main.c` 时不能根据它的函数体证明某些 caller-saved 寄存器一定保持不变。

于是 `pressure_across_call()` 在调用点前存在多个必须跨过 `call` 继续存活的 value。这会明显增加寄存器压力。

## 5. 本次 `-O2` 观察到的分配结果

关键序言和保存动作：

```asm
push   %r15
mov    %rdx,%r15
push   %r14
mov    %rcx,%r14
push   %r13
mov    %r8,%r13
push   %r12
mov    %r9,%r12
push   %rbx
mov    %rdi,%rbx
sub    $0x18,%rsp
mov    %rsi,-0x38(%rbp)
call   opaque
```

这里可以看到两种保存办法同时出现。

第一种是把活跃 value 放入 callee-saved 寄存器：

```text
RDI -> RBX
RDX -> R15
RCX -> R14
R8  -> R13
R9  -> R12
```

因为当前函数自己使用了这些 callee-saved 寄存器，所以它先 `push` 保存 caller 原来的值，并在返回前恢复。

第二种是把仍需跨越 `call` 的 `%rsi` 保存到栈槽：

```asm
mov    %rsi,-0x38(%rbp)
...
call   opaque
mov    -0x38(%rbp),%rsi
```

这就是本实验中可以直接确认的 spill/reload 对。

## 6. 为什么这属于寄存器压力，而不是 ABI 要求固定 spill `%rsi`

ABI 只告诉编译器：`%rsi` 属于 caller-saved，普通调用之后不能假定它还保留原值。ABI 并没有规定必须把它放在 `-0x38(%rbp)`。

编译器还可以选择：

- 提前计算并缩短某些 live range；
- 改用别的可用寄存器；
- 使用 callee-saved 寄存器；
- 重新计算一个便宜的 value；
- spill 到栈上，之后 reload。

本次 GCC 14.2.0 的具体选择是“多个 callee-saved 寄存器 + 一个栈槽”。具体寄存器和偏移属于当前源码、编译器和选项的代码生成结果，不是 ABI 固定布局。

## 7. 为什么要把 `opaque()` 放到独立 translation unit

如果 `opaque()` 和 caller 同时出现在一个 translation unit 中，编译器可能通过 interprocedural analysis 得知它实际不会改写某些寄存器，从而生成与普通未知外部调用不同的代码。

本实验分别编译：

```text
main.c
opaque.c
```

再链接，并且没有开启 LTO。这样在编译 `main.c` 时，`opaque()` 更接近一个普通外部调用边界，实验更容易稳定展示 caller-saved、callee-saved 和 spill/reload 的关系。

这仍然不是对所有编译器版本的保证，因此实验结论必须以实际反汇编为准。

## 8. `RSP`、栈与控制流

`pressure_across_call()` 的序言先保存 `%rbp`，随后依次 `push` 多个 callee-saved 寄存器，并额外执行：

```asm
sub $0x18,%rsp
```

因此真正执行 `call opaque` 前，当前函数已经建立了自己的保存区和栈槽。`call` 再额外把返回地址压入栈中；`opaque` 返回后，当前函数继续 reload，并在尾声按相反方向恢复 `%rsp` 和 callee-saved 寄存器。

应把两类栈内容分开理解：

```text
保存 caller 原有 callee-saved 状态
    push %rbx/%r12/... 

当前函数自己的临时 spill slot
    -0x38(%rbp)
```

两者都位于栈上，但目的不同。

## 9. `RFLAGS` 不是 live range 的主要载体，但仍要核对

本实验的 `add`、`imul` 等算术指令会更新算术标志位，`lea` 不更新 `RFLAGS`。函数没有使用条件跳转读取这些中间 flags，因此它们不会形成需要跨越 `opaque()` 保存的程序语义状态。

如果后续代码确实依赖某个条件码，那么 flags 本身也会形成数据依赖，优化器必须保证相关语义。

## 10. 不要从最终机器代码反推 GCC 的固定寄存器分配算法

从反汇编可以可靠确认：

- 哪些 value 在某个时刻位于哪些寄存器或栈槽；
- 某个寄存器何时被覆盖复用；
- 哪些 store/reload 实际发生；
- 哪些 value 必须跨越函数调用保持。

但不能仅凭这段输出断言 GCC 必然采用某一种固定的 graph coloring 或 linear scan 实现路径。编译器内部会经历多阶段优化和目标相关分配，本课程在这一节只学习最终机器状态及其约束。

## 11. 本节实验

实验入口：[`../labs/10-register-allocation-live-ranges/`](../labs/10-register-allocation-live-ranges/)

本次实际验证环境：

```text
GCC 14.2.0
GNU binutils 2.44
x86-64
```

实际完成：

```text
-O0 / -Og / -O2 构建运行      通过
reuse_chain                   39
pressure_across_call          110
AT&T objdump                  已检查
Intel objdump                 已检查
nm                            已检查
readelf                       已检查
GDB                           当前环境未安装，未执行
```

## 12. 本节完成后应能回答

1. 什么是一个机器级 value 的 live range？
2. 为什么同一个 `%rdi` 可以先保存 `a`，再保存 `x/y/z`？
3. 为什么 live range 重叠会增加寄存器压力？
4. caller-saved 与 callee-saved 规则怎样影响跨 `call` 的 value 保存？
5. 为什么 `mov %rsi,-0x38(%rbp)` 是当前代码生成中的 spill，而不是 ABI 规定的固定位置？
6. 为什么需要区分“保存 callee-saved 寄存器”和“当前函数的 spill slot”？
7. 为什么最终反汇编不足以证明 GCC 内部采用了某个固定寄存器分配算法？

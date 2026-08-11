# 第 9 课（第一部分）：`RBP` 栈帧基本模型

A08 已经建立了普通 System V AMD64 函数调用边界：参数如何传递、返回值放在哪里、哪些寄存器由谁保存，以及 `call` 如何把返回地址压入栈中。A09 接下来要回答一个更具体的问题：**函数进入以后，怎样组织自己的局部状态，怎样让返回地址、保存的寄存器和局部变量形成一个稳定、可读的栈布局？**

本节先学习最经典的 `RBP` frame pointer 模型。它不是所有优化后函数都必须采用的形式，但它非常适合建立函数栈帧的基本工作模型，也是后续理解 frame pointer omission、DWARF CFI 和栈展开的基础。

## 1. 先区分三个层次

理解 `%rbp` 时，先不要把不同规则混在一起。

### 1.1 x86-64 ISA

从指令集角度看，`RBP` 是一个 64 位通用寄存器。CPU 并不知道“函数栈帧”这种 C 语言层面的概念，也不会强制要求函数执行：

```asm
pushq %rbp
movq  %rsp, %rbp
```

同样，`RSP` 才是 `push`、`pop`、`call`、`ret` 等栈相关指令隐式使用的栈指针。

### 1.2 System V AMD64 ABI

在普通 SysV AMD64 函数调用约定中，`RBP` 属于 callee-saved 寄存器。如果一个函数修改 `%rbp`，它必须让调用者在函数返回后看到原来的值。

这就是经典序言首先执行 `pushq %rbp` 的直接原因：保存调用者的 `%rbp`，而不是因为 CPU 要求“必须建立栈帧”。

### 1.3 编译器与函数实现策略

函数可以选择把 `%rbp` 固定用作 frame pointer，也可以在允许的情况下省略 frame pointer，把 `%rbp` 当成普通 callee-saved 寄存器使用。

因此：

```text
RBP 是通用寄存器                  ISA 事实
RBP 必须由 callee 保持             ABI 规则
RBP 是否作为 frame pointer         实现/编译器选择
```

后续阅读内核汇编时，这种分层非常重要。

## 2. 函数刚进入时栈上已经有什么

假设 caller 执行：

```asm
call frame_sum
```

near `call` 会先把下一条指令的地址压入栈，然后把 `RIP` 转到 callee。

因此 `frame_sum` 刚进入、尚未修改 `%rsp` 时：

```text
高地址

... caller 的栈内容 ...

[RSP]     return address

低地址
```

此时 `%rsp` 指向返回地址。

如果函数马上执行：

```asm
pushq %rbp
```

则发生：

```text
RSP = RSP - 8
[RSP] = old RBP
```

栈变成：

```text
高地址

[RSP + 8] return address
[RSP + 0] saved caller RBP   <- RSP

低地址
```

再执行：

```asm
movq %rsp, %rbp
```

就让 `%rbp` 固定指向保存旧 `%rbp` 的位置。

## 3. 为什么需要一个稳定的 frame base

`%rsp` 经常变化。函数可能：

- 为局部变量分配空间；
- 保存其他 callee-saved 寄存器；
- 为调用其他函数准备栈参数；
- 临时调整对齐；
- 执行 `push` / `pop`。

如果所有对象都只用相对 `%rsp` 的偏移访问，那么 `%rsp` 每变化一次，偏移关系就可能随之改变。

经典 frame pointer 模型通过：

```asm
movq %rsp, %rbp
```

把某个固定位置记录到 `%rbp`。后面即使 `%rsp` 向低地址移动，仍然可以使用固定偏移描述对象。

例如继续执行：

```asm
subq $16, %rsp
```

就得到：

```text
高地址

RBP + 8    return address
RBP + 0    saved caller RBP      <- RBP
RBP - 8    local slot 1
RBP - 16   local slot 2          <- RSP

低地址
```

这就是最基本的 `RBP` 栈帧。

## 4. 序言逐条发生了什么

实验中的序言是：

```asm
pushq %rbp
movq  %rsp, %rbp
subq  $16, %rsp
```

假设函数刚进入时：

```text
entry RSP = S
entry RBP = B
[S]       = return address
```

第一条：

```asm
pushq %rbp
```

执行后：

```text
RSP = S - 8
[RSP] = B
```

第二条：

```asm
movq %rsp, %rbp
```

执行后：

```text
RBP = S - 8
RSP = S - 8
```

第三条：

```asm
subq $16, %rsp
```

执行后：

```text
RBP = S - 8
RSP = S - 24
```

因此有两个容易验证的不变量：

```text
entry_rsp - frame_rbp = 8
frame_rbp - frame_rsp = 16
```

同时：

```text
0(%rbp) = saved caller RBP
8(%rbp) = return address
```

## 5. 局部变量为什么常出现在负偏移

在经典 frame pointer 模型中，栈向低地址增长，而 `%rbp` 固定在 frame 上部，因此新分配的局部区位于 `%rbp` 的低地址一侧。

实验把两个参数复制到局部槽：

```asm
movq %rdi, -8(%rbp)
movq %rsi, -16(%rbp)
```

再读取：

```asm
movq -8(%rbp), %rax
addq -16(%rbp), %rax
```

这里的负号并不表示“变量是负数”，只是表示目标地址低于 `%rbp`。

同样，`8(%rbp)` 是正偏移，是因为返回地址位于 `%rbp` 之上的更高地址。

## 6. `leave` 做了什么

实验尾声使用：

```asm
leave
ret
```

在这里可以把 `leave` 理解为：

```asm
movq %rbp, %rsp
popq %rbp
```

第一步丢弃当前函数在 `%rbp` 以下分配的局部区：

```text
RSP = RBP
```

第二步从栈顶恢复调用者的 `%rbp`：

```text
RBP = [RSP]
RSP = RSP + 8
```

此时 `%rsp` 再次指向返回地址。随后：

```asm
ret
```

取出返回地址并恢复 caller 控制流：

```text
RIP = [RSP]
RSP = RSP + 8
```

所以经典尾声的完整效果是：

```text
丢弃 callee 局部区
→ 恢复 caller 的 RBP
→ 取出返回地址
→ 回到 caller
```

## 7. `RBP` 链为什么有助于理解栈展开

如果一串函数都采用相同的 frame pointer 规则，那么每个 frame 的：

```text
0(%rbp)
```

都保存上一层调用者的 `%rbp`，而：

```text
8(%rbp)
```

保存当前函数的返回地址。

抽象地看，会形成：

```text
current RBP
   |
   +--> saved previous RBP
             |
             +--> saved previous RBP
                       |
                       ...
```

这给“沿 frame pointer 回溯调用链”提供了直观基础。

但这里必须注意：**现代编译器并不保证所有函数都保留这种链。** 一旦函数省略 frame pointer，或者使用不同的优化布局，仅靠 `%rbp` 链就不能可靠展开整个调用栈。A09 后续会再讲 DWARF CFI 等更一般的描述方式。

## 8. 不要把源代码局部变量和栈槽一一等同

本实验故意把两个值写到：

```text
-8(%rbp)
-16(%rbp)
```

这是为了观察栈帧。

真实编译器可以：

- 一直把变量留在寄存器；
- 合并不同生命周期的栈槽；
- 消除无用变量；
- 常量折叠；
- 内联整个函数；
- 省略 frame pointer；
- 使用 `%rsp` 相对寻址而不用 `%rbp`。

所以“C 中有两个局部变量”并不意味着“机器栈上一定存在两个固定槽”。

## 9. 与 A08 栈对齐的关系

本实验的 `frame_sum` 是 leaf function，不继续调用其他函数。

它进入时普通 SysV AMD64 边界通常满足：

```text
RSP mod 16 = 8
```

执行一个 8 字节：

```asm
pushq %rbp
```

后，`%rsp mod 16 = 0`。再执行：

```asm
subq $16, %rsp
```

仍保持 `0 mod 16`。

如果当前函数后面要继续 `call` 其他普通函数，这个状态正好可以作为满足调用点 16 字节对齐的基础。

但真实 frame size 必须结合保存寄存器、局部变量、spill、outgoing stack arguments 和更高对齐要求一起计算，不能把“`push rbp; sub $16`”当成固定模板。

## 10. 本节实验

实验入口：[`../labs/09-rbp-frame/`](../labs/09-rbp-frame/)

手写汇编函数：

```asm
frame_sum:
    movq %rsp, entry_rsp(%rip)
    movq %rbp, entry_rbp(%rip)

    pushq %rbp
    movq %rsp, %rbp
    subq $16, %rsp

    ...

    movq %rdi, -8(%rbp)
    movq %rsi, -16(%rbp)
    movq -8(%rbp), %rax
    addq -16(%rbp), %rax

    leave
    ret
```

实际验证结果：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44

-O0 构建/运行                    通过
-O2 构建/运行                    通过
frame_sum(17,25)                42
entry_rsp - frame_rbp           8
frame_rbp - frame_rsp           16
0(%rbp) 与入口 RBP              一致
8(%rbp)                         已观测为返回地址
AT&T objdump                    已检查
Intel objdump                   已检查
nm/readelf                      已检查
GDB                             当前环境未安装，未执行
```

反汇编中的关键序列为：

```asm
push   %rbp
mov    %rsp,%rbp
sub    $0x10,%rsp
...
mov    %rdi,-0x8(%rbp)
mov    %rsi,-0x10(%rbp)
...
leave
ret
```

Intel 语法下对应为：

```asm
push rbp
mov  rbp,rsp
sub  rsp,0x10
...
mov  QWORD PTR [rbp-0x8],rdi
mov  QWORD PTR [rbp-0x10],rsi
...
leave
ret
```

## 11. 本节完成后应能回答

1. 为什么函数刚进入时 `[rsp]` 是返回地址？
2. `push %rbp` 保存的是谁的 `%rbp`？
3. 为什么经典 frame pointer 模型中 `0(%rbp)` 是旧 `%rbp`，`8(%rbp)` 是返回地址？
4. 为什么局部变量常使用 `%rbp` 的负偏移？
5. `leave` 和 `ret` 分别恢复什么状态？
6. 为什么 `%rbp` 不是 CPU 强制规定的“函数栈帧寄存器”？
7. 为什么有了 frame pointer 链仍不能保证对所有优化代码可靠展开调用栈？

下一最小单元将继续 A09，讨论局部变量、寄存器 spill/reload 与编译器生成的实际栈槽。
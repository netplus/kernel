# 第 8 课（第四部分）：普通函数调用边界的 16 字节栈对齐

A08 前三部分已经建立了参数寄存器、返回值、寄存器保存责任和栈上传参的基本模型。本节聚焦一个经常在手写汇编中出错的问题：**为什么普通 System V AMD64 函数在 `call` 前要求栈满足 16 字节对齐，而 callee 刚进入时 `%rsp` 又通常表现为 `8 mod 16`？**

本节只讨论普通 SysV AMD64 函数调用边界，不展开 Red Zone、完整函数栈帧或 Linux 系统调用入口。

## 1. 核心规则

对没有更高对齐要求的普通函数调用，可以记住两条：

```text
call 执行前：             RSP mod 16 = 0
callee 刚进入：          (RSP + 8) mod 16 = 0
也就是通常：             RSP mod 16 = 8
```

x86-64 psABI 的定义是：input argument area 的末端在调用前必须满足 16 字节边界；`call` 压入 8 字节返回地址后，callee 入口的 `%rsp` 指向该返回地址，因此 `%rsp + 8` 保持 16 字节对齐。

## 2. 为什么 `call` 会把对齐从 0 变成 8

假设 caller 在执行 `call target` 前：

```text
RSP = 0x...1000
RSP mod 16 = 0
```

near `call` 在 64 位模式下保存 8 字节返回地址：

```text
RSP = RSP - 8
[RSP] = return address
RIP = target
```

于是 callee 入口变为：

```text
RSP = 0x...0ff8
RSP mod 16 = 8
(RSP + 8) mod 16 = 0
```

这不是“callee 没有对齐”，而是 ABI 对函数入口的正常状态。

## 3. callee 如果还要继续调用别人，需要重新准备调用点对齐

假设 callee 刚进入时：

```text
RSP mod 16 = 8
```

如果它不做任何调整就执行另一个 `call`，那么嵌套调用点本身将是 `8 mod 16`，不满足普通 SysV AMD64 调用边界要求。

最小修正可以是：

```asm
subq $8, %rsp
call nested
addq $8, %rsp
```

变化过程：

```text
callee entry       RSP mod 16 = 8
sub $8             RSP mod 16 = 0
before nested call RSP mod 16 = 0
nested entry       RSP mod 16 = 8
return             RSP 恢复到 call 前
add $8             RSP 恢复到 outer callee 入口值
```

真实函数通常不是单纯减 8，而是根据局部变量、保存寄存器、spill 槽和栈参数整体决定 frame size。关键不是固定写 `sub $8`，而是确保**每一个实际 `call` 指令执行前**满足 ABI 要求。

## 4. `push` 会改变对齐状态

每个 64 位 `pushq` 都让 `%rsp` 减 8，因此会在两种模 16 状态之间切换：

```text
8 mod 16 --push--> 0 mod 16
0 mod 16 --push--> 8 mod 16
```

例如函数入口为 `8 mod 16`：

```asm
pushq %rbp
```

执行后 `%rsp` 变成 `0 mod 16`。如果随后直接 `call`，调用点对齐是正确的；如果又额外 `push` 一个寄存器，则再次变成 `8 mod 16`，此时在下一次 `call` 前还需要进一步调整。

因此手写汇编不能只记“prologue 里 push 了几个寄存器”，而应持续跟踪 `%rsp` 的实际变化。

## 5. 为什么编译器常用看似奇怪的栈空间大小

编译器选择 frame size 时不仅要容纳局部对象，还要同时满足：

```text
局部变量空间
callee-saved 寄存器保存
spill/reload 槽
栈上传递的 outgoing arguments
所需对象对齐
下一次 call 的 ABI 对齐
```

所以即使源代码里只有很小的局部变量，也可能看到：

```asm
subq $24, %rsp
```

而不是简单的 `subq $8` 或 `subq $16`。判断是否正确时，应从函数入口状态开始，把所有 `push/pop/sub/add` 的累计效果算到实际调用点。

## 6. 本节实验

实验入口：[`../labs/08-stack-alignment/`](../labs/08-stack-alignment/)

实验结构：

```text
C main
  ↓
probe_alignment        记录 outer callee 入口 RSP
  ↓ sub $8
记录 nested call 前 RSP
  ↓ call
nested_probe           记录 nested callee 入口 RSP
  ↓ ret
probe_alignment        恢复 RSP，返回 73
```

实际观察：

```text
outer entry:        rsp%16 = 8, (rsp+8)%16 = 0
before nested call: rsp%16 = 0
nested entry:       rsp%16 = 8, (rsp+8)%16 = 0
return:             73
```

这直接验证了“调用点对齐”和“函数入口对齐”是同一规则在 `call` 前后的两个状态。

## 7. `-O0` 与 `-O2`

本实验中 `probe_alignment` 与 `nested_probe` 使用手写汇编，因此关键 `RSP` 变化不受 C 编译器优化级别影响。C caller 分别以 `-O0` 和 `-O2` 构建，两种情况下都满足相同 ABI 边界。

这说明优化可以改变 caller 自身的 frame 和指令布局，但跨函数边界的 ABI 约束不能被改变。

## 8. 不要把用户态普通函数 ABI 与其他入口混为一谈

本节的 16 字节对齐规则属于 **System V AMD64 普通函数调用 ABI**。

以下场景不能直接套用本节的“`call` 前 0 mod 16 / callee 入口 8 mod 16”作为完整模型：

```text
Linux x86-64 syscall 入口
异常和中断入口
NMI/IST 栈切换
任务上下文切换
早期启动汇编
```

这些路径有自己的硬件压栈、入口汇编和现场布局。A13-A19 会分别结合 Linux 5.10 源码分析。

## 9. 更高对齐要求

psABI 还规定：当某些需要更高对齐的参数通过栈传递时，调用边界可能要求 32 或 64 字节对齐，例如相应的宽向量类型。

因此“16 字节”是本课程当前普通整数/指针函数调用模型的基本规则，不是所有参数组合的最高要求。

## 10. 本次实际验证

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44

-O0 构建与运行             通过
-O2 构建与运行             通过
outer entry RSP mod 16     8
outer (RSP+8) mod 16       0
nested call 前 RSP mod 16  0
nested entry RSP mod 16    8
nested (RSP+8) mod 16      0
返回值                     73
objdump AT&T               已检查
objdump Intel              已检查
nm/readelf                 已检查
GDB                        当前环境未安装，未执行
```

## 11. 本节完成后应能回答

1. 为什么 caller 在普通 `call` 前要让 `%rsp` 满足 16 字节对齐？
2. 为什么 callee 入口通常是 `%rsp mod 16 = 8`？
3. 为什么 `(rsp + 8) mod 16 = 0` 与调用点 `rsp mod 16 = 0` 是同一条规则？
4. 一个还要继续调用其他函数的 callee 为什么必须重新处理对齐？
5. `pushq`、`popq`、`subq` 和 `addq` 分别如何改变对齐状态？
6. 为什么不能把某一个固定的 `subq $N,%rsp` 当成通用模板？
7. 为什么系统调用、异常和中断入口不能直接套用普通用户态函数 ABI 的完整栈模型？

下一部分进入 A08 的 Red Zone。
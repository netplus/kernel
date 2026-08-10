# Lab 08-3 预期与实际分析

## 1. 预期函数入口状态

调用：

```c
abi_probe8(11, 22, 33, 44, 55, 66, 77, 88);
```

在 `abi_probe8` 刚进入且尚未修改 `%rsp` 时，预期：

```text
RDI = 11
RSI = 22
RDX = 33
RCX = 44
R8  = 55
R9  = 66

[RSP]      = return address
[RSP + 8]  = 77
[RSP + 16] = 88

(RSP + 8) mod 16 = 0
```

函数把八个参数相加，因此 `%rax` 预期返回：

```text
396
```

## 2. 本次实际环境

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
```

GDB 当前环境未安装，因此 `gdb.cmd` 已检查，但未实际执行。

## 3. 实际运行结果

`-O0` 与 `-O2` 两个程序均输出：

```text
regs: 11 22 33 44 55 66
stack: [rsp+8]=77 [rsp+16]=88
entry alignment: (rsp+8) mod 16 = 0
return: 396
```

程序自身还会逐项比较观察值；任何参数、对齐或返回值不符合预期都会以非零状态退出。

## 4. `-O0` caller 的关键反汇编

实际观察到 `call_probe` 使用：

```asm
push   $0x58
push   $0x4d
mov    $0x42,%r9d
mov    $0x37,%r8d
mov    $0x2c,%ecx
mov    $0x21,%edx
mov    $0x16,%esi
mov    $0xb,%edi
call   abi_probe8
add    $0x10,%rsp
```

所以在 `call` 之前：

```text
当前栈顶 = 77
其上 8 字节 = 88
```

`call` 再压入返回地址，callee 入口自然得到：

```text
[RSP]      return address
[RSP+8]    77
[RSP+16]   88
```

## 5. `-O2` caller 的关键反汇编

实际观察到：

```asm
sub    $0x8,%rsp
...
push   $0x58
...
push   $0x4d
call   abi_probe8
add    $0x18,%rsp
```

这里额外的 `sub $8,%rsp` 用来配合当前函数入口状态维持调用点对齐；两个 `push` 提供 16 字节栈参数，`call` 再压入 8 字节返回地址。

调用后 `add $0x18,%rsp` 一次回收：

```text
8 字节对齐调整
+ 16 字节栈参数
= 24 字节
```

优化版本的构造序列与 `-O0` 不同，但 callee 入口的 ABI 布局相同。

## 6. callee 的关键反汇编

AT&T 语法中关键指令为：

```asm
movq 8(%rsp), %r10
movq 16(%rsp), %r11
```

Intel 语法对应：

```asm
mov r10,QWORD PTR [rsp+0x8]
mov r11,QWORD PTR [rsp+0x10]
```

两种语法描述的是相同的两个栈参数槽。

## 7. 结论

本实验实际确认：

1. 六个 INTEGER 参数寄存器被占满后，本例额外两个 `long` 参数通过栈传递；
2. 在 callee 入口、尚未修改 `%rsp` 时，第一个和第二个栈参数位于 `8(%rsp)`、`16(%rsp)`；
3. `[rsp]` 被 `call` 保存的返回地址占据；
4. 普通调用入口满足 `(rsp+8) mod 16 == 0`；
5. caller 可以用不同指令序列构造参数区域，但函数边界上的 ABI 布局必须一致；
6. 本实验的“第 7/8 个参数上栈”只成立于八个参数都是 INTEGER 类且前六个已经耗尽通用参数寄存器的条件下。
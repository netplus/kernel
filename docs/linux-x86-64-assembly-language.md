# Linux x86-64 Assembly Language 系统学习教程

## 一、课程定位

本教程不是单纯罗列 x86 指令，而是围绕三个目标展开：

1. 能够阅读 GCC/Clang 生成的 x86-64 汇编。
2. 能够理解 Linux 用户态程序、系统调用和函数调用的底层过程。
3. 能够继续阅读 Linux kernel 5.10 中的启动、系统调用、中断、异常和上下文切换汇编。

默认环境：

```text
体系结构：x86-64
操作系统：Linux
汇编器：GNU assembler
主要语法：AT&T
辅助语法：Intel
ABI：System V AMD64 ABI
内核版本：Linux kernel 5.10
```

本教程不会在开始阶段重点讨论：

```text
复杂 SIMD/AVX 优化
CPU 流水线微架构细节
手工编写大型汇编程序
16 位 BIOS 编程
复杂浮点计算
```

这些内容将在掌握基本执行模型后再扩展。

---

# 第 0 章：实验环境与汇编学习方法

## 0.1 为什么汇编必须结合实验

汇编语言中很多概念单靠文字很难形成准确认识，例如：

```text
mov 是复制数值还是复制地址？
call 到底向栈中压入了什么？
cmp 为什么不保存结果？
写 EAX 为什么会改变整个 RAX？
栈帧为什么有时存在，有时不存在？
```

最有效的学习方法不是背诵指令，而是反复进行：

```text
编写 C/汇编程序
    ↓
编译
    ↓
反汇编
    ↓
单步执行
    ↓
观察寄存器、内存和栈
```

## 0.2 推荐工具

安装：

```bash
sudo apt install build-essential binutils gdb
```

核心工具：

```text
gcc        编译和生成汇编
as         GNU 汇编器
ld         GNU 链接器
objdump    反汇编和查看目标文件
readelf    分析 ELF 文件
nm         查看符号表
gdb        动态调试
addr2line  地址到源代码映射
```

推荐编译参数：

```bash
gcc -Og -g \
    -fno-omit-frame-pointer \
    -fno-stack-protector \
    -no-pie \
    demo.c -o demo
```

这些参数的意义：

```text
-Og
保留基本优化，同时便于调试。

-g
生成 DWARF 调试信息。

-fno-omit-frame-pointer
保留 RBP 栈帧，方便观察函数调用。

-fno-stack-protector
暂时去掉栈保护代码，减少干扰。

-no-pie
生成固定地址布局，便于理解代码地址和重定位。
```

常用反汇编命令：

```bash
objdump -drS demo
objdump -drS -Mintel demo
```

其中：

```text
-d   反汇编代码段
-r   显示重定位
-S   混合显示源代码和汇编
```

---

# 第 1 章：CPU 执行模型

## 1.1 背景：高级语言抽象最终会消失

C 语言中存在：

```c
变量
表达式
循环
函数
结构体
指针
```

但 CPU 并不直接认识这些概念。CPU 只执行机器指令，操作：

```text
寄存器
内存
标志位
指令地址
```

例如：

```c
long result = a + b;
```

最终可能变成：

```asm
movq %rdi, %rax
addq %rsi, %rax
```

因此，学习汇编的第一步不是背指令，而是建立 CPU 状态模型。

## 1.2 CPU 可见的核心状态

执行一条普通指令时，需要重点观察：

```text
RIP       下一条要执行的指令地址
通用寄存器 当前正在处理的数据
RSP       当前栈顶
RFLAGS    运算产生的条件状态
内存       代码和数据
```

CPU 的基本执行过程可以抽象为：

```text
从 RIP 取指令
    ↓
译码
    ↓
读取操作数
    ↓
执行运算
    ↓
写回结果
    ↓
更新 RFLAGS
    ↓
计算下一条 RIP
```

## 1.3 x86 指令为什么是变长的

x86 指令长度不是固定的，一条指令可能占用 1～15 字节。

例如：

```asm
ret
```

通常只有一个字节。

而一条带前缀、立即数和复杂寻址的指令可能占用十多个字节。

这是 x86 长期保持向后兼容的结果。新处理器必须继续执行早期 8086、80386 时代的指令编码。

设计上的收益是：

```text
兼容性强
代码密度高
寻址方式丰富
```

代价是：

```text
译码复杂
指令边界不固定
硬件前端实现更复杂
```

## 1.4 示例：简单控制流

```asm
movq $3, %rax
addq $4, %rax
cmpq $7, %rax
jne .Lerror
```

执行过程：

```text
第一条：
RAX = 3

第二条：
RAX = 7
RFLAGS 被更新

第三条：
内部计算 RAX - 7
结果为 0，因此 ZF = 1

第四条：
jne 在 ZF = 0 时跳转
当前 ZF = 1，因此不跳转
```

这一示例涉及四个核心问题：

```text
数据存放在哪里
指令如何修改数据
比较结果存放在哪里
下一条指令地址如何确定
```

## 1.5 本章实验

在 GDB 中执行：

```gdb
start
display/i $pc
display/x $rax
display/t $eflags
si
```

观察每执行一条指令后：

```text
RIP 如何变化
RAX 如何变化
ZF 如何变化
```

---

# 第 2 章：寄存器与数据宽度

## 2.1 背景：寄存器是 CPU 最直接的工作区

CPU 对内存的访问通常比寄存器慢。编译器会尽量把：

```text
函数参数
临时计算结果
循环变量
指针
返回值
```

保存在寄存器中。

x86-64 提供 16 个主要通用寄存器：

```text
RAX RBX RCX RDX
RSI RDI RBP RSP
R8  R9  R10 R11
R12 R13 R14 R15
```

特殊寄存器：

```text
RIP       指令指针
RFLAGS    状态标志
```

## 2.2 为什么一个寄存器有多个名字

以 RAX 为例：

```text
RAX   64 位
EAX   低 32 位
AX    低 16 位
AL    低 8 位
AH    第 8～15 位
```

这是 x86 向后兼容历史形成的。

早期 8086 只有 AX，后来扩展为 EAX，再扩展为 RAX，但旧程序仍然必须能够运行。

## 2.3 32 位写入为什么会清零高 32 位

执行：

```asm
movl $1, %eax
```

最终：

```text
RAX = 0x0000000000000001
```

不是：

```text
RAX 高 32 位保持不变
```

这是 x86-64 的明确架构规则。

设计原因之一是减少寄存器部分写入产生的数据依赖。CPU 可以确认整个 RAX 的结果，而不必等待旧 RAX 高位。

但执行：

```asm
movw $1, %ax
```

不会清除 RAX 高 48 位。

执行：

```asm
movb $1, %al
```

也不会清除 RAX 高 56 位。

## 2.4 示例：部分寄存器修改

假设：

```text
RAX = 0x1122334455667788
```

执行：

```asm
movb $0xff, %al
```

结果：

```text
RAX = 0x11223344556677ff
```

执行：

```asm
movw $0xabcd, %ax
```

结果：

```text
RAX = 0x112233445566abcd
```

执行：

```asm
movl $0x12345678, %eax
```

结果：

```text
RAX = 0x0000000012345678
```

## 2.5 本章重点问题

需要明确区分：

```text
寄存器名称决定访问宽度
指令后缀决定操作宽度
数据宽度决定符号扩展方式
32 位寄存器写入具有特殊清零语义
```

---

# 第 3 章：立即数、寄存器和内存操作数

## 3.1 三种基本操作数

汇编中的数据通常来自：

```text
立即数
寄存器
内存
```

立即数：

```asm
movq $100, %rax
```

表示：

```text
RAX = 100
```

寄存器：

```asm
movq %rbx, %rax
```

表示：

```text
RAX = RBX
```

内存：

```asm
movq (%rbx), %rax
```

表示：

```text
从 RBX 指向的内存地址读取 8 字节
将结果写入 RAX
```

## 3.2 地址与地址处的数据必须严格区分

下面两条指令含义完全不同：

```asm
movq %rbx, %rax
movq (%rbx), %rax
```

第一条：

```c
rax = rbx;
```

第二条：

```c
rax = *(uint64_t *)rbx;
```

可以把括号理解为 C 语言中的解引用操作。

## 3.3 x86 为什么不允许普通 mov 内存到内存

下面的形式通常不合法：

```asm
movq (%rax), (%rbx)
```

因为大多数普通 x86 指令要求：

```text
最多只有一个显式内存操作数
```

需要通过寄存器中转：

```asm
movq (%rax), %rcx
movq %rcx, (%rbx)
```

这种设计降低了通用指令执行时的复杂度。

不过 x86 也存在字符串指令：

```asm
movsb
movsq
rep movsb
```

可以完成内存到内存复制，但它们使用隐含寄存器和专用语义。

---

# 第 4 章：x86-64 内存寻址

## 4.1 背景：高级语言大量依赖地址计算

数组访问：

```c
array[i]
```

结构体成员访问：

```c
obj->field
```

二维数组：

```c
matrix[row][column]
```

最终都要转换成地址计算。

x86 为此提供了非常灵活的寻址模式。

## 4.2 基址、索引、比例和位移

AT&T 形式：

```text
disp(base, index, scale)
```

有效地址：

```text
address = disp + base + index × scale
```

其中 scale 只能是：

```text
1
2
4
8
```

这刚好对应常见 C 类型大小：

```text
char       1 字节
short      2 字节
int        4 字节
long       8 字节
```

## 4.3 数组访问示例

C 代码：

```c
long get(long *array, long i)
{
    return array[i];
}
```

参数：

```text
RDI = array 首地址
RSI = i
```

汇编：

```asm
movq (%rdi,%rsi,8), %rax
ret
```

有效地址：

```text
RDI + RSI × 8
```

读取 8 字节后放入 RAX。

## 4.4 结构体成员访问示例

```c
struct item {
    int id;
    int flags;
    long value;
};

long get_value(struct item *p)
{
    return p->value;
}
```

典型布局：

```text
偏移 0：id       4 字节
偏移 4：flags    4 字节
偏移 8：value    8 字节
```

汇编：

```asm
movq 8(%rdi), %rax
ret
```

这里：

```text
RDI 是结构体地址
8 是 value 成员偏移
```

## 4.5 RIP 相对寻址

位置无关代码经常使用：

```asm
movq global_var(%rip), %rax
```

有效地址：

```text
下一条指令地址 + 编码中的相对位移
```

这种方式使代码不依赖固定装载地址，是：

```text
PIE
共享库
内核地址随机化
模块重定位
```

的重要基础。

---

# 第 5 章：mov、lea 和数据扩展

## 5.1 mov 的本质

`mov` 负责复制数据，但不会改变源操作数。

```asm
movq %rdi, %rax
```

表示：

```text
读取 RDI
写入 RAX
RDI 保持不变
```

## 5.2 lea 为什么非常重要

`lea` 原意是：

```text
Load Effective Address
```

例如：

```asm
leaq 8(%rdi,%rsi,4), %rax
```

计算：

```text
RAX = RDI + RSI × 4 + 8
```

注意：`lea` 不访问该地址处的内存。

对比：

```asm
leaq 8(%rdi), %rax
```

表示：

```text
RAX = RDI + 8
```

而：

```asm
movq 8(%rdi), %rax
```

表示：

```text
RAX = *(uint64_t *)(RDI + 8)
```

## 5.3 编译器为什么用 lea 做算术

C 代码：

```c
long f(long x)
{
    return x * 5 + 3;
}
```

可能生成：

```asm
leaq 3(%rdi,%rdi,4), %rax
ret
```

因为：

```text
RDI + RDI × 4 + 3
= 5 × RDI + 3
```

`lea` 通常不修改 RFLAGS，因此特别适合在不破坏已有条件标志的情况下做地址或整数计算。

## 5.4 符号扩展与零扩展

假设：

```c
signed char c = -1;
long x = c;
```

需要符号扩展：

```asm
movsbq %dil, %rax
```

将 8 位有符号数扩展为 64 位：

```text
0xff → 0xffffffffffffffff
```

如果是：

```c
unsigned char c = 255;
unsigned long x = c;
```

需要零扩展：

```asm
movzbl %dil, %eax
```

结果：

```text
0xff → 0x00000000000000ff
```

常见指令：

```text
movzb  零扩展 byte
movzw  零扩展 word
movsb  符号扩展 byte
movsw  符号扩展 word
movslq 符号扩展 32 位到 64 位
```

---

# 第 6 章：算术、位运算和 RFLAGS

## 6.1 背景：有符号和无符号使用相同二进制加法器

CPU 执行：

```asm
addq %rbx, %rax
```

时，并不知道程序员把数据理解为：

```text
signed long
unsigned long
指针偏移
位图
```

加法过程相同，区别主要体现在后续如何解释标志位。

## 6.2 关键标志位

```text
ZF：结果是否为 0
SF：结果最高位是否为 1
CF：无符号进位或借位
OF：有符号溢出
```

例如 8 位运算：

```text
0xff + 1 = 0x00
```

产生：

```text
CF = 1
ZF = 1
```

有符号运算：

```text
127 + 1 = -128
```

产生：

```text
OF = 1
SF = 1
```

## 6.3 cmp 的设计

```asm
cmpq %rsi, %rdi
```

内部执行：

```text
RDI - RSI
```

但不保存结果，只更新 RFLAGS。

这使比较操作无需额外寄存器保存临时结果。

## 6.4 test 的设计

```asm
testq %rax, %rax
```

内部执行：

```text
RAX & RAX
```

不保存结果，只更新标志位。

判断是否为零：

```asm
testq %rax, %rax
je .Lzero
```

通常比：

```asm
cmpq $0, %rax
```

编码更紧凑。

## 6.5 有符号和无符号比较

执行：

```asm
cmpq %rsi, %rdi
```

后，有符号条件：

```text
jg   大于
jge  大于等于
jl   小于
jle  小于等于
```

无符号条件：

```text
ja   高于
jae  高于等于
jb   低于
jbe  低于等于
```

例如：

```text
RDI = 0xffffffffffffffff
RSI = 1
```

把 RDI 看成有符号数：

```text
-1 < 1
```

把 RDI 看成无符号数：

```text
18446744073709551615 > 1
```

因此：

```text
jl 条件成立
ja 条件也成立
```

这不是矛盾，而是同一位模式的两种解释。

## 6.6 乘法和除法

简单乘法：

```asm
imulq %rsi, %rax
```

表示：

```text
RAX = RAX × RSI
```

完整宽度乘法常涉及：

```text
RDX:RAX
```

64 位除法：

```asm
cqto
idivq %rsi
```

其中：

```text
被除数：RDX:RAX
商：RAX
余数：RDX
```

`cqto` 将 RAX 的符号扩展到 RDX。

---

# 第 7 章：条件跳转、循环和条件移动

## 7.1 背景：高级语言控制流必须转换为 RIP 变化

C 中的：

```text
if
else
for
while
switch
```

在 CPU 层面主要表现为：

```text
比较
修改标志位
条件跳转
无条件跳转
```

## 7.2 if 示例

```c
long abs_value(long x)
{
    if (x < 0)
        return -x;
    return x;
}
```

可能生成：

```asm
movq %rdi, %rax
testq %rdi, %rdi
jns .Ldone
negq %rax

.Ldone:
ret
```

分析：

```text
RDI 保存参数 x
RAX 先保存默认返回值 x
test 判断符号
jns 表示 SF = 0 时跳转
若 x 为负，则执行 neg
```

## 7.3 条件移动

优化后可能生成：

```asm
movq %rdi, %rax
negq %rax
cmovs %rdi, %rax
ret
```

或者其他等价形式。

条件移动的设计目标是减少短小分支带来的分支预测失败，但它也有局限：

```text
源操作数仍然可能被计算
长路径不适合条件移动
复杂内存访问可能不适合无条件执行
```

因此，`cmov` 并不总是优于跳转。

## 7.4 循环示例

```c
long sum(long *array, long n)
{
    long result = 0;

    for (long i = 0; i < n; i++)
        result += array[i];

    return result;
}
```

可能生成：

```asm
xorl %eax, %eax
xorl %edx, %edx

.Lloop:
cmpq %rsi, %rdx
jge .Ldone

addq (%rdi,%rdx,8), %rax
incq %rdx
jmp .Lloop

.Ldone:
ret
```

寄存器角色：

```text
RDI：array
RSI：n
RDX：i
RAX：result
```

## 7.5 switch 与跳转表

分支较多且 case 连续时，编译器可能生成跳转表：

```text
检查索引范围
    ↓
根据 case 值计算表项地址
    ↓
从表中读取目标地址
    ↓
间接跳转
```

典型形式：

```asm
jmp *.Ltable(,%rax,8)
```

这说明 `switch` 不一定会被翻译为一连串 `cmp/jne`。

---

# 第 8 章：栈、call、ret 与函数调用 ABI

## 8.1 为什么需要 ABI

单独一个编译器可以任意决定参数放在哪里，但不同编译器、不同源文件和不同语言必须互相调用。

ABI 规定：

```text
参数放在哪里
返回值放在哪里
哪些寄存器必须保存
栈如何对齐
结构体如何传递
浮点参数如何传递
可变参数如何处理
```

CPU 不会检查 ABI。ABI 是软件之间的约定。

## 8.2 System V AMD64 整数参数传递

前六个整数或指针参数：

```text
参数 1：RDI
参数 2：RSI
参数 3：RDX
参数 4：RCX
参数 5：R8
参数 6：R9
```

更多参数通过栈传递。

返回值：

```text
RAX
```

较大的返回对象可能通过调用者提供的隐藏指针返回。

## 8.3 call 的真实行为

```asm
call foo
```

核心行为：

```text
RSP = RSP - 8
memory[RSP] = call 后面一条指令的地址
RIP = foo
```

`call` 压入的是返回地址，不是调用者函数地址。

## 8.4 ret 的真实行为

```asm
ret
```

核心行为：

```text
RIP = memory[RSP]
RSP = RSP + 8
```

因此，栈中的返回地址一旦被破坏，程序就可能跳转到错误位置。

## 8.5 调用者保存与被调用者保存

调用者保存：

```text
RAX RCX RDX RSI RDI R8 R9 R10 R11
```

调用者在 `call` 后不能假设这些寄存器仍保持原值。

被调用者保存：

```text
RBX RBP R12 R13 R14 R15
```

被调用函数若修改它们，必须在返回前恢复。

## 8.6 栈对齐

System V AMD64 ABI 要求函数调用边界满足特定的 16 字节对齐规则。

正确对齐主要服务于：

```text
SSE/AVX 数据访问
编译器生成代码的一致性
函数间互操作
```

手写汇编调用 libc 函数时，栈对齐错误可能导致崩溃。

## 8.7 Red Zone

用户态 ABI 在 RSP 下方保留 128 字节 Red Zone。

叶子函数可以使用：

```text
[RSP - 128, RSP - 1]
```

而不调整 RSP。

但是 Linux 内核不使用 Red Zone，内核编译通常带：

```text
-mno-red-zone
```

原因是中断和异常可能在当前栈上保存状态，覆盖 RSP 以下区域。

## 8.8 详细函数调用示例

C 代码：

```c
long calc(long a, long b, long *out)
{
    long tmp = a + b;
    *out = tmp;
    return tmp * 2;
}
```

优化汇编可能是：

```asm
calc:
    leaq (%rdi,%rsi), %rax
    movq %rax, (%rdx)
    addq %rax, %rax
    ret
```

逐条分析。

入口状态：

```text
RDI = a
RSI = b
RDX = out
```

第一条：

```asm
leaq (%rdi,%rsi), %rax
```

计算：

```text
RAX = a + b
```

第二条：

```asm
movq %rax, (%rdx)
```

把 `a + b` 写入 `out` 指向的内存：

```c
*out = tmp;
```

第三条：

```asm
addq %rax, %rax
```

计算：

```text
RAX = 2 × tmp
```

第四条：

```asm
ret
```

返回后，调用者从 RAX 取得返回值。

该函数没有建立栈帧，因为：

```text
没有调用其他函数
没有寄存器溢出
没有必须位于内存中的局部变量
不需要保存被调用者保存寄存器
```

---

# 第 9 章：编译器如何翻译 C 语言

## 9.1 背景：汇编不是 C 代码的逐行替换

优化编译器会执行：

```text
常量折叠
死代码删除
公共子表达式消除
寄存器分配
函数内联
循环展开
强度削弱
分支合并
别名分析
```

因此，C 源代码中的一行不一定对应某条固定汇编。

## 9.2 局部变量不一定存在于栈中

```c
long f(long a)
{
    long x = a + 1;
    return x * 2;
}
```

优化后可能只有：

```asm
leaq 2(%rdi,%rdi), %rax
ret
```

变量 `x` 没有独立存储位置。

它只是编译器中间表示里的临时值。

## 9.3 指针与数组的等价性

```c
array[i]
```

在语义上接近：

```c
*(array + i)
```

汇编体现为：

```asm
movq (%rdi,%rsi,8), %rax
```

因此阅读数组汇编时应还原：

```text
基址
索引
元素大小
成员偏移
```

## 9.4 结构体对齐和填充

```c
struct example {
    char a;
    long b;
};
```

通常不是 9 字节，而可能是 16 字节：

```text
偏移 0：a
偏移 1～7：padding
偏移 8：b
```

汇编中的成员偏移可以帮助反推出结构体布局。

## 9.5 volatile 的作用边界

`volatile` 主要约束编译器：

```text
不能随意删除访问
不能随意合并访问
每次访问需要真实发生
```

但它不自动提供：

```text
CPU 内存屏障
线程同步
原子性
缓存一致性协议控制
```

在 Linux 内核中不能把 `volatile` 当作完整并发同步机制。

---

# 第 10 章：ELF、符号、重定位和动态链接

## 10.1 背景：编译和链接为什么分开

大型程序由多个源文件和库组成：

```text
main.c
net.c
util.c
libc.so
其他共享库
```

编译器无法在编译单个源文件时知道所有最终地址，因此需要：

```text
符号
重定位
链接
```

## 10.2 ELF 的主要组成

常见节：

```text
.text      机器代码
.rodata    只读常量
.data      已初始化全局变量
.bss       未显式初始化的全局变量
.symtab    完整符号表
.dynsym    动态链接符号表
.rela.*    重定位信息
.plt       过程链接表
.got       全局偏移表
```

## 10.3 查看 ELF

```bash
readelf -h demo
readelf -S demo
readelf -s demo
readelf -r demo
objdump -dr demo
```

需要区分：

```text
节 Section
描述链接视角的代码和数据组织。

段 Segment
描述运行时如何映射到进程虚拟地址空间。
```

## 10.4 外部函数调用

调用动态库函数可能看到：

```asm
call printf@PLT
```

PLT 和 GOT 的设计目的是：

```text
允许代码位置无关
支持共享库
支持运行时符号解析
支持延迟绑定
```

第一次调用时，动态链接器可能参与符号解析；后续调用通常通过 GOT 中缓存的真实地址跳转。

## 10.5 全局变量访问

位置无关代码常见：

```asm
movq global_var(%rip), %rax
```

或者通过 GOT：

```asm
movq global_var@GOTPCREL(%rip), %rax
movq (%rax), %rax
```

是否经过 GOT 取决于：

```text
符号可见性
是否跨共享对象
编译选项
链接方式
```

---

# 第 11 章：Linux x86-64 系统调用

## 11.1 背景：普通函数调用不能直接进入内核

用户态代码运行在较低特权级，不能直接：

```text
修改页表
操作设备
访问内核地址
关闭中断
配置调度器
```

系统调用提供受控入口。

典型过程：

```text
用户态准备系统调用号和参数
    ↓
执行 syscall
    ↓
CPU 切换到内核入口
    ↓
内核保存用户态上下文
    ↓
分发到具体系统调用
    ↓
返回用户态
```

## 11.2 系统调用 ABI

Linux x86-64：

```text
RAX：系统调用号
RDI：参数 1
RSI：参数 2
RDX：参数 3
R10：参数 4
R8 ：参数 5
R9 ：参数 6
```

返回值：

```text
RAX
```

错误通常编码为负 errno：

```text
-EPERM
-ENOENT
-EINVAL
```

libc 包装函数会把负错误转换为：

```text
返回 -1
设置 errno
```

## 11.3 为什么第四个参数使用 R10

普通函数第四个参数在 RCX。

但 `syscall` 指令会使用：

```text
RCX 保存用户态返回 RIP
R11 保存用户态 RFLAGS
```

因此 Linux 系统调用 ABI 改用 R10 传递第四个参数。

## 11.4 原始 write 系统调用示例

```asm
    .section .rodata
msg:
    .ascii "hello\n"

    .section .text
    .global _start

_start:
    movq $1, %rax
    movq $1, %rdi
    leaq msg(%rip), %rsi
    movq $6, %rdx
    syscall

    movq $60, %rax
    xorl %edi, %edi
    syscall
```

第一个系统调用：

```text
RAX = 1        write
RDI = 1        stdout
RSI = msg      buffer
RDX = 6        length
```

第二个系统调用：

```text
RAX = 60       exit
RDI = 0        status
```

编译：

```bash
gcc -nostdlib -no-pie hello.s -o hello
```

## 11.5 Linux kernel 5.10 入口路径

核心源码：

```text
arch/x86/entry/entry_64.S
arch/x86/entry/common.c
arch/x86/include/asm/syscall.h
```

核心入口：

```text
entry_SYSCALL_64
do_syscall_64
```

高层执行路径：

```text
用户态 syscall
    ↓
CPU 将用户 RIP 保存到 RCX
CPU 将用户 RFLAGS 保存到 R11
CPU 从 IA32_LSTAR 获取内核入口
    ↓
entry_SYSCALL_64
    ↓
swapgs
保存用户 RSP
构造 pt_regs
    ↓
do_syscall_64
    ↓
根据 RAX 查系统调用表
    ↓
执行 __x64_sys_xxx
    ↓
处理返回用户态前工作
    ↓
sysretq 或 iretq
```

需要特别注意：

```text
syscall 不会自动保存全部通用寄存器
syscall 不会自动切换到内核栈
这些工作由入口汇编完成
```

---

# 第 12 章：异常、中断与 IDT

## 12.1 背景：控制流不总是由当前程序主动决定

事件可能来自：

```text
除零
非法指令
缺页
断点
外部设备中断
本地 APIC 定时器
不可屏蔽中断
机器检查
```

这些事件会打断当前执行流，进入内核处理程序。

## 12.2 异常与中断

异常通常由当前指令同步触发：

```text
#PF 缺页异常
#GP 通用保护异常
#UD 非法指令
#DE 除法错误
```

外部中断通常是异步事件：

```text
网卡中断
磁盘完成中断
时钟中断
IPI
```

## 12.3 IDT 的作用

IDT 是中断描述符表。

每个向量描述：

```text
入口地址
代码段
门类型
特权级
IST 配置
```

CPU 根据中断向量查找对应入口。

## 12.4 为什么需要统一入口框架

不同异常的硬件入栈内容不完全一致。

有些异常自动压入错误码：

```text
#PF
#GP
#SS
```

有些异常不压入错误码。

入口汇编通常会对这些差异进行归一化，使后续 C 代码看到相对统一的 `pt_regs` 结构。

## 12.5 缺页异常示例路径

Linux 5.10 中可以重点跟踪：

```text
arch/x86/include/asm/idtentry.h
arch/x86/entry/entry_64.S
arch/x86/mm/fault.c
```

概念路径：

```text
CPU 访问无效页
    ↓
产生 #PF
    ↓
根据 IDT 进入页故障入口
    ↓
保存寄存器
    ↓
读取 CR2 获取故障虚拟地址
    ↓
exc_page_fault
    ↓
handle_page_fault
    ↓
用户态缺页、写时复制或非法访问处理
```

## 12.6 sysretq 与 iretq

`sysretq`：

```text
速度较快
适合普通系统调用返回
使用 RCX 和 R11 恢复 RIP/RFLAGS
对返回状态有约束
```

`iretq`：

```text
通用性更强
可恢复完整特权级返回状态
适用于异常、中断和特殊系统调用返回路径
成本通常更高
```

---

# 第 13 章：上下文切换

## 13.1 背景：调度器必须暂停一个任务并运行另一个任务

任务切换时，内核需要保证：

```text
任务 A 以后能够从原位置继续
任务 B 能够恢复自己的执行状态
```

但并不需要在一个位置保存所有寄存器。

一部分寄存器已经由函数调用约定、内核栈和异常入口保存。

## 13.2 Linux 5.10 关键源码

```text
arch/x86/include/asm/switch_to.h
arch/x86/entry/entry_64.S
arch/x86/kernel/process_64.c
kernel/sched/core.c
```

重点函数：

```text
context_switch
switch_to
__switch_to_asm
__switch_to
```

## 13.3 核心设计

每个任务拥有自己的内核栈。

切换时最关键的动作之一是：

```text
保存当前任务 RSP
加载下一个任务 RSP
```

一旦 RSP 切换，CPU 当前看到的：

```text
返回地址
保存寄存器
局部变量
调用链
```

都变成另一个任务的内核栈内容。

## 13.4 概念模型

```asm
pushq %rbp
pushq %rbx
pushq %r12
pushq %r13
pushq %r14
pushq %r15

movq %rsp, prev_saved_rsp
movq next_saved_rsp, %rsp

popq %r15
popq %r14
popq %r13
popq %r12
popq %rbx
popq %rbp

ret
```

这只是概念化示例，但体现了核心思想：

```text
保存被调用者保存寄存器
保存旧栈指针
恢复新栈指针
恢复新任务寄存器
从新任务栈中的返回地址继续执行
```

## 13.5 地址空间切换

不同进程可能使用不同页表。

上下文切换还可能涉及：

```text
CR3
PCID
TLB
KPTI
内核线程地址空间借用
```

但线程切换不一定总是需要完整切换地址空间。例如同一进程中的线程共享 `mm_struct`。

---

# 第 14 章：Linux x86-64 启动汇编

## 14.1 背景：CPU 上电时并不直接处于 64 位内核环境

传统 x86 启动需要经历多个模式：

```text
实模式
    ↓
保护模式
    ↓
开启 PAE
    ↓
建立初始页表
    ↓
开启 long mode
    ↓
进入 64 位内核
```

即使现代系统通过 UEFI 启动，内核仍需要处理复杂的早期环境和兼容路径。

## 14.2 关键源码

```text
arch/x86/boot/header.S
arch/x86/boot/main.c
arch/x86/boot/compressed/head_64.S
arch/x86/kernel/head_64.S
```

## 14.3 为什么启动必须大量使用汇编

C 代码运行通常依赖：

```text
可用栈
稳定调用约定
正确页表
正确段寄存器
已初始化全局变量
重定位完成
```

启动早期这些条件尚未全部成立，因此必须用汇编手工建立运行环境。

## 14.4 启动阶段重点问题

需要逐层理解：

```text
内核镜像从哪里装载
解压代码运行在哪里
页表如何建立
如何启用 CR0.PG
如何配置 EFER.LME
如何加载 CR3
如何跳入 64 位代码段
如何处理内核重定位
如何进入 start_kernel
```

## 14.5 学习策略

不要一开始逐条分析整个 `head_64.S`。

应先建立阶段模型：

```text
当前 CPU 模式
当前代码地址
当前栈在哪里
当前页表在哪里
下一阶段要建立什么条件
```

再沿控制流逐段展开。

---

# 第 15 章：GCC 内联汇编

## 15.1 背景：内联汇编不只是把指令写进 C 代码

编译器必须知道汇编代码：

```text
读取了哪些值
写入了哪些值
破坏了哪些寄存器
是否修改标志位
是否访问内存
能否被移动或删除
```

如果约束描述错误，即使汇编指令本身正确，程序仍可能被编译器优化破坏。

## 15.2 基本格式

```c
asm volatile (
    "汇编模板"
    : 输出操作数
    : 输入操作数
    : clobber
);
```

## 15.3 示例

```c
static inline long add(long a, long b)
{
    long result;

    asm (
        "addq %2, %0"
        : "=r" (result)
        : "0" (a), "r" (b)
        : "cc"
    );

    return result;
}
```

解释：

```text
"=r" (result)
输出结果必须放入通用寄存器。

"0" (a)
输入 a 与第 0 个输出使用同一个位置。

"r" (b)
输入 b 放入任意通用寄存器。

"cc"
汇编修改了条件码寄存器。
```

## 15.4 volatile 的准确含义

`asm volatile` 主要告诉编译器：

```text
不要因为输出看似未使用就删除
不要随意合并或移除该汇编
```

它不自动等价于完整内存屏障。

如果汇编可能影响编译器看不到的内存，需要：

```c
asm volatile ("" ::: "memory");
```

`"memory"` clobber 是编译器级内存屏障，不一定生成 CPU 屏障指令。

## 15.5 内核常见相关代码

```text
arch/x86/include/asm/barrier.h
arch/x86/include/asm/cmpxchg.h
arch/x86/include/asm/atomic.h
arch/x86/include/asm/irqflags.h
```

---

# 第 16 章：原子操作和内存顺序

## 16.1 背景：多核环境下普通读写并不够

多个 CPU 并发访问共享数据时，需要处理：

```text
原子性
可见性
执行顺序
编译器重排
CPU 重排
缓存一致性
```

这些是不同问题，不能混为一谈。

## 16.2 lock 前缀

例如：

```asm
lock addl $1, (%rdi)
```

保证对应读改写操作具有原子性。

现代 x86 通常通过缓存一致性协议完成，不一定真的锁住整个内存总线。

## 16.3 cmpxchg

概念语义：

```text
如果内存值等于 RAX：
    把新值写入内存
    ZF = 1
否则：
    把内存当前值读入 RAX
    ZF = 0
```

这是：

```text
无锁算法
原子变量
自旋锁
引用计数
状态机
```

的重要基础。

## 16.4 编译器屏障与 CPU 屏障

编译器屏障：

```c
asm volatile ("" ::: "memory");
```

限制编译器重排，但不一定发出硬件指令。

CPU 屏障：

```text
mfence
lfence
sfence
带 lock 的操作
```

影响 CPU 和内存系统可观察的顺序。

Linux 内核通常使用抽象接口：

```text
barrier()
smp_mb()
smp_rmb()
smp_wmb()
READ_ONCE()
WRITE_ONCE()
```

而不是在通用代码中直接写具体 x86 指令。

## 16.5 x86 内存模型的特点

x86 内存顺序相对较强，但不是“完全顺序执行”。

尤其需要理解：

```text
Store Buffer
Store → Load 重排效果
非缓存内存
设备 MMIO
编译器重排
```

即使运行在 x86 上，也不能省略内核同步原语。

---

# 第 17 章：反汇编、GDB 与源码分析方法

## 17.1 静态分析

推荐命令：

```bash
objdump -drS file.o
objdump -d -Mintel executable
readelf -s executable
readelf -r file.o
nm -n executable
```

分析顺序：

```text
定位函数符号
确定函数入口
识别参数寄存器
划分基本块
标记跳转关系
识别栈帧
识别函数调用
还原数据结构访问
```

## 17.2 GDB 动态分析

常用命令：

```gdb
disassemble /m function
disassemble /r function
break function
run
si
ni
info registers
x/16gx $rsp
x/10i $rip
bt
frame 1
```

观察栈：

```gdb
x/16gx $rsp
```

观察当前指令：

```gdb
x/i $rip
```

自动显示：

```gdb
display/i $pc
display/x $rax
display/x $rsp
```

## 17.3 分析未知函数的固定流程

面对一段未知汇编，可按以下步骤进行。

第一步：确定 ABI 输入。

```text
RDI、RSI、RDX 等分别可能是什么参数？
```

第二步：确定返回值。

```text
最终哪个值进入 RAX？
```

第三步：分析栈。

```text
RSP 减少了多少？
保存了哪些寄存器？
局部变量位于哪些偏移？
```

第四步：划分基本块。

```text
每个跳转目标是一个新的基本块。
```

第五步：恢复条件。

```text
cmp 的目标减去源是什么？
后续是有符号还是无符号跳转？
```

第六步：恢复数据结构。

```text
8(%rdi) 可能是什么成员？
(%rdi,%rax,8) 可能是什么数组？
```

第七步：结合动态调试验证。

---

# 第 18 章：Linux kernel 5.10 汇编阅读专题

完成前面章节后，进入四条内核主线。

## 18.1 系统调用入口

源码：

```text
arch/x86/entry/entry_64.S
arch/x86/entry/common.c
```

目标：

```text
理解 syscall 如何进入内核
理解 pt_regs 如何构造
理解系统调用号如何分发
理解 sysretq/iretq 返回选择
```

## 18.2 中断与异常入口

源码：

```text
arch/x86/entry/entry_64.S
arch/x86/include/asm/idtentry.h
arch/x86/kernel/idt.c
```

目标：

```text
理解硬件自动入栈内容
理解错误码归一化
理解用户态和内核态异常差异
理解 irqentry_enter/exit
```

## 18.3 上下文切换

源码：

```text
arch/x86/entry/entry_64.S
arch/x86/include/asm/switch_to.h
arch/x86/kernel/process_64.c
```

目标：

```text
理解任务内核栈切换
理解 callee-saved 寄存器保存
理解 switch_to 返回语义
理解 mm、CR3 和 TLS 切换
```

## 18.4 内核启动

源码：

```text
arch/x86/boot/
arch/x86/boot/compressed/
arch/x86/kernel/head_64.S
```

目标：

```text
理解实模式到长模式
理解初始页表
理解内核解压
理解物理地址与虚拟地址转换
理解 start_kernel 之前的环境建立
```

---

# 课程阶段安排

## 第一阶段：汇编基本执行模型

学习内容：

```text
第 0～7 章
```

学习结果：

```text
能够理解寄存器、内存、标志位和控制流
能够阅读简单函数和循环
能够区分地址计算与内存访问
```

## 第二阶段：ABI 与编译器

学习内容：

```text
第 8～10 章
```

学习结果：

```text
能够分析函数调用
能够理解栈帧和寄存器保存
能够从汇编恢复数组和结构体访问
能够理解 ELF、符号和重定位
```

## 第三阶段：Linux 底层入口

学习内容：

```text
第 11～14 章
```

学习结果：

```text
能够理解系统调用入口
能够理解异常和中断
能够理解上下文切换
能够阅读早期启动汇编
```

## 第四阶段：内核并发和高级汇编

学习内容：

```text
第 15～18 章
```

学习结果：

```text
能够阅读 GCC 内联汇编
能够理解原子操作和内存屏障
能够独立分析 Linux kernel 5.10 关键汇编路径
```

---

# 每章统一学习方法

后续逐章展开时，每一章都采用以下结构：

```text
1. 问题背景
2. CPU 或操作系统设计考虑
3. 核心概念
4. 最小汇编示例
5. 对应 C 代码
6. 指令逐条执行分析
7. GDB 动态验证
8. GCC 优化前后对比
9. Linux kernel 5.10 中的实际应用
10. 常见错误和思考题
```

最终目标不是记住所有指令，而是形成稳定的分析能力：

```text
看到汇编
    ↓
确定输入和输出
    ↓
追踪寄存器和内存
    ↓
恢复控制流
    ↓
恢复高级语义
    ↓
理解背后的 ABI 和架构设计
```

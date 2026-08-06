# 第 2 课：地址、解引用、复杂寻址与 `lea`

## 1. 本课目标

完成本课后，应能够：

1. 严格区分“数值”“地址”和“地址处的数据”；
2. 准确解释 AT&T 语法中的括号和位移；
3. 使用统一公式分析 x86-64 有效地址；
4. 从数组、结构体和指针表达式还原寻址操作数；
5. 区分 `mov` 的内存访问与 `lea` 的纯地址计算；
6. 理解 RIP-relative 寻址为什么适合 PIE、共享库和内核重定位；
7. 通过 `objdump` 和 GDB 验证地址计算及内存读取；
8. 为后续分析栈帧、`pt_regs`、协议结构体和内核入口汇编建立基础。

本课实验位于：

```text
assembly/labs/02-addressing/
```

---

## 2. 问题背景：程序为什么离不开地址计算

高级语言中的大量操作，本质上都不是简单算术，而是“先计算地址，再访问数据”。

例如：

```c
array[i]
p->member
*(ptr + offset)
matrix[row][column]
```

CPU 不认识数组名、结构体成员名或 C 指针表达式。编译器必须把它们转换为：

```text
有效地址 = 基址 + 索引 × 比例 + 位移
```

随后再决定：

```text
只需要这个地址
```

还是：

```text
需要读取或写入这个地址对应的内存
```

因此，本课的核心不是背诵一种括号格式，而是建立一个稳定的两阶段模型：

```text
第一阶段：计算有效地址
第二阶段：决定是否访问该地址处的内存
```

`lea` 只执行第一阶段；普通内存形式的 `mov` 同时执行两个阶段。

---

## 3. 数值、地址和地址处的数据

假设：

```text
RBX = 0x1000
memory[0x1000 .. 0x1007] = 0x1122334455667788
```

分析以下指令。

### 3.1 复制寄存器中的数值

```asm
movq %rbx, %rax
```

结果：

```text
RAX = 0x1000
```

CPU 只复制寄存器内容。至于 `0x1000` 被程序理解为整数还是地址，取决于后续使用方式。

### 3.2 解引用地址

```asm
movq (%rbx), %rax
```

结果：

```text
RAX = 0x1122334455667788
```

这里括号表示把 `RBX` 中的数值当作地址，并读取该地址处的 8 字节。

对应 C 语义：

```c
rax = *(uint64_t *)rbx;
```

### 3.3 计算新地址但不访问内存

```asm
leaq 8(%rbx), %rax
```

结果：

```text
RAX = 0x1008
```

`lea` 不读取 `0x1008` 处的数据。

对应 C 语义更接近：

```c
rax = (uintptr_t)rbx + 8;
```

### 3.4 访问带偏移的内存

```asm
movq 8(%rbx), %rax
```

CPU 先计算：

```text
address = RBX + 8 = 0x1008
```

然后读取：

```text
RAX = memory[0x1008 .. 0x100f]
```

这四条指令必须做到一眼区分：

```asm
movq %rbx, %rax       # 复制 RBX 中的值
movq (%rbx), %rax     # 读取 memory[RBX]
leaq 8(%rbx), %rax    # 计算 RBX + 8
movq 8(%rbx), %rax    # 读取 memory[RBX + 8]
```

---

## 4. AT&T 内存操作数的统一公式

AT&T 通用内存寻址形式：

```text
disp(base, index, scale)
```

有效地址：

```text
EA = disp + base + index × scale
```

其中：

```text
disp   displacement，位移，可以省略
base   基址寄存器，可以省略
index  索引寄存器，可以省略
scale  比例因子，只能是 1、2、4、8
```

### 4.1 只有基址

```asm
(%rax)
```

```text
EA = RAX
```

### 4.2 基址加位移

```asm
16(%rax)
```

```text
EA = RAX + 16
```

### 4.3 基址加索引

```asm
(%rax,%rcx)
```

```text
EA = RAX + RCX
```

### 4.4 基址加比例索引

```asm
(%rax,%rcx,8)
```

```text
EA = RAX + RCX × 8
```

### 4.5 完整形式

```asm
24(%rax,%rcx,4)
```

```text
EA = 24 + RAX + RCX × 4
```

### 4.6 没有基址

```asm
array(,%rcx,8)
```

这里第一个逗号前为空，表示没有 base：

```text
EA = address(array) + RCX × 8
```

这种形式在非 PIE 固定地址代码中较常见。

---

## 5. 为什么比例因子只有 1、2、4、8

这是 x86 指令编码和常见数据宽度共同形成的设计。

常见元素大小：

```text
char        1 字节
short       2 字节
int         4 字节
long        8 字节（Linux x86-64）
指针         8 字节
```

数组元素地址公式：

```text
元素地址 = 数组首地址 + 下标 × 元素大小
```

因此，1、2、4、8 足以直接覆盖最常见的数组访问。

比例因子不是任意乘法器，不能写：

```asm
(%rax,%rcx,3)     # 非法
```

当需要乘 3、5、9 等值时，编译器通常组合 base 和 index：

```asm
leaq (%rdi,%rdi,2), %rax      # 3 * RDI
leaq (%rdi,%rdi,4), %rax      # 5 * RDI
leaq (%rdi,%rdi,8), %rax      # 9 * RDI
```

---

## 6. 数组访问的完整还原

C 代码：

```c
long array_get(const long *array, size_t index)
{
    return array[index];
}
```

System V AMD64 ABI 下：

```text
RDI = array
RSI = index
```

GCC `-O2` 典型输出：

```asm
array_get:
    movq (%rdi,%rsi,8), %rax
    ret
```

逐层分析：

```text
base  = RDI = array 首地址
index = RSI = index
scale = 8   = sizeof(long)
disp  = 0
```

有效地址：

```text
EA = RDI + RSI × 8
```

内存访问宽度由 `movq` 决定：

```text
读取 8 字节
```

最终：

```text
RAX = *(long *)(array + index × 8)
```

需要区分两个独立宽度：

```text
地址宽度：通常为 64 位
数据访问宽度：由 movb/movw/movl/movq 决定
```

例如：

```asm
movb (%rdi,%rsi), %al       # 读取 1 字节
movl (%rdi,%rsi,4), %eax    # 读取 4 字节
movq (%rdi,%rsi,8), %rax    # 读取 8 字节
```

---

## 7. 结构体成员访问

C 代码：

```c
struct sample {
    int id;
    int flags;
    long value;
};

long member_get(const struct sample *item)
{
    return item->value;
}
```

典型布局：

```text
偏移 0：id       4 字节
偏移 4：flags    4 字节
偏移 8：value    8 字节
总大小：16 字节
```

优化汇编：

```asm
member_get:
    movq 8(%rdi), %rax
    ret
```

含义：

```text
RDI = item
EA  = RDI + 8
读取 8 字节到 RAX
```

结构体成员名在机器代码中已经消失，只剩下固定偏移。

因此，在分析未知汇编时：

```asm
movq 8(%rdi), %rax
movl 16(%rdi), %ecx
movw 24(%rdi), %dx
```

往往意味着 `%rdi` 指向某种结构体，而 `8/16/24` 是成员偏移。但必须结合访问宽度、调用上下文和后续用途验证，不能只凭一个偏移武断判断结构体类型。

### 7.1 对齐和填充的影响

考虑：

```c
struct padded {
    char tag;
    long value;
};
```

常见布局不是 9 字节，而是：

```text
偏移 0：tag       1 字节
偏移 1～7：padding
偏移 8：value     8 字节
总大小：16 字节
```

于是访问 `value` 仍可能是：

```asm
movq 8(%rdi), %rax
```

阅读结构体汇编时，必须考虑 ABI 对齐规则和编译器填充。

---

## 8. `lea` 的准确语义

`lea` 是 Load Effective Address，但它不会从有效地址加载数据。

```asm
leaq 16(%rbx,%rsi,8), %rax
```

执行：

```text
RAX = 16 + RBX + RSI × 8
```

不执行：

```text
RAX = memory[16 + RBX + RSI × 8]
```

Intel 语法：

```asm
lea rax, [rbx + rsi*8 + 16]
```

方括号在 Intel 语法中通常表示内存形式，但 `lea` 是特殊情况：它取方括号表达式计算出的地址，而不解引用。

### 8.1 `lea` 与 `mov` 对照

```asm
leaq 16(%rbx), %rax
```

```text
RAX = RBX + 16
```

```asm
movq 16(%rbx), %rax
```

```text
RAX = memory[RBX + 16]
```

### 8.2 `lea` 不要求计算结果是有效映射地址

例如：

```asm
leaq 4096(%rax), %rbx
```

只是整数/地址计算，不会因为 `RAX + 4096` 对应页面未映射而产生普通数据访问缺页。

只有之后真正解引用：

```asm
movq (%rbx), %rcx
```

才会触发地址翻译、权限检查和潜在异常。

### 8.3 `lea` 通常不修改 RFLAGS

```asm
cmpq %rsi, %rdi
leaq 1(%rax), %rax
jg .Lgreater
```

`lea` 可以在保留前一条 `cmp` 条件码的同时完成加法。这是编译器选择 `lea` 的原因之一。

相比之下：

```asm
addq $1, %rax
```

会更新条件标志。

---

## 9. `lea` 为什么经常用于普通整数算术

C 代码：

```c
long scale_add(long x)
{
    return x * 5 + 5;
}
```

GCC `-O2` 可生成：

```asm
scale_add:
    leaq 5(%rdi,%rdi,4), %rax
    ret
```

计算：

```text
RAX = 5 + RDI + RDI × 4
    = 5 × RDI + 5
```

这里不存在真实的内存地址语义，编译器只是复用 x86 地址生成能力完成乘加。

但不要得出“`lea` 永远比 `imul` 快”的简单结论。现代处理器上的实际吞吐和延迟取决于：

```text
寻址复杂度
具体微架构
端口占用
周围指令依赖
编译器成本模型
```

在汇编语义层面，只需先掌握：

```text
lea = 计算有效地址表达式并写入寄存器，不访问内存，不通常修改标志位
```

---

## 10. RIP-relative 寻址

典型形式：

```asm
leaq array(%rip), %rbx
movq global_value(%rip), %rax
```

其有效地址不是简单的：

```text
RIP + symbol
```

更准确地说，汇编器和链接器会编码一个相对于下一条指令地址的位移：

```text
目标地址 = 下一条指令地址 + 有符号位移
```

### 10.1 为什么不用绝对地址

绝对地址形式会把最终虚拟地址直接固化到指令或重定位中。当程序装载地址变化时，需要额外修正。

RIP-relative 寻址的优势：

```text
代码与数据整体移动后，相对距离通常保持不变
便于生成位置无关代码
减少运行时文本重定位
适合 PIE 和共享库
适合地址随机化环境
```

### 10.2 地址随机化与内核联系

用户态 PIE 程序和共享库可能被装载到不同地址；Linux 内核也存在地址布局随机化和重定位需求。相对寻址使代码更容易在不同基地址下工作。

本课实验中：

```asm
leaq array(%rip), %rbx
```

把 `array` 的运行时地址放入 `RBX`，但不读取数组元素。

下一条：

```asm
movq (%rbx), %rcx
```

才真正读取数组第一个元素。

---

## 11. x86 地址生成硬件与 SIB 概念

不要求本课记忆机器码，但需要知道复杂寻址不是汇编器展开成多条加法指令。x86 指令编码本身能够表达：

```text
base + index × scale + displacement
```

在机器码中，常通过 ModR/M 和 SIB（Scale-Index-Base）字段描述。

这解释了为什么：

```asm
movq 24(%rax,%rcx,8), %rdx
```

可以是一条机器指令，而不是：

```asm
movq %rcx, %tmp
imulq $8, %tmp
addq %rax, %tmp
addq $24, %tmp
movq (%tmp), %rdx
```

需要注意：

```text
“一条汇编指令”不等于“处理器内部只执行一个微操作”
```

复杂 x86 指令进入处理器后可能被译码成多个微操作。但从 ISA 和程序可见语义看，它仍是一条指令。

---

## 12. 常见寻址错误

### 12.1 把地址复制误认为内存读取

错误理解：

```asm
movq %rdi, %rax
```

不是：

```c
rax = *rdi;
```

而是：

```c
rax = (uintptr_t)rdi;
```

### 12.2 把 `lea` 误认为加载内存

```asm
leaq (%rdi), %rax
```

只是：

```text
RAX = RDI
```

不会读取 `memory[RDI]`。

### 12.3 忘记 AT&T 源、目标顺序

```asm
movq 8(%rdi), %rax
```

是读取到 `RAX`，不是把 `RAX` 写入内存。

写内存应为：

```asm
movq %rax, 8(%rdi)
```

### 12.4 把比例因子当成数据访问宽度

```asm
movb (%rdi,%rsi,8), %al
```

比例因子仍为 8，但只读取 1 字节。

```text
scale 决定地址计算
指令后缀决定数据访问宽度
```

### 12.5 忽略负位移

```asm
movq -8(%rbp), %rax
```

有效地址：

```text
RBP - 8
```

负位移在栈局部变量和内核入口栈布局中非常常见。

### 12.6 误认为 `lea` 可以直接以内存为目标

`lea` 的目标必须是寄存器：

```asm
leaq 8(%rdi), %rax       # 合法
leaq 8(%rdi), (%rax)     # 非法
```

---

## 13. 本课核心实验逐条预览

实验数组：

```asm
array:
    .quad 10, 20, 30, 40
```

主要代码：

```asm
leaq array(%rip), %rbx
movq %rbx, %rax
movq (%rbx), %rcx
movq 8(%rbx), %rdx
movq $2, %rsi
movq (%rbx,%rsi,8), %r8
leaq 16(%rbx), %r9
movq (%r9), %r10
leaq 5(%rsi,%rsi,4), %r11
```

假设数组首地址为 `A`，预期状态：

```text
RBX = A
RAX = A
RCX = 10
RDX = 20
RSI = 2
R8  = 30
R9  = A + 16
R10 = 30
R11 = 15
```

最后用 `R11` 作为退出状态，便于从 shell 验证：

```text
exit status = 15
```

---

## 14. 使用 `objdump` 分析

构建并反汇编：

```bash
cd assembly/labs/02-addressing
make clean all
make disasm
```

AT&T 输出重点观察：

```asm
lea    array(%rip),%rbx
mov    (%rbx,%rsi,8),%r8
lea    0x10(%rbx),%r9
```

Intel 输出可能类似：

```asm
lea    rbx,[rip+...]
mov    r8,QWORD PTR [rbx+rsi*8]
lea    r9,[rbx+0x10]
```

对照规则：

```text
AT&T：源, 目标
Intel：目标, 源
AT&T：寄存器带 %
Intel：寄存器不带 %
AT&T：立即数带 $
Intel：立即数不带 $
AT&T：disp(base,index,scale)
Intel：[base + index*scale + disp]
```

---

## 15. 使用 GDB 验证

运行：

```bash
make
make gdb
```

或者：

```bash
gdb -q -x gdb.cmd ./addressing
```

重点命令：

```gdb
x/i $rip
info registers rax rbx rcx rdx rsi r8 r9 r10 r11
x/4gx &array
x/gx $rbx
```

建议每执行一条指令都回答：

```text
1. 这条指令的源操作数是什么？
2. 目标操作数是什么？
3. 是否进行内存访问？
4. 若访问内存，有效地址是什么？
5. 访问宽度是多少？
6. 哪些寄存器发生变化？
7. RFLAGS 是否发生变化？
```

---

## 16. 与 Linux kernel 5.10 源码阅读的联系

本课知识会直接用于后续内核分析。

### 16.1 栈上的寄存器和局部状态

内核入口汇编大量使用：

```asm
偏移(%rsp)
偏移(%rbp)
```

这些偏移可能对应：

```text
硬件压栈状态
pt_regs 成员
保存的通用寄存器
返回地址
临时栈空间
```

如果不能准确计算有效地址，就无法还原系统调用和异常入口的栈布局。

### 16.2 内核结构体访问

C 编译后的内核代码会把：

```c
skb->len
sk->sk_state
task->mm
regs->ip
```

转换为“结构体基址 + 成员偏移”的访问。

分析反汇编或 vmcore 时，经常只能看到：

```asm
movl offset(%reg), %eax
movq offset(%reg), %rdx
```

需要结合 DWARF、BTF、`pahole` 或源码结构体定义恢复成员语义。

### 16.3 数组和表项

系统调用表、IDT 相关表、跳转表、per-CPU 数据索引以及网络协议表项都可能表现为：

```text
base + index × scale + displacement
```

### 16.4 地址计算不等于解引用

在内核调试中，这是非常重要的边界：

```text
计算出一个内核虚拟地址
```

不代表：

```text
该地址有效、已映射、具有访问权限或对象仍然存活
```

只有真实访存时，CPU 才执行页表翻译和权限检查；而对象生命周期错误即使地址可访问，也可能形成 use-after-free。

---

## 17. 本课练习

### 练习 1

假设：

```text
RAX = 0x1000
RCX = 3
```

计算：

```asm
24(%rax,%rcx,8)
```

答案：

```text
0x1000 + 3 × 8 + 24
= 0x1000 + 24 + 24
= 0x1030
```

### 练习 2

解释：

```asm
movl 12(%rdi,%rsi,4), %eax
```

答案：

```text
EA = RDI + RSI × 4 + 12
从 EA 读取 4 字节
写入 EAX
由于写 EAX，RAX 高 32 位清零
```

### 练习 3

下面哪条会访问内存？

```asm
leaq 8(%rdi), %rax
movq 8(%rdi), %rax
```

答案：只有第二条。

### 练习 4

将 Intel 语法转换为 AT&T：

```asm
mov rax, QWORD PTR [rbx + rcx*8 + 16]
```

答案：

```asm
movq 16(%rbx,%rcx,8), %rax
```

### 练习 5

C 代码：

```c
int get(const int *p, long i)
{
    return p[i + 2];
}
```

可用一条什么形式的指令实现？

参考答案：

```asm
movl 8(%rdi,%rsi,4), %eax
```

因为：

```text
(p + i + 2) 的字节偏移 = i × 4 + 8
```

### 练习 6

解释：

```asm
leaq (%rdi,%rdi,8), %rax
```

答案：

```text
RAX = 9 × RDI
```

不访问内存，不通常修改条件标志。

---

## 18. 本课验收标准

进入下一课前，应能够不借助资料完成：

1. 写出 `disp(base,index,scale)` 的有效地址公式；
2. 解释 `movq %rax,%rbx`、`movq (%rax),%rbx` 和 `leaq (%rax),%rbx` 的区别；
3. 从 `movq 16(%rdi,%rsi,8),%rax` 还原地址和访问宽度；
4. 从数组元素大小推断 scale；
5. 从结构体成员访问推断固定偏移的含义；
6. 解释 RIP-relative 寻址的设计价值；
7. 说明 `lea` 为什么能实现 `x*5+5`；
8. 在 GDB 中查看地址、地址处的数据和寄存器状态。

下一课进入：

```text
RFLAGS、cmp/test、有符号与无符号比较、条件跳转和基本块
```

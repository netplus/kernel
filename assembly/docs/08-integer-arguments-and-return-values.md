# 第 8 课（第一部分）：整数参数寄存器与整数返回值

A07 已经说明了 `call`/`ret` 如何完成控制流转移，但函数之间还必须约定“参数放在哪里、返回值放在哪里”。这不是 `call` 指令本身决定的，而是 ABI（Application Binary Interface，应用二进制接口）规定的。

本节只讨论 System V AMD64 ABI 中最基础的一条路径：**标量整数和指针形成的 INTEGER 类参数，以及一个普通整数返回值**。caller-saved/callee-saved、栈上传参、16 字节对齐、Red Zone、结构体参数与返回值放到 A08 后续部分。

## 1. 为什么需要调用约定

如果调用者和被调用者分别由不同源文件、不同语言甚至不同编译器产生，它们仍然需要在机器代码层面互相理解。

例如：

```c
long add6(long a, long b, long c, long d, long e, long f);
```

调用者必须知道：

```text
a 放哪里？
b 放哪里？
...
f 放哪里？
返回值从哪里取？
```

如果双方使用不同约定，即使函数名和类型声明完全相同，机器代码也无法正确交换数据。

因此 ABI 解决的是“二进制边界上的共同语言”。

## 2. 先区分 ISA 与 ABI

### x86-64 ISA 规定

A07 已学习：

```text
call  保存返回地址并跳到目标
ret   从栈顶取得返回地址并返回
```

这些属于处理器指令语义。

### System V AMD64 ABI 规定

ABI 进一步规定：

```text
整数参数使用哪些寄存器
浮点参数使用哪些寄存器
哪些寄存器由 caller/callee 保存
栈如何对齐
返回值如何传递
```

因此不能把：

```text
call/ret 机制
```

和：

```text
函数调用约定
```

混为一谈。

## 3. INTEGER 类参数的前六个通用寄存器

System V AMD64 psABI 对 INTEGER 类参数按从左到右的顺序分配通用寄存器：

```text
第 1 个 INTEGER 参数 → RDI
第 2 个 INTEGER 参数 → RSI
第 3 个 INTEGER 参数 → RDX
第 4 个 INTEGER 参数 → RCX
第 5 个 INTEGER 参数 → R8
第 6 个 INTEGER 参数 → R9
```

本节使用 64 位 `long`，避免较窄整数类型带来的扩展规则干扰。

对于：

```c
abi_probe6(11, 22, 33, 44, 55, 66);
```

在进入被调函数的机器边界处，应看到：

```text
RDI = 11
RSI = 22
RDX = 33
RCX = 44
R8  = 55
R9  = 66
```

这条规则的关键点是“参数的逻辑顺序”映射到固定寄存器顺序，而不是由函数自己去栈中寻找前六个普通整数参数。

## 4. 指针为什么也走这条路径

在 AMD64 psABI 的参数分类中，普通指针属于 INTEGER 类。

例如：

```c
void inspect(void *p, size_t len);
```

在没有其他特殊参数干扰时，典型入口为：

```text
RDI = p
RSI = len
```

这里的“INTEGER”是 ABI 的参数分类名称，不是说指针在 C 语言类型系统里变成了整数。

## 5. 返回值：普通整数使用 RAX

对于一个普通、可装入一个 INTEGER eightbyte 的整数返回值，例如：

```c
long sum6(...);
```

返回值通过 `%rax` 交给调用者。

因此被调用者可以：

```asm
    movq %rdi, %rax
    addq %rsi, %rax
    ...
    ret
```

而调用者在 `call` 返回后从 `%rax` 取得结果。

本节实验中：

```text
11 + 22 + 33 + 44 + 55 + 66 = 231
```

所以 `ret` 前 `%rax = 231`，调用者随后观察到返回值 `231`。

更大的返回对象可能使用 `%rax/%rdx`、SSE 寄存器或隐藏内存指针；这些不在本节展开。

## 6. C caller + 汇编 callee：为什么这种实验更直接

如果只把一个 C 函数反汇编，我们看到的是“编译器选择的实现”。

本节实验改用：

```text
C caller
  ↓ ABI 边界
手写汇编 callee
```

汇编函数入口第一时间把六个参数寄存器保存到全局变量：

```asm
abi_probe6:
    movq %rdi, seen_rdi(%rip)
    movq %rsi, seen_rsi(%rip)
    movq %rdx, seen_rdx(%rip)
    movq %rcx, seen_rcx(%rip)
    movq %r8,  seen_r8(%rip)
    movq %r9,  seen_r9(%rip)
```

这样验证的是一个真实的二进制函数边界：

```text
C 编译器生成 caller
        ↓
按照 ABI 填充参数寄存器
        ↓
手写汇编 callee 直接观察寄存器
```

如果 caller 不遵守 ABI，实验会立即失败。

## 7. `-O0` 下的调用点

本实验在 GCC 14.2、`-O0 -fno-pie` 下观察到：

```asm
mov    $0x42,%r9d
mov    $0x37,%r8d
mov    $0x2c,%ecx
mov    $0x21,%edx
mov    $0x16,%esi
mov    $0xb,%edi
call   abi_probe6
```

十六进制立即数对应：

```text
0x0b = 11
0x16 = 22
0x21 = 33
0x2c = 44
0x37 = 55
0x42 = 66
```

这正好显示六个参数寄存器的分配顺序。

这里 GCC 使用 `%edi/%esi/...` 的 32 位子寄存器装载这些较小的正数常量。写 32 位通用寄存器会把对应 64 位寄存器高 32 位清零，因此最终被调函数看到的 64 位值仍然正确。

不要把这种“使用 32 位 mov 装载常量”的具体代码生成方式误认为 ABI 要求；ABI 要求的是函数边界上的参数值和位置。

## 8. `-O2` 下出现 tail call 不会改变 ABI

本实验的辅助函数：

```c
__attribute__((noinline))
static long call_probe(void)
{
    return abi_probe6(11, 22, 33, 44, 55, 66);
}
```

在 GCC 14.2 `-O2` 下被优化成：

```asm
mov    $0x42,%r9d
mov    $0x37,%r8d
mov    $0x2c,%ecx
mov    $0x21,%edx
mov    $0x16,%esi
mov    $0xb,%edi
jmp    abi_probe6
```

这里最后不是 `call`，而是 tail call `jmp`。

这说明两件事：

1. ABI 规定参数如何出现在函数入口，并不要求 caller 必须使用某一种高级语言形态；
2. 编译器可以优化控制流，但进入 `abi_probe6` 时六个参数寄存器仍必须满足 ABI。

因此阅读优化汇编时，应把“ABI 数据约定”和“编译器控制流优化”分开理解。

## 9. 汇编 callee 如何构造返回值

实验的 `abi_probe6`：

```asm
    movq %rdi, %rax
    addq %rsi, %rax
    addq %rdx, %rax
    addq %rcx, %rax
    addq %r8,  %rax
    addq %r9,  %rax
    ret
```

寄存器变化可以写成：

```text
RAX = RDI
RAX += RSI
RAX += RDX
RAX += RCX
RAX += R8
RAX += R9
```

最终：

```text
RAX = 231
```

`ret` 只负责恢复控制流；返回值之所以能被 caller 读取，是因为 ABI 约定了 `%rax` 的含义。

## 10. 这些参数寄存器在函数内部是否必须保持不变

不是。

“参数从 `%rdi/%rsi/...` 传入”只描述函数入口边界。函数开始执行以后，可以：

```text
把参数复制到别的寄存器
把参数保存到栈
直接修改参数寄存器
完全不再保留原值
```

是否必须为 caller 保留某个寄存器，是 caller-saved/callee-saved 规则的问题，下一部分单独讨论。

所以不要产生下面的误解：

```text
错误：RDI 永远代表第一个参数
正确：在符合 ABI 的函数调用入口，RDI 承载第一个可分配到 INTEGER 参数寄存器的参数；进入函数后它只是普通寄存器之一
```

## 11. “前六个参数都在寄存器”并不总是正确

本节故意选择六个纯 64 位整数，因此规则很整齐。

真实 ABI 会先对每个参数分类：

```text
INTEGER
SSE
SSEUP
X87
MEMORY
...
```

不同类别使用不同寄存器集合；大对象可能直接通过内存传递。

因此更准确的表述是：

> 对按 ABI 分类为 INTEGER、且仍有可用通用参数寄存器的参数，依次使用 `%rdi/%rsi/%rdx/%rcx/%r8/%r9`。

而不是：

> 所有函数的前六个参数都固定在这六个寄存器。

后续“小结构体和大结构体”部分会回到参数分类算法。

## 12. 与 Linux kernel 5.10 的关系

本节讲的是 **用户态 System V AMD64 ABI**，不是 Linux 内核系统调用 ABI。

两者必须区分：

```text
普通用户态函数调用：System V AMD64 ABI
Linux x86-64 syscall：Linux syscall ABI
```

例如 Linux x86-64 系统调用的第 4 个参数并不是 `%rcx`，而会使用 `%r10`。这一差异在 A13“Linux x86-64 系统调用 ABI”中专门分析。

因此不要把本节的 `%rdi/%rsi/%rdx/%rcx/%r8/%r9` 直接套到 `syscall` 指令入口。

## 13. 实验与验证

配套实验：

[`../labs/08-integer-arguments-and-return/`](../labs/08-integer-arguments-and-return/)

本次实际验证环境：

```text
GCC: GNU GCC 14.2.0
GNU assembler: binutils 2.44
GNU ld: binutils 2.44
```

已验证：

```text
-O0 构建                通过
-O2 构建                通过
两个程序运行             通过
六个入口参数寄存器        11 22 33 44 55 66
RAX 返回值               231
objdump AT&T            已检查
objdump Intel           已检查
nm                      已检查
GDB                     当前环境未安装，未执行
```

规范依据为 x86-64 psABI 项目的 System V AMD64 ABI “Parameter Passing / Returning of Values”规则；其中 INTEGER 参数寄存器序列明确为 `%rdi,%rsi,%rdx,%rcx,%r8,%r9`，INTEGER 返回值从 `%rax,%rdx` 序列分配。本节只验证单 eightbyte 整数返回，因此使用 `%rax`。

## 14. 本节完成后应能回答

1. 为什么 `call` 指令语义不足以定义完整函数调用？
2. 什么是 ABI，它解决什么二进制兼容问题？
3. 六个 INTEGER 参数寄存器的顺序是什么？
4. 普通单个 64 位整数返回值为什么在 `%rax`？
5. 为什么指针通常也走 INTEGER 参数寄存器？
6. 为什么不能简单说“所有函数的前六个参数都在这六个寄存器”？
7. 为什么 `-O2` 下 tail call 仍然必须满足同一 ABI 参数约定？
8. 普通函数 ABI 与 Linux syscall ABI 为什么不能混用？

下一部分继续学习 caller-saved 与 callee-saved 寄存器，回答“函数调用以后哪些寄存器值必须还能保持”。
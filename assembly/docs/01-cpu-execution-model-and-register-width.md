# 第 1 课：CPU 执行模型、寄存器宽度与 `mov`

## 1. 本课目标

完成本课后，应能够：

1. 用 `RIP + 通用寄存器 + RSP + RFLAGS + 内存` 描述一段汇编的执行状态；
2. 区分机器指令、汇编指令、标签和汇编伪指令；
3. 理解 `RAX/EAX/AX/AL/AH` 的位宽关系；
4. 准确解释写 `EAX` 为什么会清零 `RAX` 高 32 位；
5. 区分立即数、寄存器值、地址和地址处的数据；
6. 使用 GCC、GNU assembler、`objdump` 和 GDB 验证指令效果；
7. 在 AT&T 与 Intel 语法之间进行基本转换。

本课实验位于：

```text
assembly/labs/01-register-width/
```

---

## 2. 问题背景：高级语言最终如何被 CPU 执行

C 语言允许我们写：

```c
long add(long a, long b)
{
    return a + b;
}
```

但 CPU 不认识：

- 变量名 `a`、`b`；
- C 类型 `long`；
- `return` 关键字；
- 函数参数这一高级语言概念。

编译器必须根据目标架构和 ABI，把高级语义转换成机器指令。在 Linux x86-64 的 System V AMD64 ABI 下，这个函数可能被转换为：

```asm
add:
    leaq (%rdi,%rsi), %rax
    ret
```

这里隐含着约定：

```text
RDI = 第一个整数参数 a
RSI = 第二个整数参数 b
RAX = 整数返回值
```

CPU 实际处理的是：

```text
RAX = RDI + RSI
从栈中取回返回地址并继续执行
```

因此，汇编学习的核心不是把每条指令机械翻译成一句 C，而是回答：

1. 当前数据在哪里？
2. 这条指令读取了什么？
3. 这条指令修改了什么？
4. 下一条指令从哪里执行？
5. 修改后的位模式应如何解释？

---

## 3. CPU 执行状态模型

初学阶段可以把 CPU 的可观察执行状态抽象为：

```text
CPU 状态 = RIP + 通用寄存器 + RSP + RFLAGS + 内存
```

### 3.1 `RIP`：下一条指令在哪里

`RIP` 是 64 位指令指针。它标识下一条将要执行的机器指令地址。

正常顺序执行时，CPU 根据当前指令长度推进 `RIP`。发生以下事件时，`RIP` 会被显式或隐式改写：

- `jmp` 条件或无条件跳转；
- `call` 函数调用；
- `ret` 函数返回；
- `syscall` 系统调用；
- 中断和异常；
- `iretq`、`sysretq` 等特权级返回。

x86 指令是变长指令，一条指令占 1～15 字节。因此反汇编中相邻指令地址并不固定增加 4。这与很多固定长度指令集不同。

### 3.2 通用寄存器：CPU 的直接工作区

x86-64 主要通用寄存器：

```text
RAX RBX RCX RDX
RSI RDI RBP RSP
R8  R9  R10 R11
R12 R13 R14 R15
```

寄存器可以保存：

- 整数；
- 指针；
- 数组索引；
- 位图；
- 函数参数；
- 返回值；
- 临时计算结果。

寄存器中没有 C 类型标签。CPU 只看到位模式。例如：

```text
0xffffffffffffffff
```

它可以被解释为：

- `uint64_t` 最大值；
- `int64_t` 的 `-1`；
- 全 1 位图；
- 通常无效的虚拟地址。

具体含义由后续指令和程序上下文决定。

### 3.3 `RSP`：当前栈顶

`RSP` 同时也是通用寄存器，但 ABI 和指令语义赋予它栈顶指针角色。

在常见 x86-64 Linux 程序中，栈向低地址增长：

```text
高地址
+--------------------+
| 调用者数据         |
+--------------------+
| 返回地址           |
+--------------------+ ← 函数入口时的 RSP
| 保存的寄存器       |
+--------------------+
| 局部变量           |
+--------------------+ ← 调整后的 RSP
低地址
```

后续学习 `call`、`ret`、栈帧和上下文切换时，必须持续追踪 `RSP`。

### 3.4 `RFLAGS`：运算产生的条件状态

本课先关注：

| 标志 | 含义 |
|---|---|
| `ZF` | 运算结果是否为 0 |
| `SF` | 运算结果最高位是否为 1 |
| `CF` | 无符号运算是否产生进位或借位 |
| `OF` | 有符号运算是否溢出 |

`add`、`sub`、`cmp`、`test` 等指令会更新相关标志；普通 `mov` 不会重新计算这些算术标志。

这项设计很重要。例如编译器可以先执行比较，再插入不修改条件标志的搬运指令，最后执行条件跳转。

### 3.5 内存：代码和数据的主要存储位置

寄存器数量有限，程序的大部分代码和数据位于内存。汇编分析中必须严格区分：

```asm
movq %rbx, %rax
```

与：

```asm
movq (%rbx), %rax
```

第一条表示：

```text
RAX = RBX
```

第二条表示：

```text
RAX = memory64[RBX]
```

也就是把 `RBX` 当作地址，读取该地址处的 8 字节。

对应 C 风格伪代码：

```c
rax = rbx;
rax = *(uint64_t *)rbx;
```

---

## 4. 取指、译码、执行和写回

可以用下面的简化过程理解一条指令：

```text
从 RIP 指向的位置取指令字节
        ↓
识别指令、操作数和位宽
        ↓
读取寄存器或内存操作数
        ↓
执行算术、逻辑、数据传送或控制转移
        ↓
把结果写回寄存器或内存
        ↓
按指令语义更新 RFLAGS
        ↓
确定新的 RIP
```

这不是现代乱序 CPU 内部实现的完整微架构描述，但它是分析架构可见行为的有效模型。

需要区分两个层面：

- **架构语义**：程序能够观察到的寄存器、内存和异常结果；
- **微架构实现**：流水线、微操作、寄存器重命名、乱序执行、缓存等内部机制。

本阶段先稳定掌握架构语义，之后再讨论性能和微架构。

---

## 5. 汇编文件中并非每一行都是 CPU 指令

观察：

```asm
    .section .text
    .global _start
    .type _start, @function

_start:
    movq $60, %rax
    xorl %edi, %edi
    syscall
```

这里包含三类元素。

### 5.1 汇编伪指令

```asm
.section .text
.global _start
.type _start, @function
```

伪指令由汇编器处理，不是 CPU 执行的机器指令。

它们分别用于：

- 切换当前输出节；
- 导出符号；
- 声明符号类型。

### 5.2 标签和符号

```asm
_start:
```

标签把名字 `_start` 绑定到当前位置。链接器、调试器和反汇编器可以通过该符号定位代码。

### 5.3 CPU 指令

```asm
movq $60, %rax
xorl %edi, %edi
syscall
```

这些最终被编码为机器字节，由 CPU 执行。

因此，阅读 `.s` 文件时不能假定每一行都会对应一条机器指令。

---

## 6. 寄存器的不同访问宽度

以 `RAX` 为例：

```text
RAX   64 位，bit 63..0
EAX   32 位，bit 31..0
AX    16 位，bit 15..0
AL     8 位，bit 7..0
AH     8 位，bit 15..8
```

它们不是五个互相独立的寄存器，而是同一个架构寄存器的不同访问窗口。

可以表示为：

```text
63                              32 31              16 15       8 7        0
+--------------------------------+------------------+-----------+----------+
|                                |                  |    AH     |    AL    |
+--------------------------------+------------------+-----------+----------+
<------------------------------ RAX -------------------------------------->
                                  <--------------- EAX ------------------->
                                                     <-------- AX -------->
```

这种命名来自 x86 的向后兼容历史：早期处理器有 `AX`，32 位扩展增加 `EAX`，64 位扩展增加 `RAX`。

### 6.1 部分写入示例

假设初始值：

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

只修改低 8 位。

继续执行：

```asm
movw $0xabcd, %ax
```

结果：

```text
RAX = 0x112233445566abcd
```

只修改低 16 位。

继续执行：

```asm
movl $0x12345678, %eax
```

结果：

```text
RAX = 0x0000000012345678
```

写 32 位寄存器时，高 32 位被清零。

### 6.2 写 `EAX` 为什么会清零高 32 位

这是 x86-64 指令集架构明确规定的语义，不是 GCC 的优化技巧。

主要设计收益：

1. **结果完整确定**：处理器不需要把新的低 32 位和旧的高 32 位合并；
2. **减少数据依赖**：后续读取 `RAX` 不依赖旧 `RAX` 的高 32 位；
3. **自然完成零扩展**：32 位无符号值写入 `EAX` 后，可直接作为 64 位零扩展值使用；
4. **简化常见代码生成**：大量 32 位整数运算不需要额外清零指令。

但写 `AX` 或 `AL` 不会清零其余位，因此部分写入分析必须追踪旧寄存器值。

### 6.3 其他寄存器名称

```text
RBX / EBX / BX / BL / BH
RCX / ECX / CX / CL / CH
RDX / EDX / DX / DL / DH
RSI / ESI / SI / SIL
RDI / EDI / DI / DIL
RBP / EBP / BP / BPL
RSP / ESP / SP / SPL
R8  / R8D / R8W / R8B
```

`AH/BH/CH/DH` 是历史遗留的高 8 位寄存器名称，在涉及 REX 前缀的 64 位指令编码中存在额外限制。初期只需知道它们访问 bit 15..8，不要把它们误认为独立寄存器。

---

## 7. `mov` 指令和数据宽度

AT&T 语法通常写作：

```text
mov<宽度> 源操作数, 目标操作数
```

常见后缀：

| 后缀 | 宽度 | 名称 |
|---|---:|---|
| `b` | 8 位 | byte |
| `w` | 16 位 | word |
| `l` | 32 位 | long |
| `q` | 64 位 | quadword |

示例：

```asm
movb $1, %al
movw $1, %ax
movl $1, %eax
movq $1, %rax
```

这里 `long` 是传统汇编命名中的 32 位，不要与 x86-64 Linux C 语言里的 64 位 `long` 混淆。

### 7.1 立即数操作数

AT&T 语法用 `$` 表示数值本身：

```asm
movq $100, %rax
```

含义：

```text
RAX = 100
```

如果遗漏 `$`，语义可能变成内存访问或符号引用，必须特别谨慎。

### 7.2 寄存器操作数

AT&T 语法用 `%` 标记寄存器：

```asm
movq %rbx, %rax
```

含义：

```text
RAX = RBX
RBX 保持不变
```

虽然指令名叫 `mov`，但它更接近“复制”，不会自动清空源操作数。

### 7.3 内存操作数

括号表示以寄存器内容作为地址：

```asm
movq (%rbx), %rax
```

含义：

```text
从虚拟地址 RBX 读取 8 字节
把读取结果写入 RAX
```

如果该地址未映射、权限不允许或访问跨越不可用页面，CPU 可能产生缺页异常。Linux 最终可能向用户进程发送 `SIGSEGV`。

### 7.4 普通 `mov` 通常不能内存到内存

下面形式非法：

```asm
movq (%rax), (%rbx)
```

需要经过寄存器中转：

```asm
movq (%rax), %rcx
movq %rcx, (%rbx)
```

多数普通 x86 指令最多只有一个显式内存操作数。这一限制避免一条通用指令同时处理两个复杂地址计算和两次普通内存访问。

x86 另有 `movsb/movsq/rep movsb` 等字符串指令，可通过隐含寄存器完成内存复制，但它们属于专用指令族。

---

## 8. `movabs` 与 64 位立即数

下面的值不能总是由普通形式直接编码为完整 64 位立即数：

```text
0x1122334455667788
```

GNU 汇编中可以写：

```asm
movabsq $0x1122334455667788, %rax
```

`movabs` 强调使用能够承载完整 64 位立即数的编码形式。

反汇编器有时即使源代码写的是 `movq`，也可能显示为 `movabs`；判断时应关注机器编码和最终语义，而不是只依赖助记符外观。

---

## 9. AT&T 与 Intel 语法对照

| 含义 | AT&T | Intel |
|---|---|---|
| `RAX = RBX` | `movq %rbx, %rax` | `mov rax, rbx` |
| `RAX = 10` | `movq $10, %rax` | `mov rax, 10` |
| 读取 `RBX` 指向的 8 字节 | `movq (%rbx), %rax` | `mov rax, QWORD PTR [rbx]` |
| `RAX += RBX` | `addq %rbx, %rax` | `add rax, rbx` |

最重要的区别：

```text
AT&T：源, 目标
Intel：目标, 源
```

此外：

```text
AT&T 寄存器带 %，立即数带 $
Intel 通常不加这些前缀
AT&T 常用指令后缀表示宽度
Intel 常通过寄存器或 BYTE/DWORD/QWORD PTR 表示宽度
```

建议以 AT&T 为主，因为 Linux 内核和 GCC 内联汇编经常使用它；同时定期用 Intel 语法反汇编进行对照。

---

## 10. 最小纯汇编实验

实验文件：

```text
assembly/labs/01-register-width/register_width.s
```

核心代码：

```asm
    .section .text
    .global _start
    .type _start, @function

_start:
    movabsq $0x1122334455667788, %rax
    movb    $0xff, %al
    movw    $0xabcd, %ax
    movl    $0x12345678, %eax

    movq    %rax, %rdi
    movq    $60, %rax
    syscall
```

前四条指令用于观察部分寄存器写入。

最后三条执行 Linux x86-64 原始 `exit` 系统调用：

```text
RAX = 60    系统调用号 exit
RDI = status
syscall     进入内核
```

执行到：

```asm
movq %rax, %rdi
```

时，`RDI` 得到：

```text
0x0000000012345678
```

随后 `RAX` 被改为系统调用号 60。

### 10.1 为什么程序退出状态显示为 120

shell 通常显示退出状态的低 8 位：

```text
0x12345678 & 0xff = 0x78 = 120
```

因此：

```bash
./register_width
echo $?
```

显示 `120`，只能证明退出参数的低 8 位。要观察完整 64 位值，必须在 `movq %rax,%rdi` 之前使用 GDB 查看 `RAX`。

---

## 11. 构建过程

进入实验目录：

```bash
cd assembly/labs/01-register-width
make
```

Makefile 将执行：

```bash
as --64 -g register_width.s -o register_width.o
ld register_width.o -o register_width
```

构建链：

```text
register_width.s
    ↓ GNU assembler
register_width.o
    ↓ GNU linker
register_width
```

目标文件已经包含机器代码，但地址布局、符号引用和可执行文件入口仍需链接器处理。

也可以让 GCC 充当构建驱动：

```bash
gcc -nostdlib -no-pie -g register_width.s -o register_width
```

参数含义：

```text
-nostdlib  不链接 C 运行时启动代码和标准库
-no-pie    生成非 PIE 可执行文件，便于初期观察固定代码地址
-g         生成调试信息
```

---

## 12. 使用 `objdump` 观察机器指令

AT&T 语法：

```bash
make disasm
```

等价于：

```bash
objdump -dr register_width
```

Intel 语法：

```bash
make disasm-intel
```

等价于：

```bash
objdump -dr -Mintel register_width
```

反汇编输出通常包含：

```text
指令地址    机器指令字节    汇编表示
```

重点观察：

1. 相邻地址增量并不相同，说明 x86 指令变长；
2. `movabs` 的机器编码较长，因为包含完整 64 位立即数；
3. `AL/AX/EAX/RAX` 对应不同操作数宽度；
4. `_start` 是符号，CPU 最终执行的是该地址处的字节；
5. AT&T 和 Intel 反汇编描述的是同一组机器指令。

---

## 13. GDB 逐指令验证

使用实验脚本启动：

```bash
gdb -x gdb.cmd ./register_width
```

脚本会：

- 在 `_start` 设置断点；
- 启动程序；
- 自动显示当前指令；
- 自动显示 `RAX`、`RDI` 和 `RSP`。

反复执行：

```gdb
si
```

预期状态：

| 执行完的指令 | `RAX` | 说明 |
|---|---|---|
| `movabsq ...,%rax` | `0x1122334455667788` | 写入完整 64 位值 |
| `movb $0xff,%al` | `0x11223344556677ff` | 只替换低 8 位 |
| `movw $0xabcd,%ax` | `0x112233445566abcd` | 只替换低 16 位 |
| `movl $0x12345678,%eax` | `0x0000000012345678` | 高 32 位自动清零 |
| `movq %rax,%rdi` | `RAX` 不变 | `RDI=0x12345678` |
| `movq $60,%rax` | `0x3c` | 准备 `exit` 系统调用号 |

可以手工查看：

```gdb
p/x $rax
p/x $rdi
p/x $eflags
x/i $rip
info registers
```

### 13.1 观察 `RFLAGS`

在 `mov` 指令前后执行：

```gdb
p/x $eflags
```

普通 `mov` 不会根据搬运结果重新设置 `ZF/SF/CF/OF`。要注意，GDB 显示的整个 `RFLAGS` 还包含其他位，不应只比较一个十六进制数字就草率得出结论；重点是相关算术条件位未被 `mov` 重新计算。

### 13.2 为什么 `syscall` 后不能像普通函数一样继续单步

`exit` 系统调用会终止当前进程。内核不会返回到下一条用户态指令。因此 GDB 会报告进程已经退出，而不是继续显示 `_start` 后续代码。

---

## 14. 对应 C 代码与编译器输出

实验文件 `companion.c`：

```c
#include <stdint.h>

uint64_t zero_extend_u32(uint32_t x)
{
    return x;
}

int64_t sign_extend_i32(int32_t x)
{
    return x;
}
```

生成不同优化级别的汇编：

```bash
make companion
```

将得到：

```text
companion-O0.s
companion-Og.s
companion-O2.s
```

优化版本的典型结果：

```asm
zero_extend_u32:
    movl %edi, %eax
    ret

sign_extend_i32:
    movslq %edi, %rax
    ret
```

分析：

### 14.1 无符号 32 位扩展到 64 位

`uint32_t` 参数位于 `EDI`。执行：

```asm
movl %edi, %eax
```

会把低 32 位写入 `EAX`，同时清零 `RAX` 高 32 位，因此自然得到 `uint64_t` 零扩展结果。

### 14.2 有符号 32 位扩展到 64 位

`int32_t` 的 bit 31 是符号位。必须执行：

```asm
movslq %edi, %rax
```

把 bit 31 复制到高 32 位。

例如：

```text
EDI = 0xffffffff
```

零扩展结果：

```text
RAX = 0x00000000ffffffff
```

符号扩展结果：

```text
RAX = 0xffffffffffffffff
```

两者位模式和数值语义完全不同。

### 14.3 为什么 `-O0` 外观更复杂

`-O0` 版本可能：

- 建立 `RBP` 栈帧；
- 把参数暂存到栈；
- 再从栈加载返回值；
- 保留更多与源代码变量对应的存储位置。

`-O2` 则倾向于直接在参数寄存器和返回寄存器之间完成操作。

这说明：

> 汇编不是 C 源码逐行替换。同一语义在不同优化级别下可以产生不同控制流和数据流。

---

## 15. 设计考虑与常见误区

### 15.1 寄存器没有固定 C 类型

不能因为某个值位于 `RAX`，就断定它是 `long`。必须结合：

- 指令宽度；
- 符号扩展或零扩展；
- 比较指令和跳转条件；
- 函数原型；
- 内存访问方式。

### 15.2 `mov` 不会清空源操作数

```asm
movq %rbx, %rax
```

执行后：

```text
RAX = 原 RBX
RBX = 原 RBX
```

它是复制，不是高级语言容器之间的“移动所有权”。

### 15.3 `$value` 与内存中的 `value` 不同

AT&T 中：

```asm
movq $10, %rax
```

装载立即数 10。

而：

```asm
movq data(%rip), %rax
```

访问符号 `data` 对应的内存。

是否访问内存要从操作数格式判断，而不是从符号名称猜测。

### 15.4 写 `EAX` 会影响整个 `RAX`

看到：

```asm
xorl %eax, %eax
```

必须得出：

```text
RAX = 0
```

不能只说 `EAX = 0` 而认为高 32 位保持不变。

### 15.5 不要仅依赖程序最终输出

退出码、打印格式和调试器展示都可能截断或重新解释数据。寄存器语义应通过：

- 指令规范；
- GDB 完整寄存器值；
- 反汇编；
- 可重复实验

共同验证。

### 15.6 不要把反汇编地址当成永远固定

本实验使用非 PIE 便于观察，但现代 Linux 常启用：

- PIE；
- ASLR；
- 共享库重定位；
- 内核 KASLR。

后续学习 RIP 相对寻址、ELF 和重定位后，再系统理解地址变化。

---

## 16. 与 Linux kernel 5.10 的联系

本课知识会直接用于后续内核源码分析。

### 16.1 `pt_regs` 保存的是寄存器状态

系统调用、异常和中断入口需要把部分 CPU 状态组织成 `struct pt_regs`，后续 C 代码才能统一访问用户态或被打断现场。

关键源码：

```text
arch/x86/entry/entry_64.S
arch/x86/include/asm/ptrace.h
```

### 16.2 系统调用号常通过 `EAX/RAX` 处理

Linux x86-64 系统调用 ABI 使用 `RAX` 传递系统调用号和返回值。看到对 `EAX` 的写入时，必须考虑它对整个 `RAX` 的零扩展效果。

### 16.3 汇编入口需要区分值、地址和内存内容

例如：

```asm
movq %rsp, %rdi
leaq offset(%rsp), %rdi
movq offset(%rsp), %rdi
```

分别表示：

- 复制当前栈地址；
- 计算栈中某字段地址；
- 读取栈中某字段值。

如果这一差异不清楚，就无法可靠分析系统调用入口和异常栈。

### 16.4 `RIP/RSP/RFLAGS` 是特权级切换核心状态

后续学习 `syscall/sysretq`、中断门和 `iretq` 时，将持续追踪：

```text
用户 RIP
用户 RSP
用户 RFLAGS
内核入口 RIP
内核栈 RSP
```

本课先建立观察方法，不立即进入复杂入口宏。

---

## 17. 练习

### 练习 1：部分寄存器写入

初始：

```text
RAX = 0xffff000011112222
```

依次执行：

```asm
movb $0x33, %al
movw $0x4455, %ax
movl $0x66778899, %eax
```

写出每一步的 `RAX`。

### 练习 2：值与解引用

解释：

```asm
movq %rdi, %rax
movq (%rdi), %rax
```

并说明第二条可能触发什么异常。

### 练习 3：语法转换

将下面 AT&T 汇编转换为 Intel 语法：

```asm
movq $10, %rax
movq %rbx, %rcx
addq %rcx, %rax
```

### 练习 4：退出码截断

为什么下面程序不能通过 `echo $?` 证明 `RDI` 的完整 64 位值？

```asm
movabsq $0x1122334455667788, %rdi
movq $60, %rax
syscall
```

### 练习 5：优化级别比较

比较 `companion-O0.s`、`companion-Og.s` 和 `companion-O2.s`：

- 是否建立栈帧；
- 参数是否写入栈；
- 零扩展和符号扩展使用什么指令；
- 为什么外观变化不改变函数语义。

---

## 18. 练习答案摘要

### 练习 1

```text
初始：              ffff000011112222
写 AL 后：          ffff000011112233
写 AX 后：          ffff000011114455
写 EAX 后：         0000000066778899
```

### 练习 2

```text
movq %rdi,%rax    复制 RDI 的位模式
movq (%rdi),%rax  把 RDI 当作地址，读取 8 字节
```

第二条可能产生缺页异常，Linux 用户态最终可能收到 `SIGSEGV`。

### 练习 3

```asm
mov rax, 10
mov rcx, rbx
add rax, rcx
```

### 练习 4

shell 通常只展示进程等待状态中的低 8 位退出码，因此完整 64 位参数被截断。

---

## 19. 本课验收标准

在不查资料的情况下，应能准确解释：

```asm
movabsq $0x1122334455667788, %rax
movb $0xff, %al
movw $0xabcd, %ax
movl $0x12345678, %eax
```

并能完成：

```bash
make
make run
make disasm
make disasm-intel
gdb -x gdb.cmd ./register_width
```

若对任何一步仍依赖猜测，应重复 GDB 单步实验，再进入下一课“地址计算、内存寻址与 `lea`”。

# Linux x86-64 汇编与内核入口

本目录学习 x86-64 汇编，并为阅读 Linux kernel 5.10 的启动、系统调用、异常、中断和上下文切换代码打下基础。

课程主要回答以下问题：

```text
CPU 如何执行一条指令？
寄存器、内存、栈和标志位如何变化？
C 代码如何转换成机器指令？
函数参数、返回值和局部变量如何保存？
用户态如何进入内核态，又如何返回？
内核入口代码如何保存和恢复执行现场？
```

## 课程大纲

### A00：实验环境与基本工具

- GCC、GNU assembler 和 linker 的分工；
- `.c`、`.s`、`.o` 和 ELF 文件的关系；
- `objdump`、`readelf`、`nm` 和 GDB；
- AT&T 语法与 Intel 语法；
- `-O0`、`-Og` 和 `-O2` 的基本差别。

### A01：CPU 执行模型、寄存器宽度与 `mov`

- `RIP`、通用寄存器、`RSP`、`RFLAGS` 和内存；
- `RAX/EAX/AX/AL/AH` 的关系；
- 8、16、32、64 位写入；
- 写 `EAX` 时高 32 位清零；
- 立即数、寄存器和内存操作数；
- 零扩展与符号扩展。

教程：[`docs/01-cpu-execution-model-and-register-width.md`](docs/01-cpu-execution-model-and-register-width.md)

实验：[`labs/01-register-width/`](labs/01-register-width/)

### A02：地址、解引用、数组、结构体与 `lea`

- 地址与地址处的数据；
- `disp(base,index,scale)`；
- 一维数组、二维数组和指针数组；
- 结构体成员、结构体数组和嵌套结构体；
- 对齐、填充、`sizeof` 和 `offsetof`；
- RIP-relative 寻址；
- `lea` 的地址计算和整数运算用途。

教程：[`docs/02-addressing-dereference-and-lea.md`](docs/02-addressing-dereference-and-lea.md)

实验：[`labs/02-addressing/`](labs/02-addressing/)

### A03：`RFLAGS`、比较、条件跳转与基本块

- `CF`、`ZF`、`SF` 和 `OF`；
- `cmp` 与 `test`；
- 有符号比较与无符号比较；
- `jcc`、`setcc` 和 `cmovcc`；
- 基本块、控制流图和循环回边；
- 分支预测的基本概念。

教程：[`docs/03-rflags-comparison-and-control-flow.md`](docs/03-rflags-comparison-and-control-flow.md)

实验：[`labs/03-flags-and-branches/`](labs/03-flags-and-branches/)

### A04：整数算术、位运算、移位、乘法与除法

- `add`、`sub`、`neg`、`inc` 和 `dec`；
- `and`、`or`、`xor` 和 `not`；
- `shl`、`shr` 和 `sar`；
- `mul`、`imul`、`div` 和 `idiv`；
- `RDX:RAX` 的隐式操作数；
- 常数乘除法的编译器优化。

教程：[`docs/04-integer-arithmetic-shifts-multiply-divide.md`](docs/04-integer-arithmetic-shifts-multiply-divide.md)

实验：[`labs/04-arithmetic-and-shifts/`](labs/04-arithmetic-and-shifts/)

### A05：循环、状态机与 `switch`

- `while`、`do-while` 和 `for`；
- 数组和指针遍历；
- 循环回边；
- `switch` 比较链；
- 跳转表和间接跳转。

### A06：栈、`push/pop` 与初始用户栈

- 栈向低地址增长；
- `RSP` 的变化；
- `push` 和 `pop`；
- `_start` 时的 `argc`、`argv`、`envp` 和 auxiliary vector；
- 栈对齐。

### A07：`call`、`ret` 与返回地址

- 直接调用和间接调用；
- 返回地址如何保存；
- 函数指针；
- 递归；
- 返回地址损坏的基本后果。

### A08：System V AMD64 ABI

- 整数参数寄存器；
- 返回值寄存器；
- caller-saved 与 callee-saved；
- 栈上传递的参数；
- 16 字节栈对齐；
- Red Zone；
- 小结构体和大结构体的参数、返回规则。

### A09：函数栈帧、局部变量与栈展开

- 函数序言和尾声；
- `RBP` 栈帧；
- 局部变量和寄存器溢出；
- 叶子函数；
- frame pointer omission；
- DWARF CFI 和调用栈展开的基础。

### A10：编译器优化后的汇编

- 内联；
- 尾调用；
- 公共子表达式；
- 寄存器分配；
- spill 和 reload；
- `-O0`、`-Og` 和 `-O2` 对照；
- 优化代码的调试限制。

### A11：ELF、符号与重定位

- `.text`、`.rodata`、`.data` 和 `.bss`；
- section 与 segment；
- 符号表；
- 强符号、弱符号和未定义符号；
- PC-relative 重定位；
- 静态链接的基本过程。

### A12：PIC、PIE、GOT 与 PLT

- 位置无关代码；
- RIP-relative 访问；
- PIE 和 ASLR；
- GOT 与 PLT；
- 动态链接和延迟绑定。

### A13：Linux x86-64 系统调用 ABI

- `syscall` 指令；
- 系统调用号和参数寄存器；
- `RCX`、`R11` 和 `R10` 的特殊作用；
- 原始返回值与 `errno`；
- libc 包装函数与直接系统调用。

### A14：Linux 5.10 系统调用入口与返回

- `entry_SYSCALL_64`；
- 用户栈与内核栈切换；
- `pt_regs`；
- `do_syscall_64`；
- 返回用户态前的检查；
- `sysretq` 与 `iretq`。

### A15：异常、中断与特权级切换

- Ring 0 与 Ring 3；
- IDT、GDT 和 TSS；
- trap、fault 和 interrupt；
- CPU 自动压栈的内容；
- 有错误码和无错误码异常；
- IST 和特殊异常栈。

### A16：缺页异常入口

- `#PF`；
- `CR2` 和错误码；
- 异常入口如何构造寄存器现场；
- 从汇编入口进入内存管理代码；
- 异常处理完成后的返回。

缺页处理的主体放在 [`../memory/`](../memory/) 中学习。

### A17：上下文切换汇编

- `switch_to`；
- `__switch_to_asm`；
- callee-saved 寄存器；
- 内核栈切换；
- 从旧任务返回到新任务的过程。

调度主体放在 [`../scheduler/`](../scheduler/) 中学习。

### A18：原子指令、内存屏障与内联汇编

- `xchg`、`cmpxchg` 和 `xadd`；
- `lock` 前缀；
- `mfence`、`lfence` 和 `sfence`；
- GCC 扩展内联汇编；
- 输入、输出和 clobber 约束；
- 内核原子操作和屏障接口的汇编基础。

### A19：早期启动汇编阅读基础

- 实模式、保护模式和长模式；
- 控制寄存器；
- 早期页表；
- 远跳转和模式切换；
- `head_64.S` 所需的汇编基础。

完整启动过程放在 [`../boot-crash/`](../boot-crash/) 中学习。

## 默认环境

```text
体系结构：x86-64
操作系统：Linux
内核源码：Linux kernel 5.10
汇编器：GNU assembler
主要语法：AT&T
辅助语法：Intel
ABI：System V AMD64 ABI
```

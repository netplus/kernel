# Lab 02：地址、解引用、比例寻址与 `lea`

## 1. 实验目的

本实验验证以下区别：

```text
寄存器中的地址值
地址处的数据
带偏移的内存访问
base + index × scale + displacement
lea 只计算地址、不访问内存
RIP-relative 地址获取
lea 用于整数乘加
```

对应主文档：

```text
assembly/docs/02-addressing-dereference-and-lea.md
```

## 2. 文件说明

```text
README.md             实验步骤
addressing.s          纯汇编实验程序
companion.c           数组、结构体和乘加的 C 对照代码
Makefile              构建、运行、反汇编和调试入口
gdb.cmd               GDB 自动单步观察脚本
expected-analysis.md  每条指令的预期状态
```

## 3. 环境准备

Debian/Ubuntu：

```bash
sudo apt install build-essential binutils gdb make
```

openEuler/RHEL：

```bash
sudo dnf install gcc binutils gdb make
```

确认：

```bash
gcc --version
as --version
ld --version
objdump --version
gdb --version
```

## 4. 构建

```bash
cd assembly/labs/02-addressing
make clean all
```

将生成：

```text
addressing.o
addressing
companion-O0.s
companion-O2.s
```

汇编程序直接使用 GNU assembler 和 linker：

```bash
as --64 -g -o addressing.o addressing.s
ld -o addressing addressing.o
```

它不依赖 libc，入口是 `_start`。

## 5. 运行验证

```bash
make run
```

预期：

```text
exit status=15 (expected 15)
```

退出状态来自：

```asm
leaq 5(%rsi,%rsi,4), %r11
```

此时：

```text
RSI = 2
R11 = 5 + 2 + 2 × 4 = 15
```

随后：

```asm
movq $60, %rax
movq %r11, %rdi
syscall
```

执行 `exit(15)`。

## 6. 查看数组的内存布局

源代码：

```asm
array:
    .quad 10, 20, 30, 40
```

每个元素占 8 字节，因此布局是：

```text
array + 0   = 10
array + 8   = 20
array + 16  = 30
array + 24  = 40
```

使用 GDB：

```gdb
x/4gd &array
x/4gx &array
```

`gd` 以十进制 8 字节整数显示，`gx` 以十六进制 8 字节整数显示。

## 7. 反汇编

```bash
make disasm
```

Makefile 会分别显示 AT&T 和 Intel 语法。

重点对照：

```asm
# AT&T
movq (%rbx,%rsi,8), %r8
leaq 16(%rbx), %r9

# Intel
mov r8, QWORD PTR [rbx+rsi*8]
lea r9, [rbx+0x10]
```

回答：

1. 哪一条访问内存？
2. 哪一条只计算地址？
3. `8` 在第一条中表示什么？
4. `16` 在第二条中表示字节还是元素个数？

答案：

```text
mov 访问内存，lea 不访问。
8 是比例因子，对应元素大小 8 字节。
16 是字节位移。
```

## 8. GDB 自动观察

```bash
make gdb
```

脚本会：

1. 在 `_start` 处断下；
2. 显示数组地址和四个元素；
3. 对前 11 条指令逐条 `si`；
4. 显示关键寄存器；
5. 在最终 `syscall` 前核对 `RAX=60`、`RDI=15`、`R11=15`。

手工调试也可使用：

```bash
gdb -q ./addressing
```

```gdb
break _start
run
set disassembly-flavor att
x/i $rip
info registers rax rbx rcx rdx rsi r8 r9 r10 r11
x/4gd &array
si
```

## 9. 逐条实验任务

### 任务 1：地址与数据

执行：

```asm
leaq array(%rip), %rbx
movq %rbx, %rax
movq (%rbx), %rcx
```

记录：

```text
RBX = ?
RAX = ?
RCX = ?
```

判断哪些寄存器保存地址，哪个寄存器保存数组元素。

### 任务 2：位移访问

分析：

```asm
movq 8(%rbx), %rdx
```

验证：

```text
RDX = 20
```

把位移改为 `24`，重新构建后应读到 `40`。

### 任务 3：比例索引

分析：

```asm
movq $2, %rsi
movq (%rbx,%rsi,8), %r8
```

把 `RSI` 改为 `3`，应读到 `40`。

再把 scale 错改为 `4`，观察读取结果。此时地址落在 8 字节元素中间，读取到的 8 字节会跨越两个相邻元素，结果取决于小端字节布局。该实验用于说明：

```text
有效地址合法，不代表数据类型语义正确
```

### 任务 4：`lea` 后再解引用

```asm
leaq 16(%rbx), %r9
movq (%r9), %r10
```

在两条指令之间观察：

```gdb
p/x $r9
x/gd $r9
```

确认 `R9` 只是地址，`R10` 才是读取出的值。

### 任务 5：`lea` 整数算术

修改：

```asm
leaq 5(%rsi,%rsi,4), %r11
```

尝试实现：

```text
3*x
9*x
8*x+7
```

参考：

```asm
leaq (%rsi,%rsi,2), %r11      # 3*x
leaq (%rsi,%rsi,8), %r11      # 9*x
leaq 7(,%rsi,8), %r11         # 8*x+7
```

## 10. C 代码对照

查看：

```bash
make c-asm
```

重点在 `companion-O2.s` 中定位：

```text
array_get
member_get
scale_add
```

预期核心形式：

```asm
array_get:
    movq (%rdi,%rsi,8), %rax

member_get:
    movq 8(%rdi), %rax

scale_add:
    leaq 5(%rdi,%rdi,4), %rax
```

比较 `-O0` 和 `-O2`：

```text
-O0 通常把参数和临时变量写入栈
-O2 倾向直接使用参数寄存器和复杂寻址
```

## 11. 深入实验：观察小端序

在 GDB 中：

```gdb
x/32bx &array
```

第一个 `.quad 10` 在内存中通常表现为：

```text
0a 00 00 00 00 00 00 00
```

这是 x86 的 little-endian 布局：最低有效字节位于最低地址。

本实验不系统展开字节序；后续分析网络协议头时会专门讨论主机字节序和网络字节序。

## 12. 实验报告建议

记录以下内容：

1. `array` 的实际运行地址；
2. 每条指令执行后的关键寄存器；
3. 每个内存操作数的 EA 公式；
4. `mov` 和 `lea` 的访存差异；
5. AT&T 与 Intel 语法对照；
6. `companion.c` 在 `-O0/-O2` 下的差异；
7. 修改 scale 后出现异常数据的原因。

完整预期结果见：

```text
expected-analysis.md
```

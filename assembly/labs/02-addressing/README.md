# Lab 02：复合取址、结构体布局与 `lea`

## 1. 实验目标

本实验从简单数组扩展到真实程序中常见的复合对象：

```text
一维数组
结构体成员
结构体数组
结构体内数组
嵌套结构体
连续二维数组
指针数组与多级解引用
lea 地址计算与整数乘加
```

核心方法：

```text
对象地址 = 基址 + 下标×对象大小 + 成员偏移
```

若对象继续嵌套，就继续叠加偏移或执行下一次解引用。

对应主文档：

```text
assembly/docs/02-addressing-dereference-and-lea.md
```

---

## 2. 文件说明

```text
addressing.s          纯汇编综合实验
companion.c           C 表达式与优化汇编对照
layout_demo.c         sizeof/offsetof 运行时验证
Makefile              构建、运行和调试入口
gdb.cmd               分阶段观察地址和寄存器
expected-analysis.md  逐项地址公式与预期结果
```

---

## 3. 构建与运行

```bash
cd assembly/labs/02-addressing
make clean all
make run
```

预期：

```text
exit status=168 (expected 168)
```

校验和来自：

```text
long_array[2]       = 3
records[1].value    = 22
bucket.values[2]    = 7
outer.in.value      = 44
matrix[1][2]        = 7
rows[1][2]          = 70
lea arithmetic      = 15
--------------------------------
total               = 168
```

---

## 4. 先观察结构体布局

```bash
make layout
```

典型输出：

```text
sizeof(struct sample) = 16
  id=0 flags=4 value=8
sizeof(struct record) = 24
  id=0 flags=4 value=8 stamp=16
sizeof(struct bucket) = 24
  count=0 values=8
sizeof(struct inner) = 16
sizeof(struct outer) = 24
  seq=0 in=8 in.value=16
```

这些数字不是教学假设，而是编译器和 ABI 共同确定的实际布局。

---

## 5. 查看编译器如何翻译 C

```bash
make c-asm
```

重点搜索：

```text
array_get
array_element_address
member_get
record_value_get
bucket_value_get
nested_value_get
matrix_get
pointer_matrix_get
scale_add
```

典型模式：

```asm
array_get:
    movq (%rdi,%rsi,8), %rax

array_element_address:
    leaq (%rdi,%rsi,8), %rax

record_value_get:
    leaq (%rsi,%rsi,2), %rax
    movq 8(%rdi,%rax,8), %rax

pointer_matrix_get:
    movq (%rdi,%rsi,8), %rax
    movq (%rax,%rdx,8), %rax
```

不要要求不同 GCC 版本生成完全相同的指令；只需验证最终地址公式等价。

---

## 6. 反汇编与语法对照

```bash
make disasm
```

AT&T：

```asm
movq 8(%rbx,%rax,8), %r9
```

Intel：

```asm
mov r9, QWORD PTR [rbx+rax*8+0x8]
```

统一解释：

```text
EA = RBX + RAX×8 + 8
读取 8 字节到 R9
```

---

## 7. GDB 分阶段观察

```bash
make gdb
```

脚本会在以下位置停下：

```text
after_array
after_struct_array
after_embedded_array
after_nested_struct
after_matrix
after_pointer_chain
after_lea_arithmetic
```

每个阶段都显示关键寄存器和预期地址公式。

手工观察示例：

```gdb
break _start
run
x/4gd &long_array
x/12wx &records
x/12gd &matrix
x/2gx &rows
```

---

## 8. 分层练习

### 基础练习：数组和成员

1. 把 `long_array[2]` 改为 `[3]`，预期读到 4。
2. 把 `bucket.values[2]` 改为 `[0]`，写出新 EA。
3. 解释为什么 `movl` 和 `movq` 读取结果不同。

### 进阶练习：结构体数组

1. 手工计算 `records[1].stamp` 的地址。
2. 修改汇编读取该值，预期得到 202。
3. 将 `struct record` 增加一个 `char tag`，运行 `make layout`，观察大小和偏移是否变化。

### 进阶练习：二维数组

1. 修改为读取 `matrix[2][3]`，预期得到 12。
2. 写出线性下标和字节偏移。
3. 比较 `matrix_get` 和 `pointer_matrix_get` 的解引用次数。

### 深入练习：指针链

在 GDB 中停在 `after_pointer_chain` 之前：

```gdb
x/2gx &rows
x/3gd row1
```

逐条执行：

```asm
movq (%rbx,%rsi,8), %rax
movq (%rax,%rdx,8), %r13
```

明确第一条取得地址，第二条才取得元素值。

### 关联练习：`container_of`

假设成员地址位于 `RDI`，成员在结构体中的偏移为 16：

```asm
leaq -16(%rdi), %rax
```

说明为什么这可以恢复外层结构体地址。

---

## 9. 实验报告建议

至少记录：

1. 每个数据结构的 `sizeof` 和关键 `offsetof`；
2. 七个实验对象的地址公式；
3. 每项发生了几次解引用；
4. 每条读取指令的访问宽度；
5. 连续二维数组和指针数组的布局差异；
6. `lea` 和 `mov` 的区别；
7. GCC `-O0` 与 `-O2` 的主要差异。

详细答案见：

```text
expected-analysis.md
```

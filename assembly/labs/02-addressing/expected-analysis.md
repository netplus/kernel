# Lab 02 预期分析

本实验不再只验证一种数组形式，而是把 C 语言中常见的复合取址统一为一个公式：

```text
对象地址 = 基址 + 对象下标 × 对象大小 + 成员偏移
```

如果成员自身还是数组或嵌套对象，就继续在这个结果上叠加新的索引和偏移。

---

## 1. 数据布局

### 1.1 一维数组

```text
long_array = {1, 2, 3, 4}
sizeof(long) = 8
```

```text
long_array[i] 地址 = A + i × 8
```

### 1.2 结构体数组

```c
struct record {
    int id;       // offset 0
    int flags;    // offset 4
    long value;   // offset 8
    long stamp;   // offset 16
};                // sizeof = 24
```

```text
records[i].value 地址 = R + i × 24 + 8
```

### 1.3 结构体内数组

```c
struct bucket {
    long count;    // offset 0
    int values[4]; // offset 8
};                 // sizeof = 24
```

```text
bucket.values[i] 地址 = B + 8 + i × 4
```

### 1.4 嵌套结构体

```text
outer.in 偏移       = 8
inner.value 偏移    = 8
outer.in.value 偏移 = 16
```

### 1.5 连续二维数组

```c
long matrix[3][4];
```

C 采用行优先布局：

```text
matrix[row][column] 地址
= M + (row × 4 + column) × 8
```

### 1.6 指针数组

```c
long *rows[2];
```

`rows[row][column]` 需要两次读取：

```text
row_pointer = memory[rows + row × 8]
value       = memory[row_pointer + column × 8]
```

它与连续二维数组不是同一种内存布局。

---

## 2. 指令状态表

| 观察点 | 地址计算 | 解引用次数 | 预期结果 |
|---|---|---:|---:|
| `long_array[2]` | `A + 2×8` | 1 | `R8=3` |
| `records[1].value` | `R + 1×24 + 8` | 1 | `R9=22` |
| `bucket.values[2]` | `B + 8 + 2×4` | 1 | `R10=7` |
| `outer.in.value` | `O + 8 + 8` | 1 | `R11=44` |
| `matrix[1][2]` | `M + (1×4+2)×8` | 1 | `R12=7` |
| `rows[1][2]` | 先 `P+1×8`，再 `row1+2×8` | 2 | `R13=70` |
| `5+2+2×4` | 纯整数计算 | 0 | `R14=15` |

---

## 3. 结构体数组为什么需要两级乘法

源代码：

```asm
leaq (%rsi,%rsi,2), %rax
movq 8(%rbx,%rax,8), %r9
```

当 `RSI=1` 时：

```text
RAX = 1 + 1×2 = 3
EA  = RBX + 3×8 + 8
    = RBX + 24 + 8
```

这里先把索引变成 `3*i`，再利用比例因子 8 得到 `24*i`。原因是 x86 内存操作数的 scale 只能是 1、2、4、8，不能直接写 24。

这是一种常见编译器分解方式：

```text
对象大小不能直接编码
→ 把大小分解为若干可编码的乘加或移位
```

---

## 4. `movslq` 的意义

```asm
movslq 8(%rbx,%rsi,4), %r10
```

该成员类型是 `int`，读取宽度是 4 字节；目标寄存器是 64 位，因此还需要决定如何扩展。

`movslq` 表示：

```text
读取 signed 32-bit
→ 符号扩展为 signed 64-bit
```

若成员是 `unsigned int`，编译器通常可以通过写入 32 位寄存器完成零扩展，例如：

```asm
movl 8(%rdi,%rsi,4), %eax
```

写 `EAX` 会自动把 `RAX` 高 32 位清零。

---

## 5. 连续二维数组与指针数组

### 连续二维数组

```asm
leaq (%rdx,%rsi,4), %rax
movq (%rbx,%rax,8), %r12
```

只有一次真正的内存读取。行和列先合并为线性下标。

### 指针数组

```asm
movq (%rbx,%rsi,8), %rax
movq (%rax,%rdx,8), %r13
```

第一次读取行指针，第二次读取行中的元素。两次解引用意味着：

- 两次潜在的地址翻译与缓存访问；
- 每一层指针都可能为空或无效；
- 各行不要求连续存放。

---

## 6. GCC `-O2` 预期模式

不同 GCC 版本可能选择不同但等价的指令，重点看语义。

```asm
array_get:
    movq (%rdi,%rsi,8), %rax

array_element_address:
    leaq (%rdi,%rsi,8), %rax

record_value_get:
    leaq (%rsi,%rsi,2), %rax
    movq 8(%rdi,%rax,8), %rax

bucket_value_get:
    movl 8(%rdi,%rsi,4), %eax

nested_value_get:
    movq 16(%rdi), %rax

pointer_matrix_get:
    movq (%rdi,%rsi,8), %rax
    movq (%rax,%rdx,8), %rax

scale_add:
    leaq 5(%rdi,%rdi,4), %rax
```

`matrix_get` 可能先把 `row` 乘以 32，因为每行是 4 个 `long`：

```text
row stride = 4 × 8 = 32 bytes
```

随后再叠加 `column × 8`。

---

## 7. 最终校验

```text
3 + 22 + 7 + 44 + 7 + 70 + 15 = 168
```

执行：

```bash
make run
```

预期：

```text
exit status=168 (expected 168)
```

在最终系统调用前：

```text
R8  = 3
R9  = 22
R10 = 7
R11 = 44
R12 = 7
R13 = 70
R14 = 15
RDI = 168
RAX = 60
```

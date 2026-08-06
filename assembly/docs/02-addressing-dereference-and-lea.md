# 第 2 课：地址、解引用、数组、结构体与 `lea`

## 1. 本课要解决什么问题

高级语言里，下面这些写法看起来各不相同：

```c
array[i]
p->member
records[i].value
bucket->values[i]
outer->inner.value
matrix[row][column]
rows[row][column]
```

但落到 CPU 层面，本质上都在做两件事：

```text
第一步：算出目标对象的地址
第二步：决定是否读取或写入这个地址
```

本课的目标，是让你看到一条内存访问指令时，能把它还原为：

```text
基址是谁？
索引是谁？
对象大小是多少？
成员偏移是多少？
访问了多少字节？
发生了几次解引用？
```

完成本课后，应能够：

1. 严格区分“值”“地址”和“地址处的数据”；
2. 使用统一公式分析 AT&T 内存操作数；
3. 还原一维数组、结构体、结构体数组和结构体内数组；
4. 还原嵌套结构体与二维数组；
5. 区分连续二维数组和指针数组；
6. 识别一层或多层指针解引用；
7. 区分 `mov` 访存和 `lea` 地址计算；
8. 根据 `movb/movw/movl/movq` 判断访问宽度；
9. 根据 `movsx/movzx` 判断符号扩展和零扩展；
10. 理解 RIP-relative 寻址、对齐、字节序和 `container_of` 等关联知识。

配套实验：

```text
assembly/labs/02-addressing/
```

---

## 2. 建议的阅读方式

本课同时面向不同基础的读者，每个主题按三层展开：

```text
主线：先掌握能直接读汇编的核心结论
原理：理解为什么编译器会这样生成代码
关联知识：了解它在 ABI、ELF 和 Linux 内核中的延伸
```

第一次学习时，优先抓住以下四句话：

```text
括号表示可能访问内存。
lea 只计算地址，不解引用。
数组下标最终变成“下标 × 元素大小”。
结构体成员最终变成固定字节偏移。
```

---

## 3. 最核心的三种语义

假设：

```text
RBX = 0x1000
memory[0x1000 .. 0x1007] = 0x1122334455667788
```

### 3.1 复制寄存器中的值

```asm
movq %rbx, %rax
```

结果：

```text
RAX = 0x1000
```

CPU 只知道复制了一个 64 位数值。这个数值是否被程序解释为地址，是软件语义，不是 `mov` 指令自身携带的类型信息。

### 3.2 读取地址处的数据

```asm
movq (%rbx), %rax
```

结果：

```text
RAX = 0x1122334455667788
```

执行过程可以拆成：

```text
EA = RBX
RAX = memory[EA .. EA+7]
```

这里发生了一次解引用。

### 3.3 计算地址，但不访问内存

```asm
leaq 8(%rbx), %rax
```

结果：

```text
RAX = RBX + 8 = 0x1008
```

`lea` 不读取 `0x1008` 处的数据。即使该地址尚未映射，这条指令本身也不会因为普通数据访问而产生缺页异常。

### 3.4 四条最容易混淆的指令

```asm
movq %rbx, %rax       # RAX = RBX
movq (%rbx), %rax     # RAX = memory[RBX]
leaq 8(%rbx), %rax    # RAX = RBX + 8
movq 8(%rbx), %rax    # RAX = memory[RBX + 8]
```

建议每次都先用自然语言读出来，而不要只盯着括号形式。

---

## 4. AT&T 内存操作数的统一公式

通用形式：

```text
displacement(base, index, scale)
```

有效地址：

```text
EA = displacement + base + index × scale
```

其中：

```text
displacement  固定字节位移，可省略
base          基址寄存器，可省略
index         索引寄存器，可省略
scale         比例因子，只能是 1、2、4、8
```

### 4.1 常见形式

```asm
(%rax)                   # EA = RAX
16(%rax)                 # EA = RAX + 16
(%rax,%rcx)              # EA = RAX + RCX
(%rax,%rcx,8)            # EA = RAX + RCX*8
24(%rax,%rcx,4)          # EA = RAX + RCX*4 + 24
symbol(,%rcx,8)          # EA = symbol + RCX*8
symbol(%rip)             # RIP-relative 地址
```

### 4.2 `scale` 为什么只有 1、2、4、8

这既是 x86 指令编码的限制，也正好覆盖常见元素大小：

```text
char      1
short     2
int       4
long      8（Linux x86-64）
pointer   8
```

不能写：

```asm
(%rax,%rcx,24)           # 非法
```

当对象大小是 12、16、24、40 等值时，编译器会用移位、`lea` 或乘法把它分解。

---

## 5. 一维数组：最基本的索引寻址

C 代码：

```c
long array_get(const long *array, size_t index)
{
    return array[index];
}
```

System V AMD64 ABI：

```text
RDI = array
RSI = index
```

典型汇编：

```asm
movq (%rdi,%rsi,8), %rax
ret
```

分解：

```text
base  = array
index = index
scale = sizeof(long) = 8
EA    = array + index*8
```

随后 `movq` 读取 8 字节。

### 5.1 取元素地址和取元素值

C：

```c
return &array[index];
```

汇编：

```asm
leaq (%rdi,%rsi,8), %rax
```

C：

```c
return array[index];
```

汇编：

```asm
movq (%rdi,%rsi,8), %rax
```

两者的有效地址公式完全相同，区别只有最后一步：

```text
lea：返回地址
mov：读取地址处的数据
```

### 5.2 元素大小不一定等于访问宽度吗

正常类型访问中，两者通常一致：

```asm
movb (%rdi,%rsi), %al       # char 数组
movw (%rdi,%rsi,2), %ax     # short 数组
movl (%rdi,%rsi,4), %eax    # int 数组
movq (%rdi,%rsi,8), %rax    # long 数组
```

但在手写汇编、序列化数据、网络报文或无类型内存操作中，程序可能故意用不同宽度访问同一片内存。因此应分别判断：

```text
scale 决定索引步长
指令后缀决定本次读取/写入宽度
```

---

## 6. 结构体：成员名最终变成字节偏移

```c
struct sample {
    int id;
    int flags;
    long value;
};
```

Linux x86-64 上的典型布局：

```text
offset 0   id       4 bytes
offset 4   flags    4 bytes
offset 8   value    8 bytes
sizeof(struct sample) = 16
```

访问：

```c
return item->value;
```

典型汇编：

```asm
movq 8(%rdi), %rax
```

成员名 `value` 不会出现在机器代码里，只保留：

```text
基址 item + 固定偏移 8
```

### 6.1 为什么需要填充

```c
struct padded {
    char tag;
    long value;
};
```

典型布局：

```text
offset 0   tag      1 byte
offset 1-7 padding
offset 8   value    8 bytes
sizeof = 16
```

填充的主要目的，是让成员满足对齐要求，使多数访问更符合处理器和 ABI 的约定。

### 6.2 用工具验证，不要只靠猜

```c
sizeof(struct sample)
offsetof(struct sample, value)
```

配套实验中的 `layout_demo.c` 会打印这些值。

[关联知识] DWARF 调试信息会记录结构体类型、成员名和偏移，因此带调试信息时 GDB 可以显示高级类型；机器指令本身只有地址和偏移。

---

## 7. 结构体数组：对象步长与成员偏移叠加

这是第二课必须掌握的关键组合。

```c
struct record {
    int id;       // offset 0
    int flags;    // offset 4
    long value;   // offset 8
    long stamp;   // offset 16
};                // sizeof = 24

long get(const struct record *records, size_t i)
{
    return records[i].value;
}
```

地址公式：

```text
records[i].value 地址
= records 基址
+ i × sizeof(struct record)
+ offsetof(struct record, value)

= base + i×24 + 8
```

但 x86 的 scale 不能直接写 24。编译器可能生成：

```asm
leaq (%rsi,%rsi,2), %rax
movq 8(%rdi,%rax,8), %rax
```

第一条：

```text
RAX = i + i×2 = 3i
```

第二条：

```text
EA = base + (3i)×8 + 8
   = base + i×24 + 8
```

### 7.1 通用还原方法

看到两条组合指令时，不要孤立分析：

```asm
leaq (%rsi,%rsi,2), %rax
movq 8(%rdi,%rax,8), %rax
```

先把第一条结果代入第二条：

```text
3i → 3i×8 → 24i → 再加成员偏移 8
```

### 7.2 对象大小为 16 时

编译器可能：

```asm
salq $4, %rsi
movq 8(%rdi,%rsi), %rax
```

也可能使用两次 `lea`。具体形式不唯一，必须还原数学关系，而不是背固定模板。

---

## 8. 结构体内数组：成员偏移与数组索引叠加

```c
struct bucket {
    long count;     // offset 0
    int values[4];  // offset 8
};

int get(const struct bucket *bucket, size_t i)
{
    return bucket->values[i];
}
```

地址公式：

```text
bucket->values[i]
= bucket 基址
+ offsetof(bucket, values)
+ i × sizeof(int)

= base + 8 + i×4
```

典型汇编：

```asm
movl 8(%rdi,%rsi,4), %eax
```

这里同时出现了：

```text
8  ：成员 values 的固定偏移
RSI：数组下标
4  ：int 元素大小
```

这类形式在内核中非常常见，例如结构体内嵌位图、统计数组、队列数组或协议字段数组。

---

## 9. 嵌套结构体：偏移可以逐层相加

```c
struct inner {
    int state;     // offset 0
    int flags;     // offset 4
    long value;    // offset 8
};

struct outer {
    long seq;      // offset 0
    struct inner in; // offset 8
};
```

访问：

```c
outer->in.value
```

地址公式：

```text
outer 基址
+ offsetof(struct outer, in)
+ offsetof(struct inner, value)

= base + 8 + 8
= base + 16
```

典型汇编：

```asm
movq 16(%rdi), %rax
```

编译器通常会把多个固定偏移折叠成一个最终偏移，因此仅凭 `16(%rdi)` 无法知道它是一层成员还是多层嵌套成员。需要结合类型信息或上下文。

---

## 10. 连续二维数组：先线性化，再访问

```c
long matrix[3][4];
```

C 语言采用行优先布局：一整行连续存放，然后才是下一行。

```text
matrix[0][0] matrix[0][1] matrix[0][2] matrix[0][3]
matrix[1][0] matrix[1][1] ...
```

访问：

```c
matrix[row][column]
```

地址公式：

```text
EA = base + (row × 列数 + column) × 元素大小
   = base + (row×4 + column)×8
```

一种可能的汇编：

```asm
leaq (%rdx,%rsi,4), %rax
movq (%rdi,%rax,8), %rax
```

其中：

```text
RSI = row
RDX = column
RAX = column + row×4
```

编译器也可能直接计算每行字节跨度：

```text
row stride = 4 × 8 = 32 bytes
```

例如先执行 `row << 5`，再叠加 `column × 8`。两种方式语义相同。

[关联知识] 对多维数组而言，编译器必须知道除第一维外的维度大小，才能计算每一行的跨度。这就是函数参数常写成 `long matrix[][4]` 的原因之一。

---

## 11. 指针数组和二维数组不是一回事

考虑：

```c
long *rows[2];
```

访问：

```c
rows[row][column]
```

典型汇编：

```asm
movq (%rdi,%rsi,8), %rax
movq (%rax,%rdx,8), %rax
```

第一条：

```text
RAX = rows[row]
```

得到一行的指针。

第二条：

```text
RAX = rows[row][column]
```

读取该行中的元素。

### 11.1 两种布局的根本区别

连续二维数组：

```text
所有元素位于一整块连续内存
通常一次解引用即可读取元素
```

指针数组：

```text
先有一组指针，每个指针再指向一行
各行可以位于不同位置
通常需要两次解引用
```

### 11.2 为什么解引用次数很重要

每一层指针都意味着：

```text
可能为空
可能指向无效地址
可能造成额外缓存未命中
可能需要新的地址翻译
```

阅读未知汇编时，连续出现两条基于前一次加载结果的访存，往往意味着指针链：

```asm
movq 16(%rdi), %rax
movq 8(%rax), %rax
```

可近似还原为：

```c
return rdi->member_ptr->submember;
```

但最终类型仍需结合上下文验证。

---

## 12. 访问宽度、符号扩展和零扩展

地址算对了，只完成了一半。还必须判断读取了多少字节，以及如何扩展到目标寄存器。

### 12.1 访问宽度

```asm
movb 8(%rdi), %al      # 1 byte
movw 8(%rdi), %ax      # 2 bytes
movl 8(%rdi), %eax     # 4 bytes
movq 8(%rdi), %rax     # 8 bytes
```

同一个地址，用不同宽度读取，会得到不同结果。

### 12.2 有符号扩展

```asm
movsbq (%rdi), %rax    # signed char -> signed long
movswq (%rdi), %rax    # signed short -> signed long
movslq (%rdi), %rax    # signed int -> signed long
```

若源值为 `-1`：

```text
0xff → 0xffffffffffffffff
```

### 12.3 零扩展

```asm
movzbl (%rdi), %eax
movzwl (%rdi), %eax
```

若源值为 `0xff`：

```text
0xff → 0x00000000000000ff
```

读取无符号 32 位值时，经常只需：

```asm
movl (%rdi), %eax
```

因为写入 `EAX` 会自动清零 `RAX` 高 32 位。

[关联知识] 这与第一课“写 32 位寄存器会清零高 32 位”直接相关。

---

## 13. `lea`：地址生成器，也可用于整数算术

`lea` 的准确语义：

```text
计算内存操作数形式对应的有效地址
把结果写入寄存器
不读取该地址处的数据
通常不修改算术标志位
```

```asm
leaq 16(%rbx,%rsi,8), %rax
```

结果：

```text
RAX = RBX + RSI×8 + 16
```

### 13.1 `lea` 与 `mov` 对照

```asm
leaq 16(%rbx), %rax    # RAX = RBX + 16
movq 16(%rbx), %rax    # RAX = memory[RBX + 16]
```

### 13.2 用 `lea` 做乘加

```asm
leaq (%rdi,%rdi,2), %rax      # 3*x
leaq (%rdi,%rdi,4), %rax      # 5*x
leaq (%rdi,%rdi,8), %rax      # 9*x
leaq 7(,%rdi,8), %rax         # 8*x + 7
```

这并不意味着结果必须是有效内存地址。此时 `lea` 只是整数乘加工具。

### 13.3 为什么编译器喜欢 `lea`

常见原因：

```text
一条指令完成加法和有限比例乘法
不需要额外立即乘法指令
通常不修改 RFLAGS
```

但不能简单概括为“`lea` 永远比 `imul` 快”。不同微架构、寻址复杂度和依赖链会影响真实性能。

---

## 14. RIP-relative 寻址

典型形式：

```asm
leaq global_data(%rip), %rax
movq global_value(%rip), %rax
```

x86-64 指令通常编码的是相对于下一条指令地址的有符号位移：

```text
target = next_RIP + displacement
```

它的价值是代码不必知道自己被装载到哪个绝对地址，因此适合：

```text
PIE 可执行文件
共享库
ASLR
内核和模块重定位
```

`lea symbol(%rip)` 得到符号地址；`mov symbol(%rip)` 读取符号内容。

[关联知识] 如果符号位于其他共享对象，还可能通过 GOT 间接取得地址，这会在 ELF 与动态链接课程中展开。

---

## 15. 对齐、非对齐访问和 packed 结构体

x86 通常允许普通整数的非对齐访问，例如 8 字节值不在 8 字节边界上也可能正常读取。但非对齐访问仍可能：

```text
跨越缓存行
跨越页边界
增加微架构处理成本
在某些原子操作或 SIMD 场景受限制
```

C 中的：

```c
__attribute__((packed))
```

可以减少或取消填充，但会改变成员偏移和访问方式，也可能带来非对齐访问。

在网络协议头中经常遇到 packed 布局，但内核通常配合专门的非对齐访问辅助函数，而不是盲目解引用任意类型指针。

---

## 16. 字节序是“取址正确之后”的下一层问题

即使有效地址和访问宽度都正确，读取出的多字节数值仍需要按字节序解释。

x86 是 little-endian：低有效字节放在低地址。

```text
64-bit value 0x000000000000000a
memory: 0a 00 00 00 00 00 00 00
```

网络协议通常使用 big-endian，也称网络字节序。因此分析 Linux 网络栈时，还要关注：

```text
htons/ntohs
htonl/ntohl
__be16/__be32
get_unaligned_be16
```

本课只建立关联，网络字节序会在协议头解析专题中详细展开。

---

## 17. Linux 内核中的直接关联

### 17.1 结构体字段访问

内核代码大量围绕结构体：

```text
struct sk_buff
struct net_device
struct sock
struct task_struct
struct pt_regs
```

汇编中的：

```asm
movq 16(%rdi), %rax
```

可能就是读取某个内核结构体字段。具体偏移取决于内核版本、配置、编译器和结构体布局。

### 17.2 `container_of`

Linux 内核常用：

```c
container_of(member_ptr, struct type, member)
```

其核心数学关系是：

```text
对象地址 = 成员地址 - 成员偏移
```

汇编中可能表现为：

```asm
leaq -offset(%rdi), %rax
```

这正是本课“地址 + 固定偏移”的反向使用。

### 17.3 柔性数组成员

内核结构体有时以柔性数组结尾：

```c
struct object {
    unsigned int count;
    char data[];
};
```

访问 `data[i]` 仍然是：

```text
对象基址 + data 成员偏移 + i×元素大小
```

只是对象实际分配大小可能大于 `sizeof(struct object)`。

### 17.4 页故障

`lea` 只计算线性地址，不进行普通数据读取；真正的 `mov (%reg),...` 才会触发地址翻译和权限检查，并可能产生 `#PF`。这会在异常与页表课程中继续展开。

---

## 18. 阅读复杂取址的固定步骤

面对：

```asm
movq 8(%rdi,%rax,8), %rcx
```

按以下顺序分析。

### 第一步：写出机械公式

```text
EA = RDI + RAX×8 + 8
```

### 第二步：判断访问宽度

```text
movq → 读取 8 字节
```

### 第三步：判断寄存器角色

结合 ABI 和前文：

```text
RDI 可能是对象或数组基址
RAX 可能是索引，或经过缩放的中间索引
```

### 第四步：回看 RAX 如何得到

若前面是：

```asm
leaq (%rsi,%rsi,2), %rax
```

则：

```text
RAX = 3×RSI
EA  = RDI + RSI×24 + 8
```

### 第五步：尝试还原高级语义

可能是：

```c
records[index].value
```

### 第六步：用证据验证

检查：

```text
sizeof(record) 是否为 24
value 偏移是否为 8
访问宽度是否与成员类型匹配
后续用途是否支持这一判断
```

不要只凭一个偏移就断定具体类型。

---

## 19. 常见误区

### 误区 1：看到括号就认为一定是指针变量

括号只表示使用内存操作数形式。它可能来自数组、结构体、栈变量、全局变量、MMIO 或手工构造地址。

### 误区 2：把 displacement 当成元素个数

```asm
16(%rax)
```

`16` 是字节，不是第 16 个元素。

### 误区 3：认为 scale 就是本次读取宽度

```asm
movb (%rdi,%rsi,8), %al
```

索引步长是 8 字节，但本次只读取 1 字节。

### 误区 4：把二维数组和二级指针等同

```c
long matrix[3][4]
long **rows
```

它们的内存布局和解引用次数不同。

### 误区 5：认为一个结构体数组元素总能用一条比例寻址表示

对象大小若不是 1、2、4、8，编译器需要先缩放索引。

### 误区 6：认为取到地址就等于访问成功

`lea` 得到一个数值不代表该地址有效；只有后续实际访问时才进行相应检查。

---

## 20. 本课实验主线

实验依次验证：

```text
long_array[2]
records[1].value
bucket.values[2]
outer.in.value
matrix[1][2]
rows[1][2]
lea 整数乘加
```

执行：

```bash
cd assembly/labs/02-addressing
make clean all
make run
make layout
make disasm
make c-asm
make gdb
```

重点不是记住编译器某一次生成的确切指令，而是对每个函数写出最终地址公式。

---

## 21. 本课验收标准

看到下面的 C 表达式，应能立即写出抽象地址公式：

```c
array[i]
records[i].value
bucket->values[i]
outer->in.value
matrix[row][column]
rows[row][column]
```

分别为：

```text
base + i×element_size
base + i×record_size + value_offset
base + values_offset + i×int_size
base + in_offset + value_offset
base + (row×column_count + column)×element_size
memory[base + row×pointer_size] + column×element_size
```

还应能回答：

```text
最终是 lea 还是 mov？
发生几次解引用？
读取多少字节？
是否需要符号扩展？
```

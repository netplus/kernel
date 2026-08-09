# Lab 04：整数算术、位运算、移位、乘法与除法

## 1. 实验要回答什么

本实验用一组小而明确的指令验证下面几个问题：

1. `add/sub` 如何修改固定宽度整数；
2. `and/or/xor/not` 分别怎样处理位模式；
3. `sar` 和 `shr` 为什么会对同一位模式产生不同结果；
4. 变量移位为什么使用 `CL`；
5. 两操作数 `imul` 与单操作数 `mul` 的结果位置有什么区别；
6. 有符号除法为什么需要 `cqto`；
7. 无符号除法为什么通常先清零 `RDX`；
8. 编译器为什么可能不用 `imul/idiv` 实现常数乘除法。

对应教程：

[`../../docs/04-integer-arithmetic-shifts-multiply-divide.md`](../../docs/04-integer-arithmetic-shifts-multiply-divide.md)

---

## 2. 文件说明

```text
arithmetic_and_shifts.s  纯汇编实验
companion.c              C 语言对照代码
Makefile                 构建、运行和反汇编入口
gdb.cmd                  GDB 观察脚本
expected-analysis.md     预期寄存器结果和解释
```

---

## 3. 构建与运行

```bash
make clean all
make run
```

预期输出：

```text
exit status=189 (expected 189)
```

退出状态只是自动化校验。真正需要观察的是各标签处的寄存器值。

---

## 4. 纯汇编实验主线

程序依次执行：

```text
普通加减
→ 位运算
→ not
→ sar / shr
→ imul
→ mul
→ cqto + idiv
→ 清零 RDX + div
→ 计算校验和
```

主要观察标签：

```text
after_add_sub
after_bitops
after_not
after_shifts
after_imul
after_mul
after_idiv
after_div
```

这些标签保留在 ELF 符号表中，便于 GDB 和 `nm` 定位。

---

## 5. 预期寄存器结果

| 观察点 | 主要寄存器 | 预期结果 |
|---|---|---|
| `after_add_sub` | `RBX` | `22` |
| `after_bitops` | `RSI` | `0x22` |
| `after_not` | `RSI` | `0xffffffffffffffdd` |
| `after_shifts` | `R9` | `-4` |
| `after_shifts` | `R10` | `0x3ffffffffffffffc` |
| `after_imul` | `R11` | `63` |
| `after_mul` | `RDX:RAX` | `0:42` |
| `after_idiv` | `RAX/RDX` | `-11 / -1` |
| `after_div` | `RAX/RDX` | `11 / 1` |

完整解释见：

[`expected-analysis.md`](expected-analysis.md)

---

## 6. GDB 调试

```bash
make gdb
```

脚本会在各观察标签处停止，并打印相关寄存器。

手工调试时可以使用：

```gdb
info registers rax rdx rcx rbx rsi r8 r9 r10 r11 r12 r13 r14 r15 eflags
x/10i $pc
si
```

建议特别比较：

```text
sar 后的 R9
shr 后的 R10
```

它们来自同一个初始位模式：

```text
0xfffffffffffffff0
```

但一个按有符号右移处理，一个按无符号右移处理。

---

## 7. 观察 `not` 与标志位

在 `after_bitops` 停止时记录 `RFLAGS`，然后执行：

```asm
notq %rsi
```

在 `after_not` 再次记录 `RFLAGS`。

预期：

```text
RSI 发生变化
条件标志不因 not 改变
```

这可以和 `and/or/xor` 对标志位的影响进行对比。

---

## 8. 观察 `sar` 与 `shr`

实验中：

```asm
movq $-16, %r8
movq %r8, %r9
sarq $2, %r9

movq %r8, %r10
movb $2, %cl
shrq %cl, %r10
```

分析时先写出完整位模式，再解释结果。

不要只记：

```text
sar 是有符号
shr 是无符号
```

而应说明：

```text
sar 高位复制原符号位
shr 高位补 0
```

---

## 9. 观察乘法的结果位置

### 两操作数 `imul`

```asm
movq $7, %r11
imulq $9, %r11
```

结果直接保存在：

```text
R11 = 63
```

### 单操作数 `mul`

```asm
movq $6, %rax
movq $7, %rcx
mulq %rcx
```

完整结果保存在：

```text
RDX:RAX
```

本例结果很小，因此：

```text
RDX = 0
RAX = 42
```

实验目标是建立“操作数形式不同，结果位置也可能不同”的意识。

---

## 10. 观察有符号除法

关键代码：

```asm
movq $-100, %rax
cqto
movq $9, %rcx
idivq %rcx
```

在 GDB 中单步观察 `cqto` 前后：

```text
RAX
RDX
```

预期：

```text
cqto 前：RAX = -100
cqto 后：RDX = -1
```

这不是为了保存余数，而是在构造 128 位有符号被除数 `RDX:RAX`。

`idivq` 执行后：

```text
RAX = -11
RDX = -1
```

---

## 11. 观察无符号除法

关键代码：

```asm
movq $100, %rax
xorq %rdx, %rdx
movq $9, %rcx
divq %rcx
```

这里清零 `RDX` 是为了把 64 位的 `100` 表示成 128 位被除数：

```text
RDX:RAX = 0:100
```

执行后：

```text
RAX = 11
RDX = 1
```

不要把 `RDX` 只理解为“余数寄存器”。在除法执行前，它首先是被除数的高半部分。

---

## 12. 反汇编

```bash
make disasm
```

重点寻找：

```asm
andq
orq
xorq
notq
sarq
shrq
imulq
mulq
cqto
idivq
divq
```

同时查看 Intel 语法：

```bash
objdump -drS -Mintel arithmetic-and-shifts
```

注意 AT&T 与 Intel 的操作数顺序不同，但机器码完全相同。

---

## 13. C 与编译器输出对照

```bash
make c-asm
```

重点函数：

```text
bit_mix
signed_shift
unsigned_shift
multiply
divide_signed
divide_unsigned
divide_by_10
scale_by_10
```

`-O2` 下重点观察：

```text
signed_shift       是否使用 sar
unsigned_shift     是否使用 shr
multiply           是否使用 imul
divide_signed      是否出现 cqto + idiv
divide_unsigned    是否先清零 EDX/RDX 再 div
divide_by_10       是否避免 idiv
scale_by_10        是否使用 lea/add/shift 等等价形式
```

具体输出会随 GCC 版本和优化策略变化，因此不要把某一份反汇编当成固定答案。

---

## 14. 分层练习

### 基础练习

1. 计算 `0x55 & 0x0f`、`0x55 | 0x80` 和 `0x55 ^ 0xff`；
2. 解释 `not` 与 `neg` 的区别；
3. 写出 `-16` 的 64 位补码表示；
4. 分别计算它执行 `sar $2` 和 `shr $2` 后的结果；
5. 说明 `idivq` 为什么同时使用 `RAX` 和 `RDX`。

### 进阶练习

1. 把 `mulq` 的操作数改大，使 `RDX` 出现非 0 高半部分；
2. 删除无符号除法前的 `xorq %rdx,%rdx`，观察旧 `RDX` 如何改变被除数；
3. 将变量移位次数改为 65，观察 64 位移位计数屏蔽规则；
4. 对比 `divide_by_10` 在 `-O0` 和 `-O2` 下的实现。

其中第 2 项应先计算可能的商是否能放入 64 位，避免无意触发 `#DE`。

### 系统方向练习

在后续 Linux 内核反汇编中寻找以下模式：

```text
and + 条件判断       状态位检查
shift + mask         字段提取或地址对齐
lea / shift / add    倍数和索引计算
cqto + idiv          有符号变量除法
xor edx,edx + div    无符号变量除法
```

先恢复算术语义，再结合源码判断变量的实际含义。

---

## 15. 验收标准

完成实验后，应能够看到：

```asm
movq %rdi, %rax
cqto
idivq %rsi
```

就说明：

```text
这是有符号 64 位除法；
被除数实际为 RDX:RAX；
cqto 根据 RAX 符号准备高 64 位；
RSI 是显式除数；
RAX 接收商；
RDX 接收余数。
```

看到：

```asm
movl %esi, %ecx
shrq %cl, %rax
```

则应能够说明 `CL` 提供运行时移位次数，而 `shr` 高位补 0，更接近无符号右移语义。

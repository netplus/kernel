# Lab 03 预期分析

## 1. `cmpq $7, %rax`

入口前：

```text
RAX = 7
```

`cmp source,destination` 概念上执行：

```text
destination - source
RAX - 7
7 - 7 = 0
```

结果不写回，但标志位应满足：

```text
ZF = 1
CF = 0
OF = 0
SF = 0
RAX 仍为 7
```

因此 `sete` 写入 1。

## 2. `testq %rcx, %rcx`

前置状态：

```text
RCX = 0
```

概念运算：

```text
RCX & RCX = 0
```

因此：

```text
ZF = 1
SF = 0
CF = 0
test 会把 CF 和 OF 清零
```

`test reg,reg` 是编译器判断寄存器是否为零的惯用形式。

## 3. 同一位模式的有符号与无符号解释

```text
R8 = 0xffffffffffffffff
```

有符号解释：

```text
R8 = -1
-1 < 1
```

无符号解释：

```text
R8 = 18446744073709551615
R8 > 1
```

执行：

```asm
cmpq $1, %r8
```

后：

```text
setl = 1    signed less: SF != OF
seta = 1    unsigned above: CF = 0 且 ZF = 0
```

这证明 CPU 不存储“signed 类型”或“unsigned 类型”；后续条件码决定如何解释同一组标志位。

## 4. 有符号溢出与无符号进位

### `LONG_MAX + 1`

```text
0x7fffffffffffffff + 1
= 0x8000000000000000
```

按有符号解释：

```text
正数 + 正数 得到负数
OF = 1
```

按无符号解释没有越过 `2^64 - 1`：

```text
CF = 0
```

因此：

```text
seto  = 1
setnc = 1
```

### `ULONG_MAX + 1`

```text
0xffffffffffffffff + 1
= 0x0000000000000000
```

因此：

```text
CF = 1    无符号进位
ZF = 1    结果为零
OF = 0    -1 + 1 在有符号范围内
```

## 5. 条件跳转与基本块

负数判断路径：

```text
入口块
  testq %rax,%rax
  jns .Lnonnegative
      ├─ 不跳转 → .Lnegative
      └─ 跳转   → .Lnonnegative
```

`RAX=-5` 时 `SF=1`，因此 `jns` 不跳转，执行 `.Lnegative`。

每个基本块满足：

1. 只从块首进入；
2. 块内除最后一条外没有跳转；
3. 最后一条决定后继基本块。

## 6. 最大值分支

```asm
cmpq %rcx, %rax
jle .Lselect_second
```

比较的是：

```text
RAX - RCX
9 - 4
```

有符号条件 `9 <= 4` 不成立，因此顺序执行 `.Lselect_first`，最终：

```text
RDX = 9
max_value = 9
```

## 7. 最终校验值

成立的布尔结果：

```text
result_eq              1
result_zero            1
result_signed_less     1
result_unsigned_above  1
result_overflow        1
result_no_carry        1
result_carry           1
result_wrap_zero       1
branch_negative        1
max_value              9
```

合计：

```text
8 + 1 + 9 = 18
```

## 8. 编译器输出观察

典型 GCC `-O2` 输出可能包括：

```asm
is_zero:
    testq %rdi, %rdi
    sete  %al

signed_less:
    cmpq  %rsi, %rdi
    setl  %al

unsigned_above:
    cmpq  %rdi, %rsi
    setb  %al

max_signed:
    cmpq   %rsi, %rdi
    cmovge %rdi, %rax
```

`unsigned_above` 使用 `setb` 并不表示语义变了。编译器交换了比较操作数，因此：

```text
left > right
```

可等价改写为：

```text
right < left
```

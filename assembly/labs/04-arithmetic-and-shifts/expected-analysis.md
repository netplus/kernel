# Lab 04 预期分析

本文件记录纯汇编实验的主要观察结果。数值以 64 位寄存器为准。

## 1. `after_add_sub`

前面执行：

```asm
movq $20, %rbx
addq $7, %rbx
subq $5, %rbx
```

因此：

```text
RBX = 22 = 0x16
```

最后一条 `subq` 会更新算术标志位。

---

## 2. `after_bitops`

执行过程：

```text
0xf0 & 0x3c = 0x30
0x30 | 0x03 = 0x33
0x33 ^ 0x11 = 0x22
```

因此：

```text
RSI = 0x22 = 34
```

`and/or/xor` 会根据结果更新 `ZF/SF/PF`，并清零 `CF/OF`。

---

## 3. `after_not`

前一条指令：

```asm
notq %rsi
```

所以：

```text
RSI = ~0x22
    = 0xffffffffffffffdd
```

`not` 不修改 `RFLAGS`。因此这里的条件标志仍然来自前面的 `xorq $0x11,%rsi`。

随后第二次 `notq %rsi` 会把 RSI 恢复为 `0x22`，便于最后计算校验和。

---

## 4. `after_shifts`

初始位模式：

```text
R8 = -16
   = 0xfffffffffffffff0
```

算术右移：

```asm
sarq $2, %r9
```

保持符号位：

```text
R9 = -4
   = 0xfffffffffffffffc
```

逻辑右移：

```asm
shrq %cl, %r10
```

其中 `CL=2`，高位补 0：

```text
R10 = 0x3ffffffffffffffc
```

这两个结果说明，同一位模式使用 `sar` 和 `shr` 会得到完全不同的解释。

---

## 5. `after_imul`

```asm
movq $7, %r11
imulq $9, %r11
```

结果：

```text
R11 = 63 = 0x3f
```

这里使用两操作数 `imul`，只保留 64 位目标结果。

---

## 6. `after_mul`

执行：

```asm
movq $6, %rax
movq $7, %rcx
mulq %rcx
```

单操作数 `mulq` 的完整结果写入：

```text
RDX:RAX
```

因为：

```text
6 * 7 = 42
```

所以：

```text
RAX = 42
RDX = 0
R12 = 42
```

高 64 位为 0，说明结果完全能够放入低 64 位。

---

## 7. `after_idiv`

执行：

```asm
movq $-100, %rax
cqto
movq $9, %rcx
idivq %rcx
```

`cqto` 把 `RAX` 符号扩展到 `RDX:RAX`。

计算结果：

```text
-100 / 9 = -11，余数 -1
```

因此：

```text
RAX = -11 = 0xfffffffffffffff5
RDX = -1  = 0xffffffffffffffff
R13 = -11
R14 = -1
```

满足：

```text
-100 = (-11) * 9 + (-1)
```

`div/idiv` 后的算术标志不应作为有效结果解释，重点观察商和余数。

---

## 8. `after_div`

执行：

```asm
movq $100, %rax
xorq %rdx, %rdx
movq $9, %rcx
divq %rcx
```

先清零 `RDX`，因此被除数是：

```text
RDX:RAX = 100
```

结果：

```text
RAX = 11
RDX = 1
R15 = 11
```

满足：

```text
100 = 11 * 9 + 1
```

---

## 9. 最终校验和

程序使用观察到的寄存器值计算：

```text
22
+ 34
- (-4)
+ 63
+ 42
- (-11)
- (-1)
+ 11
+ 1
= 189
```

因此：

```text
exit status = 189
```

这里只使用退出状态验证这组小整数结果。Linux 进程退出状态只能可靠表示低 8 位，因此不能用它代替一般的 64 位寄存器观察。

---

## 10. `companion.c` 的 `-O2` 观察重点

不同 GCC 版本的具体指令序列可能不同，但可以重点寻找以下语义：

```text
signed_shift
    有符号右移，通常出现 sar

unsigned_shift
    无符号右移，通常出现 shr

multiply
    普通 64 位乘法，通常出现两操作数 imul

divide_signed
    通常先把被除数放入 RAX，再使用 cqto + idiv

divide_unsigned
    通常先清零 EDX/RDX，再使用 div

divide_by_10
    -O2 下可能使用乘法、取高半部、移位和修正，而不是 idiv

scale_by_10
    可能使用 lea、add、shift 或 imul 的等价组合
```

分析编译器输出时，以高级语义为准，不要求不同编译器版本生成完全相同的指令序列。

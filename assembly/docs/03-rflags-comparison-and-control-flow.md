# 第 3 课：`RFLAGS`、比较、条件跳转与基本块

## 1. 本课目标

完成本课后，应能够：

1. 说明 `RFLAGS` 在算术、比较和控制流中的作用；
2. 区分 `CF`、`ZF`、`SF`、`OF` 的语义；
3. 准确解释 `cmp source,destination` 的操作数顺序；
4. 理解 `test reg,reg` 为什么常用于零值和符号判断；
5. 根据同一组标志位分别完成有符号和无符号比较；
6. 区分有符号溢出与无符号进位；
7. 阅读 `jcc`、`setcc` 和 `cmovcc`；
8. 从条件跳转识别基本块和控制流图；
9. 用 GDB 观察具体指令后的标志位；
10. 为后续学习循环、函数调用、系统调用返回路径和内核分支代码建立基础。

本课实验位于：

```text
assembly/labs/03-flags-and-branches/
```

---

## 2. 问题背景：CPU 如何记住“上一次运算的性质”

高级语言允许我们直接写：

```c
if (a > b)
    return a;
```

CPU 需要解决两个问题：

1. 如何比较 `a` 和 `b`；
2. 如何让下一条跳转指令知道比较结果。

x86 采用的基本设计是：

```text
算术/逻辑指令更新 RFLAGS
条件跳转读取 RFLAGS
```

典型过程：

```asm
cmpq %rsi, %rdi
jg .Lgreater
```

`cmp` 不保存减法结果，而是把“结果是否为零、是否为负、是否发生进位、是否有符号溢出”等性质记录在标志位中；`jg` 再根据这些标志位决定是否改变 `RIP`。

这种设计的收益包括：

- 比较不需要占用额外通用寄存器；
- 多种条件可以复用同一次比较结果；
- 条件跳转、条件置位和条件移动共享统一条件码体系。

代价是标志位属于隐式状态：两条相关指令之间若插入会修改标志位的指令，原比较结果就会丢失。

---

## 3. `RFLAGS` 中的关键状态位

| 标志位 | 名称 | 核心语义 |
|---|---|---|
| `CF` | Carry Flag | 无符号进位或借位 |
| `PF` | Parity Flag | 结果最低字节中 1 的数量是否为偶数 |
| `AF` | Auxiliary Carry | 低 4 位到高 4 位的进位，主要服务历史 BCD 语义 |
| `ZF` | Zero Flag | 结果是否为 0 |
| `SF` | Sign Flag | 结果最高位是否为 1 |
| `OF` | Overflow Flag | 有符号结果是否超出可表示范围 |
| `DF` | Direction Flag | 字符串指令地址递增还是递减 |
| `IF` | Interrupt Flag | 是否允许可屏蔽中断，用户态不可随意控制 |

需要特别避免一个误解：

> `SF=1` 只表示结果最高位为 1；有符号大小判断不能只看 `SF`，还必须结合 `OF`。

---

## 4. 哪些指令会修改标志位

### 4.1 常见会更新算术标志的指令

```asm
add sub cmp
and or xor test
shl shr sar
inc dec
```

### 4.2 通常不修改算术标志的指令

```asm
mov
lea
push
pop
```

例如：

```asm
cmpq %rsi, %rdi
movq %rax, %rbx
jg .Lgreater
```

中间的 `mov` 不破坏比较结果。

而：

```asm
cmpq %rsi, %rdi
addq $1, %rax
jg .Lgreater
```

`jg` 判断的是 `add` 产生的新标志，而不再是 `cmp` 的结果。

### 4.3 `inc/dec` 的特殊性

`inc` 和 `dec` 会更新多个标志位，但不会修改 `CF`。这是历史兼容语义。因此当代码依赖无符号进位链时，不能把 `addq $1` 随意替换为 `incq`。

---

## 5. `cmp`：执行减法，但不保存结果

AT&T 语法：

```asm
cmpq source, destination
```

概念操作：

```text
destination - source
```

结果不写回，只更新标志位。

例如：

```asm
cmpq %rsi, %rdi
```

概念上是：

```text
RDI - RSI
```

不是 `RSI - RDI`。

### 5.1 等值比较

```asm
cmpq %rsi, %rdi
je .Lequal
```

当 `RDI-RSI=0` 时 `ZF=1`，因此 `je` 跳转。

`je` 与 `jz` 是同一条件的不同助记符：

```text
je：强调比较语义 equal
jz：强调标志语义 zero
```

机器编码相同。

### 5.2 操作数顺序错误的后果

考虑：

```c
if (a < b)
```

若 `RDI=a`、`RSI=b`，正确形式通常是：

```asm
cmpq %rsi, %rdi
jl .La_less
```

因为检查的是 `a-b`。把操作数写反后，条件也必须相应翻转。

---

## 6. `test`：执行按位与，但不保存结果

```asm
testq source, destination
```

概念操作：

```text
destination & source
```

结果不写回，只更新标志位；`test` 会把 `CF` 和 `OF` 清零。

### 6.1 判断寄存器是否为零

```asm
testq %rax, %rax
je .Lzero
```

`RAX & RAX` 仅在 `RAX=0` 时结果为 0。

### 6.2 判断某个位是否设置

```asm
testq $0x8, %rax
jnz .Lbit3_set
```

概念上检查 `RAX & 0x8`。这类代码在 Linux 内核的状态位、特性位和协议标志处理中极其常见。

### 6.3 判断符号

```asm
testq %rax, %rax
js .Lnegative
```

`test` 的结果与原值相同，因此 `SF` 反映原值最高位。

---

## 7. `CF` 与 `OF`：两个完全不同的“溢出”概念

### 7.1 无符号进位：`CF`

8 位示例：

```text
0xff + 1 = 0x00
CF = 1
ZF = 1
```

### 7.2 有符号溢出：`OF`

8 位补码范围为 `-128～127`：

```text
127 + 1 = 0x80
OF = 1
CF = 0
```

两个正数相加得到负数，说明有符号结果不可表示。

### 7.3 两者可以独立出现

| 运算 | 结果位模式 | `CF` | `OF` |
|---|---:|---:|---:|
| `0xffff...ffff + 1` | `0` | 1 | 0 |
| `0x7fff...ffff + 1` | `0x8000...0000` | 0 | 1 |
| `1 + 1` | `2` | 0 | 0 |

因此不能用 `OF` 判断无符号范围，也不能用 `CF` 判断有符号范围。

---

## 8. 有符号和无符号比较

执行一次：

```asm
cmpq %rsi, %rdi
```

之后可以从两种语义解释标志位。

### 8.1 等于和不等于与符号无关

```text
je / jz     ZF = 1
jne / jnz   ZF = 0
```

### 8.2 无符号条件

| 条件 | 跳转 | 标志表达式 |
|---|---|---|
| `<` | `jb` / `jc` | `CF=1` |
| `<=` | `jbe` | `CF=1 或 ZF=1` |
| `>` | `ja` | `CF=0 且 ZF=0` |
| `>=` | `jae` / `jnc` | `CF=0` |

`above / below` 通常表示无符号比较。

### 8.3 有符号条件

| 条件 | 跳转 | 标志表达式 |
|---|---|---|
| `<` | `jl` | `SF != OF` |
| `<=` | `jle` | `ZF=1 或 SF != OF` |
| `>` | `jg` | `ZF=0 且 SF=OF` |
| `>=` | `jge` | `SF=OF` |

发生有符号溢出时，结果符号位可能与真实数学大小相反，因此不能简单只看 `SF`。

### 8.4 典型示例：`-1` 与 `1`

```asm
movq $-1, %rax
cmpq $1, %rax
```

之后：

```text
jl 条件成立：-1 < 1
ja 条件也成立：ULONG_MAX > 1
```

这不矛盾，因为两条指令采用不同的数据解释规则。

---

## 9. 条件码的三种消费方式

### 9.1 `jcc`：条件跳转

```asm
cmpq %rsi, %rdi
jge .Lgreater_or_equal
```

条件成立时修改 `RIP`。

### 9.2 `setcc`：生成布尔值

```asm
cmpq %rsi, %rdi
setl %al
```

`AL` 被设置为 0 或 1。注意 `setcc` 只写 8 位，常见写法是先通过 `xorl %eax,%eax` 清零完整返回寄存器。

### 9.3 `cmovcc`：条件移动

```asm
movq %rsi, %rax
cmpq %rsi, %rdi
cmovg %rdi, %rax
```

概念上实现：

```c
return rdi > rsi ? rdi : rsi;
```

`cmovcc` 不改变控制流，可以避免某些短分支的预测失败，但并不总是更快：两边表达式可能仍要提前计算，可预测分支本身成本也可能很低。

---

## 10. 条件跳转与基本块

一个基本块通常满足：

1. 只能从第一条指令进入；
2. 块内除最后一条外没有跳转；
3. 最后一条决定下一个可能执行的块。

例如：

```asm
    testq %rdi, %rdi
    jns nonnegative

negative:
    movl $-1, %eax
    ret

nonnegative:
    movl $1, %eax
    ret
```

可划分为：

```text
Block A: test + jns
   ├── false → Block B
   └── true  → Block C

Block B: return -1
Block C: return 1
```

块之间的连接形成控制流图 CFG。后续阅读循环、错误处理路径、内核入口和调度代码时，都应先划分基本块，而不是把函数当作一条线性指令流。

---

## 11. `if/else` 的典型翻译

C 代码：

```c
long max_signed(long a, long b)
{
    if (a > b)
        return a;
    return b;
}
```

分支版本：

```asm
cmpq %rsi, %rdi
jle .Lreturn_b
movq %rdi, %rax
ret

.Lreturn_b:
movq %rsi, %rax
ret
```

条件移动版本：

```asm
movq %rsi, %rax
cmpq %rsi, %rdi
cmovg %rdi, %rax
ret
```

两者语义相同，但控制流结构不同。

---

## 12. 循环是“回边”形成的控制流

```asm
.Lloop:
    testq %rdi, %rdi
    je .Ldone
    subq $1, %rdi
    jmp .Lloop
.Ldone:
```

从循环尾部跳回较低地址形成回边。识别回边是恢复循环结构的关键。

---

## 13. 分支预测的设计考虑

现代 CPU 会预测条件跳转结果和目标，以便提前取指和执行。预测正确时分支成本可能很低；预测失败时错误路径上的推测工作需要被丢弃。

阅读代码时应区分：

```text
语义问题：跳转何时成立
性能问题：该分支是否容易预测
```

Linux 内核中的 `likely()` / `unlikely()` 主要向编译器提供概率信息，影响代码布局和优化决策，并不是简单生成一条硬件预测提示指令。

---

## 14. GDB 中观察标志位

常用命令：

```gdb
info registers eflags
p/x $eflags
p/t $eflags
x/8i $rip
si
```

建议在 `cmp/test/add/sub` 执行后立即观察，避免后续指令覆盖标志位。

实验程序保留了可供 GDB 直接下断点的符号：

```text
after_cmp_equal
after_test_zero
after_cmp_signed_unsigned
after_signed_overflow
after_unsigned_carry
negative
after_sign_branch
select_first
max_done
```

---

## 15. 与 Linux kernel 5.10 的联系

内核汇编和编译后的 C 代码中大量出现：

```asm
testq %rax, %rax
jz ...

cmpq $0, offset(%rsp)
jne ...

testl $MASK, flags(%rdi)
jnz ...
```

典型用途包括：

- 判断函数返回值是否为错误或空指针；
- 检查任务状态和 CPU 特性位；
- 检查 `pt_regs` 中的用户态/内核态状态；
- 选择系统调用快速返回或慢速返回路径；
- 网络协议栈中检查 skb、socket 和协议标志。

后续分析 `entry_SYSCALL_64` 时，需要沿条件跳转识别快速 SYSRET 路径、IRET 慢路径、信号/调度/审计处理路径和异常修复路径。

---

## 16. 常见错误

1. 忘记 AT&T 操作数顺序：`cmpq %rsi,%rdi` 检查的是 `RDI-RSI`；
2. 混用有符号和无符号跳转；
3. 以为 `cmp` 会修改操作数；
4. 在比较和跳转之间插入会覆盖标志位的指令；
5. 以为 `setcc` 会写完整寄存器；
6. 把 `CF` 和 `OF` 当成同一个概念；
7. 只看助记词，不看编译器是否交换了比较操作数。

---

## 17. 本课实验任务

```bash
cd assembly/labs/03-flags-and-branches
make clean all
make run
make disasm
make c-asm
make gdb
```

重点完成：

1. 验证 `cmp` 后 `RAX` 未变化；
2. 验证 `test 0,0` 后 `ZF=1`；
3. 验证同一次 `cmp(-1,1)` 后 `setl` 和 `seta` 都得到 1；
4. 比较 `LONG_MAX+1` 与 `ULONG_MAX+1` 的 `OF/CF/ZF`；
5. 画出负数判断和最大值选择的 CFG；
6. 对比 `companion.c` 的 `-O0` 与 `-O2` 输出；
7. 解释编译器为什么可能使用 `setcc` 或 `cmovcc` 代替条件跳转。

---

## 18. 验收标准

在进入下一课前，应能够不借助资料解释：

```text
cmpq %rsi,%rdi 为什么表示 RDI-RSI
ZF、CF、SF、OF 分别描述什么
jg/jl 与 ja/jb 为什么不能混用
为什么 -1 既可能“小于 1”又可能“高于 1”
testq %rax,%rax 为什么能判断零和符号
setcc 为什么经常需要先清零 EAX
条件跳转如何划分基本块
```

下一课进入：

> 栈、`push/pop`、`call/ret`、System V AMD64 ABI 与函数栈帧。

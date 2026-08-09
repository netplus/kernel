# Lab 05 预期分析

## 1. `while` 循环

程序计算：

```text
1 + 2 + 3 + 4 + 5 = 15
```

在 `after_while`：

```text
RAX = 15
R8  = 15
RCX = 6
```

关键控制流：

```text
.Lwhile_test
→ cmpq $5, %rcx
→ jg .Lwhile_done
→ 循环体
→ incq %rcx
→ jmp .Lwhile_test
```

`jmp .Lwhile_test` 构成明显回边。

## 2. `do-while` 循环

程序计算：

```text
4 + 3 + 2 + 1 = 10
```

在 `after_do_while`：

```text
RAX = 10
R9  = 10
RCX = 0
```

关键指令：

```asm
decq %rcx
jne .Ldo_body
```

循环体先执行，条件在尾部检查。这正是 `do-while` 的基本结构。

## 3. 数组指针遍历

数组：

```text
3, 5, 7, 9
```

结果：

```text
R10 = 24
```

循环中没有单独保存数组下标，而是直接移动指针：

```asm
addq (%rsi), %rax
addq $8, %rsi
```

每次增加 8 字节，移动到下一个 `long`。

这说明源代码中的数组下标在优化或手写汇编中可以转化成指针变化。

## 4. 状态机

初始状态：

```text
state = 0
score = 0
```

转换过程：

```text
state 0: score += 1, state = 1
state 1: score += 2, state = 2
state 2: score += 3, state = 3
state 3: 不再匹配处理状态，退出
```

因此：

```text
R11 = 6
RCX = 3
```

控制流反复回到 `.Lstate_dispatch`，形成状态分发循环。

## 5. 跳转表 `switch`

选择值：

```text
RDI = 4
```

范围检查：

```asm
cmpq $5, %rdi
ja .Lswitch_default
```

由于 4 在 `0..5` 范围内，进入表驱动路径。

表基址：

```asm
leaq .Lswitch_table(%rip), %rdx
```

读取第 4 项：

```asm
movslq (%rdx,%rdi,4), %rax
```

即读取：

```text
table_base + 4 * 4
```

位置处的 32 位有符号偏移。

随后：

```asm
addq %rdx, %rax
jmp *%rax
```

把相对偏移转换成实际目标地址，并间接跳到 `.Lcase4`。

`case4` 返回：

```text
R12 = 19
```

## 6. 最终校验值

各阶段：

```text
while          15
do-while       10
array loop     24
state machine   6
switch          19
------------------
checksum        74
```

因此程序通过 Linux x86-64 `exit` 系统调用返回：

```text
exit status = 74
```

## 7. GCC `-O2` 预期观察

具体指令会随 GCC 版本变化，但重点观察语义。

### `dense_switch`

连续 `case 0..5` 很可能产生：

```text
范围检查
→ 取得跳转表基址
→ 按 op 索引 32 位相对偏移
→ 基址加偏移
→ 间接 jmp
```

一种典型形式是：

```asm
cmpl   $5, %eax
ja     .Ldefault
leaq   .Ltable(%rip), %rdx
movslq (%rdx,%rax,4), %rax
addq   %rdx, %rax
jmp    *%rax
```

### `sparse_switch`

`1/10/100/1000` 的值分布较稀疏，通常不适合建立覆盖整个范围的跳转表。

更可能看到：

```text
cmp
je
ja/jb
cmov
```

组成的比较结构。

### `run_state_machine`

这个状态机的状态变化非常确定。优化器可能：

- 合并多个状态处理块；
- 消除某些显式状态赋值；
- 把多次循环迭代折叠成较短的控制流。

因此不要要求优化后的代码仍与源代码中的 `for + switch` 一一对应。

## 8. 验收问题

完成实验后，应能回答：

1. `while` 和 `do-while` 的条件检查位置有什么不同？
2. 什么是控制流中的回边？
3. 为什么数组循环可能看不到显式下标？
4. 状态机如何表示为“分发块 + 状态处理块 + 回边”？
5. 稠密和稀疏 `switch` 为什么可能采用不同实现？
6. `jmp *%rax` 与 `jmp label` 有什么区别？
7. 跳转表为什么要先做范围检查？
8. 表项为什么可以保存相对偏移而不是完整 64 位地址？

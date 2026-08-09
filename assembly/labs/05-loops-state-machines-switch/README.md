# Lab 05：循环、状态机与 `switch`

## 1. 实验要回答什么

本实验围绕控制流展开，重点验证下面几个问题：

1. `while` 循环怎样形成“条件检查 + 循环体 + 回边”；
2. `do-while` 为什么常见为循环尾部的一次条件跳转；
3. 数组遍历为什么可以直接移动指针，而不保留显式下标；
4. 状态机怎样表现为状态分发、状态处理和回到分发点；
5. 稠密 `switch` 怎样通过范围检查和跳转表选择目标；
6. `jmp *%rax` 这样的间接跳转与直接跳转有什么不同；
7. 稀疏 `switch` 为什么更可能使用比较结构；
8. GCC `-O2` 为什么可能改变甚至消除源代码中的循环或状态变量。

对应教程：

[`../../docs/05-loops-state-machines-and-switch.md`](../../docs/05-loops-state-machines-and-switch.md)

---

## 2. 文件说明

```text
control_flow.s          纯汇编控制流实验
companion.c             C 语言对照代码
Makefile                构建、运行和反汇编入口
gdb.cmd                 GDB 观察脚本
expected-analysis.md    预期结果和控制流分析
```

---

## 3. 构建与运行

```bash
make clean all
make run
```

预期：

```text
exit status=74 (expected 74)
```

校验值由五部分组成：

```text
while          15
do-while       10
array loop     24
state machine   6
switch          19
------------------
checksum        74
```

退出状态只用于快速判断纯汇编程序是否走过了预期路径。真正需要观察的是各个标签处的寄存器和跳转关系。

---

## 4. 反汇编

```bash
make disasm
```

会同时输出 AT&T 和 Intel 语法。

建议先寻找：

```text
条件跳转
无条件跳转
后向跳转
间接跳转
跳转目标
```

纯汇编程序中应能看到：

```asm
jg     ...
jne    ...
jmp    ...
movslq (...), %rax
jmp    *%rax
```

其中最后两条是相对跳转表的关键部分。

---

## 5. GDB 观察

```bash
make gdb
```

脚本会在下面几个位置停止：

```text
after_while
after_do_while
after_array_loop
after_state_machine
after_switch
```

预期主要结果：

```text
after_while          R8  = 15
after_do_while       R9  = 10
after_array_loop     R10 = 24
after_state_machine  R11 = 6
after_switch         R12 = 19
```

手工调试时可以使用：

```gdb
info registers rax rcx rdx rsi rdi r8 r9 r10 r11 r12 eflags
x/16i $pc
si
continue
```

观察循环时，不要只记录寄存器最终值。还应记录：

```text
条件在哪里检查？
哪条指令修改条件所依赖的标志位？
哪条边回到前面的基本块？
退出循环时是哪一个条件成立？
```

---

## 6. 观察 `while` 与 `do-while`

### `while`

重点找到：

```text
.Lwhile_test
→ 条件跳转到退出
→ 循环体
→ 无条件跳回 .Lwhile_test
```

它对应“先检查、后执行”。

### `do-while`

重点找到：

```asm
decq %rcx
jne .Ldo_body
```

它对应“先执行、后检查”。

比较两种循环后，应能从汇编结构判断条件检查发生在循环体之前还是之后。

---

## 7. 观察数组遍历

纯汇编实验直接移动 `%rsi`：

```asm
addq (%rsi), %rax
addq $8, %rsi
```

每轮都把指针移动到下一个 `long`。

这里没有单独保存数组索引。

这说明：

> C 语言中的 `array[i]` 不要求汇编中一定存在一个名为 `i` 的独立运行时值。

---

## 8. 观察状态机

状态寄存器为 `%rcx`。

按照实际执行顺序记录：

```text
state 0
→ state 1
→ state 2
→ state 3
→ 退出
```

同时记录 `%rax`：

```text
0
→ 1
→ 3
→ 6
```

重点不是记住这些数值，而是识别：

```text
状态分发块
状态处理块
状态更新
回到分发块的跳转
```

---

## 9. 观察跳转表

选择值固定为：

```text
RDI = 4
```

重点单步执行：

```asm
leaq .Lswitch_table(%rip), %rdx
cmpq $5, %rdi
ja .Lswitch_default
movslq (%rdx,%rdi,4), %rax
addq %rdx, %rax
jmp *%rax
```

建议在 `jmp *%rax` 前查看：

```gdb
p/x $rdx
p/x $rax
x/6wx $rdx
x/i $rax
```

需要能够解释：

```text
RDX 是表基址
RDI 是索引
每个表项为 4 字节相对偏移
RAX 最终变成目标代码地址
jmp *%rax 按运行时地址跳转
```

---

## 10. C 编译器对照

```bash
make c-asm
```

重点比较 `-O0` 和 `-O2` 下的：

```text
sum_while
sum_do_while
sum_array
dense_switch
sparse_switch
run_state_machine
```

### `dense_switch`

连续 `case 0..5` 在常见 GCC `-O2` 输出中可以看到：

```text
范围检查
→ 相对偏移表
→ movslq
→ add
→ 间接 jmp
```

### `sparse_switch`

`case 1/10/100/1000` 更可能表现为多次比较和条件选择。

### `run_state_machine`

不要期待优化后的代码仍保留源代码的 `for (;;) + switch` 形状。这个例子用于观察优化器如何合并确定的状态转换。

编译器版本不同，具体指令可以不同；应比较控制流语义，而不是要求逐条一致。

---

## 11. 符号检查

```bash
make symbols
```

应能看到：

```text
_start
after_while
after_do_while
after_array_loop
after_state_machine
after_switch
```

这些全局标签用于稳定地设置 GDB 断点。

---

## 12. 分层练习

### 基础练习

1. 画出纯汇编 `while` 的控制流图；
2. 标出循环头、循环体、回边和出口；
3. 说明 `do-while` 为什么至少执行一次；
4. 说明数组循环中 `%rsi` 每次增加 8 的原因。

### 进阶练习

1. 把 `while` 改成从 5 递减到 1；
2. 给数组循环增加“遇到 7 时提前退出”；
3. 给状态机增加一个错误状态；
4. 把跳转表选择值改成 6，观察 `default` 路径；
5. 把跳转表改成 `case 3..8`，思考索引为什么需要先减去最小 case 值。

### 编译器练习

1. 改变 `dense_switch` 的 case 密度，观察 GCC 何时放弃跳转表；
2. 把每个 case 改成只返回常量，观察是否变成数据查找表；
3. 比较 `-O0` 与 `-O2` 下状态机的基本块数量；
4. 在 `sum_array` 中加入条件分支，重新画 CFG。

---

## 13. 常见误区

### 只按反汇编地址从上到下阅读

循环和多分支代码必须按控制流图阅读，否则容易把没有实际执行的文本当作执行顺序。

### 把所有后向跳转都当作相同类型循环

后向跳转只能提示存在回边，还要结合条件、状态更新和出口判断其语义。

### 认为 `switch` 必然存在间接跳转

case 稀疏或逻辑简单时，编译器可以使用比较、条件移动或普通数据表。

### 忽略跳转表的范围检查

直接使用未经检查的索引访问目标地址表会破坏控制流，因此范围检查通常是理解跳转表的第一步。

---

## 14. 验收标准

完成实验后，看到：

```asm
cmpl   $5, %eax
ja     .Ldefault
leaq   .Ltable(%rip), %rdx
movslq (%rdx,%rax,4), %rax
addq   %rdx, %rax
jmp    *%rax
```

应能够说明：

```text
先检查索引范围
表项大小为 4 字节
表项保存相对偏移
偏移与基址相加得到目标地址
最后执行间接跳转
```

完整预期分析见：

[`expected-analysis.md`](expected-analysis.md)

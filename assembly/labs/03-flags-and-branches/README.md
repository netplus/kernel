# Lab 03：`RFLAGS`、比较与条件分支

## 1. 实验要回答什么

本实验围绕一个核心问题展开：

> CPU 如何把一次算术或比较的结果性质，交给后续条件指令使用？

需要验证：

1. `cmp` 和 `test` 只更新标志，不保存运算结果；
2. 同一组比较标志可以按有符号或无符号语义解释；
3. `CF` 描述无符号进位/借位，`OF` 描述有符号溢出；
4. `setcc` 生成 0/1，`cmovcc` 条件选择数据，`jcc` 条件选择路径；
5. 条件跳转会把代码划分成基本块并形成 CFG；
6. 编译器可能在分支、`setcc` 和 `cmovcc` 之间选择不同实现。

对应教程：

[`../../docs/03-rflags-comparison-and-control-flow.md`](../../docs/03-rflags-comparison-and-control-flow.md)

---

## 2. 文件说明

```text
flags_and_branches.s  纯汇编实验
companion.c           C 语言对照代码
Makefile              构建、运行和反汇编入口
gdb.cmd               GDB 观察脚本
expected-analysis.md  预期寄存器、标志位和控制流分析
```

---

## 3. 推荐学习顺序

### 基础路径

```bash
make clean all
make run
make gdb
```

目标是观察 `ZF/CF/SF/OF` 的实际变化，并确认不同条件成立与否。

### 进阶路径

```bash
make disasm
make c-asm
```

对照纯汇编和 GCC 输出，寻找：

```asm
testq
cmpq
sete / setl / setb / setc
cmovge / cmovs
```

### 系统方向路径

在反汇编上手工划分基本块，画出条件边、无条件边和汇合块，并尝试对应到内核中的状态检查或错误路径。

---

## 4. 构建与运行

```bash
make clean all
make run
```

预期：

```text
exit status=18 (expected 18)
```

校验和组成：

```text
8 个成立的标志条件
+ 1 个负数分支结果
+ 最大值 9
= 18
```

退出状态只是为了提供自动化校验；真正的学习重点是每个观察点的寄存器和 `RFLAGS`。

---

## 5. 实验案例总览

| 案例 | 预期重点 |
|---|---|
| `cmp 7,7` | `ZF=1`，`RAX` 仍为 7 |
| `test 0,0` | `ZF=1` |
| `cmp -1,1` | 有符号 `<` 和无符号 `>` 同时成立 |
| `LONG_MAX+1` | `OF=1`、`CF=0` |
| `ULONG_MAX+1` | `CF=1`、`ZF=1`、`OF=0` |
| 负数分支 | 进入 `negative` 基本块 |
| `max(9,4)` | 选择结果 9，并在汇合块保存 |

---

## 6. GDB 调试

```bash
make gdb
```

脚本会在保留于 ELF 符号表中的观察标签处停止。

手工调试常用：

```gdb
info registers rax rcx r8 r11 r14 eflags
p/x $eflags
x/12i $pc
si
continue
```

每个观察点记录：

```text
前一条更新标志的指令
操作数位模式
按有符号解释的关系
按无符号解释的关系
ZF/CF/SF/OF
下一条条件是否成立
```

不要只记录“跳了或没跳”，还要解释为什么。

---

## 7. 反汇编与基本块

```bash
make disasm
```

建议先标记：

```text
所有条件跳转
所有无条件跳转
所有跳转目标
所有 ret/syscall 等终止点
```

然后划分基本块。

一个可用的基本块分析模板：

```text
Block 名称：
入口条件：
读取的寄存器/内存：
修改的寄存器/内存：
最后一条控制转移：
后继块：
```

重点观察负数分支和最大值选择如何从多个路径进入汇合位置。

---

## 8. 编译器输出对照

```bash
make c-asm
```

重点函数：

```text
is_zero
signed_less
unsigned_above
max_signed
sign_class
add_with_carry
```

分析时不要只寻找固定指令名称，而应先确认语义：

- `value == 0` 可能是 `test + sete`；
- 有符号 `<` 通常使用 `setl` 或对应跳转；
- 无符号 `>` 可能因 `cmp` 操作数顺序不同而表现为 `seta` 或 `setb`；
- `max_signed` 可能使用分支，也可能使用 `cmov`；
- 加法进位可通过 `setc` 或等价的数据比较得到。

具体输出会随 GCC 版本和优化级别变化，但类型语义必须保持一致。

---

## 9. 分层练习

### 基础练习

1. 说明 `cmpq $7,%rax` 是否改变 `RAX`；
2. 说明 `testq %rcx,%rcx` 为什么可判断零；
3. 写出 `jl`、`ja` 分别属于哪种类型语义；
4. 对比 `LONG_MAX+1` 与 `ULONG_MAX+1` 的标志。

### 进阶练习

在一次 `cmp` 后分别插入：

```asm
movq %rax, %rbx
```

和：

```asm
addq $1, %rbx
```

预测后续 `setcc` 是否仍使用原比较结果，并用 GDB 验证。

交换某次 `cmp` 的源、目标操作数，修改条件码使高级语义保持不变。

对比：

```text
jcc   选择执行路径
setcc 生成布尔值
cmov  选择寄存器数据
```

### 系统方向练习

1. 为纯汇编程序画 CFG；
2. 标记主路径、分支路径、汇合块；
3. 说明长度、地址、`size_t` 通常为什么使用无符号条件；
4. 在 Linux 内核反汇编中寻找 `test mask,field` 模式，并尝试恢复字段和掩码语义。

---

## 10. 常见调试误区

### 只看 GDB 显示的标志名称

GDB 可能以名称集合展示当前标志，但仍应理解每一位由哪条指令产生。

### 在错误位置观察

要观察某条 `cmp/add/test` 的标志，应在该指令执行之后、下一条修改标志的指令之前停止。

### 忘记 signed/unsigned

同一位模式可能得到完全不同的大小关系。必须先确定源语言类型或后续条件码族。

### 把线性反汇编当作唯一执行顺序

条件跳转可能跳过中间文本。应按 CFG 而不是只按文件行号分析。

---

## 11. 验收标准

完成实验后，应能够针对：

```asm
cmpq %rsi, %rdi
jbe target
```

准确说明：

```text
概念运算是 RDI-RSI
jbe 是无符号 <=
依赖 CF 或 ZF
跳转与不跳转进入不同基本块
中间不能有覆盖标志的指令
```

完整预期结果见：

[`expected-analysis.md`](expected-analysis.md)

# Lab 03：RFLAGS、比较与条件分支

本实验用于验证以下关键事实：

1. `cmp` 和 `test` 只更新标志位，不保存运算结果；
2. 同一组 `cmp` 结果可以按有符号或无符号方式解释；
3. `CF` 描述无符号进位/借位，`OF` 描述有符号溢出；
4. `setcc` 只写入一个字节；
5. 条件跳转会把函数划分为基本块并形成控制流图；
6. 编译器可能把短分支优化为 `setcc` 或 `cmovcc`。

## 文件说明

```text
flags_and_branches.s  纯汇编实验
companion.c           C 语言对照代码
Makefile              构建、运行和反汇编入口
gdb.cmd               GDB 观察脚本
expected-analysis.md  预期寄存器、标志位和控制流分析
```

## 构建与运行

```bash
make clean all
make run
```

预期输出：

```text
exit status=18 (expected 18)
```

退出状态 18 来自：

```text
8 个成立的标志条件
+ 1 个负数分支结果
+ 最大值 9
= 18
```

## 查看反汇编

```bash
make disasm
```

该命令同时输出 AT&T 和 Intel 语法。

## 对比编译器输出

```bash
make c-asm
```

重点寻找：

```asm
testq
cmpq
sete / setl / setb / setc
cmovge / cmovs
```

实际指令可能随 GCC 版本变化，但语义应保持一致。

## GDB 调试

```bash
make gdb
```

建议在各观察标签处重点检查：

```gdb
info registers rax rcx r8 r11 r14 eflags
p/x $eflags
x/12i $pc
```

`gdb.cmd` 已设置关键断点并输出对应寄存器和标志位。

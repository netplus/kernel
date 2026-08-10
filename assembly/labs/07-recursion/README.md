# Lab 07（第三部分）：递归调用与多层返回地址

## 1. 实验目标

本实验验证递归调用如何在栈上形成多层返回现场。

需要确认：

1. 每执行一次递归 `call` 都会压入新的返回地址栈项；
2. 同一个递归调用点产生的返回地址数值可以相同，但它们位于不同栈地址；
3. 当前实验每个非基例层额外保存一个 8 字节参数和一个 8 字节返回地址；
4. 最深一层最先通过 `ret` 返回；
5. 每层 `pop` 恢复自己的参数后再继续计算；
6. 最外层返回以后 `RSP` 恢复到调用前值。

对应教程：

[`../../docs/07-recursion-and-multiple-return-addresses.md`](../../docs/07-recursion-and-multiple-return-addresses.md)

## 2. 文件

```text
recursive_call.s       纯汇编递归实验
Makefile               构建、运行、符号和反汇编入口
gdb.cmd                递归深度观察脚本
expected-analysis.md  已验证结果与栈分析
```

## 3. 构建和运行

```bash
make clean all
make run
```

预期：

```text
exit status=6 (expected 6)
```

程序计算：

```text
recursive_sum(3) = 3 + 2 + 1 + 0 = 6
```

同时检查递归完全返回以后 `RSP` 是否等于调用前保存的值；失败时退出码为 99。

## 4. 反汇编和符号

```bash
make symbols
make disasm
```

重点寻找：

```asm
pushq %rdi
subq $1, %rdi
call recursive_sum
popq %rdi
addq %rdi, %rax
ret
```

当前参考构建中：

```text
recursive_sum / recursive_entry = 0x40102a
before_recursive_call           = 0x401030
after_recursive_call            = 0x401039
recursive_base                  = 0x40103e
```

递归 `call` 位于 `0x401034`，下一条指令为 `0x401039`，因此每个非基例层压入的返回地址值均为 `0x401039`。这些值相同，但对应不同的栈槽。

## 5. 每层栈空间

对于一个非基例层，进入本层后记 `RSP=S`：

```text
pushq %rdi  → RSP=S-8，保存本层 n
call ...    → RSP=S-16，保存返回地址
```

因此当前手写实验每个非基例层额外使用 16 字节。

这不是 x86-64 递归的固定开销；真实编译器生成的函数可能保存更多寄存器或分配局部变量。

## 6. GDB

如果环境安装了 GDB：

```bash
make gdb
```

建议在 `recursive_entry`、`before_recursive_call`、`after_recursive_call` 和 `recursive_base` 处观察：

```text
RDI
RAX
RSP
[RSP]
[RSP+8]
```

当前自动执行环境未安装 GDB，因此 GDB 输出没有记作已验证结果。

## 7. 已实际验证

```text
as --64 -g             通过
ld                     通过
程序运行               exit status=6
nm -n                  通过
objdump AT&T           通过
objdump Intel          通过
GDB                    未安装，未执行
```

详细分析见 [`expected-analysis.md`](expected-analysis.md)。

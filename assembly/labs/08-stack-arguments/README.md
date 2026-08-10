# Lab 08-3：寄存器耗尽后的栈上传参

## 1. 实验目标

验证八个 64 位 INTEGER 参数跨越 System V AMD64 ABI 函数边界时的实际位置：

```text
参数 1-6 → RDI、RSI、RDX、RCX、R8、R9
参数 7   → callee 入口 [RSP+8]
参数 8   → callee 入口 [RSP+16]
```

同时验证普通调用入口的栈对齐关系：

```text
(RSP + 8) mod 16 = 0
```

对应教程：

[`../../docs/08-stack-passed-arguments.md`](../../docs/08-stack-passed-arguments.md)

## 2. 文件

```text
main.c                 C caller、结果检查
probe.S                手写汇编 callee
Makefile               -O0/-O2 构建、运行、反汇编和符号检查
gdb.cmd                函数入口栈布局观察脚本
expected-analysis.md   预期与实际验证结果
```

## 3. 实验结构

```text
main
  ↓
call_probe
  ↓
abi_probe8(11,22,33,44,55,66,77,88)
  ├─ 记录 RDI..R9
  ├─ 记录入口 RSP
  ├─ 读取 8(RSP)  → 77
  ├─ 读取 16(RSP) → 88
  └─ 八个参数求和，通过 RAX 返回 396
  ↓
main 逐项验证
```

汇编 probe 在读取栈参数之前不修改 `%rsp`，因此偏移直接对应函数入口布局。

## 4. 构建与运行

```bash
make clean all
make run
```

预期 `-O0` 和 `-O2` 都输出：

```text
regs: 11 22 33 44 55 66
stack: [rsp+8]=77 [rsp+16]=88
entry alignment: (rsp+8) mod 16 = 0
return: 396
```

程序只有在所有观察值都符合预期时才返回 0。

## 5. 反汇编

```bash
make disasm
```

重点观察：

- caller 如何准备第 7、第 8 个参数；
- `call` 如何在参数区域下方再压入返回地址；
- `abi_probe8` 的 `8(%rsp)` 和 `16(%rsp)`；
- `-O0` 与 `-O2` 如何用不同序列满足相同 ABI 边界。

同时生成 AT&T 与 Intel 两种语法，避免把源/目的操作数顺序和寻址写法混淆。

## 6. 符号

```bash
make symbols
```

检查：

```text
abi_probe8
seen_regs
seen_stack
seen_entry_rsp
```

## 7. GDB

如果环境安装了 GDB：

```bash
gdb -q -x gdb.cmd ./stack_args_O0
```

脚本会在 `abi_probe8` 入口打印六个参数寄存器，并直接查看：

```text
[RSP]
[RSP+8]
[RSP+16]
```

本次验证环境未安装 GDB，因此脚本未实际执行。

## 8. 本次实际验证

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44

-O0 构建和运行             通过
-O2 构建和运行             通过
RDI..R9                   11 22 33 44 55 66
[RSP+8]                   77
[RSP+16]                  88
(RSP+8) mod 16            0
RAX 返回值                396
AT&T 反汇编               已检查
Intel 反汇编              已检查
nm                        已检查
GDB                       未安装，未执行
```

详细反汇编分析见 [`expected-analysis.md`](expected-analysis.md)。
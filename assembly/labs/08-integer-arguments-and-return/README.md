# Lab 08-1：INTEGER 参数寄存器与整数返回值

## 1. 实验目标

验证 System V AMD64 ABI 的最基础函数边界：

```text
RDI, RSI, RDX, RCX, R8, R9
```

分别承载前六个可分配到通用寄存器的 INTEGER 参数，并验证普通单个 64 位整数返回值通过 `%rax` 返回。

实验采用 **C caller + 手写汇编 callee**，避免只根据 C 编译器生成的单侧代码推断 ABI。

对应教程：

[`../../docs/08-integer-arguments-and-return-values.md`](../../docs/08-integer-arguments-and-return-values.md)

## 2. 文件

```text
main.c               C 调用者和结果检查
abi_probe.S          汇编被调函数，直接捕获入口寄存器
Makefile             -O0/-O2 构建与反汇编
gdb.cmd              入口寄存器和 RAX 返回值观察脚本
expected-analysis.md 预期与实际验证结果
```

## 3. 构建与运行

```bash
make clean all
make run
```

预期两个版本都输出：

```text
args: 11 22 33 44 55 66
return: 231
```

程序只有在六个捕获值和返回值都正确时才返回 0。

## 4. 反汇编

```bash
make disasm
```

重点检查 `call_probe`：

```text
11 → EDI/RDI
22 → ESI/RSI
33 → EDX/RDX
44 → ECX/RCX
55 → R8D/R8
66 → R9D/R9
```

再检查 `abi_probe6` 是否在入口直接读取六个寄存器，并把相加结果放入 `%rax`。

注意：当前 GCC `-O2` 会把 `call_probe()` 的最后一次调用优化成 tail call `jmp abi_probe6`。这不改变 ABI 参数寄存器约定。

## 5. GDB

如果系统安装了 GDB：

```bash
gdb -q -x gdb.cmd ./abi_probe_O0
```

脚本在 `abi_probe6` 入口打印六个参数寄存器，`finish` 后打印 `%rax`。

本次验证环境未安装 GDB，因此该脚本尚未实际执行；不要把脚本的预期输出当成已验证结果。

## 6. 本次实际验证

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44

-O0 构建和运行      通过
-O2 构建和运行      通过
AT&T 反汇编         已检查
Intel 反汇编        已检查
nm                  已检查
GDB                 未安装，未执行
```

详细分析见 [`expected-analysis.md`](expected-analysis.md)。

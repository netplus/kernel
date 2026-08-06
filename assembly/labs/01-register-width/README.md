# Lab 01：寄存器宽度与部分写入

## 实验目的

验证以下 x86-64 架构规则：

- 写 `AL` 只修改低 8 位；
- 写 `AX` 只修改低 16 位；
- 写 `EAX` 修改低 32 位并清零 `RAX` 高 32 位；
- `mov` 不重新计算算术条件标志；
- shell 退出码不能展示完整 64 位寄存器值。

## 文件

```text
register_width.s  最小纯汇编实验
companion.c       观察编译器的零扩展和符号扩展
Makefile          构建、运行和反汇编
gdb.cmd           GDB 单步脚本
expected-analysis.md  预期结果与解释
```

## 构建

```bash
make
```

## 运行

```bash
make run
```

预期：

```text
exit status: 120 (expected 120 / 0x78)
```

`120` 只是最终 `0x12345678` 的低 8 位。

## 反汇编

AT&T：

```bash
make disasm
```

Intel：

```bash
make disasm-intel
```

## GDB 单步

```bash
gdb -x gdb.cmd ./register_width
```

在断点处反复执行：

```gdb
si
```

预期 `RAX` 依次出现：

```text
0x1122334455667788
0x11223344556677ff
0x112233445566abcd
0x0000000012345678
```

## 比较编译器输出

```bash
make companion
less companion-O0.s
less companion-Og.s
less companion-O2.s
```

重点定位：

```text
zero_extend_u32
sign_extend_i32
```

观察 32 位无符号零扩展和 32 位有符号符号扩展的差异。

## 详细讲解

参见：

[`../../docs/01-cpu-execution-model-and-register-width.md`](../../docs/01-cpu-execution-model-and-register-width.md)

# A08 Red Zone 实验

本实验验证 System V AMD64 ABI 的 128-byte Red Zone，并区分三个问题：

1. leaf function 可以在不修改 `%rsp` 的情况下使用 `%rsp` 以下 128 字节作为临时空间；
2. Red Zone 中的数据不能假定跨普通函数调用继续有效；
3. Linux kernel 5.10 的 x86-64 内核代码使用 `-mno-red-zone`，因此不能把用户态 SysV Red Zone 规则直接套到内核 C 代码。

## 文件

- `main.c`：C caller，以及用于观察编译器 Red Zone 使用的 leaf function；
- `red-zone.S`：手写 leaf function 和跨调用边界实验；
- `Makefile`：构建、运行和反汇编检查；
- `expected-analysis.md`：实际验证结果与反汇编解释；
- `gdb.cmd`：可选的 GDB 观察脚本。

## 构建与运行

```bash
make
make run
make inspect
```

预期输出：

```text
asm leaf result=66
red-zone value survived nested call=0
compiler leaf result=50
```

程序返回 0 表示三个检查均通过。

## 关键观察点

`red_zone_leaf` 在入口处保存 `%rsp`，随后访问 `-8(%rsp)`、`-16(%rsp)` 和 `-120(%rsp)`，期间没有 `sub/add %rsp`。返回前再次比较 `%rsp`，验证 leaf function 可以直接使用 Red Zone。

`red_zone_call_boundary` 先把哨兵值放在入口 `%rsp-16`。为了让嵌套 `call` 前满足 16 字节调用边界，它执行 `subq $8,%rsp`；随后的 `call` 会把返回地址写到原入口 `%rsp-16`，因此原 Red Zone 数据被覆盖。实验返回 0 表示哨兵没有跨调用存活。

C 侧 `compiler_leaf()` 使用 `volatile` 局部数组，使 GCC `-O2` 生成可观察的栈访问。当前验证环境中，反汇编显示它直接使用负的 `%rsp` 偏移而没有调整 `%rsp`。

## GDB

当前自动验证环境没有安装 GDB，因此 `gdb.cmd` 已检查但未执行。具备 GDB 的环境可运行：

```bash
gdb -q ./red-zone -x gdb.cmd
```

# Lab 06：观察 `_start` 的初始用户栈

## 1. 实验目标

本实验不链接 libc，直接定义 ELF 入口 `_start`，验证 Linux x86-64 程序刚开始执行时的初始用户栈。

需要验证：

1. `_start` 的初始 `RSP` 可以直接作为进程启动栈基准；
2. `[RSP]` 是 `argc`；
3. `argv[]` 紧跟在 `argc` 后，并以 NULL 结束；
4. `envp[]` 紧跟在 argv NULL 后，并以 NULL 结束；
5. auxiliary vector 位于 envp NULL 后；
6. 每个 64 位 auxv 条目由 `a_type/a_val` 两个 8 字节值组成；
7. `AT_NULL` 结束 auxv；
8. 可以在 auxv 中找到 `AT_PAGESZ`；
9. 本实验环境中初始 `RSP` 为 16 字节对齐。

对应教程：

[`../../docs/06-initial-user-stack.md`](../../docs/06-initial-user-stack.md)

---

## 2. 文件

```text
initial_stack.s       直接从 _start 解析初始栈
Makefile              构建、运行、反汇编和符号检查
expected-analysis.md  预期布局与校验值
gdb.cmd               GDB 原始栈观察脚本
```

---

## 3. 构建和运行

```bash
make clean all
make run
```

`run` 使用固定命令：

```bash
env -i DEMO=1 ./initial-stack alpha beta
```

因此预期：

```text
argc = 3
```

程序把六项检查编码为退出状态，全部成功时：

```text
exit status=63 (expected 63)
```

退出状态只是自动化校验；实验重点仍然是理解地址计算和内存布局。

---

## 4. 六个检查位

```text
1   initial RSP % 16 == 0
2   argc == 3
4   argv[argc] == NULL
8   至少存在一个 envp 指针
16  auxv 扫描到 AT_NULL
32  找到非零 AT_PAGESZ
```

总和：

```text
63
```

完整解释见 [`expected-analysis.md`](expected-analysis.md)。

---

## 5. 反汇编

```bash
make disasm
```

同时检查 AT&T 和 Intel 语法。

重点定位：

```asm
movq (%rbx), %r12
leaq 8(%rbx), %r13
leaq 8(%r13,%r12,8), %r14
addq $8, %r15
addq $16, %r15
cmpq $6, %rax
testq %rax, %rax
```

分别对应：

```text
argc
argv base
envp base
envp 扫描步长
auxv 扫描步长
AT_PAGESZ
AT_NULL
```

---

## 6. ELF 与符号检查

```bash
make symbols
```

确认：

- ELF class 为 ELF64；
- Machine 为 x86-64；
- ELF entry 指向 `_start`；
- `_start` 符号存在。

本实验直接使用 `as + ld`，不会经过 C 运行时启动文件，因此入口观察更直接。

---

## 7. GDB

如果环境安装了 GDB：

```bash
make gdb
```

脚本会在 `_start` 第一条指令之前停住，并显示：

```text
initial RSP
argc
初始栈若干 8 字节槽
argv[0..2] 指向的字符串
envp 起始位置
```

GDB 自身创建被调试进程时可能带入不同环境，因此不要要求 `make gdb` 的 envp 数量与 `make run` 完全一致。应验证的是布局关系。

---

## 8. 本次编写时的实际验证

已实际执行：

```text
as --64 -g
ld
make run
nm
readelf -h
objdump -drS
```

结果：

```text
exit status=63
ELF64 x86-64
_start 为入口符号
反汇编中的 argv/envp/auxv 地址计算与源码一致
```

当前执行环境未安装 GDB，因此 `gdb.cmd` 已检查命令和地址计算逻辑，但未在本次编写环境中实际执行。

---

## 9. 验收标准

完成实验后，应能够从一个未知的初始 `RSP=S` 推导：

```text
argc       = *(uint64_t *)S
argv       = S + 8
envp       = argv + (argc + 1) * 8
auxv       = 第一个 envp NULL 之后 8 字节
next_auxv  = current_auxv + 16
结束条件    = a_type == AT_NULL
```

并能解释为什么 `argv[]/envp[]` 中是指针，而不是字符串本体。

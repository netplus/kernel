# A09 实验：局部变量、寄存器与 spill/reload

本实验验证两个问题：

1. C 源码中的局部变量是否一定对应栈槽；
2. 当一个值必须跨越会破坏 caller-saved 寄存器的函数调用存活时，编译器如何在 callee-saved 寄存器与栈槽之间分配它。

## 1. 构建与运行

```bash
make clean
make
make check
```

本仓库维护时使用的验证环境：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
GNU objdump 2.44
```

实际运行结果：

```text
local_expr(7,11)=170
local_expr(7,11)=170
local_expr(7,11)=170
spill_wrapper=178
```

四个程序均以退出码 0 结束。

## 2. 对比 `local_expr`

分别查看：

```bash
objdump -dr locals-o0
objdump -dr locals-og
objdump -dr locals-o2
```

在本次 GCC 14.2.0 验证中，`-O0` 版本建立 `%rbp` 栈帧，并把参数和 `x/y/z` 等中间值写入 `%rbp` 负偏移位置，例如：

```asm
mov    %rdi,-0x28(%rbp)
mov    %rsi,-0x30(%rbp)
...
mov    %rax,-0x8(%rbp)
mov    %rax,-0x10(%rbp)
mov    %rax,-0x18(%rbp)
```

而 `-Og` 与 `-O2` 版本都没有为这些源码局部变量建立对应栈槽；计算直接在寄存器中完成后返回。

因此不能把“源码里有局部变量”等同于“机器栈上必然存在一个固定槽”。

## 3. 观察真正的保存与 reload

`spill_wrapper()` 先调用 `opaque()`，然后仍然需要原来的 12 个参数去调用 `consume12()`。这使一批值必须跨过第一次 `call` 保持有效。

为了让实验中的 frame base 稳定可读，`spill.c` 单独使用：

```text
-O2 -fno-omit-frame-pointer
```

查看：

```bash
objdump -dr spill-o2
objdump -dr -Mintel spill-o2
```

本次反汇编中，`RBX/R12-R15` 用来保存部分活跃值；同时 `%r8/%r9` 中的两个参数被保存到当前栈帧：

```asm
mov    %r8,-0x40(%rbp)
mov    %r9,-0x38(%rbp)
call   opaque
...
mov    -0x38(%rbp),%r9
...
mov    -0x40(%rbp),%r8
```

这里前两条 store 是为了让值跨 `opaque()` 存活，后两条 load 是在准备下一次调用时把值重新装回 ABI 指定的参数寄存器。它们是本实验中可直接观察的 spill/reload 行为。

注意：具体选择哪一个值放在哪个寄存器或栈槽，是当前编译器版本、优化级别、寄存器压力和指令选择共同作用的结果，不属于 SysV AMD64 ABI 固定规定。

## 4. 还要区分 outgoing stack arguments

`consume12()` 有 12 个 INTEGER 参数。前六个走寄存器，后六个按 ABI 走栈。因此 `spill_wrapper()` 在第二次 `call` 前还会看到若干 `push`。

这些为被调用函数准备的栈参数属于 outgoing arguments，不能和编译器为了保存活跃值而使用的 spill slot 混为一谈。

## 5. GDB

当前验证环境没有安装 GDB，因此没有执行单步实验。可以在具备 GDB 的环境中分别在 `local_expr`、`spill_wrapper` 和两次 `call` 前后观察 `$rsp`、`$rbp`、`$r8`、`$r9` 以及对应栈内存。

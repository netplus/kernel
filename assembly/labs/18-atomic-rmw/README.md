# A18 实验：观察 `xchg`、`cmpxchg`、`xadd` 与多线程原子 RMW

本实验对应 [`../../docs/18-atomic-rmw-xchg-cmpxchg-xadd.md`](../../docs/18-atomic-rmw-xchg-cmpxchg-xadd.md)。目标不是用用户态代码复刻 Linux `atomic_t`，而是直接验证第一部分依赖的 x86-64 指令事实：memory `xchg` 的交换结果、`cmpxchg` 成功/失败时 RAX 与 ZF、locked `xadd` 的 old-value 返回，以及普通 read-modify-write 与 locked RMW 在多线程竞争下的差别。

## 1. 构建

```bash
make clean
make
```

要求 x86-64 Linux、GCC/Clang、GNU make、pthread 和 binutils。源码刻意把三个指令 wrapper 标成 `noinline`，方便在反汇编中定位。

## 2. 先检查实际机器指令

```bash
make check-disasm
objdump -dr -Mintel atomic_rmw
objdump -dr atomic_rmw
```

重点确认：

```text
do_xchg      memory xchg，没有显式 lock 前缀
do_cmpxchg   lock cmpxchg，并有 setz 读取 ZF
do_xadd      lock xadd
worker       普通 counter 更新与 locked xadd 对照
```

AT&T 与 Intel 语法的操作数顺序不同；判断读写对象时不要只看文本顺序。

## 3. 单指令语义验证

运行：

```bash
./atomic_rmw
```

前四行应满足以下不变量：

```text
xchg:
    初始 memory=10, register input=20
    old=10, new memory=20

cmpxchg success:
    expected=10, memory=10, desired=20
    ZF=1, RAX=10, memory=20

cmpxchg failure:
    expected=10, memory=15, desired=20
    ZF=0, RAX=15, memory=15

xadd:
    memory=10, increment=3
    old=10, new memory=13
```

这里的 RAX 是 `cmpxchg` 的架构隐含 accumulator；它不是因为 System V AMD64 ABI 把 expected 参数规定在 RAX。wrapper 在执行指令前由编译器完成参数搬运。

## 4. 多线程 lost-update 对照

程序默认创建 4 个线程，每线程执行 1,000,000 次更新。每轮先对 `plain_counter` 做普通 load/increment/store，再用 `lock xadd` 更新 `atomic_counter`。

```bash
./atomic_rmw
./atomic_rmw 5000000
```

最终：

```text
expected = threads * iterations
atomic_counter == expected
```

必须成立，否则实验返回非零。

`plain_counter < expected` 在有足够竞争时通常可以观察到，用来展示 lost update；但它**不是每次运行都必须失败的测试条件**。线程调度可能使某次运行恰好没有表现出明显丢失，因此实验只打印普通计数器结果，不把 `plain_counter != expected` 写成 pass/fail 条件。

`volatile` 只用于让普通对照保持可观察的内存 load/store 形状；它不提供跨 CPU 原子 RMW，也不是 Linux `READ_ONCE/WRITE_ONCE` 或内存屏障的替代品。

## 5. 可以用 GDB 单步观察什么

```bash
gdb ./atomic_rmw
(gdb) disassemble /r do_cmpxchg
(gdb) break do_cmpxchg
(gdb) run
```

在 `cmpxchg` 前后检查：

```text
RAX
目标内存
RFLAGS.ZF（bit 6）
```

成功 case 应看到 ZF=1；失败 case 应看到 ZF=0 且 RAX 被实际内存值覆盖。单步时以当前反汇编地址为准，不硬编码偏移。

## 6. 本实验不能证明什么

本实验可以验证具体 RMW 指令及竞争更新结果，但不能单独证明完整 memory-ordering 规则。`lock` 指令与 x86 ordering、Linux `smp_mb()`/acquire/release API 的关系属于 A18 后续单元。

同样，源码中的 `"memory"`、`"cc"`、`+m`、`+a` 是 GCC extended-asm contract；它们与 CPU 的原子性不是同一层机制。完整约束语义也留给后续单元。

## 7. 当前验证状态

仓库维护环境通过 GitHub connector 写入文件，当前运行没有可直接执行仓库工作树的 shell，因此本次未声称已经运行 `make`/`objdump`/pthread 程序。代码和命令已经按 x86-64/GCC extended asm 规则检查；下一次具备可执行 checkout 的环境时，应补实际构建、运行和双语法反汇编结果。

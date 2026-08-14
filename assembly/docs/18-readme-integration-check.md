# A18 README 接入核验

本文件记录 A18 正式接入领域大纲前的最后一次一致性检查。它不替代 `assembly/README.md`，只固定本章已经完成的材料、接入顺序和实验状态，避免在 A18 尚未进入唯一课程大纲时继续推进 A19。

## 1. 已完成材料

A18 已形成三个独立课程单元：

1. 原子 RMW：`xchg`、`cmpxchg`、`xadd`、`LOCK_PREFIX` 与 Linux 5.10 `arch_atomic_*`；
2. memory ordering：x86 TSO、Linux 5.10 barrier API、acquire/release 与 `CONFIG_SMP`；
3. GCC extended asm：operand、constraint、matching、early-clobber、`cc`、`memory` 与 `volatile`。

对应入口必须使用以下文件名：

```text
docs/18-atomic-rmw-xchg-cmpxchg-xadd.md
labs/18-atomic-rmw/
source-paths/18-atomic-rmw-x86-linux-5.10.md

docs/18-memory-ordering-and-barriers.md
labs/18-memory-ordering-barriers/
source-paths/18-memory-barriers-x86-linux-5.10.md

docs/18-gcc-extended-asm-constraints.md
labs/18-gcc-extended-asm-constraints/
source-paths/18-gcc-extended-asm-constraints-linux-5.10.md

docs/18-a18-completion-review.md
```

三个实验目录都已经包含 `expected-analysis.md`，因此 README 不应再把 expected analysis 误写成待补内容。

## 2. README 必须表达的机制边界

A18 的收章说明必须明确：

```text
CPU atomic RMW
!= CPU / Linux memory ordering
!= GCC compiler contract
```

第一层回答一次共享内存 read-modify-write 如何不可分割；第二层回答不同 load/store 的可见顺序；第三层回答编译器如何理解 inline asm 的输入、输出、位置约束和副作用。

因此不能写成：

- `"memory"` clobber 提供 CPU full barrier；
- `asm volatile` 自动提供 atomicity；
- `LOCK` 与 GCC constraint 属于同一层机制；
- `smp_mb()` 必然编译成 `mfence`；
- memory `xchg` 的锁定语义来自显式 `lock` 前缀。

## 3. 实验状态

A18 三组实验的源码、构建方法、观察点和 expected analysis 已完成，但当前维护环境没有可执行的 Linux 5.10 checkout。因此 README 收章时必须继续明确以下内容尚未作为本轮实测结论：

- Linux 5.10 Kbuild 后 atomic/barrier 宏的最终反汇编；
- 用户态 atomic RMW 实验的 GCC/binutils 构建、运行与 `objdump`；
- Store Buffering / Message Passing 的本机运行观察；
- `-O2` extended-asm 对照的实际生成代码。

这些是实验执行环境限制，不是机制内容缺口，也不能把 `expected-analysis.md` 中的预期输出改写成已运行结果。

## 4. 收章动作

下一次修改 `assembly/README.md` 时，A18 区域应按以下顺序接入：

```text
第一部分：atomic RMW
  教程
  实验
  Linux 5.10 source-path

第二部分：memory ordering / barriers
  教程
  实验
  Linux 5.10 source-path

第三部分：GCC extended asm constraints
  教程
  实验
  Linux 5.10/GCC source-path

整章一致性复核
A18 已完成 + 实验执行环境边界
```

只有完成上述 README 接入后，领域大纲层面的 A18 才算正式完成。A19 虽然仓库中已经存在第一轮长模式切换材料，但课程推进顺序仍应先收口 A18，再继续 A19。
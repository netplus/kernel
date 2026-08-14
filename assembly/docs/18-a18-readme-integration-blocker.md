# A18 README 接入阻塞记录

A18 三个课程单元的正文、事实核验、实验与 `expected-analysis.md` 已经完成，整章一致性复核也已确认原大纲要求全部覆盖。当前唯一未完成的收章动作，是把这些入口写入 `assembly/README.md` 并正式标记 A18 完成。

## 已核验的接入内容

README 的 A18 节需要接入以下材料：

第一部分：原子 RMW、`xchg`、`cmpxchg` 与 `xadd`

- 教程：[`18-atomic-rmw-xchg-cmpxchg-xadd.md`](18-atomic-rmw-xchg-cmpxchg-xadd.md)
- 实验：[`../labs/18-atomic-rmw/`](../labs/18-atomic-rmw/)
- Linux 5.10 源码事实核验：[`../source-paths/18-atomic-rmw-x86-linux-5.10.md`](../source-paths/18-atomic-rmw-x86-linux-5.10.md)

第二部分：x86 memory ordering 与 Linux 5.10 barrier

- 教程：[`18-memory-ordering-and-barriers.md`](18-memory-ordering-and-barriers.md)
- 实验：[`../labs/18-memory-ordering-barriers/`](../labs/18-memory-ordering-barriers/)
- Linux 5.10 源码事实核验：[`../source-paths/18-memory-barriers-x86-linux-5.10.md`](../source-paths/18-memory-barriers-x86-linux-5.10.md)

第三部分：GCC extended asm constraints

- 教程：[`18-gcc-extended-asm-constraints.md`](18-gcc-extended-asm-constraints.md)
- 实验：[`../labs/18-gcc-extended-asm-constraints/`](../labs/18-gcc-extended-asm-constraints/)
- Linux 5.10/GCC 事实核验：[`../source-paths/18-gcc-extended-asm-constraints-linux-5.10.md`](../source-paths/18-gcc-extended-asm-constraints-linux-5.10.md)

整章一致性复核：[`18-a18-completion-review.md`](18-a18-completion-review.md)

## README 收章时必须保留的边界

A18 必须明确区分三个层次：

```text
CPU atomic RMW
!= CPU/Linux memory ordering
!= GCC compiler contract
```

还必须保留实验状态：当前维护环境没有可执行 Linux 5.10 checkout，因此 GCC/Kbuild/objdump/litmus 的 expected analysis 不能写成已运行结果。

## 本次环境 blocker

本次运行能够通过 GitHub connector 读取和创建仓库文件，但现有文件更新接口要求提交 `assembly/README.md` 的完整替换内容，不支持局部 patch。领域 README 已经超过单次安全重写所适合的规模；当前执行环境又没有可联网的 git checkout（容器访问 github.com DNS 失败），因此无法在不冒险截断或重写既有 A00-A17 大纲的前提下完成这次局部接入。

这是当前执行环境的写入能力 blocker，而不是课程内容 blocker。后续一旦获得可 patch 的仓库工作树或支持局部 edit 的 GitHub 写接口，应直接修改 A18 节，不再新增课程机制内容；完成链接复核后标记 A18 完成，再继续 A19。
# A18 第二部分实验预期分析：x86 memory ordering 与 Linux 5.10 barrier

本文给出 [`README.md`](README.md) 的验收基线。它用于区分“Linux 5.10 源码规定了什么”“当前内核构建实际生成了什么”“某次 litmus 运行观察到什么”以及“x86 架构允许什么”。没有实际构建或运行证据时，不应把下面的预期写成实测结果。

## 1. 验收前提

所有内核反汇编结论都必须同时记录：

```text
Linux source: v5.10
architecture: x86-64
CONFIG_SMP: y / n
compiler/binutils version
```

公共 `smp_*` API 的最终实现受 `CONFIG_SMP` 影响，因此没有配置上下文的反汇编不能作为完整验收证据。

## 2. 三层证据必须分开

本实验涉及三个不同层次：

1. compiler ordering：`barrier()`、`"memory"` clobber、`READ_ONCE()`/`WRITE_ONCE()` 对编译器可见；
2. CPU ordering：`mfence/lfence/sfence`、locked RMW、memory `xchg` 以及 x86 TSO；
3. Linux API：`mb()`、`smp_mb()`、release/acquire 等跨架构接口表达的 ordering 契约。

验收时不能用“有 `memory` clobber”替代 CPU barrier，也不能用“反汇编没有 fence”推导 Linux API 没有 ordering 语义。

## 3. `CONFIG_SMP=y` 的反汇编验收矩阵

在 Linux 5.10 x86-64 常规 SMP 构建中，预期关系如下。具体寄存器分配、地址和编码由实际工具链决定。

| probe | 预期 CPU 指令层特征 | 不能据此推出 |
| --- | --- | --- |
| `probe_mb` | `mfence` | `smp_mb()` 也必须使用 `mfence` |
| `probe_rmb` | `lfence` | `smp_rmb()` 也必须使用 `lfence` |
| `probe_wmb` | `sfence` | `smp_wmb()` 也必须使用 `sfence` |
| `probe_smp_mb` | full-ordering primitive；v5.10 x86 主线应看到 locked RMW | 所有配置都固定为同一字节序列 |
| `probe_smp_rmb` | 不应机械出现额外 `lfence` | API 没有 read ordering 语义 |
| `probe_smp_wmb` | 不应机械出现额外 `sfence` | API 没有 write ordering 语义 |
| `probe_release` | 通常是普通 store，无额外 `mfence` | release 只是 compiler barrier，或其他架构也如此 |
| `probe_acquire` | 通常是普通 load，无额外 `mfence` | acquire 只是 compiler barrier，或其他架构也如此 |
| `probe_store_mb` | memory `xchg` | full ordering 必须写成 `store; mfence` |

`__smp_mb()` 的具体 locked instruction 应以当前 v5.10 头文件和实际 object 为准；验收重点是它确实提供 CPU full ordering，而不是背诵某个地址或机器码。

## 4. `CONFIG_SMP=n` 的边界

UP 构建中，公共 `smp_*` 接口不再需要解决另一 CPU 同时访问造成的硬件重排问题，可以退化到单 CPU/compiler-ordering fallback。

因此 SMP 与 UP 对照的正确结论是：

```text
CONFIG_SMP 改变 Linux 公共 smp_* API 的映射需求。
```

不能要求 UP 的 `smp_mb()` 必须保留 SMP 构建中的 locked RMW。反过来，也不能由 UP 反汇编推出 SMP 下不需要硬件 ordering primitive。

## 5. acquire/release 的验收重点

对 x86-64，release-store 与 acquire-load 的关键观察通常是“没有额外 fence”。这个负面观察只有结合两类证据才有意义：

```text
Linux 5.10 x86 barrier.h 的 __smp_store_release/__smp_load_acquire 定义
+
实际 probe 反汇编中的普通 store/load
```

原因不是 release/acquire 没有语义，而是 x86 TSO 已提供 CPU 层所需的普通 load/store 顺序，Linux 仍需要编译器层约束访问不能越过 API 边界。

## 6. `smp_store_mb()` 的验收重点

预期 `probe_store_mb()` 使用 memory `xchg`。A18 第一部分已经建立 memory `xchg` 的隐含锁定语义，因此这里应解释为：Linux 用一次交换同时完成 store 和 full ordering。

正确模型是：

```text
memory xchg
= atomic exchange
+ x86 locked ordering semantics
```

而不是把它翻译成概念上的 `store; mfence` 后再宣称机器码必须如此。

## 7. Store Buffering litmus 的允许结果

测试模型：

```text
initial: x = 0, y = 0

CPU0:                       CPU1:
store x = 1                 store y = 1
load  r0 = y                load  r1 = x
```

使用 C11 relaxed atomics 表达测试变量时，关注 `r0=0, r1=0`。在 x86 TSO 下，Store→Load 是允许出现可见重排效果的方向，store buffer 使两个 CPU 都先读到对方旧值成为允许结果。

因此：

- 观察到 `0/0`：与该模型相容，但一次观察不是 Linux barrier 实现的完整证明；
- 没观察到 `0/0`：不能证明架构禁止它；
- 出现频率：不是架构契约，不能作为 barrier 强弱的量化指标。

运行报告应记录 CPU、是否虚拟化、线程 affinity、迭代次数和各结果计数。

## 8. Message Passing 的验收边界

模型：

```text
producer:
data = 42
release-store ready = 1

consumer:
if acquire-load ready == 1
        read data
```

本实验用它说明 release/acquire API 表达同步关系。在 x86 上即使最终反汇编只是普通 store/load，也不能把“没有 fence”解释成“没有 ordering”。

若实现用户态测试，应使用语言定义良好的 atomic acquire/release，而不是普通共享变量或 `volatile` 制造 data race。运行没有观察到错误结果，只能作为实现观察；API/架构保证仍应由语言模型、Linux API 定义和 x86 ordering 共同解释。

## 9. AT&T / Intel 反汇编检查

两种语法必须指向同一机器指令语义。检查时至少确认：

- `mfence/lfence/sfence` 不涉及操作数方向差异；
- locked RMW 的 memory operand 在两种语法中指向同一地址；
- `xchg` 的一端确实是 memory operand；
- 不因为 Intel/AT&T operand 顺序不同而误判 load/store 方向。

如果编译器内联或优化导致 probe 边界消失，应先用 `noinline`、symbol/relocation 信息和完整 object 反汇编确认，而不是从相邻指令猜测 API 的落点。

## 10. 最终验收清单

A18 第二部分实验达到独立验收标准时，应能回答：

```text
当前构建是否 CONFIG_SMP=y？
mb/rmb/wmb 各自生成了什么？
smp_mb 与 smp_rmb/smp_wmb 为什么不同？
release/acquire 为什么可以没有额外 fence？
smp_store_mb 为什么可以使用 xchg？
Store Buffering 的 0/0 是允许结果还是必须结果？
为什么一次没观察到 0/0 不能证明禁止？
哪些结论来自源码，哪些来自反汇编，哪些只是本机运行观察？
```

当前维护环境没有可执行的 Linux 5.10 checkout，因此上述 Kbuild、`objdump` 和 litmus 结果仍待实际环境补充；这不改变源码级验收基线，但不能将预期矩阵标记为本机实测。
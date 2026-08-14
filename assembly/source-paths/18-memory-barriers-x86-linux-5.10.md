# A18 第二部分源码事实核验：x86-64 memory ordering 与 Linux 5.10 屏障接口

本文只记录 Linux kernel v5.10 / x86-64 的源码事实，为 A18 后续“内存顺序与屏障”教程提供版本基线。原子 RMW 指令本身已在 `18-atomic-rmw-x86-linux-5.10.md` 核验；这里重点回答：Linux 的 `mb/rmb/wmb`、`smp_mb/rmb/wmb`、acquire/release 和 atomic 前后屏障，在 x86-64 上实际落到什么。

## 1. 需要区分的三个层次

后续正文必须始终区分：

1. **compiler ordering**：`barrier()`、`asm volatile(... ::: "memory")` 等约束编译器重排；
2. **CPU memory ordering**：x86 的内存模型与 `mfence/lfence/sfence`、locked RMW 等硬件语义；
3. **Linux memory-ordering API**：`mb()`、`smp_mb()`、`smp_store_release()` 等跨架构接口。

不能由 `"memory"` clobber 单独推出 CPU full barrier，也不能因为 x86 TSO 较强就删除 Linux API 所表达的跨 CPU happens-before 关系。

## 2. Linux 5.10 需要核对的源码

主路径：

```text
arch/x86/include/asm/barrier.h
include/asm-generic/barrier.h
arch/x86/include/asm/atomic.h
arch/x86/include/asm/cmpxchg.h
```

`arch/x86/include/asm/barrier.h` 提供 x86 的 `__smp_*` 实现；`include/asm-generic/barrier.h` 根据 `CONFIG_SMP` 把公共 `smp_*` API 映射到架构实现或 UP fallback。

## 3. `mb/rmb/wmb` 与 `smp_*` 不是同一组接口

在 x86-64 上，设备/通用 barrier 与 SMP barrier 必须分开理解。x86 的架构 barrier 文件中，SMP 主线定义：

```text
__smp_mb()   -> locked add on stack memory + "memory","cc"
__smp_rmb()  -> dma_rmb()
__smp_wmb()  -> compiler barrier path
```

而工具侧同源 x86-64 barrier 定义清楚展示了：

```text
mb()  -> mfence
rmb() -> lfence
wmb() -> sfence
```

因此不能写成“Linux x86 的 `smp_mb/rmb/wmb` 就分别是 `mfence/lfence/sfence`”。尤其在普通 x86 TSO 主线上，`smp_rmb()`/`smp_wmb()` 可以只需要 compiler-ordering 层，而 full `smp_mb()` 仍需要真正的 CPU ordering primitive。

实际内核构建应以当前 v5.10 `arch/x86/include/asm/barrier.h` 和最终反汇编为准；工具目录中的定义只能作为指令层对照，不能替代内核头文件。

## 4. `__smp_mb()` 为什么使用 locked RMW

v5.10 x86-64 的 `__smp_mb()` 使用对当前栈附近内存执行的 locked `addl $0,...(%rsp)`，并声明 `memory` 与 `cc` clobber。这里的加零不是为了改变数据，而是借助 locked RMW 的 ordering/serialization 语义建立 full SMP barrier；`memory` clobber 同时约束编译器。

因此分析它时必须同时看到两层：

```text
lock addl ...    CPU ordering primitive
"memory"         compiler ordering contract
```

二者不是同一个机制。

## 5. acquire/release 在普通 x86 TSO 主线上

v5.10 x86 的架构实现定义：

```text
__smp_store_release(p, v)
    compiletime_assert_atomic_type(*p)
    barrier()
    WRITE_ONCE(*p, v)

__smp_load_acquire(p)
    READ_ONCE(*p)
    compiletime_assert_atomic_type(*p)
    barrier()
```

也就是说，在普通 x86 TSO 主线上，release store / acquire load 不要求额外 `mfence`：CPU ordering 由 x86 内存模型已经提供，源码中的 `barrier()` 负责阻止编译器跨越该点重排，而 `READ_ONCE/WRITE_ONCE` 固定相应访问。

这不能推广成“acquire/release 永远只是 compiler barrier”；这是 x86 架构实现结论，其他架构可能需要专用指令或 barrier。

## 6. `CONFIG_SMP` 的公共 API 边界

`include/asm-generic/barrier.h` 在 `CONFIG_SMP` 下把公共接口映射到 `__smp_*` 架构实现；非 SMP 构建则为 `smp_*` 提供 compiler-ordering/单 CPU fallback。

因此教材和实验都必须记录：

```text
CONFIG_SMP=y ?
目标架构是否 x86-64 ?
观察的是 Linux API、架构宏，还是最终机器指令？
```

不能把 SMP 构建下的 locked full barrier 描述成所有配置下都固定存在的指令。

## 7. atomic 前后 barrier

v5.10 x86 `barrier.h` 明确把：

```text
__smp_mb__before_atomic()
__smp_mb__after_atomic()
```

定义为空操作，并注明 x86 atomic operations 已经具有所需的 serializing/order 属性。公共 `smp_mb__before_atomic()` / `smp_mb__after_atomic()` 在 SMP 下使用这些架构实现。

这里也要避免过度推广：这是 Linux 5.10 x86 对相应 atomic API ordering 契约的实现选择，不等于“任何带 atomic 字样的 C/C++ 操作都天然是 full barrier”。

## 8. `smp_store_mb()` 与 `xchg`

x86 架构实现把 `__smp_store_mb(var, value)` 建立在 `xchg(&var, value)` 上。结合 A18 第一部分已经核验的 memory `xchg` 隐含锁定语义，可以看到 Linux 利用同一次交换同时完成 store 与所需 full ordering，而不是机械地生成 `store; mfence` 两条指令。

这也是为什么学习 memory ordering 不能只背 fence 助记符：locked RMW 同样可以承担 barrier 语义。

## 9. 与 A18 第一部分的衔接

第一部分已经确认：

```text
xchg memory      隐含锁定语义
LOCK cmpxchg     原子条件 RMW
LOCK xadd        原子 fetch-add
```

第二部分需要增加的不是“这些指令是否原子”，而是：

```text
这些操作对前后其他 load/store 提供什么 ordering？
Linux API 要表达什么 happens-before 关系？
在 x86 TSO 下哪些 API 可以退化为 compiler barrier？
哪些仍必须生成硬件 ordering primitive？
```

## 10. 后续教程必须保持的结论边界

后续正文至少应明确：

- `barrier()` 是 compiler barrier，不是 CPU full memory barrier；
- `mb/rmb/wmb` 与 `smp_mb/rmb/wmb` 不能按名字机械等同；
- x86-64 普通 TSO 主线上，SMP read/write barriers 可以比 full `smp_mb()` 更轻；
- `smp_store_release()` / `smp_load_acquire()` 在 x86 上通常不需要额外 fence 指令，但这依赖 x86 ordering；
- `CONFIG_SMP` 决定公共 `smp_*` API 是否需要跨 CPU hardware ordering；
- locked RMW 与 memory `xchg` 除原子性外还能承担 ordering 角色；
- GCC `"memory"` clobber、CPU fence/locked instruction、Linux memory-barrier API 属于三个不同层次。

## 11. 实验建议

正式实验应至少比较：

1. 一个独立 translation unit 中 `mb()`、`rmb()`、`wmb()` 的反汇编；
2. `smp_mb()` 与 `smp_rmb()/smp_wmb()` 在 `CONFIG_SMP=y` x86-64 内核中的最终反汇编；
3. `smp_store_release()` / `smp_load_acquire()` 是否只留下普通 load/store；
4. `smp_store_mb()` 是否落到 memory `xchg`；
5. 同一源码在 UP/SMP 配置下的差异。

若没有可构建的 Linux 5.10 checkout，只能记录源码级核验，不能把预期反汇编写成实际构建结果。

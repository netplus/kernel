# A18 第二部分：x86 内存顺序与 Linux 5.10 屏障

A18 第一部分解决的是“多个 CPU 同时修改同一个内存位置时，一次 read-modify-write 怎样保持不可分割”。这还没有回答另一个问题：**CPU0 已经执行了若干次 load/store，CPU1 按什么顺序能够观察到这些访问？**

原子性与顺序性是两个不同问题。`lock xadd` 可以同时具有原子 RMW 和很强的 ordering 语义，但不能因此把“atomic”“barrier”“compiler barrier”当作同义词。本节先建立 x86-64 的基本 ordering 模型，再映射到 Linux 5.10 的 barrier API。

Linux 5.10 具体实现已经按版本核验，见 [`../source-paths/18-memory-barriers-x86-linux-5.10.md`](../source-paths/18-memory-barriers-x86-linux-5.10.md)。

## 1. 为什么程序顺序不等于其他 CPU 的观察顺序

考虑两个共享变量：

```c
int data;
int ready;
```

CPU0 想发布数据：

```text
CPU0:
data = 42;
ready = 1;
```

CPU1 想消费数据：

```text
CPU1:
if (ready == 1)
        use(data);
```

源码中的先后顺序只是起点。要证明“CPU1 看到 `ready == 1` 后一定能看到对应的 `data == 42`”，至少要同时回答：

```text
编译器是否可以重新安排访问？
CPU/缓存一致性系统允许怎样的观察顺序？
两个 CPU 之间使用了什么同步协议？
```

因此 Linux 不直接依赖“C 代码看起来在前面”，而使用 `READ_ONCE()`、`WRITE_ONCE()`、acquire/release 和 barrier API 表达需要保持的顺序。

## 2. 三个层次必须分开

分析 barrier 时始终先判断当前说的是哪一层。

### 2.1 compiler ordering

例如：

```c
barrier();
```

以及 GCC extended asm 中的：

```text
"memory" clobber
```

它们首先约束的是**编译器**：不要把相关内存访问跨越该点自由移动。

它们本身并不要求 CPU 执行 `mfence`，也不能单独建立跨 CPU 的硬件 full barrier。

### 2.2 CPU memory ordering

这是 x86 架构和微架构执行内存访问时必须满足的规则。这里才涉及：

```text
x86 的普通 load/store ordering
store buffer
mfence / lfence / sfence
locked RMW
memory xchg
```

### 2.3 Linux memory-ordering API

Linux 提供跨架构接口：

```text
mb()/rmb()/wmb()
smp_mb()/smp_rmb()/smp_wmb()
smp_store_release()/smp_load_acquire()
smp_store_mb()
```

API 表达的是内核算法需要的 ordering 契约；具体机器指令由目标架构和配置实现。同一个 Linux API 在 x86 和弱内存序架构上完全可能生成不同指令。

## 3. x86 TSO 的基础工作模型

学习 Linux x86 barrier 时，可以先使用一个简化但有用的模型：x86 对普通 cacheable memory 提供较强的 Total Store Order（TSO）语义，但仍存在必须认真处理的 Store→Load ordering。

一个直观来源是 store buffer。CPU 执行 store 后，可以先把写入放进本 CPU 的 store buffer；后续 load 在某些条件下可以继续执行，而其他 CPU 尚未观察到该 store 已经全局可见。

因此不要把 x86 TSO 理解成：

> 所有内存访问都严格按源码顺序在所有 CPU 上同时生效。

更合适的课程模型是：

```text
普通 x86 load/store 已提供较强顺序保证
但 full ordering 仍可能需要真正的硬件 primitive
Linux 利用这些架构保证把部分 barrier 实现得很轻
```

这里讨论的是普通 WB/cacheable shared memory 主线。MMIO、non-temporal store、特殊 cache type 等具有额外规则，不在本基础单元展开。

## 4. 原子性不自动等于完整的 ordering 讨论

第一部分已经看到：

```text
memory xchg
lock cmpxchg
lock xadd
```

可以完成原子 RMW。

但读代码时仍应分别问：

1. 目标位置的更新是否原子？
2. 这条操作与前后其他内存访问之间提供什么顺序？
3. Linux API 要求的 ordering 是否已经由这条指令满足？

Linux 5.10 x86 会利用 locked RMW 的 ordering 属性实现 full SMP barrier，也会让 atomic 前后的某些 barrier 宏为空。这是架构实现选择，不应推广成“任何 atomic C 操作都是 full barrier”。

## 5. `mb/rmb/wmb` 与 `smp_*` 是两组接口

名称相似不代表实现相同。

### 5.1 `mb()`、`rmb()`、`wmb()`

x86 的通用/设备 barrier 主线使用硬件 fence：

```text
mb()   -> mfence
rmb()  -> lfence
wmb()  -> sfence
```

这些接口不能简单因为“机器是单 CPU”就全部消失，因为它们的使用场景不只是在 CPU 间建立 SMP 顺序。

### 5.2 `smp_mb()`、`smp_rmb()`、`smp_wmb()`

`smp_*` 明确面向 CPU 间同步。Linux 5.10 x86 的 SMP 主线更接近：

```text
smp_mb()   -> 真正的 full CPU ordering primitive
smp_rmb()  -> 利用 x86 read ordering，通常无需额外 fence
smp_wmb()  -> 利用 x86 write ordering，通常无需额外 fence
```

其中 v5.10 x86 的 `__smp_mb()` 使用 locked RMW，而不是机械使用 `mfence`。

因此下面这种记忆法是错误的：

```text
smp_mb  = mfence
smp_rmb = lfence
smp_wmb = sfence
```

正确方法是从 Linux API 的语义要求出发，再看当前架构怎样满足它。

## 6. Linux 5.10 x86 的 `smp_mb()`

源码主线使用对栈内存执行的 locked add：

```text
lock addl $0, ...(%rsp)
```

“加零”并不是为了修改业务数据。真正需要的是 locked RMW 提供的 ordering 属性。

这一实现同时包含两个层次：

```text
locked add       CPU ordering
"memory" clobber compiler ordering
```

如果只看到 `"memory"` 就说“这是 full CPU barrier”，遗漏了关键硬件机制；如果只看到 `lock add` 而忽略 compiler contract，也没有完整描述 C/asm 交界。

## 7. 为什么 x86 的 `smp_rmb()` / `smp_wmb()` 可以更轻

Linux API 需要阻止的是特定方向的重排。x86 普通 load/load 和 store/store 顺序已经足够强，因此 SMP read/write barrier 在常规主线上不需要像弱内存序架构那样额外发出重型 fence。

这并不表示：

```text
smp_rmb() 没有语义
smp_wmb() 没有语义
```

它们仍然是内核并发算法中的 ordering 标记，并且必须同时阻止编译器破坏所需顺序。只是 x86 CPU 层已经天然满足相应部分，所以机器指令可以很轻甚至不出现额外 fence。

这也是阅读跨架构 Linux 代码时应保留 `smp_*` API、而不是因为当前在 x86 上“反汇编看不到 fence”就删除它的原因。

## 8. acquire/release：发布与获取

前面的 `data/ready` 例子更适合使用 release/acquire，而不是无条件 full barrier。

发布方：

```c
WRITE_ONCE(data, 42);
smp_store_release(&ready, 1);
```

消费方：

```c
if (smp_load_acquire(&ready) == 1)
        value = READ_ONCE(data);
```

核心语义是：

```text
release:
    release 之前的相关访问不能越过发布点跑到后面

acquire:
    acquire 之后的相关访问不能越过获取点跑到前面
```

当 acquire load 读到了与 release store 建立同步关系的值时，就可以建立算法需要的跨 CPU happens-before 关系。

## 9. 为什么 x86 acquire/release 常看不到 fence

Linux 5.10 x86 的实现主线是：

```text
smp_store_release
    compiler barrier
    WRITE_ONCE store

smp_load_acquire
    READ_ONCE load
    compiler barrier
```

没有额外 `mfence` 并不表示 acquire/release “只对编译器有效”。更准确的理解是：

```text
Linux API 定义所需 ordering
编译器 barrier 防止 compiler reorder
x86 TSO 已经提供 CPU 层所需的 load/store ordering
```

换到弱内存序架构，完全可能需要专用 acquire/release 指令或硬件 barrier。

## 10. `smp_store_mb()` 为什么可以使用 `xchg`

Linux 5.10 x86 的 `__smp_store_mb(var, value)` 使用 `xchg`。

第一部分已经确认 memory `xchg` 具有隐含锁定语义。因此它可以把：

```text
写入新值
+
full ordering
```

合并到同一次交换操作中。

这说明 barrier 不能只按 `mfence/lfence/sfence` 三个助记符来学习。locked RMW 和 memory `xchg` 也可以承担 ordering primitive 的角色。

## 11. atomic 前后 barrier 为什么在 x86 可以为空

Linux 提供：

```text
smp_mb__before_atomic()
smp_mb__after_atomic()
```

用于某些只需要在 atomic operation 一侧补 ordering 的算法。

Linux 5.10 x86 的：

```text
__smp_mb__before_atomic()
__smp_mb__after_atomic()
```

为空，因为该架构 atomic 操作已经提供这里所要求的 ordering。

这个结论有严格范围：

```text
Linux 5.10
x86 架构 atomic API
这些特定 Linux barrier 契约
```

不能据此声称 C11/C++ atomic 的所有 memory_order、任意编译器 builtin 或任意“原子变量”都天然是 full barrier。

## 12. `CONFIG_SMP` 为什么必须进入分析

公共 `smp_*` API 通过 generic barrier 层根据 `CONFIG_SMP` 选择实现。

在 SMP 内核中，CPU 间 ordering 是实际需求，公共接口映射到架构的 `__smp_*` 实现；在 UP 配置中，不存在另一个并行执行同一内核的 CPU，因此相关接口可以退化为 compiler-ordering fallback。

所以验证 Linux barrier 时必须记录：

```text
目标是否 x86-64
CONFIG_SMP 是否启用
观察的是源码宏还是最终机器指令
```

同一段调用在不同配置下得到不同反汇编并不矛盾。

## 13. 一个实用的阅读顺序

以后看到内核并发代码中的 barrier，可以按以下顺序判断：

```text
1. 先找共享状态和两个执行者。
2. 写出每一侧需要保持的 load/store 顺序。
3. 判断需要 full barrier，还是 acquire/release 已足够。
4. 确认代码使用的是 mb/rmb/wmb 还是 smp_* API。
5. 再进入 arch/x86/include/asm/barrier.h 看 x86 实现。
6. 检查 CONFIG_SMP 等配置。
7. 最后用 objdump 检查目标内核的真实机器指令。
```

这样不会从“我看到了 `mfence`/没看到 `mfence`”倒推算法语义。

## 14. 常见误区

### 误区一：`barrier()` 就是 CPU memory barrier

不是。它首先是 compiler barrier。

### 误区二：x86 是强内存序，所以不需要 Linux barrier

不对。Linux API 还承担 compiler ordering、跨架构语义和并发协议表达；full Store→Load 等顺序也不能一概忽略。

### 误区三：`smp_rmb()` 没生成 `lfence`，所以它什么也没做

不对。CPU 层可以利用 x86 ordering，编译器层仍需保持所要求的顺序。

### 误区四：所有 barrier 最终都应该是 `mfence/lfence/sfence`

不对。locked RMW、memory `xchg` 和架构天然 ordering 都可能承担实现角色。

### 误区五：原子操作等于 full memory barrier

不能这样泛化。必须查看具体 atomic API 的 ordering contract 与架构实现。

## 15. 与 A18 第一部分的统一模型

现在可以把 A18 前两部分放在同一张图里：

```text
共享内存并发
   |
   +-- 同一位置的 read-modify-write 会不会被竞争打断？
   |      -> atomic RMW
   |      -> xchg / lock cmpxchg / lock xadd
   |
   +-- 不同内存访问之间允许怎样排序？
          -> memory ordering
          -> acquire/release / smp barriers / full barriers
```

底层指令可能同时参与两个问题，但概念上仍应分开分析。

## 16. 本节完成后应能回答的问题

读完本节，应能解释：

1. 为什么源码顺序不能直接当作跨 CPU 的观察顺序；
2. compiler ordering、CPU ordering 与 Linux barrier API 的区别；
3. x86 TSO 为什么使部分 Linux SMP barrier 比弱内存序架构更轻；
4. `mb/rmb/wmb` 与 `smp_mb/rmb/wmb` 为什么不能机械一一对应；
5. Linux 5.10 x86 的 `smp_mb()` 为什么可以使用 locked RMW；
6. release/acquire 分别约束哪一侧的访问；
7. x86 上 acquire/release 为什么通常不需要额外 fence；
8. `smp_store_mb()` 为什么可以基于 memory `xchg`；
9. 为什么 `CONFIG_SMP` 会影响公共 `smp_*` API 的最终实现；
10. 为什么原子性、ordering 和 GCC `"memory"` clobber 必须分层理解。

下一最小单元应通过反汇编和 litmus-style 实验验证这些结论：先检查 barrier API 的实际指令，再用两个 CPU 的消息传递/Store Buffering 模型观察“允许出现什么”，而不是把一次偶然运行结果当作架构保证。

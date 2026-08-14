# A18 源码事实核验：x86-64 原子 RMW、LOCK 与 Linux 5.10 atomic 接口

本文只固定 A18 第一部分所需的 Linux 5.10/x86-64 源码事实。内存屏障的完整语义和 GCC 扩展内联汇编约束分别留给后续单元。

## 1. 问题边界

A18 需要先区分三个层次：

1. x86-64 指令本身的 read-modify-write（RMW）语义；
2. `LOCK` 前缀或指令隐含的原子性；
3. Linux 5.10 `atomic_t`/`arch_atomic_*` 接口如何落到这些指令。

“一个 C 表达式看起来只有一行”并不意味着它是跨 CPU 原子的；反过来，Linux 的 atomic 接口也不能只从 C 函数名推断最终指令，必须检查 x86 实现和配置条件。

## 2. Linux 5.10 源码基线

本单元核对以下 upstream v5.10 文件：

```text
arch/x86/include/asm/atomic.h
arch/x86/include/asm/cmpxchg.h
arch/x86/include/asm/alternative.h
```

其中：

- `atomic.h` 定义 x86 的 `arch_atomic_*` 基本实现；
- `cmpxchg.h` 定义 `arch_xchg()`、`arch_cmpxchg()`、`try_cmpxchg()`、`xadd()` 等底层操作；
- `alternative.h` 定义 `LOCK_PREFIX`，并说明 SMP alternatives 对 lock prefix 的处理。

## 3. `xchg`：内存操作数时不需要显式 `lock`

Linux 5.10 在 `cmpxchg.h` 中通过 `__xchg_op()` 生成不同宽度的 `xchg`。`arch_xchg(ptr, v)` 传入的 lock 字符串为空：

```text
arch_xchg(ptr, v)
    -> __xchg_op(ptr, v, xchg, "")
```

源码旁的注释明确指出：即使在 SMP 上也不添加 `lock`，因为 `xchg` 对内存操作数本身就隐含锁定语义。

这意味着要区分：

```text
xchg reg, reg       普通寄存器交换
xchg reg, [mem]     对内存操作数执行原子交换，隐含锁定语义
```

A18 后续实验应直接检查最终反汇编，而不是期待看到 `lock xchg` 文本。

## 4. `cmpxchg`：RAX 是隐含比较/返回寄存器

Linux 5.10 的 `__raw_cmpxchg()` 对 8/16/32/64-bit 宽度分别生成 `cmpxchgb/w/l/q`。以内存目标为例，其核心模型是：

```text
expected 放入 AL/AX/EAX/RAX
new      放入普通输入寄存器
cmpxchg new, [mem]
```

架构语义可以概括为：

```text
if accumulator == memory:
    ZF = 1
    memory = new
else:
    ZF = 0
    accumulator = memory
```

因此 `cmpxchg` 不只是“比较后可能写内存”：失败路径还会把实际内存旧值带回 accumulator。

Linux `arch_cmpxchg(ptr, old, new)` 返回目标内存原来的值，调用者可将返回值与 `old` 比较判断成功与否。

## 5. `try_cmpxchg()`：失败时更新 expected

Linux 5.10 的 `__raw_try_cmpxchg()` 同样使用 accumulator 作为 expected 输入/实际旧值输出，并通过 condition-code output 取得 ZF。

接口语义是：

```text
bool try_cmpxchg(ptr, &old, new)
```

- 成功：返回 `true`，`*ptr` 被写成 `new`；
- 失败：返回 `false`，并把实际观察到的旧值写回 `old`。

源码中只有失败时才执行：

```text
*_old = __old;
```

这使典型重试循环可以直接复用被更新后的 expected：

```c
old = READ_ONCE(*p);
do {
        new = f(old);
} while (!try_cmpxchg(p, &old, new));
```

这与只返回旧值的 `cmpxchg()` API 是不同的接口形状。

## 6. `xadd`：一次 RMW 同时得到旧值

Linux 5.10 定义：

```text
xadd(ptr, inc)
    -> __xadd(ptr, inc, LOCK_PREFIX)
    -> __xchg_op(ptr, inc, xadd, LOCK_PREFIX)
```

其接口注释明确说明：把 `inc` 加到 `*ptr`，并原子返回 `*ptr` 的旧值。

因此：

```text
old = xadd(ptr, inc)
new = old + inc
```

`arch_atomic_fetch_add(i, v)` 直接返回 `xadd(&v->counter, i)`；`arch_atomic_add_return(i, v)` 则返回 `i + xadd(...)`。两者底层可以使用同一条 `xadd`，但 C 接口分别返回 old value 和 new value。

## 7. `arch_atomic_*` 到具体指令

Linux 5.10 `arch/x86/include/asm/atomic.h` 的主线对应关系如下：

```text
arch_atomic_add/sub       -> LOCK_PREFIX addl/subl
arch_atomic_inc/dec       -> LOCK_PREFIX incl/decl
arch_atomic_fetch_add     -> xadd(..., LOCK_PREFIX)
arch_atomic_add_return    -> i + xadd(..., LOCK_PREFIX)
arch_atomic_cmpxchg       -> arch_cmpxchg -> cmpxchg(..., LOCK_PREFIX)
arch_atomic_try_cmpxchg   -> try_cmpxchg -> cmpxchg(..., LOCK_PREFIX)
arch_atomic_xchg          -> arch_xchg -> xchg（内存形式隐含锁定）
```

`arch_atomic_read()` 和 `arch_atomic_set()` 在该文件中分别使用 `__READ_ONCE` 和 `__WRITE_ONCE`；它们不是通过 `lock` RMW 指令实现。不要把“atomic_t 接口”机械等同于“每个操作都有 LOCK 前缀”。

## 8. `LOCK_PREFIX` 的 CONFIG_SMP 条件

Linux 5.10 `arch/x86/include/asm/alternative.h` 中：

```text
CONFIG_SMP=y:
    LOCK_PREFIX -> 记录到 .smp_locks，并生成 "lock; "

CONFIG_SMP=n:
    LOCK_PREFIX -> 空字符串
```

SMP kernel 还利用 alternatives 机制管理这些 lock-prefix 位置，以支持 UP/SMP 场景切换。因此源码里的 `LOCK_PREFIX` 不是简单的固定文本常量。

这也是为什么 A18 实验必须记录：

```text
内核配置
编译后的实际指令
```

而不能只引用宏展开后的源代码字符串。

`xchg` 是一个重要例外：`arch_xchg()` 不使用 `LOCK_PREFIX`，因为内存形式的 `xchg` 自身提供所需原子语义。

## 9. `memory` 与 `cc` clobber 的边界

这些实现大量使用 GCC extended asm：

- `"+m"` 表示目标内存既读又写；
- accumulator 常用 `"a"`/`"+a"` 约束；
- `"memory"` clobber 约束编译器对周围内存访问的重排；
- 部分 RMW 模板声明 `"cc"`，或通过 `CC_SET/CC_OUT` 显式消费条件码。

这些是**编译器与内联汇编之间的契约**，不是 CPU `LOCK` 的同义词。A18 后续“内联汇编”单元应单独展开，当前只固定这一边界。

同样，CPU memory-ordering、Linux acquire/release/full-barrier API 与 `mfence/lfence/sfence` 的关系不能从 `"memory"` clobber直接推出，留给屏障单元核验。

## 10. 第一部分可据此建立的执行模型

当前已核验的最小主线是：

```text
Linux atomic API
        |
        +-- fetch/add-return -> xadd
        |
        +-- compare/exchange -> cmpxchg
        |
        +-- exchange         -> xchg
        |
        +-- simple add/sub   -> lock add/sub（SMP 主线）

x86 RMW instruction
        |
        +-- memory value 被读取
        +-- 算术/比较/交换
        +-- memory value 条件或无条件写回
        +-- 返回旧值/更新 flags（依指令而定）
```

第一部分教程应先解释为什么并发更新需要“读 + 判断/计算 + 写”作为不可分割的 RMW，再分别讲 `xchg`、`cmpxchg`、`xadd`，最后映射到 Linux 5.10 `arch_atomic_*`。

## 11. 尚未在本单元展开的内容

以下内容属于 A18 后续最小单元：

```text
mfence / lfence / sfence 与 x86 ordering
Linux smp_mb()/smp_rmb()/smp_wmb() 等屏障接口
acquire / release / relaxed atomic variants
GCC extended asm 输入/输出/early-clobber/匹配约束
完整 compiler barrier 与 CPU barrier 区分
```

这些内容不能根据本文件的 `LOCK_PREFIX` 或 `"memory"` clobber 直接补全。

# A18 第一部分：原子 RMW、`xchg`、`cmpxchg` 与 `xadd`

并发代码中的一个常见误区，是把一条 C 语句当成一条不可分割的 CPU 操作。例如：

```c
counter++;
```

从语义上看它只是“加一”，但机器通常需要先读取旧值、计算新值，再把新值写回内存。如果两个 CPU 同时执行这组三步操作，它们可能读到同一个旧值，最终丢失一次更新。

因此，本节先不讨论完整的内存屏障，而只回答一个更基础的问题：**怎样让一次 read-modify-write（RMW）在多个 CPU 竞争同一内存位置时成为一个不可分割的原子操作？**

Linux 5.10 在 x86-64 上大量使用 `xchg`、`cmpxchg`、`xadd` 和带 `LOCK` 前缀的算术指令实现这类操作。本节先建立这些指令的寄存器、内存和 RFLAGS 模型，再映射到 Linux 5.10 的 `arch_atomic_*` 接口。

## 1. 普通 read-compute-write 为什么会丢失更新

假设共享变量初值为 10，CPU0 和 CPU1 都要执行加一。如果编译结果在概念上是：

```text
load  [counter] -> register
add   $1, register
store register  -> [counter]
```

可能出现：

```text
CPU0: read 10
CPU1: read 10
CPU0: compute 11
CPU1: compute 11
CPU0: write 11
CPU1: write 11
```

执行了两次“加一”，结果却只有 11。

问题不在 `add` 的整数计算，而在于整个“读旧值 → 计算 → 写新值”不是一个不可分割的共享内存操作。原子 RMW 指令解决的正是这个问题。

需要先区分三个概念：

```text
RMW 指令语义       指令读取并修改同一目标
原子 RMW           其他 CPU 不能观察到该 RMW 被并发更新打断的中间状态
memory ordering    该操作与前后其他内存访问之间允许怎样排序
```

本节聚焦前两项。完整 ordering 留给 A18 后续屏障单元。

## 2. `xchg`：无条件交换

最简单的 RMW 是交换：

```asm
xchgq %rax, (%rdi)
```

执行前假设：

```text
RAX       = 20
[RDI]     = 10
```

执行后：

```text
RAX       = 10
[RDI]     = 20
```

也就是说，寄存器得到内存旧值，内存得到寄存器旧值。

对于 x86，`xchg` 的一个重要特殊规则是：**当一个操作数是内存时，它具有锁定的原子交换语义，不需要显式写成 `lock xchg`。**

因此看到 Linux 5.10 的 `arch_xchg()` 最终生成普通文本形式的 `xchg`，不能据此判断它“没有原子性”。反过来，寄存器与寄存器之间的 `xchg` 没有共享内存 RMW 问题。

`xchg` 不应被理解成“先 load，再 store，只是汇编写在一行”。它在架构上是一条交换操作。

## 3. `cmpxchg`：只有旧值符合预期才写入

很多无锁算法不能无条件覆盖共享值，而需要表达：

> 只有内存仍然等于我之前观察到的 expected，才把它改成 new。

x86 的 `cmpxchg` 正是这个模型。64-bit 形式可以写成：

```asm
cmpxchgq %rdx, (%rdi)
```

其中 `%rax` 是隐含的 expected/old-value 寄存器。

### 3.1 成功路径

执行前：

```text
RAX       = 10       expected
RDX       = 20       new
[RDI]     = 10       actual
```

比较成功后：

```text
ZF        = 1
[RDI]     = 20
RAX       = 10
```

内存从 expected 更新成 new。

### 3.2 失败路径

如果执行前：

```text
RAX       = 10       expected
RDX       = 20       new
[RDI]     = 15       actual
```

则执行后：

```text
ZF        = 0
[RDI]     = 15       不写 new
RAX       = 15       返回实际观察到的内存值
```

因此 `cmpxchg` 的失败路径不是简单的“什么都不做”。它会把实际旧值送回 accumulator。

这正是 compare-and-exchange 循环能够高效重试的基础。

## 4. `cmpxchg` 的 RFLAGS

`cmpxchg` 会按照比较结果更新算术标志。对于 compare-and-exchange 是否成功，最直接的标志是 ZF：

```text
ZF = 1    accumulator == memory，交换成功
ZF = 0    accumulator != memory，交换失败
```

Linux 5.10 的 `try_cmpxchg()` 实现会直接利用 condition-code output 获得这个布尔结果。

这里应区分两种 API 形状：

```text
cmpxchg(ptr, old, new)
    返回目标位置原来的值

try_cmpxchg(ptr, &old, new)
    返回 bool；失败时把实际旧值写回 old
```

第二种形式特别适合重试循环：

```c
old = READ_ONCE(*p);
do {
        new = f(old);
} while (!try_cmpxchg(p, &old, new));
```

失败以后 `old` 已经被更新为本次实际观察到的值，下一轮可以直接重新计算 `new`。

## 5. `xadd`：加法和“返回旧值”合并成一次 RMW

`xadd` 可以理解为 exchange-and-add。以：

```asm
xaddq %rax, (%rdi)
```

为例，执行前：

```text
RAX       = 3
[RDI]     = 10
```

执行后：

```text
RAX       = 10
[RDI]     = 13
```

所以它同时完成两件事：

1. 把增量加到内存；
2. 把内存旧值返回到寄存器。

这使同一条底层指令可以支持不同的 C 接口。

Linux 5.10 x86 实现中：

```text
arch_atomic_fetch_add(i, v)
    返回 old

arch_atomic_add_return(i, v)
    使用 old + i 得到并返回 new
```

两者都可以基于 `xadd`，区别在于接口最终向调用者返回旧值还是新值。

与内存形式 `xchg` 不同，Linux 的 `xadd` 原子共享内存路径使用 `LOCK_PREFIX`。

## 6. `LOCK` 前缀解决什么问题

对于普通内存形式的算术/RMW 指令，仅仅“是一条机器指令”并不足以推出多 CPU 原子性。x86 提供 `LOCK` 前缀，使支持的内存 RMW 在多处理器环境中具有所需的原子语义。

例如 Linux 5.10 的 x86 `arch_atomic_add()` 主线使用：

```text
LOCK_PREFIX addl
```

`arch_atomic_fetch_add()` 则通过带 `LOCK_PREFIX` 的 `xadd` 实现。

但不要把规则简化成“Linux atomic 指令前面一定有 lock”：

- `arch_atomic_xchg()` 使用内存形式 `xchg`，它自身具有锁定语义；
- `arch_atomic_read()`/`arch_atomic_set()` 不是 RMW；
- Linux 5.10 的 `LOCK_PREFIX` 还受 `CONFIG_SMP` 与 SMP alternatives 机制影响。

因此分析具体内核时，应同时看源码宏、配置和最终反汇编。

## 7. Linux 5.10 `arch_atomic_*` 的映射

A18 已按 Linux 5.10 核验以下主线：

```text
arch_atomic_add/sub
    -> LOCK_PREFIX addl/subl

arch_atomic_inc/dec
    -> LOCK_PREFIX incl/decl

arch_atomic_fetch_add
    -> xadd(..., LOCK_PREFIX)

arch_atomic_add_return
    -> i + xadd(..., LOCK_PREFIX)

arch_atomic_cmpxchg
    -> arch_cmpxchg
    -> cmpxchg(..., LOCK_PREFIX)

arch_atomic_try_cmpxchg
    -> try_cmpxchg
    -> cmpxchg(..., LOCK_PREFIX)

arch_atomic_xchg
    -> arch_xchg
    -> memory xchg
```

对应源码事实记录见：

[`../source-paths/18-atomic-rmw-x86-linux-5.10.md`](../source-paths/18-atomic-rmw-x86-linux-5.10.md)

这张映射的用途不是让读者背函数名，而是建立一个检查方法：看到 Linux atomic API 时，继续追到架构实现，再检查实际 RMW 指令、输入输出寄存器、flags 和配置条件。

## 8. `CONFIG_SMP` 与 `LOCK_PREFIX`

Linux 5.10 的 `LOCK_PREFIX` 不是简单固定为字符串 `"lock; "`。

在 SMP 配置下，x86 alternatives 机制会记录并管理这些 lock-prefix 位置；在非 SMP 配置下，对应宏可以为空。

因此教材中说：

> `arch_atomic_add()` 在 x86 SMP 主线上使用 locked add。

比说：

> `arch_atomic_add()` 永远编译成 `lock add`。

更准确。

实验中如果要验证内核最终指令，也必须记录被观察内核的 `.config`。

## 9. compiler contract 与 CPU 原子性不是一回事

Linux 这些实现大量使用 GCC extended asm，例如：

```text
+m
+a
memory clobber
cc / condition-code output
```

这些约束告诉编译器：内联汇编读写哪些 C 对象、哪些寄存器/flags 会改变，以及周围代码可以怎样安排。

它们不等价于 CPU 的 `LOCK` 语义。

例如：

```text
"memory" clobber
```

首先是一个 compiler barrier/编译器可见副作用边界，不能单独推出“CPU 已执行 full memory barrier”。同样，CPU 指令具有原子 RMW 语义，也不意味着编译器可以不知道这段 asm 修改了哪些对象。

A18 后续会单独展开 extended asm constraints 和 memory ordering，本节只建立边界。

## 10. 把三条指令放在一起比较

可以用下面的模型记忆，而不是只记助记符：

| 指令 | 主要输入 | 内存更新 | 主要输出 | 成功判断 |
| --- | --- | --- | --- | --- |
| memory `xchg` | register + memory | 无条件交换 | register 得到 old memory | 不需要条件成功 |
| `cmpxchg` | accumulator expected + new + memory | 仅 expected==actual 时写 new | 失败时 accumulator 得到 actual | ZF |
| `xadd` | increment + memory | memory = old + increment | register 得到 old memory | 无条件 RMW |

三者都可能服务于原子算法，但解决的问题不同：

```text
xchg       无条件取得所有权/替换值
cmpxchg    条件更新，是很多 lock-free retry loop 的基础
xadd       原子计数并同时取得更新前的值
```

## 11. 与普通函数 ABI 的区别

这些指令中的寄存器角色是**指令编码/架构规则**，不是 System V AMD64 函数 ABI。

例如 `cmpxchg` 使用 RAX 作为隐含 accumulator，是 x86 指令语义；某个 C wrapper 如何把函数参数搬到 RAX/RDX/RDI，则属于编译器和 ABI 层。

阅读反汇编时应先问：

```text
这个寄存器角色来自指令本身，还是来自函数调用 ABI？
```

否则很容易把两层规则混在一起。

## 12. 本节完成后应能回答的问题

读完本节，应能解释：

1. 为什么普通 load/add/store 会在并发更新中丢失修改；
2. 原子 RMW 与 memory ordering 为什么不是同一个问题；
3. memory `xchg` 为什么不要求显式 `lock`；
4. `cmpxchg` 成功和失败时内存、RAX、ZF 分别怎样变化；
5. `try_cmpxchg()` 为什么会在失败时更新 expected；
6. `xadd` 为什么天然适合实现 fetch-add；
7. Linux 5.10 的主要 `arch_atomic_*` 如何映射到 x86 指令；
8. 为什么 `LOCK_PREFIX` 必须结合 `CONFIG_SMP` 和最终反汇编理解；
9. 为什么 GCC asm 的 `"memory"`/`"cc"` 不能与 CPU 原子性或完整内存屏障混为一谈。

下一最小单元将通过可运行实验直接观察 `xchg`、`cmpxchg`、`xadd` 的寄存器、内存和 ZF 结果，并检查多线程下普通 RMW 与 locked atomic RMW 的差异。
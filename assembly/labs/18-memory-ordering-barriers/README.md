# A18 第二部分实验：x86 memory ordering 与 Linux 5.10 barrier

本实验对应 [`../../docs/18-memory-ordering-and-barriers.md`](../../docs/18-memory-ordering-and-barriers.md) 和 [`../../source-paths/18-memory-barriers-x86-linux-5.10.md`](../../source-paths/18-memory-barriers-x86-linux-5.10.md)。目标不是用一次运行“证明 x86 内存模型”，而是把三类证据分开：Linux 5.10 源码宏定义、目标内核实际生成的机器指令、并发 litmus test 的运行观察。

## 1. 验证问题

本实验验证以下结论：

1. `mb()/rmb()/wmb()` 与 `smp_mb()/smp_rmb()/smp_wmb()` 不是同一组接口；
2. Linux 5.10 x86-64、`CONFIG_SMP=y` 时，full `smp_mb()` 需要真实 CPU ordering primitive，而 `smp_rmb()/smp_wmb()` 可利用 x86 TSO 而不额外生成对应 fence；
3. `smp_store_release()` / `smp_load_acquire()` 在 x86 主线上通常落成普通 store/load 加 compiler-ordering 约束，而不是机械插入 `mfence`；
4. `smp_store_mb()` 可利用 memory `xchg`；
5. Store Buffering litmus 中“观察到某个结果”与“架构允许/禁止某个结果”不是同一层证据。

## 2. 环境要求

静态内核验证需要：

```text
Linux kernel v5.10 源码 checkout
x86-64 toolchain
一份明确的 .config
objdump
```

必须先记录：

```bash
git describe --always --dirty
scripts/config --state CONFIG_SMP 2>/dev/null || grep '^CONFIG_SMP=' .config
${CC:-gcc} --version | head -1
objdump --version | head -1
```

如果没有 Linux 5.10 checkout，只能完成源码级检查和用户态 litmus；不得把下面的预期反汇编写成实际构建结果。

## 3. 先检查 v5.10 宏定义

在内核源码根目录执行：

```bash
grep -nE '(^|[[:space:]])#define (mb|rmb|wmb|__smp_mb|__smp_rmb|__smp_wmb|__smp_store_release|__smp_load_acquire|__smp_store_mb)' \
    arch/x86/include/asm/barrier.h

grep -nE 'CONFIG_SMP|smp_mb\(|smp_rmb\(|smp_wmb\(' include/asm-generic/barrier.h
```

这里验证的是**源码映射关系**，还不是最终机器指令。尤其 `smp_*` 公共接口需要结合 `CONFIG_SMP` 判断。

## 4. 用内核 translation unit 观察最终指令

建立临时文件 `barrier_probe.c`（不提交到生产内核）：

```c
#include <linux/compiler.h>
#include <asm/barrier.h>

int probe_data;
int probe_flag;

noinline void probe_mb(void)
{
        WRITE_ONCE(probe_data, 1);
        mb();
        WRITE_ONCE(probe_flag, 1);
}

noinline void probe_rmb(void)
{
        int a = READ_ONCE(probe_data);
        rmb();
        int b = READ_ONCE(probe_flag);
        asm volatile("" : : "r"(a), "r"(b) : "memory");
}

noinline void probe_wmb(void)
{
        WRITE_ONCE(probe_data, 1);
        wmb();
        WRITE_ONCE(probe_flag, 1);
}

noinline void probe_smp_mb(void)
{
        WRITE_ONCE(probe_data, 1);
        smp_mb();
        WRITE_ONCE(probe_flag, 1);
}

noinline void probe_smp_rmb(void)
{
        int a = READ_ONCE(probe_data);
        smp_rmb();
        int b = READ_ONCE(probe_flag);
        asm volatile("" : : "r"(a), "r"(b) : "memory");
}

noinline void probe_smp_wmb(void)
{
        WRITE_ONCE(probe_data, 1);
        smp_wmb();
        WRITE_ONCE(probe_flag, 1);
}

noinline void probe_release(int v)
{
        smp_store_release(&probe_flag, v);
}

noinline int probe_acquire(void)
{
        return smp_load_acquire(&probe_flag);
}

noinline void probe_store_mb(int v)
{
        smp_store_mb(probe_flag, v);
}
```

最可靠的构建方法是把它临时加入当前 v5.10 kernel build，使它继承内核自己的 `KBUILD_CFLAGS`、配置宏和 alternatives 条件。不要直接用普通用户态 `gcc barrier_probe.c`，否则得到的并不是“当前内核配置下的 Linux barrier 实现”。

例如可临时放入 `kernel/` 并在 `kernel/Makefile` 增加：

```make
obj-y += barrier_probe.o
```

然后只构建目标对象：

```bash
make olddefconfig
make -j"$(nproc)" kernel/barrier_probe.o
objdump -drwC -Mintel kernel/barrier_probe.o > /tmp/barrier-probe.intel.txt
objdump -drwC -Matt kernel/barrier_probe.o > /tmp/barrier-probe.att.txt
```

实验结束后删除临时 Makefile 修改和 probe 文件。

## 5. 反汇编观察点

逐个定位：

```bash
grep -nE '<probe_(mb|rmb|wmb|smp_mb|smp_rmb|smp_wmb|release|acquire|store_mb)>' \
    /tmp/barrier-probe.intel.txt
```

在 Linux 5.10、x86-64、`CONFIG_SMP=y` 的常规构建中，重点检查：

```text
probe_mb       : 是否存在 mfence
probe_rmb      : 是否存在 lfence
probe_wmb      : 是否存在 sfence
probe_smp_mb   : 是否存在 locked RMW（不要预设必须是 mfence）
probe_smp_rmb  : 是否没有额外 lfence
probe_smp_wmb  : 是否没有额外 sfence
probe_release  : 发布 store 周围是否没有额外 mfence
probe_acquire  : 获取 load 周围是否没有额外 mfence
probe_store_mb : 是否出现 memory xchg
```

必须以当前 v5.10 checkout 和当前 `.config` 的实际反汇编为准。编译器版本、alternatives 和配置可能改变具体编码，因此验收对象首先是**语义对应关系**，不是固定字节序列。

## 6. SMP 与 UP 对照

如果环境允许，另建一份 `CONFIG_SMP=n` 的 x86-64 配置，再构建同一 probe。比较：

```text
SMP build 的 smp_mb()
UP build 的 smp_mb()
```

预期公共 `smp_*` API 在 UP 下可退化到 compiler-ordering fallback。这里的重点是说明 `CONFIG_SMP` 属于 Linux API 映射条件；不要把 SMP 构建里看到的 locked instruction 写成所有配置的固定实现。

## 7. Store Buffering litmus：只作为运行观察

用户态可用下面的经典模型理解 Store→Load：

```text
初始：x = 0, y = 0

CPU0                 CPU1
x = 1                y = 1
r0 = y               r1 = x
```

关注结果：

```text
r0 == 0 && r1 == 0
```

在 x86 TSO 模型中，store buffer 使 Store→Load 成为必须认真处理的方向，因此这个结果不是仅凭“每个线程源码中 store 在 load 前”就能排除的。

如果自己编写 pthread/C11 测试，必须同时处理 compiler reorder 和 C 语言 data-race/atomic 语义。推荐使用 C11 relaxed atomics 表达测试变量，而不是用普通 `volatile int` 冒充跨线程同步原语。

伪代码：

```c
_Atomic int x, y;

CPU0:
atomic_store_explicit(&x, 1, memory_order_relaxed);
r0 = atomic_load_explicit(&y, memory_order_relaxed);

CPU1:
atomic_store_explicit(&y, 1, memory_order_relaxed);
r1 = atomic_load_explicit(&x, memory_order_relaxed);
```

重复很多轮可以尝试观察 `0/0`，但：

- 一次没观察到 `0/0` 不能证明架构禁止它；
- 观察频率不是架构保证；
- 线程调度、CPU affinity、编译器、虚拟化环境都会影响出现概率；
- Linux kernel barrier 的正确性不能靠这个用户态测试单独证明。

## 8. Message Passing 对照

再建立发布/获取模型：

```text
producer:
data = 42
release-store ready = 1

consumer:
if acquire-load ready == 1
        read data
```

这里要验证的不是“x86 有没有生成 fence”，而是：release/acquire API 表达同步关系；在 x86 上，CPU 层所需顺序可由 TSO 满足，所以反汇编可能只看到普通 store/load，而编译器层仍受 API 约束。

## 9. 验收标准

完成实验时至少保存以下证据：

1. kernel commit/tag 与 `CONFIG_SMP`；
2. `barrier.h`/generic barrier 的对应宏；
3. probe 的 AT&T 与 Intel 反汇编；
4. `mb/rmb/wmb` 与 `smp_*` 的指令差异；
5. acquire/release 和 `smp_store_mb()` 的实际指令；
6. 若执行 litmus，记录 CPU、affinity、迭代次数和结果计数；
7. 明确区分“源码事实”“反汇编事实”“本机运行观察”“架构保证”。

## 10. 本次维护环境的执行边界

本实验文档已按 Linux 5.10 已核验的 barrier 源码关系编写，但当前维护环境没有可执行的 `netplus/kernel` Linux 5.10 checkout，因此本次不能实际运行 Kbuild、`objdump` 或多线程 litmus。这里没有填写虚构的指令地址、编码或运行次数；待具备 checkout 的环境后，应按上述步骤补充真实结果。

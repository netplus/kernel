# A18 实验预期分析：原子 RMW 的寄存器、内存与标志位

本文是 [`README.md`](README.md) 的验收基线。它只固定实验应验证的架构事实，不把尚未执行的具体地址、机器码或线程竞争结果写成实测值。

## 1. `xchgq`：memory 形式完成真正的交换

实验初始条件为：

```text
memory = 10
register operand = 20
```

执行 `xchgq reg, mem` 后必须得到：

```text
register operand = 10
memory = 20
```

因此 `do_xchg()` 返回 10，而调用者随后读取 `x` 应得到 20。

反汇编验收点：目标必须是 memory `xchg`。源码没有写显式 `lock` 前缀是正确的；x86 对带 memory operand 的 `xchg` 定义了锁定的 read-modify-write 语义。不能据此推导所有没有 `lock` 文本的 memory RMW 都是原子的。

`xchg` 不提供本实验需要解释的条件码结果，因此这里不把 RFLAGS 作为验收对象。

## 2. `cmpxchgq` 成功：比较相等，写入 desired，ZF=1

成功 case 的指令前状态：

```text
RAX(expected) = 10
memory        = 10
desired       = 20
```

`cmpxchg` 比较 accumulator 与 destination。两者相等时：

```text
ZF     = 1
RAX    = 10
memory = 20
```

RAX 保持原 expected 值；memory 被 desired 覆盖。因此程序应打印与下列不变量等价的结果：

```text
cmpxchg_success zf=1 rax=10 mem=20
```

这里的 RAX 是 x86 `cmpxchg` 的隐式 accumulator，不是 System V AMD64 C 参数 ABI 对 `expected` 的固定寄存器要求。编译器必须根据 `+a` constraint 在指令前把该值放入 RAX。

## 3. `cmpxchgq` 失败：实际 memory 回写 accumulator，ZF=0

失败 case 的指令前状态：

```text
RAX(expected) = 10
memory        = 15
desired       = 20
```

比较不相等时不得写入 desired，而是把 destination 的实际值装入 accumulator：

```text
ZF     = 0
RAX    = 15
memory = 15
```

因此程序应满足：

```text
cmpxchg_failure zf=0 rax=15 mem=15
```

这也是理解 Linux `try_cmpxchg()` expected 更新语义的机器指令基础：失败后调用者可以得到刚刚观察到的实际内存值。

`setz` 必须在 `cmpxchg` 之后、任何会覆盖相关 flags 的指令之前读取 ZF。反汇编时应确认编译器保持这一数据依赖。

## 4. `xaddq`：内存得到和，寄存器得到 old value

指令前：

```text
memory    = 10
increment = 3
```

执行 locked `xadd` 后：

```text
register operand = 10
memory           = 13
```

所以 `do_xadd()` 返回 old value 10，随后读取 `x` 得到 13：

```text
xadd old=10 new=13
```

反汇编必须出现对目标 memory 的 `lock xadd`。这正是 Linux 5.10 `arch_atomic_fetch_add()` / `arch_atomic_add_return()` 所依赖的基本指令模型，但用户态 wrapper 本身不是 Linux `atomic_t` API 的实现验证。

## 5. 多线程计数：只把 atomic counter 作为硬验收条件

四个线程、每线程 `N` 次时：

```text
expected = 4 * N
```

locked RMW 计数器必须满足：

```text
atomic_counter == expected
```

否则说明实验实现或运行环境出现了与预期不符的问题。

普通 counter 的 load/increment/store 不是一个不可分割的 RMW。多个线程可以读到相同 old value，并各自写回相同 new value，从而产生 lost update。因此竞争充分时通常会观察到：

```text
plain_counter < expected
```

但这不是单次运行的硬验收条件。调度可能使某次运行碰巧得到 expected；实验不能把“这次没有观察到 lost update”误写成普通 RMW 已获得原子性。

## 6. 反汇编的最小验收集合

AT&T 与 Intel 两种输出都应检查，至少确认：

```text
do_xchg:
    memory xchg
    无需显式 lock 文本

do_cmpxchg:
    lock cmpxchg
    accumulator 为 RAX
    后续 setz/sete 读取 ZF

do_xadd:
    lock xadd

worker:
    plain_counter 存在分离的 read/modify/write 形状
    atomic_counter 使用 locked RMW
```

寄存器分配和确切地址属于编译器/链接器产物，不应硬编码到验收文档。AT&T 与 Intel 的源/目的操作数显示顺序不同，也不能用文本位置代替指令语义判断。

## 7. inline asm constraint 复核

本实验 wrapper 的约束应按以下方式理解：

- `+m`：对应 memory operand 既读又写；
- `+r`：寄存器 operand 既是输入又承接输出；
- `+a`：expected 既作为 RAX 输入，又在失败时接收实际 memory value；
- `=q`：`setz` 输出一个可编码的 8-bit register；
- `"cc"`：声明 condition codes 被汇编修改；
- `"memory"`：阻止编译器把其他内存访问自由跨过该 asm 重排。

最后一项是 compiler barrier 语义，不是 CPU 原子性来源。CPU 原子 RMW 来自 x86 指令及其 lock 语义；compiler constraint、CPU atomicity 和 memory ordering 必须保持为三个不同层次。

## 8. 当前环境下的结论边界

在没有实际 checkout/shell 的维护运行中，只能完成源码与 constraint 的静态复核，不能宣称已经得到：

```text
具体机器码
具体寄存器分配
plain_counter 的某个数值
线程运行耗时
GDB 中的具体 RFLAGS 值
```

具备可执行环境后，独立验收应至少包含：

```bash
make clean && make
make check-disasm
./atomic_rmw
./atomic_rmw 5000000
objdump -dr atomic_rmw
objdump -dr -Mintel atomic_rmw
```

只有这些命令真实执行后，才能把对应输出记录为“实测结果”。

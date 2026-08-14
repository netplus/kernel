# A18 实验预期分析：GCC extended asm constraints

本文给 `18-gcc-extended-asm-constraints` 实验提供验收基线。它描述的是 **constraint 正确时 GCC 必须维护的数据流关系**，不是对某个 GCC 版本具体寄存器分配的预测。

## 1. 验收层次

实验结果应分三层判断：

1. C 级确定性结果是否正确；
2. `-O2` 反汇编是否满足 operands/constraints/clobbers 描述的数据流；
3. 哪些行为来自 x86 指令本身，哪些只是 GCC compiler contract。

不能仅凭程序输出正确就认定 constraint 正确。错误 contract 可能在某一次寄存器分配中碰巧没有暴露。

## 2. `+r`：同一位置的 read/write 生命周期

`read_write_operand(5)` 的确定结果是 12。

`+r(x)` 表示 asm 入口时该 machine location 中已有 `x`，asm 退出时同一 operand 又产生新的 `x`。因此反汇编必须满足：

```text
old x -> 某个 GPR -> add $7, same GPR -> new x
```

具体 GPR 不是验收条件。关键是 destination 不能被当作纯 output 而丢失旧值。

## 3. matching constraint：位置相同，不是数值相同

`matching_operand(9, 4)` 的确定结果是 13。

output 0 为 `=r(out)`，input `x` 使用 `"0"`，因此 GCC 必须让 `x` 的输入位置与 output 0 使用同一 machine location。反汇编可能先 move，也可能因为调用约定和寄存器分配直接复用现有寄存器；两者都合法。

验收关系是：

```text
location(x at asm entry) == location(out at asm exit)
```

不是 `x == out` 的数值约束。

## 4. early-clobber：output 不能覆盖尚未消费的 input

`early_clobber_example(20, 22)` 的确定结果是 42。

模板第一条指令已经写 `tmp`，第二条指令才读取 `b`：

```asm
movq %1, %0
addq %2, %0
```

因此 `=&r(tmp)` 的 `&` 要求 output 在所有普通 input 被认为消费完之前就可能被改写。GCC 不能把 `tmp` 与仍需在第二条指令读取的 `b` 分配到同一寄存器。

验收重点不是看到某个固定寄存器组合，而是第二条 `add` 读取的 `b` 必须仍保存原始 22。

## 5. `cmpxchg`：accumulator、memory 与 ZF 的联合 contract

第一次调用从：

```text
*p       = 11
*expected = 11
desired   = 42
```

开始，应得到：

```text
success   = 1
*p        = 42
*expected = 11
ZF        = 1 at cmpxchg completion
```

第二次调用从：

```text
*p        = 42
*expected = 7
desired   = 99
```

开始，应得到：

```text
success   = 0
*p        = 42
*expected = 42
ZF        = 0 at cmpxchg completion
```

这里 `+a(old)` 必须同时表达两件事：asm 入口 accumulator 保存 expected；失败时 `cmpxchg` 又把 actual memory value 写回 accumulator。若只把 accumulator 描述成 input，compiler 就不知道失败后的 `old` 已改变；若只描述成 output，又丢失 compare 输入。

`+m(*p)` 表示具体 target object 被读写。`sete` 消费 `cmpxchg` 产生的 ZF，因此 `"cc"` 必须声明 condition codes 被修改。`"memory"` 告诉 compiler asm 还具有比显式 operand 更宽的 memory side effect/order visibility；它不是 CPU fence，也不是 `LOCK` 原子性的来源。

反汇编验收至少应看到：

```text
expected -> RAX
lock cmpxchg <desired-reg>, (<target-address>)
sete <byte-destination>
```

具体 desired register 和 byte destination 不固定。

## 6. 精确 `+m` 与全局 `"memory"` clobber

`precise_memory_operand()` 进入 asm 时：

```text
old = 3
*p  = 55
```

memory `xchg` 后：

```text
return old = 55
*p         = 3
```

`+m(*p)` 精确描述 `*p` 这个 C object 的 read/write dependency；它并不等价于告诉 GCC “任意内存都可能变化”。相反，`"memory"` clobber 是更宽泛的 compiler-visible memory side-effect 声明。

memory `xchg` 的 locked/atomic 语义来自 x86 ISA，不来自 `+m`，也不来自 `"memory"`。

## 7. `cc`、`memory`、`volatile` 的边界

验收时应能明确说出：

```text
cc       -> compiler 不可假定 condition codes 跨 asm 保持
memory   -> compiler 必须保守处理相关内存状态/移动
volatile -> 限制 compiler 删除或随意搬移该 asm statement
```

它们都不等价于：

```text
LOCK
CPU full memory barrier
禁止 CPU speculation
Linux smp_mb()
```

这些属于不同语义层。

## 8. `-O2` 反汇编的正确判定方法

优化后允许发生 move 消除、寄存器复用、调用约定寄存器直接沿用等变化。因此不要按固定指令字节或固定寄存器验收。

应按数据流验收：

```text
+ operand 的旧值是否真的进入 asm？
matching operands 是否共享位置？
early-clobber output 是否避开仍存活的 input？
cmpxchg 的 RAX 是否同时承担 expected/actual 生命周期？
失败路径是否能把 actual 写回 *expected？
显式 memory operand 与 memory clobber 是否被正确区分？
```

AT&T 与 Intel 反汇编只是同一机器码的两种表示，两者必须表达相同 operand direction 和 memory target。

## 9. 当前环境边界

当前课程维护环境没有可执行的仓库 checkout，因此本文件只给出经过源码语义复核的验收基线，尚未记录 GCC/binutils 版本、实际寄存器分配或程序运行输出。

获得可执行 Linux/x86-64 环境后，应实际执行：

```bash
make clean
make
make run
make disasm-att
make disasm-intel
```

只有这些命令真实运行后，才能把具体生成指令和输出标记为实测结果。
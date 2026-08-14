# A18 第三部分：GCC extended asm constraints 与编译器契约

A18 前两部分已经分别讨论了 x86 原子 RMW 指令和 Linux 5.10 的内存屏障。本节继续解决另一个不同的问题：当 C 代码中嵌入一段汇编时，编译器怎样知道这段汇编读取了什么、修改了什么，以及哪些机器位置必须保持一致。

这不是 x86 指令本身能够解决的问题。CPU 只执行最终机器码；在机器码产生之前，GCC 还必须进行寄存器分配、公共子表达式消除、load/store 移动和死代码删除。extended asm 的 operands、constraints、clobbers 和 `volatile` 正是编译器与汇编模板之间的契约。

Linux 5.10 x86 的原子操作大量使用这种机制，因此阅读 `cmpxchg.h`、`atomic.h` 时，既要理解指令语义，也要理解 compiler contract。

## 1. 一段 inline asm 同时存在两个正确性问题

考虑一个抽象过程：

```text
C objects
   |
   | operands / constraints / clobbers
   v
GCC register allocation and optimization
   |
   v
asm template
   |
   v
x86 instructions
```

这里有两个独立的正确性条件。

第一，汇编模板本身必须符合 ISA。例如 `cmpxchg` 必须按 x86 规定使用 accumulator，并正确理解成功/失败时 RAX、memory 和 ZF 的变化。

第二，constraints 必须把这些变化准确告诉 GCC。即使模板中的 `cmpxchg` 完全正确，如果 GCC 被告知 RAX 只是输入、目标内存只是输出，编译器看到的数据流就与 CPU 实际执行的数据流不同，优化后的程序仍可能错误。

因此：

```text
inline asm correctness
  = instruction semantics correct
  + compiler data-flow contract correct
```

## 2. extended asm 的基本结构

GNU C 常见形式是：

```c
asm volatile (
    "..."
    : outputs
    : inputs
    : clobbers
);
```

四部分承担不同职责：

- template 描述 assembler 最终看到的指令文本；
- output operands 告诉 GCC 哪些 C 值由 asm 产生或更新；
- input operands 告诉 GCC asm 执行前需要哪些值；
- clobbers 描述 operand 列表之外还会被破坏的状态。

constraint 则进一步规定 operand 可以或必须位于哪里，例如 general register、memory 或 accumulator。

这些规则属于 GCC extended asm，不属于 System V AMD64 函数调用 ABI。`"a"` 表示 accumulator constraint，并不意味着“这是第几个函数参数”。

## 3. `=` 与 `+`：输出是否还需要旧值

最先要问的问题不是“输出放哪个寄存器”，而是“asm 是否读取输出对象的旧值”。

```c
"=r"(out)
```

表示 write-only output。GCC 可以认为进入 asm 前 `out` 的旧值对这段 asm 没有意义。

```c
"+r"(value)
```

表示 read/write operand：进入 asm 时旧值是输入，离开 asm 时同一 operand 又承载新值。

内存也一样：

```c
"+m"(*p)
```

表示目标内存既被读取又被写回。

这对 read-modify-write 尤其重要。假设一条指令语义是：

```text
old = memory
memory = f(old)
```

如果把 memory 错写成纯 `"=m"`，compiler data-flow 就丢掉了对 old value 的读取。

## 4. `r`、`m` 与 `a` 描述机器位置

常见 constraint 包括：

```text
r   general-purpose register
m   memory operand
a   x86 accumulator register class
```

`r` 给寄存器分配器较大的自由度；`m` 让模板直接引用一个内存操作数；`a` 则用于 ISA 对 accumulator 有明确要求的场景。

例如 x86-64 `cmpxchgq` 的 expected/actual 通道固定使用 RAX，因此 compiler contract 必须体现这一点。不能把 expected 当作任意 `"r"` 输入，然后期待 assembler 或 CPU 自动理解哪个值应进入 RAX。

更重要的是，`cmpxchg` 失败时 RAX 会被实际内存值覆盖，所以 accumulator 不只是 input。

抽象地说，它的数据流是：

```text
input:
    RAX = expected
    memory = actual
    new = replacement

if actual == expected:
    memory = new
    ZF = 1
else:
    RAX = actual
    ZF = 0
```

因此描述 accumulator 时必须把“进入时需要 expected”和“失败后可能产生 actual”同时告诉编译器。Linux 5.10 的 cmpxchg/try_cmpxchg 实现正建立在这个事实之上。

## 5. matching constraint：两个 C operand 必须共享一个机器位置

有时 C 接口希望把初始值和最终结果写成两个逻辑 operand，但 ISA 要求它们使用同一个寄存器。GCC 可以用 matching constraint 表达这种 identity。

例如：

```c
asm("..."
    : "=r"(result)
    : "0"(initial));
```

`"0"` 的意思不是 initial 与 result 数值相等，而是 input 必须与 output operand 0 分配到同一个 location。

也可以使用 symbolic operand name 表达同样的绑定关系。

因此 matching constraint 解决的是：

```text
C 中两个逻辑角色
        |
        v
必须映射到同一个 machine location
```

它不能替代 read/write constraint，也不能自动处理 early-clobber。

## 6. early-clobber `&` 为什么存在

GCC 通常可以假定 asm 在产生 output 前已经读取完 input，因此某个 output register 有机会与某个不相关 input 共用寄存器。

对于单条、具有普通读写时序的指令，这可能完全正确。但多指令模板可能很早就覆盖 output，而后面的指令仍需要某个 input。

此时：

```c
"=&r"(tmp)
```

告诉 GCC：这个 output 会被提前破坏，不允许把它与仍需读取的 input 分配到同一寄存器。

因此 `&` 影响的是 register allocation correctness。它不会让指令变得原子，也不会形成 CPU memory barrier。

## 7. `cc`：告诉 GCC condition codes 已变化

很多 x86 算术和原子指令会修改 RFLAGS 中的条件码，例如 ZF、CF、SF、OF。

如果 asm 修改了 condition-code state，而这些变化没有通过更精确的 condition-code output 暴露，就需要按 compiler contract 声明相应 clobber，例如：

```c
: "cc"
```

这表示 GCC 不能假定 asm 前后的 condition-code state 保持不变。

某些接口还会直接把 flags 中的条件变成 C 布尔输出。例如 compare-exchange 接口需要知道操作是否成功时，可以消费 ZF 所表达的 equal condition。

无论采用哪种形式，这仍然只是“编译器如何理解 flags”。CPU 是否原子执行 memory RMW 取决于 `LOCK`、memory `xchg` 等 ISA 规则，而不是 `"cc"`。

## 8. 精确 memory operand 与 `"memory"` clobber

这两个概念经常被混为一谈。

如果 asm 明确只读写某个 C 对象，可以把它作为 operand 描述：

```c
"+m"(*p)
```

这样 GCC 能看到一个精确的 read/write dependency。

而：

```c
: "memory"
```

表示 asm 可能影响 operand 列表没有完整描述的内存状态。GCC 因而需要放弃一部分跨越该 asm 的 memory-value 假设，并限制相关优化。

可以把两者理解成：

```text
+m(*p)      precise object dependency
"memory"    broad compiler-visible memory side effect
```

`"memory"` 常被称为 compiler memory barrier，但这个名称不能扩展成“CPU full barrier”。它不会自动产生 `mfence`、locked instruction，也不能单独阻止 CPU speculative access。

CPU ordering 必须由 x86 架构规则或 Linux barrier primitive 另外保证。

## 9. `asm volatile` 也不是硬件屏障

`volatile` 主要告诉 GCC：这段 asm 具有不能仅从普通 output data flow 判断的可见意义，因此不能像普通无用计算那样随意删除，并对编译器移动它施加相应约束。

但下面三个结论都不成立：

```text
asm volatile => atomic
asm volatile => CPU full barrier
asm volatile => no speculation
```

反过来，一段具有真正可见 output 的非-volatile asm 也不意味着一定会被删除。

判断是否需要 `volatile`，应从 compiler-visible side effect 出发，而不是从“这段汇编看起来重要”出发。

## 10. 用 `cmpxchg` 把三层机制分开

`cmpxchg` 是理解 Linux inline asm 的好例子，因为它同时涉及三层。

### 10.1 ISA 层

CPU 规定：

- accumulator 保存 expected；
- memory 与 expected 比较；
- 成功时 memory 写入 replacement；
- 失败时 accumulator 得到 actual；
- ZF 反映比较结果；
- 对共享内存做原子 RMW 时需要相应锁定语义。

### 10.2 compiler-contract 层

GCC 必须知道：

- memory 是 read/write；
- accumulator 是 input/output；
- replacement 是 input；
- flags 会变化或其条件会被消费；
- 必要时还存在额外 memory side effect。

### 10.3 Linux API 层

Linux 再把这些机制封装成不同接口，例如“返回旧值”或“失败时更新 expected”的 compare-exchange 形状。

所以阅读内核宏时，不应看到 `+a`、`+m` 或 `memory` 就直接推断硬件语义。应先问这个 constraint 在 compiler data-flow 中承担什么职责，再回到实际 x86 指令。

## 11. 一个错误 constraint 为什么可能在 `-O0` 看起来正常

错误的 inline asm 经常具有迷惑性：在 `-O0`、寄存器压力低或某次特定编译中，它可能恰好生成预期机器码。

这不能证明 contract 正确。

constraints 的作用之一就是给优化器和寄存器分配器提供长期成立的事实。到了 `-O2`，编译器可能：

- 重用寄存器；
- 把 C 值长期保存在寄存器中；
- 消除它认为没有变化的 load；
- 移动它认为彼此无依赖的操作。

如果 asm 的声明与真实 side effects 不一致，这些本来合法的优化就可能暴露错误。

因此 A18 的 extended-asm 实验必须至少在 `-O2` 下检查生成代码，并把“错误 constraint 对照”作为编译器契约教学材料，而不能要求 miscompile 每次稳定复现。

## 12. 阅读 Linux 5.10 inline asm 的推荐顺序

遇到一个内核 inline-asm primitive，可以按下面顺序阅读。

第一步，先确定 C API contract：输入是什么，返回 old 还是 new，失败是否更新 expected。

第二步，展开 operands 与 constraints：哪些是 input、output、read/write；哪些必须使用 accumulator；是否存在 matching 或 early-clobber。

第三步，检查 clobbers：flags 和 operand 之外的 memory side effects 是否已经描述。

第四步，再看 x86 指令：实际读写哪些寄存器、内存和 RFLAGS。

第五步，最后判断 multiprocessor atomicity 与 ordering：是否有 `LOCK_PREFIX`、memory `xchg`、fence 或 Linux barrier API，以及 `CONFIG_SMP`/alternatives 是否改变最终编码。

这个顺序能避免把 GCC constraint 字符、x86 ISA 和 Linux memory model 混成同一个层次。

## 13. 本节需要保留的核心模型

GCC extended asm 的核心不是记忆一张 constraint 字符表，而是让编译器获得与机器指令一致的数据流模型：

```text
C value/object
    |
    | operand + constraint
    v
machine location
    |
    | asm instruction semantics
    v
new register/memory/flags state
    |
    | output + clobber contract
    v
compiler-visible state after asm
```

其中：

- `=` 表示 write-only output；
- `+` 表示 read/write operand；
- `r/m/a` 约束机器位置；
- matching constraint 要求 input/output 共享 location；
- `&` 防止 early output 与尚未消费的 input 错误重叠；
- `cc` 描述 condition-code side effect；
- `memory` 描述宽泛的 compiler-visible memory side effect；
- `volatile` 约束 compiler 对 asm statement 的部分删除/移动行为。

这些 compiler rules 与 x86 `LOCK`、fence、TSO 和 Linux barrier API 相互配合，但不能互相替代。

## 14. Linux 5.10 源码入口

本节对应的版本事实核验见：

[`../source-paths/18-gcc-extended-asm-constraints-linux-5.10.md`](../source-paths/18-gcc-extended-asm-constraints-linux-5.10.md)

重点源码路径为：

```text
arch/x86/include/asm/cmpxchg.h
arch/x86/include/asm/atomic.h
arch/x86/include/asm/barrier.h
```

第一部分的原子 RMW 指令语义与第二部分的 memory-ordering/barrier 机制应分别参阅对应章节，不在本节重复展开。

## 15. 下一步实验

下一最小单元将使用小型 C/extended-asm 对照程序，在 `-O2` 下通过 AT&T/Intel `objdump` 检查：

- `=r` 与 `+r` 的数据流差异；
- `+m` 如何建立精确 memory dependency；
- accumulator constraint 在 `cmpxchg` 中的实际寄存器落点；
- matching constraint 如何固定 location identity；
- early-clobber 如何限制寄存器重叠；
- `cc`、`memory` 和 `volatile` 的 compiler-contract 边界。

错误 constraint 示例只用于解释为什么声明不完整会使优化器获得错误事实，不以偶然的错误运行结果作为验收标准。
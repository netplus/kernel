# A18 源码事实核验：GCC extended asm 约束与 Linux 5.10 x86 用法

本文固定 A18 第三部分所需的事实边界：GCC extended asm 如何把 C 对象、寄存器、内存和 condition codes 描述给编译器，以及 Linux 5.10 x86 原子操作为什么使用这些约束。这里讨论的是**编译器与 asm 模板之间的契约**；x86 原子 RMW 和 CPU memory ordering 已分别在 A18 第一、第二部分核验。

## 1. 为什么需要单独核验 constraints

内联汇编同时处在两个世界之间：

```text
C / compiler IR
        |
        | operands + constraints + clobbers
        v
assembler template
        |
        v
x86 machine instruction
```

只读 asm 模板不足以判断代码是否正确。模板可能写出正确的 `cmpxchg`，但如果没有告诉编译器 accumulator 会变化、目标内存会被读写、flags 会变化，编译器仍可能基于错误的数据流模型优化周围代码。

反过来，`"memory"` clobber 或 `"cc"` 也不会凭空给 CPU 增加 `LOCK`、`mfence` 或原子性。A18 必须把这两层分开。

## 2. 本单元核验基线

Linux 5.10 x86 侧重点检查：

```text
arch/x86/include/asm/cmpxchg.h
arch/x86/include/asm/atomic.h
arch/x86/include/asm/barrier.h
```

GCC 约束语义按 GNU extended asm 文档核验，重点包括：

```text
=       write-only output
+       read/write output
&       early-clobber output
r       general register
m       memory operand
a       x86 accumulator register class
0 / [name]   matching constraint
cc      condition-code clobber
memory  compiler-visible memory clobber
volatile     asm side-effect/移动删除边界之一
```

这些符号是 GCC/compiler contract；具体机器指令语义仍由 x86 ISA 决定。

## 3. `=` 与 `+`：输出是否需要旧值

GCC 对 output operand 的基本区分是：

```text
"=r"(out)   asm 只产生新值；进入 asm 时旧值不构成输入
"+r"(x)     asm 既读取 x 的旧值，又写回 x 的新值
"+m"(*p)    目标内存既被读取又被写入
```

因此 read-modify-write 不能错误写成纯 write-only output。如果 asm 先消费旧值再产生新值，编译器必须在数据流上看到“read + write”。

Linux 5.10 的 x86 RMW 模板正依赖这种表达方式：内存目标以 read/write memory operand 参与，寄存器 old/new 值也按指令实际数据流声明。

## 4. `cmpxchg` 为什么需要 accumulator 约束

x86 `cmpxchg` 的 expected/actual 通道不是任意 GPR，而是隐含 accumulator：8/16/32/64 位分别对应 AL/AX/EAX/RAX。

因此 Linux 5.10 的 cmpxchg 实现必须让编译器知道：

```text
进入指令：accumulator = expected
成功：     memory = new，accumulator 保留 expected/old
失败：     accumulator = actual memory value
```

这就是 accumulator operand 必须同时表达输入和输出的原因。不能只把 expected 写成 input-only `"a"`，因为失败路径会修改 accumulator；也不能只声明 output，因为执行比较前 CPU 必须先得到 expected。

这类约束解决的是“编译器把哪个 C 值放到哪个机器位置，以及执行后哪个 C 值发生变化”，不是 System V AMD64 函数参数 ABI。

## 5. matching constraint：输入和输出必须是同一个位置

GCC 允许 input operand 使用数字或 symbolic name 与某个 output operand 绑定，例如：

```text
output 0: "=r"(result)
input:    "0"(initial)
```

含义不是“两个值碰巧相等”，而是要求编译器把 input 与对应 output 分配到**同一个 location**。

当一条 ISA 指令规定某个寄存器既承载输入又承载输出，而 C 接口又希望把“输入变量”和“输出变量”写成不同表达式时，matching constraint 是重要工具。

如果实际 asm 会在读取所有其他输入之前就覆盖这个 output，还必须进一步考虑 early-clobber，而不能只靠 matching 关系。

## 6. `&` early-clobber：输出过早覆盖时阻止危险重叠

GCC 默认可以假设：一条 extended asm 的输入在输出产生之前已经被消费，因此某些 output register 可以与不相关 input 共用寄存器。

如果 asm 模板由多条指令组成，或者某个 output 在其他 input 尚未使用完之前就被写坏，这个默认假设可能不成立。此时 output 应使用 `&`：

```text
"=&r"(tmp)
```

它告诉寄存器分配器：这个输出在 asm 很早阶段就被 clobber，不能与仍需读取的 input 占用同一寄存器。

因此 `&` 不是“让 asm 更原子”，而是修正 compiler register-allocation contract。

## 7. `"cc"` 与 condition-code output

x86 的 `cmpxchg`、`xadd`、`add/sub` 等会修改 RFLAGS 中的算术条件码。编译器必须知道 asm 对 flags 的影响。

一种表达方式是：

```text
: "cc"
```

表示 condition-code state 被 clobber。

另一类实现会通过 GCC condition-code output 直接把某个条件（例如 ZF 对应的 equal）变成 C 布尔输出。Linux 5.10 的 `try_cmpxchg()` 就属于“既执行 compare-exchange，又消费成功条件”的接口形状。

二者都属于 compiler-visible flags contract。它们不能替代 CPU `LOCK` 语义。

## 8. `"memory"` clobber 的准确边界

GCC 文档把 `"memory"` 定义为 compiler-visible memory side-effect 边界：编译器不能假定 asm 前缓存于寄存器的内存值在 asm 后仍然有效，并需要相应限制周围 memory access 的优化。

应把它理解为：

```text
compiler memory barrier / unknown memory side effect
```

而不是：

```text
CPU full memory barrier
```

GCC 文档也明确指出，`"memory"` 本身不能阻止处理器执行 speculative reads；需要 CPU ordering 时仍要依赖架构规定或 processor-specific fence/locked primitive。

这与 A18 第二部分的结论一致：Linux 5.10 x86 `smp_mb()` 的 CPU ordering 来自 locked RMW，而不是仅来自 `"memory"` clobber。

## 9. 精确 memory operand 与全局 `"memory"` 不是同一个工具

如果 asm 只访问一个编译器能够描述的 C 对象，应尽量通过 operand 明确告诉编译器实际读写对象，例如：

```text
"+m"(*p)
```

这建立精确的数据依赖。

`"memory"` clobber 则表达 asm 可能影响 operand 列表之外的内存，作用范围更宽，可能迫使编译器丢弃更多关于内存值的假设。

因此不能把：

```text
精确 +m operand
```

和：

```text
全局 memory clobber
```

视为完全等价的写法。Linux 内联汇编常同时需要精确 operand 与 compiler barrier 语义，具体应以该宏的 contract 为准。

## 10. `asm volatile` 解决的也不是 CPU ordering

`volatile` 主要约束编译器对 asm statement 的删除、合并和移动等优化，尤其适用于具有编译器无法从 outputs 完整推导出的副作用的 asm。

它不自动表示：

```text
原子
full barrier
禁止 CPU speculative execution
```

同样，不带 `volatile` 也不表示某条有可见 output 的 asm 一定会消失。是否需要 `volatile` 必须从 compiler-visible side effects 判断。

## 11. 把 Linux 5.10 atomic 模板分层阅读

以后看到类似 x86 atomic inline asm，应按下面顺序阅读：

```text
第一层：C API contract
    返回 old 还是 new？失败是否更新 expected？

第二层：extended asm contract
    哪些 operand 是 input/output/read-write？
    是否固定 accumulator？
    是否有 matching / early-clobber？
    flags 与 memory side effects 如何声明？

第三层：x86 instruction semantics
    xchg/cmpxchg/xadd 实际修改什么寄存器、内存、RFLAGS？

第四层：multiprocessor atomicity / ordering
    是否需要 LOCK_PREFIX？
    memory xchg 是否隐含锁定？
    是否还需要 barrier？

第五层：Linux configuration
    CONFIG_SMP / alternatives 是否改变最终编码？
```

这种顺序可以避免从一个 constraint 字符直接推出硬件语义。

## 12. 与前两部分的连接

A18 第一部分已经固定：

```text
xchg / cmpxchg / xadd
LOCK_PREFIX
arch_atomic_* 映射
```

第二部分已经固定：

```text
x86 TSO
mb/rmb/wmb
smp_mb/rmb/wmb
acquire/release
smp_store_mb
```

本单元补上的第三层是：

```text
C value
  -> GCC operand/constraint/clobber
  -> assembler template operand
  -> x86 register/memory/flags
```

因此到这里才能完整解释为什么一段 Linux inline asm 既要“机器指令正确”，又要“constraints 正确”。

## 13. 第三部分教程与实验应验证什么

下一最小单元不应再重复 atomic/barrier 原理，而应直接围绕 compiler contract 建立教程和实验。至少需要对照：

```text
"=r" 与 "+r"
"+m"
"a" / "+a"
matching constraint "0"
early-clobber "&"
"cc"
"memory"
asm volatile
```

实验应使用 `-O2` 反汇编，因为 constraints 的意义正体现在寄存器分配和优化阶段；同时至少检查 AT&T/Intel 两种反汇编，避免把 GCC constraint 与汇编语法的操作数顺序混淆。

错误 constraint 示例只能作为受控教学对照，不应依赖 undefined/miscompiled behavior 每次稳定复现某个运行结果。验收重点应是生成代码和 compiler data-flow contract，而不是把偶然错误输出当作规范保证。

## 14. 当前核验结论

A18 第三部分可以据此建立以下核心模型：

```text
extended asm correctness
    = assembler template 符合 ISA
    + operands/constraints 正确描述 C <-> machine data flow
    + clobbers 正确描述额外 side effects
```

其中：

- `=` / `+` 决定 output 是否还读取旧值；
- matching constraint 固定 input/output location identity；
- `&` 防止 early output 与尚未消费的 input 错误重叠；
- `cc` 描述 condition codes；
- `memory` 描述 compiler-visible unknown memory side effects；
- `volatile` 约束 compiler 对 asm statement 的部分优化；
- 以上任何一项都不能单独替代 x86 `LOCK`、fence 或 Linux barrier API。

第三部分正式教程应继续保持这个分层，而不是把 extended asm 写成一张 constraint 字符表。
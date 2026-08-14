# A18 整章一致性复核：原子 RMW、内存顺序与 extended asm

A18 的三个部分分别回答三个不同层次的问题。整章收口前必须把这三个层次重新放到同一个模型中检查，避免把相邻概念写成同义词。

## 1. 三个层次

### 1.1 x86 指令与原子 RMW

第一部分讨论 CPU 实际执行的 read-modify-write 指令。

- memory `xchg` 交换寄存器和内存，内存形式本身具有锁定语义；
- `cmpxchg` 使用 accumulator 保存 expected，成功时写入 new，失败时把 actual 写回 accumulator，并通过 ZF 表示比较结果；
- `xadd` 把加法和返回 old value 合并为一次 RMW；
- Linux 5.10 x86 SMP 主线中的若干 atomic RMW 通过 `LOCK_PREFIX` 获得跨 CPU 的原子更新语义；
- `LOCK_PREFIX` 受 `CONFIG_SMP` 和 alternatives 机制影响，不能脱离配置把源码宏机械等同于最终固定字节序列。

这里回答的是“同一共享内存位置的一次更新怎样不可分割”。它不是完整的 memory-ordering 模型。

对应材料：

- [`18-atomic-rmw-xchg-cmpxchg-xadd.md`](18-atomic-rmw-xchg-cmpxchg-xadd.md)
- [`../labs/18-atomic-rmw/`](../labs/18-atomic-rmw/)
- [`../source-paths/18-atomic-rmw-x86-linux-5.10.md`](../source-paths/18-atomic-rmw-x86-linux-5.10.md)

## 2. x86 memory ordering 与 Linux barrier API

第二部分讨论一个不同问题：一个 CPU 的 load/store 与另一个 CPU 的观察顺序之间有什么保证。

需要保持以下边界：

```text
atomicity
!= memory ordering
!= compiler ordering
```

Linux 5.10 x86 barrier 接口必须从架构实现、公共 barrier 层和当前配置共同理解：

- `mb/rmb/wmb` 与 `smp_mb/rmb/wmb` 不是简单的“宏名对应某一条 fence 指令”；
- x86 TSO 允许 Linux 在部分 acquire/release、read/write barrier 路径中只需要 compiler-ordering 约束，而不额外发出 fence；
- full SMP barrier 可以利用 locked RMW 的 ordering 属性；
- `smp_store_mb()` 可以利用 memory `xchg`；
- `CONFIG_SMP=n` 时公共 `smp_*` 接口具有不同的展开边界，因此实验必须记录配置；
- Store Buffering 等 litmus 的一次运行结果只能作为观察，不能代替架构规则。某个允许结果“本次没有出现”不等于架构禁止它。

对应材料：

- [`18-memory-ordering-and-barriers.md`](18-memory-ordering-and-barriers.md)
- [`../labs/18-memory-ordering-barriers/`](../labs/18-memory-ordering-barriers/)
- [`../source-paths/18-memory-barriers-x86-linux-5.10.md`](../source-paths/18-memory-barriers-x86-linux-5.10.md)

## 3. GCC extended asm 是编译器契约

第三部分讨论机器码生成之前的 compiler contract。

operands、constraints、clobbers 和 `volatile` 的作用，是告诉 GCC：

- asm 读取什么；
- asm 写回什么；
- 哪些输入输出必须占用同一个 machine location；
- 哪些 output 在所有 input 消费完成前就可能被覆盖；
- condition codes 是否被修改；
- 编译器对周围内存访问能够做什么重排。

因此必须保持以下区别：

- `+r`/`+a` 描述 read/write operand，不产生 CPU 原子性；
- matching constraint 描述 location identity，不等于值相等；
- early-clobber `&` 是寄存器分配生命周期约束；
- `cc` 告诉编译器 flags 被修改，不负责读取 ZF 的程序语义；
- `"memory"` clobber 是 compiler memory barrier，不等于 CPU full fence；
- `asm volatile` 约束 asm 自身的优化/移动边界，但不能替代完整的数据流描述。

`cmpxchg` 是三个层次交汇的代表：x86 ISA 规定 accumulator、memory 和 flags 的机器行为；`LOCK` 决定共享内存 RMW 的原子/ordering 属性；GCC constraints 则必须准确描述这些机器副作用，使优化器生成正确代码。

对应材料：

- [`18-gcc-extended-asm-constraints.md`](18-gcc-extended-asm-constraints.md)
- [`../labs/18-gcc-extended-asm-constraints/`](../labs/18-gcc-extended-asm-constraints/)
- [`../source-paths/18-gcc-extended-asm-constraints-linux-5.10.md`](../source-paths/18-gcc-extended-asm-constraints-linux-5.10.md)

## 4. A18 大纲覆盖检查

领域大纲要求：

```text
xchg / cmpxchg / xadd
lock prefix
mfence / lfence / sfence
GCC extended inline asm
input / output / clobber constraints
Linux atomic and barrier assembly basics
```

当前三部分已经形成如下覆盖关系：

| 大纲要求 | 主要位置 |
| --- | --- |
| `xchg/cmpxchg/xadd` | 第一部分 |
| `lock` / `LOCK_PREFIX` | 第一、第二部分 |
| `mfence/lfence/sfence` 与 Linux barrier 映射边界 | 第二部分 |
| Linux atomic API | 第一部分 source-path 与教程 |
| Linux barrier API | 第二部分 source-path 与教程 |
| GCC extended asm | 第三部分 |
| input/output/matching/early-clobber | 第三部分 |
| `cc` / `memory` clobber | 第三部分 |

因此从课程内容覆盖看，A18 已不存在新的必需机制小节。剩余工作是把三部分教程、实验、Linux 5.10 source-path 和本复核入口接入 `assembly/README.md`，并在 README 中明确实际构建验证的状态。

## 5. 实验状态与完成边界

三部分实验都已经给出独立的观察点和 expected analysis，但当前维护环境没有可执行的 Linux 5.10 checkout，因此不能把以下项目标记为已实测：

- Linux 5.10 Kbuild 后 barrier/atomic 宏的最终反汇编；
- A18 用户态实验的 GCC/binutils 实际构建与 `objdump` 输出；
- Store Buffering / Message Passing 的本机运行观察；
- `-O2` extended-asm 对照的实际生成代码。

这属于实验执行环境限制，不改变已经完成的源码事实核验与课程模型。README 收口时必须继续保留“待具备 checkout 环境实测”的说明，不能把 expected analysis 写成运行结果。

## 6. 收章标准

A18 可以在以下条件满足后正式标记完成：

1. 三部分教程、实验和 source-path 全部接入 `assembly/README.md`；
2. README 明确三层边界：CPU atomic RMW、CPU/Linux memory ordering、GCC compiler contract；
3. README 保留实际构建/反汇编/并发运行尚未执行的环境限制；
4. 所有相对链接和文件名复核无误。

完成这些收口项后，下一章按当前领域大纲进入 A19：早期启动汇编阅读基础。
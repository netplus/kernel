# TSS、IST 与特殊异常栈

A15 第一部分讨论了 `#DE`、`#GP` 这类普通异常入口：CPU 先建立硬件异常 frame，Linux 再规范化 error-code slot、保存通用寄存器并形成 `pt_regs`。这个模型有一个隐含前提：异常入口能够获得一个可信的栈。

但 NMI、double fault、debug exception 和 machine check 面临更苛刻的问题。异常可能发生在内核已经处于敏感入口阶段时，甚至当前栈本身就是故障的一部分。此时如果入口代码必须先依赖旧 `%rsp` 才能换栈，已经太晚了。

x86-64 为此提供 TSS 中的 Interrupt Stack Table（IST）。它允许 IDT gate 指定一个独立栈，使 CPU 在执行第一条 Linux entry 指令之前就完成 `%rsp` 的切换。

本文以 Linux kernel 5.10 x86-64 为实现基线。重点不是背诵几个 IST 编号，而是建立下面的执行模型：

```text
per-CPU exception stack
 -> TSS.ist[]
 -> TSS descriptor / TR
 -> IDT gate.IST
 -> CPU chooses new RSP
 -> hardware exception frame
 -> Linux special entry
```

## 1. 先区分两种“异常时换栈”

x86-64 中至少有两种不同原因会导致异常/中断入口换栈。

第一种是特权级变化。例如普通异常从 CPL3 用户态进入 CPL0 内核态时，CPU 需要进入 ring-0 栈，并在新栈上保存旧用户态 `SS:RSP` 等返回现场。

第二种是 IDT gate 显式指定 IST。只要 gate 的 IST field 非零，CPU 就使用 TSS 中相应 IST entry 提供的新栈指针。这个动作并不要求发生 CPL3 -> CPL0；异常即使发生在 CPL0，IST 仍然可以强制换栈。

因此必须记住：

```text
privilege-level stack switch != IST stack switch
```

这一区分解释了为什么 NMI 或 double fault 在已经运行于内核态时仍然能够获得独立入口栈。

## 2. TSS 在现代 x86-64 Linux 中仍然有什么作用

早期 x86 可以利用 Task State Segment（TSS）进行 hardware task switching。现代 Linux x86-64 的普通进程调度并不采用这种方式，但 CPU 的异常入口硬件接口仍需要 TSS。

Linux 5.10 在 `arch/x86/include/asm/processor.h` 中定义 64-bit `struct x86_hw_tss`。与本文有关的字段可抽象为：

```text
sp0
sp1
sp2
ist[0]
ist[1]
...
ist[6]
```

TSS 是 per-CPU 对象，而不是每个 task 一份。Linux 5.10 还会复用硬件没有实际使用的 ring 字段：例如 `sp1` 与 `sp2` 在 Linux 中承担自己的入口实现用途。因此阅读源码时不能机械地把 `sp0/sp1/sp2` 都解释成 Linux 正在使用 ring 0/1/2 hardware task stacks。

对 A15 来说，最重要的是 `ist[7]`：这些字段保存若干特殊异常栈的栈顶地址。

## 3. IST 数组下标与 IDT gate 编码不是同一个数字

Linux 5.10 在 `arch/x86/include/asm/page_64_types.h` 中定义了类似下面的 C 侧索引：

```text
IST_INDEX_DF  = 0
IST_INDEX_NMI = 1
IST_INDEX_DB  = 2
IST_INDEX_MCE = 3
```

这些值用于访问零基 C 数组 `tss.ist[]`。

但是 x86-64 IDT descriptor 中的 IST field 使用另一套编码：

```text
0   不使用 IST
1   IST1
2   IST2
...
7   IST7
```

所以 `IST_INDEX_DF == 0` 并不意味着 double fault 的 IDT gate 把 IST field 写成 0。源码中的构造宏负责把 Linux 的数组索引转换为 descriptor 所需的编码。

如果把这两个数值空间混在一起，会得出“#DF 没有使用 IST”这种完全相反的结论。

## 4. exception stack 如何进入 TSS

Linux 5.10 的相关初始化位于 `arch/x86/kernel/cpu/common.c`。

正常运行前，每个 CPU 都要准备自己的异常栈。`tss_setup_ist()` 将这些栈的 top address 写入当前 CPU 的 `x86_hw_tss.ist[]`。

可以把这一阶段理解为：

```text
Linux 分配/准备 exception stack
        |
        v
得到 stack top
        |
        v
tss_setup_ist()
        |
        v
cpu_tss_rw.x86_tss.ist[n] = stack_top
```

这里保存的是将来 CPU 可以直接装入 `%rsp` 的栈顶，而不是 C handler 的参数。

## 5. CPU 怎样找到当前 CPU 的 TSS

仅仅在内存中存在一个 `struct tss_struct` 还不够。CPU 必须能够通过架构定义的描述符机制找到它。

Linux 为当前 CPU 在 GDT 中建立 TSS descriptor，并通过 `ltr` 装载 Task Register（TR）。因此从 CPU 角度看，寻找 IST stack pointer 的关系可以简化为：

```text
TR
 -> GDT 中的 TSS descriptor
 -> 当前 CPU 的 TSS
 -> ist[n]
 -> exception stack top
```

GDT 并不直接保存 exception stack。GDT 中保存的是 TSS descriptor；真正的栈指针位于 TSS。

这也是 GDT、TSS 和 IST 三个概念之间最重要的关系。

## 6. IDT gate 决定是否使用 IST

A15 第一部分已经说明，异常 vector 通过 IDT 找到入口 gate。64-bit IDT gate 除了包含 handler address、selector、type 等信息，还包含 IST field。

Linux 5.10 在 `arch/x86/include/asm/desc.h` 中构造 gate descriptor，在 `arch/x86/kernel/idt.c` 中决定具体 vector 使用什么 gate。

因此是否使用 IST 是 **IDT descriptor 的属性**，不是进入 C handler 后才决定的策略。

执行顺序是：

```text
异常发生
 -> CPU 根据 vector 查 IDT gate
 -> CPU 看到非零 IST field
 -> CPU 经 TR/TSS 取得 IST stack pointer
 -> CPU 切换 RSP
 -> CPU 在新栈上建立异常返回 frame
 -> RIP 才进入 Linux entry symbol
```

所以 Linux 汇编入口看到的 `%rsp` 已经位于 exception stack。不能把它描述成“Linux entry code 先运行，然后调用 `tss_setup_ist()` 或从 TSS 换栈”。`tss_setup_ist()` 是初始化阶段的工作，真正的入口换栈由 CPU 完成。

## 7. Linux 5.10 的核心 IST 用户

在 Linux 5.10 x86-64 正常运行期，基础课程需要关注四类入口：

```text
#DF  double fault       -> double-fault IST
NMI  non-maskable int   -> NMI IST
#DB  debug exception    -> debug IST
#MC  machine check      -> MCE IST（CONFIG_X86_MCE）
```

Linux 5.10 还存在与 `#VC`/SEV-ES 相关的 IST 支持，但这不是当前基础课程的主线。

这里的 vector 列表是 Linux 5.10 的实现选择。不同内核版本可能调整某些入口，因此不能依据其他版本的文章反推 v5.10。

## 8. 为什么 double fault 特别需要独立栈

Double fault 表示处理前一个异常时又出现了特定组合的异常条件。此时原来的入口条件可能已经损坏，其中就可能包括当前内核栈。

假设 `#DF` 仍必须继续使用旧 `%rsp`：

```text
原异常
 -> 栈状态已经不可用
 -> #DF
 -> 仍尝试在坏栈上建立 frame
 -> 再次失败
```

CPU 最终可能进入 triple fault，并导致 reset。

IST 的意义在于让 `#DF` 不必先信任旧栈：IDT gate 直接要求 CPU 从 TSS 取得一个独立 stack top。CPU 在进入 Linux double-fault entry 之前就已经有了新的 `%rsp`。

IST 不能保证 double fault 一定可恢复，但它至少提高了入口代码能够建立最小诊断现场的机会。

## 9. 为什么 NMI 也不能只依赖普通内核栈模型

NMI 不受普通 interrupt-disable 状态屏蔽，可以在非常敏感的执行阶段到达。例如 CPU 可能正位于普通异常、系统调用入口或其他低级 entry code 中。

因此 NMI 不能简单假定：

```text
当前 RSP 一定处于普通 C 函数可安全使用的内核栈状态
```

NMI IST 提供一个更独立的入口基础。CPU 先切换到 NMI stack，再进入 Linux 的 NMI entry code。

不过“使用独立 IST”并不等于“NMI 可以无限安全嵌套”。Linux 仍需要专门的 entry/paranoid 逻辑处理 GS 状态、嵌套和返回现场等问题。IST 只解决其中最底层的“先得到可信栈”问题。

## 10. `#DB` 与 `#MC` 为什么也有特殊入口

`#DB` 可以发生在很细的指令边界，并与 single-step、hardware breakpoint 等调试状态有关。Linux 5.10 为 debug exception 配置独立 IST，同时入口代码还有专门处理，不能直接套用第一部分 `#DE/#GP -> error_entry` 的普通模型。

在 `CONFIG_X86_MCE` 下，`#MC` 使用 machine-check IST。Machine check 可能发生在系统硬件状态已经不完全可靠的情况下，独立入口栈同样减少了对当前 `%rsp` 的依赖。

这些设计的共同目标不是让异常“更快”，而是降低特殊异常入口对被打断现场的假设。

## 11. 与第一部分普通异常逐阶段对照

以用户态 `#DE` 与内核态发生的 IST-backed 特殊异常做概念对照：

```text
普通 #DE（CPL3 -> CPL0）

vector -> IDT gate (IST=0)
       -> privilege transition 获得 ring-0 entry stack
       -> CPU 保存返回现场
       -> Linux 补 synthetic error-code slot
       -> error_entry
       -> PUSH_AND_CLEAR_REGS
       -> pt_regs

IST-backed exception

vector -> IDT gate (IST!=0)
       -> CPU 经 TR/TSS 取得 ist[n]
       -> RSP 切到 exception stack
       -> CPU 保存返回现场
       -> special/paranoid entry
       -> Linux 继续保存/规范化现场
       -> handler
```

两条路径最后都需要让 Linux 获得足够完整的执行现场，但“入口第一条指令执行前 `%rsp` 从哪里来”不同。

这正是学习 TSS/IST 时最应该掌握的差异。

## 12. 栈切换发生后，旧 RSP 是否消失

不会。

异常最终必须能够返回到被打断现场，因此 CPU 在入口 frame 中保存恢复执行所需的状态。发生 privilege transition 或 IST stack switch 时，旧栈状态也属于返回所需的信息。

所以“换到 IST stack”并不是丢弃旧 stack pointer，而是：

```text
old execution context
        |
CPU switches to IST RSP
        |
CPU records return context on new stack
        |
Linux handler runs
        |
return path restores interrupted context
```

后续分析实际 entry 汇编时，应始终同时追踪当前 `%rsp` 和 frame 中保存的旧 `%rsp`，不能只看当前寄存器值。

## 13. 初始化时序为什么重要

IST 依赖多个条件同时成立：

1. exception stack 已经准备好；
2. stack top 已写入 TSS；
3. GDT 中 TSS descriptor 已正确建立；
4. TR 已指向当前 CPU 的 TSS；
5. IDT gate 已安装正确的 IST 编码。

因此早期启动阶段不能在这些条件尚未建立时就假定普通运行期 IST 可用。Linux 5.10 的 IDT/TSS 初始化顺序正是为了满足这种依赖。

这也是阅读 `idt.c` 时不能只搜索某个 vector 最终 descriptor 的原因：还需要确认这个 descriptor 在什么初始化阶段安装。

## 14. 配置和版本边界

本文只描述 Linux kernel 5.10 x86-64 主线。

需要特别注意：

- `CONFIG_X86_64` 是本文 TSS/IST 布局的基础；
- `CONFIG_X86_MCE` 影响 machine-check 入口；
- `#VC`/SEV-ES 有额外条件，本章不展开；
- PTI 会改变普通用户态进入内核时 entry stack/page-table 的实现细节，但不改变 IST 的架构含义；
- 32-bit x86 的 double-fault 等实现不能直接套用；
- 更新内核中的入口机制也不能反向解释 Linux 5.10。

## 15. 阅读源码时应抓住的主线

对应 Linux 5.10，可以按下面顺序阅读：

```text
arch/x86/include/asm/processor.h
    struct x86_hw_tss

arch/x86/include/asm/page_64_types.h
    IST_INDEX_*

arch/x86/kernel/cpu/common.c
    tss_setup_ist()
    cpu_init_exception_handling()

arch/x86/include/asm/desc.h
    TSS descriptor / IDT gate 构造

arch/x86/kernel/idt.c
    哪些 vector 使用 IST

arch/x86/entry/entry_64.S
arch/x86/entry/entry_64_compat.S（只在需要时）
    special/paranoid entry 的实际执行过程
```

源码事实核验见：[`../source-paths/15-tss-ist-special-exceptions-linux-5.10.md`](../source-paths/15-tss-ist-special-exceptions-linux-5.10.md)。

## 16. 本节应形成的工作模型

学完这一部分，应能够回答：

- TSS 为什么在不使用 hardware task switching 的现代 x86-64 Linux 中仍然存在；
- privilege-level stack switch 与 IST stack switch 有什么区别；
- GDT/TSS descriptor、TR、TSS.ist[] 和 IDT gate.IST 如何串起来；
- 为什么 CPU 必须在进入第一条 Linux 特殊异常指令之前完成 IST 换栈；
- 为什么 `#DF`、NMI、`#DB`、`#MC` 不能简单套用普通 `#DE/#GP` 的入口假设；
- Linux 5.10 的哪些结论受配置或版本影响。

下一步通过实验读取实际 IDT descriptor 与当前 CPU TSS/IST 指针，并在隔离 Linux 5.10 guest 中对普通异常栈和可安全观测的 IST-backed 入口进行对照。破坏性的 `#DF/#MC` 不作为为了“看到现象”而主动触发的实验。
# Linux 5.10 x86-64 TSS、IST 与特殊异常栈源码事实核验

本文是 A15 第二部分的源码事实核验。范围限定为 Linux 5.10 x86-64 中 TSS 的栈指针字段、IST 初始化、IDT gate 的 IST 选择，以及 `#DB`、NMI、`#DF`、`#MC` 等特殊入口为什么不能简单套用普通异常的“继续使用当前内核栈”模型。

## 1. 先区分三个问题

TSS/IST 容易被混成一个概念，实际需要分开：

1. **特权级切换需要哪一个 ring stack**：x86-64 TSS 提供 `sp0/sp1/sp2`；Linux 主要关心 ring 0 入口所需状态，但 Linux 5.10 x86-64 的 `sp0` 还受到 entry trampoline/PTI 设计影响，不能简单等同于“当前 task 内核栈顶”。
2. **某个 IDT gate 是否指定 IST**：64-bit IDT gate 有 IST 字段；非零值要求 CPU 从 TSS 的对应 IST entry 取得新的栈指针。
3. **Linux 把哪些异常配置为 IST**：这是 Linux 5.10 的具体实现选择，必须从 `arch/x86/kernel/idt.c` 与 TSS 初始化代码核对，不能从“异常是否严重”猜测。

因此，“CPL3 -> CPL0 会切栈”和“IST 会切栈”是两个不同机制。IST 可以在已经位于 CPL0 时仍强制换到指定异常栈，这正是它对 NMI、double fault 等入口有价值的原因。

## 2. Linux 5.10 的 64-bit hardware TSS 布局

源码：

```text
arch/x86/include/asm/processor.h
```

在 `CONFIG_X86_64` 下，`struct x86_hw_tss` 的关键部分为：

```text
u32 reserved1
u64 sp0
u64 sp1
u64 sp2
u64 reserved2
u64 ist[7]
...
```

这里有两个必须保留的 Linux 5.10 实现细节：

- `sp1` 被 Linux 用来保存 `cpu_current_top_of_stack`，因为 Linux 不使用 ring 1；
- `sp2` 不被 ring 2 使用，A14 已核验 `entry_SYSCALL_64` 借它暂存 user RSP。

所以不能把 `sp0/sp1/sp2` 全部按硬件 ring stack 的教科书用途解释成 Linux 的实际用途。

TSS 是 per-CPU 对象：

```text
DECLARE_PER_CPU_PAGE_ALIGNED(struct tss_struct, cpu_tss_rw);
```

而不是每个 task 都维护一份独立 TSS。现代 x86-64 Linux 并不使用早期 x86 的 hardware task switching 来完成普通调度；这里的 TSS 主要服务于入口栈、IST 和 I/O bitmap 等硬件接口。

## 3. IST index 与实际数组下标

源码：

```text
arch/x86/include/asm/page_64_types.h
```

Linux 5.10 定义：

```text
IST_INDEX_DF  = 0
IST_INDEX_NMI = 1
IST_INDEX_DB  = 2
IST_INDEX_MCE = 3
IST_INDEX_VC  = 4
```

`struct x86_hw_tss` 的 C 数组是零基 `ist[7]`，而 x86-64 IDT gate 的 IST field 在架构上使用 1..7 表示 IST1..IST7，0 表示不使用 IST。因此阅读 IDT 构造宏时必须注意“C 数组下标”和“gate 中编码值”之间的转换，不能看到 `IST_INDEX_DF == 0` 就误认为 double fault 的 gate 不使用 IST。

## 4. IST 栈由谁写入 TSS

Linux 5.10 的 per-CPU exception handling 初始化在：

```text
arch/x86/kernel/cpu/common.c
```

`cpu_init_exception_handling()` 获取当前 CPU 的 `cpu_tss_rw`，调用 `tss_setup_ist()`，随后建立 TSS descriptor、执行 `load_TR_desc()`，最后装载当前 IDT。

`CONFIG_X86_64` 下 `tss_setup_ist()` 将各 exception stack top 写入：

```text
x86_tss.ist[IST_INDEX_DF]
x86_tss.ist[IST_INDEX_NMI]
x86_tss.ist[IST_INDEX_DB]
x86_tss.ist[IST_INDEX_MCE]
x86_tss.ist[IST_INDEX_VC]
```

其中 `#VC` 对应的栈只有在相关 SEV-ES 映射条件成立时才真正可用；A15 基础主线不展开 SEV-ES。

这一步说明 IST 不是“进入异常后 Linux 汇编再决定换栈”。IDT gate 已经告诉 CPU 使用哪个 IST entry，CPU 入口动作会先使用 TSS 中准备好的指针建立新的入口栈，然后才到达 Linux 的汇编 entry symbol。

## 5. IDT gate 如何携带 IST 选择

源码：

```text
arch/x86/include/asm/desc.h
arch/x86/kernel/idt.c
```

64-bit `pack_gate()` 会把传入的 `ist` 写入 `gate->bits.ist`。因此最终是否使用 IST 是 IDT descriptor 的属性，不是 C handler 的属性。

Linux 5.10 的 `idt.c` 还体现了初始化时序：早期/default IDT 在 TSS/IST 尚未完整建立时不能依赖 exception stacks；在 `cpu_init_exception_handling()` 已建立 TSS 后，相关 vectors 才安装为 IST variants。这一时序是理解“为什么同一个 vector 在早期启动和正常运行期 gate 属性可能不同”的关键。

## 6. Linux 5.10 哪些特殊异常使用 IST

在 x86-64 的正常 IST IDT 表中，核心映射为：

```text
#DB   -> IST_INDEX_DB
NMI   -> IST_INDEX_NMI
#DF   -> IST_INDEX_DF
#MC   -> IST_INDEX_MCE    (CONFIG_X86_MCE)
```

Linux 5.10 还包含 `IST_INDEX_VC`，服务于 `#VC`/SEV-ES 相关入口；它受相应配置和运行环境约束，不属于本课程的普通异常主线。

需要特别避免一个版本混淆：不同 Linux 版本中 `#BP`/debug stack 的处理曾调整。A15 第二部分应以 v5.10 当前 `idt.c` 的实际表项为准，不从旧文档或新内核反推。

## 7. 为什么这些入口需要特殊栈

### 7.1 `#DF`

Double fault 往往意味着前一个异常的正常处理条件已经破坏，其中就可能包括当前栈不可继续安全使用。若 `#DF` 仍依赖出问题的栈，处理器可能再次失败并走向 triple fault/reset。独立 IST stack 的核心价值是给 `#DF` 一个不依赖当前 `%rsp` 可用性的入口基础。

### 7.2 NMI

NMI 可以在普通内核代码甚至其他敏感入口阶段到来。它不能假定被打断现场正处于一个适合普通异常 prologue 使用的栈状态。使用独立 IST stack 能减少对旧 `%rsp` 状态的依赖。

### 7.3 `#DB`

Debug exception 可能出现在非常细的指令边界，并存在嵌套/调试状态相关问题。Linux 为它配置独立 debug IST，并在 entry code 中还有专门的 paranoid/debug 处理；因此不能把 A15 第一部分 `#DE/#GP` 的普通 `error_entry` 模型机械套到 `#DB`。

### 7.4 `#MC`

在 `CONFIG_X86_MCE` 下 machine check 使用自己的 IST。Machine check 可能发生在系统状态已经不可靠的场景，独立入口栈同样减少对当前内核栈可用性的假设。

IST 并不能保证系统一定可恢复；它只是提高入口本身仍能建立最小可靠执行现场的机会。

## 8. 与普通 CPL3 -> CPL0 stack switch 的关键区别

可以用两个问题判断：

```text
问题 A：gate 的 IST field 是否为 0？
问题 B：入口是否发生 privilege-level change？
```

普通异常从 user mode 进入 kernel mode且 gate 不使用 IST 时，CPU 按 privilege transition 取得 ring-0 stack 状态并保存旧 user SS:RSP。

若 gate 指定 IST，则 IST 是显式的 stack source；即使异常发生在 CPL0，CPU 也会从 TSS IST entry 取得新 RSP。也就是说：

```text
privilege stack switch != IST stack switch
```

这也是为什么只用“Ring 3 进入 Ring 0 所以换栈”无法解释 NMI/#DF 在内核态嵌套发生时的安全入口需求。

## 9. GDT、TSS descriptor 与 TR 的关系

Linux 5.10 使用 `set_tss_desc()` 在 per-CPU GDT 中建立 TSS descriptor，随后 `load_TR_desc()` 通过 `ltr` 让 CPU 的 task register 指向该 TSS descriptor。

因此硬件查找 IST 的链条可以抽象为：

```text
TR
 -> GDT 中的 TSS descriptor
 -> 当前 CPU 的 x86_hw_tss
 -> ist[n]
 -> exception stack top
```

这里 GDT 并不保存 exception stack 本身；GDT 中的 TSS descriptor 只是让 CPU 找到 TSS。真正的 stack pointer 存在 TSS 的 IST fields 中。

## 10. 配置条件与版本边界

本文件结论以 Linux v5.10 x86-64 为基线，至少需要注意：

- `CONFIG_X86_64`：本文的 64-bit TSS/IST 模型；32-bit double-fault 等路径不同；
- `CONFIG_X86_MCE`：决定 machine-check 相关 IDT/IST entry 是否建立；
- SEV-ES/`#VC`：Linux 5.10 已有 `IST_INDEX_VC`，但其映射和入口只在相应环境有意义；
- PTI 会影响普通 ring-0 entry stack 的实现细节，不能据此改变 IST 的架构含义；
- 不能把更新内核中 FRED 等入口机制反向套到 Linux 5.10。

## 11. 第二部分正文应采用的连续模型

后续教程应围绕下面这条主线展开：

```text
per-CPU exception stack storage
 -> tss_setup_ist()
 -> x86_hw_tss.ist[]
 -> TSS descriptor + ltr/TR
 -> IDT gate.IST
 -> CPU chooses IST RSP
 -> hardware exception frame on exception stack
 -> special/paranoid Linux entry
 -> handler
```

然后与第一部分普通异常对照：

```text
#DE/#GP: ordinary IDT entry model
#DB/NMI/#DF/#MC: IST-backed special entry model
```

重点不是背诵 vector 列表，而是理解“为什么 CPU 在进入第一条 Linux 指令之前就必须已经有一个可信的 `%rsp`”。

## 12. 本次核验结论与下一步

本次已经完成 A15 第二部分的源码事实核验：确认了 Linux 5.10 x86-64 hardware TSS 的 `sp0/sp1/sp2/ist[7]` 布局、per-CPU TSS、IST index、`tss_setup_ist()` 初始化、TSS descriptor/TR 链条以及特殊异常的 IST 使用边界。

下一最小单元应基于这些已核验事实编写 A15 第二部分正式教程。实验阶段优先在隔离 Linux 5.10 guest 中用匹配 `vmlinux` 检查 IDT descriptor 的 IST bits、当前 CPU TSS 的 IST pointers，并对普通 `#DE` 与可安全观测的 debug/NMI 路径比较 `%rsp` 所属 stack range；无法安全触发 `#DF/#MC` 时只做静态/调试器观测，不为了实验完整性制造破坏性故障。

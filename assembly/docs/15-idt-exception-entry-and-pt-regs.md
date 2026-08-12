# A15 第一部分：IDT 异常入口、error code 与 `pt_regs`

A14 讨论了 `SYSCALL`：CPU 执行 `syscall` 指令后并不会自动构造完整的 IRET frame，Linux 必须在 `entry_SYSCALL_64` 中主动保存用户现场。异常入口不同。除法错误、通用保护异常等事件通过 IDT gate 进入内核时，CPU 已经先保存了一部分返回现场；Linux 再补齐入口布局、保存通用寄存器，并把它整理成 C handler 可以使用的 `struct pt_regs`。

这一部分只讨论 Linux 5.10 x86-64 的普通异常入口，以 `#DE`（Divide Error）和 `#GP`（General Protection）为代表。缺页处理主体留给 A16；`#DB/#DF/#MC` 等涉及 IST 或 paranoid entry 的特殊路径放在 A15 后续部分。

## 1. 先把四个层次分开

阅读异常入口时，最容易出现的问题是把 CPU 自动动作、ABI、Linux 汇编入口和 C handler 混成一个过程。可以先建立四层模型：

```text
x86-64 architecture
    IDT gate
    privilege transition
    hardware return frame
    optional hardware error code

Linux idtentry stub
    normalize the slot before RIP

Linux error_entry
    save GPRs
    establish kernel GS/CR3 state when needed
    obtain a stable pt_regs frame

C exception handler
    struct pt_regs *regs
    optional error_code argument
```

只有第一层属于 CPU 架构自动完成的动作。`pushq $-1`、`PUSH_AND_CLEAR_REGS`、`swapgs` 和 `sync_regs` 都是 Linux 软件入口代码的一部分。

## 2. IDT gate 解决什么问题

异常发生时，CPU 不能像普通函数调用那样假定当前 RIP、栈和特权级仍适合继续执行。IDT（Interrupt Descriptor Table）为 vector 指定入口 gate。CPU 根据 vector 找到 gate，检查相关属性，并把控制流转移到内核入口。

对于从 CPL3 进入 CPL0 的普通异常，CPU 还必须保留将来返回用户态所需的控制状态。概念上可以把硬件 frame 看成：

```text
RIP
CS
RFLAGS
RSP
SS
```

这里列的是字段关系，而不是压栈时间顺序。x86 栈向低地址增长。后面从 `%rsp` 和 `struct pt_regs` 偏移分析内存时，必须始终区分“先后压入”与“最终低地址到高地址布局”。

如果异常本来发生在 CPL0，则不能直接套用上面的 CPL3 -> CPL0 栈切换模型。Linux 入口代码会根据保存的 CS 区分来源；内核态异常还有自己的 GS 状态和返回现场边界。本节先把 user-mode ordinary exception 的主线讲清楚。

## 3. CPU 自动保存的内容不是完整 `pt_regs`

CPU 为异常返回保存的是控制状态，而不是 Linux 所需的全部通用寄存器。因此下面的说法是错误的：

> 异常发生后，CPU 自动把 `struct pt_regs` 压到内核栈。

正确模型是：

```text
CPU hardware frame
        +
Linux entry software saves GPRs
        =
Linux can expose a pt_regs-shaped frame
```

这也是异常入口与 A14 syscall 入口的重要差别。两条路径最后都能得到 `pt_regs`，但形成它的前半段完全不同。

## 4. 为什么还要处理 error code

x86 异常并不统一。有些异常由 CPU 压入 error code，有些没有。

本节使用两个代表：

```text
#DE, vector 0
    no hardware error code

#GP, vector 13
    hardware pushes an error code
```

Linux 后面的寄存器保存代码希望看到稳定的入口布局，所以必须先把这两种情况规范化。Linux 5.10 的 `idtentry` 宏正是在这个位置处理差异。

## 5. `#DE`：Linux 补出 `orig_ax` 槽

Linux 5.10 在 `arch/x86/include/asm/idtentry.h` 中使用普通 `DECLARE_IDTENTRY` 声明 `exc_divide_error`。64 位汇编侧生成的入口核心可以抽象为：

```asm
asm_exc_divide_error:
        ASM_CLAC
        pushq $-1
        call error_entry
        ...
```

`pushq $-1` 不是 CPU 提供的 error code。它是 Linux 软件主动补出的槽，后面对应 `pt_regs.orig_ax`。

从用户态进入时，可以把 `error_entry` 之前的关系理解成：

```text
Linux synthetic slot: -1
CPU: RIP
CPU: CS
CPU: RFLAGS
CPU: RSP
CPU: SS
```

这里的 `-1` 表示这不是 syscall restart 所使用的 syscall number。`#DE` 的 C handler 只需要：

```c
void exc_divide_error(struct pt_regs *regs)
```

C 层某些处理代码使用数值 0 描述 `#DE` 的 trap error 语义，也不能据此反推“CPU 压入了 0”。硬件根本没有为 `#DE` 生成 error-code slot。

## 6. `#GP`：先借用同一槽保存硬件 error code

`#GP` 在 Linux 5.10 中使用 `DECLARE_IDTENTRY_ERRORCODE`。CPU 已经压入 error code，因此 Linux stub 不再执行 `pushq $-1`。

在进入共同寄存器保存路径前，布局可以抽象为：

```text
CPU error code
CPU: RIP
CPU: CS
CPU: RFLAGS
CPU: RSP
CPU: SS
```

这个 CPU error code 暂时占据了后续 `pt_regs.orig_ax` 所在的位置。保存完 GPR 后，`idtentry_body` 对 error-code exception 做两件事：

```asm
movq ORIG_RAX(%rsp), %rsi
movq $-1, ORIG_RAX(%rsp)
```

第一步把真实 error code 取出来，按照 System V AMD64 C ABI 放到第二参数 `%rsi`；第二步把 `regs->orig_ax` 规范化为 `-1`。

因此进入 C handler 时：

```c
void exc_general_protection(struct pt_regs *regs,
                            unsigned long error_code)
```

真正的 `#GP` error code 在 `error_code` 参数中，而不是 `regs->orig_ax` 中。

这是一个很重要的时间关系：

```text
entry stub 刚进入：
    orig_ax 位置 = CPU error code

C handler 即将调用：
    %rsi          = CPU error code
    regs->orig_ax = -1
```

如果只在 C handler 中观察 `pt_regs`，就已经看不到 error code 曾经占用 `orig_ax` 槽的中间状态。

## 7. `error_entry` 如何形成共同的寄存器现场

`#DE` 和 `#GP` 在进入 `error_entry` 前已经保证：硬件 RIP frame 前面存在一个 8-byte 槽。

```text
#DE: Linux synthetic -1
#GP: CPU error code
```

于是 `error_entry` 可以执行共同的：

```text
cld
PUSH_AND_CLEAR_REGS save_ret=1
```

保存通用寄存器。随后入口根据保存的 CS 判断异常来自用户态还是内核态。对于用户态来源，Linux 还需要建立正确的 GS/CR3 状态，并在需要时通过 `sync_regs` 把现场同步到稳定的 task stack。

这里不要把 `swapgs` 理解成“所有异常固定执行一次”。它取决于入口来源和入口类型。A15 后续讲 IST/paranoid entry 时，这个区别会更加重要。

## 8. 最终 `pt_regs` 的布局

Linux 5.10 x86-64 `struct pt_regs` 的 64 位布局尾部是：

```text
r15 ... di
orig_ax
ip
cs
flags
sp
ss
```

当 `%rsp == &regs->r15` 时，每个槽 8 byte：

```text
orig_ax = 120
ip      = 128
cs      = 136
flags   = 144
sp      = 152
ss      = 160
sizeof(struct pt_regs) = 168
```

因此从用户态普通异常进入后，可以把最终现场理解成两部分：

```text
Linux software-saved GPRs
        ↓
r15 ... di
orig_ax
        ↓
architecture return state
ip
cs
flags
sp
ss
```

`orig_ax` 位于两者交界处，并且被不同入口复用，所以不能脱离上下文解释：

```text
syscall entry:
    orig_ax = syscall number

ordinary #DE C handler:
    orig_ax = -1

ordinary #GP C handler:
    orig_ax = -1
    real hardware error code = second C argument
```

## 9. `#DE` 与 `#GP` 的完整对照

| 阶段 | `#DE` | `#GP` |
| --- | --- | --- |
| CPU 提供 error code | 否 | 是 |
| Linux `has_error_code` | 0 | 1 |
| stub `pushq $-1` | 是 | 否 |
| `error_entry` 前统一槽 | `-1` | hardware error code |
| GPR 保存 | `PUSH_AND_CLEAR_REGS` | `PUSH_AND_CLEAR_REGS` |
| C 参数 1 | `%rdi = regs` | `%rdi = regs` |
| C 参数 2 | 无 | `%rsi = error_code` |
| handler 中 `orig_ax` | `-1` | `-1` |

这张表描述普通异常的统一入口思想，不应机械推广到所有 vector。`#PF` 的处理主体属于 A16；`#DB/#DF/#MC` 等还涉及特殊入口和 IST。

## 10. 从异常发生到 C handler 的连续模型

现在可以把第一部分压缩成一条执行线：

```text
user instruction
    ↓ exception
IDT gate
    ↓
CPU switches privilege/stack as required
CPU saves return state
CPU optionally pushes hardware error code
    ↓
Linux idtentry stub
    #DE: push synthetic -1
    #GP: keep hardware error-code slot
    ↓
error_entry
    save GPRs
    classify user/kernel origin
    establish required GS/CR3 state
    obtain stable pt_regs
    ↓
idtentry_body
    #GP: move error code to %rsi
    normalize orig_ax to -1
    ↓
C exception handler
```

返回路径最终需要恢复这些状态并通过 IRET 语义返回，但本节的重点是入口现场如何形成。A14 已经介绍了 IRET 所需的基本返回 frame，A15 后续只在异常入口需要的范围内复用这一知识。

## 11. 常见误区

第一，**“所有异常都有 error code”**是错误的。`#DE` 没有，`#GP` 有。

第二，**“没有 error code 时 CPU 压 0”**也是错误的。Linux 5.10 的普通 `#DE` 入口是软件 `pushq $-1`，用途是形成统一的 `orig_ax` 槽。

第三，**“`regs->orig_ax` 就是异常 error code”**不成立。对于 `#GP`，error code 在调用 C handler 前已经移入 `%rsi`，`orig_ax` 被重写为 `-1`。

第四，**“CPU 自动保存所有寄存器”**不成立。GPR 是 Linux 的 `PUSH_AND_CLEAR_REGS` 保存的。

第五，**“异常一定执行 `swapgs`”**不成立。必须根据 user/kernel 来源和具体入口类型判断。

第六，**“用户态异常模型可以原样解释内核态异常”**不成立。CPL 是否变化会影响硬件栈切换和返回 frame 的解释。

## 12. Linux 5.10 源码阅读入口

本节对应的源码事实已经在以下文件中单独核验：

- [`../source-paths/15-exception-interrupt-entry-basics-linux-5.10.md`](../source-paths/15-exception-interrupt-entry-basics-linux-5.10.md)
- [`../source-paths/15-de-gp-error-code-pt-regs-linux-5.10.md`](../source-paths/15-de-gp-error-code-pt-regs-linux-5.10.md)

建议按下面顺序阅读 Linux v5.10 源码：

```text
arch/x86/include/asm/idtentry.h
    ↓ generated asm entry declarations
arch/x86/entry/entry_64.S
    ↓ idtentry / error_entry
arch/x86/entry/calling.h
    ↓ PUSH_AND_CLEAR_REGS
arch/x86/include/asm/ptrace.h
    ↓ struct pt_regs
arch/x86/kernel/traps.c
    ↓ exc_divide_error / exc_general_protection
```

掌握这一部分后，下一步应通过实验观察 `#DE/#GP` 的入口现场，再继续学习 TSS、IST 和特殊异常入口。
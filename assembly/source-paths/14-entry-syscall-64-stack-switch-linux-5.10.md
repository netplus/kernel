# A14 Linux 5.10 源码核验：`entry_SYSCALL_64` 的入口现场与内核栈切换

本文件只核验 A14 的第一个最小单元：64 位用户态执行 `syscall` 后，Linux 5.10 如何接收硬件留下的寄存器状态、保存用户 `%rsp`、切换到当前任务的内核栈，并开始构造 `struct pt_regs`。

这里暂不展开 `do_syscall_64()` 的分派逻辑，也不展开返回用户态时的 `SYSRETQ/IRETQ` 选择。它们属于 A14 后续单元。

## 1. 为什么入口代码不能直接像普通 C 函数一样执行

普通 System V AMD64 函数调用发生在已经建立好的同一执行环境中：调用者用 `call` 压入返回地址，`%rsp` 已经指向调用栈，callee 可以按照 ABI 使用这条栈。

64 位 `syscall` 不是普通 `call`。x86-64 硬件进入 syscall target 时：

- 用户返回 RIP 已放入 `%rcx`；
- 用户 RFLAGS 已放入 `%r11`，其中 RF 在保存前由硬件清除；
- 新的 RIP、CS、SS 等来自预先设置的 syscall MSR；
- RFLAGS 会按 MSR 中的 mask 清除相应位；
- **硬件不会自动把返回现场压到内核栈**；
- **硬件不会自动修改 `%rsp`**。

因此进入 `entry_SYSCALL_64` 的最初几条指令仍面对用户 `%rsp`。Linux 必须先在不依赖用户栈的条件下保存这个值，再取得当前 CPU/任务对应的内核栈顶，之后才能安全地用 `pushq` 构造内核入口现场。

这也是 syscall 入口与后面 A15 要学习的 IDT 异常/中断入口的重要差别之一：不能把异常入口的硬件压栈模型套到 `SYSCALL` 上。

## 2. Linux 5.10 源码基线

本节按 upstream Linux **v5.10** 核验，主要文件为：

```text
arch/x86/entry/entry_64.S
arch/x86/entry/calling.h
arch/x86/include/asm/ptrace.h
```

`arch/x86/entry/entry_64.S` 中 `entry_SYSCALL_64` 的入口主线为：

```text
entry_SYSCALL_64
  -> swapgs
  -> 保存用户 %rsp 到 cpu_tss_rw + TSS_sp2
  -> SWITCH_TO_KERNEL_CR3 scratch_reg=%rsp
  -> %rsp = cpu_current_top_of_stack
  -> 压入 ss/sp/flags/cs/ip/orig_ax
  -> PUSH_AND_CLEAR_REGS rax=$-ENOSYS
  -> %rdi = %rax
  -> %rsi = %rsp
  -> call do_syscall_64
```

本文件只详细核验到 `PUSH_AND_CLEAR_REGS` 完成、`%rsp` 指向完整 `struct pt_regs` 为止。

## 3. `syscall` 刚进入内核时有什么

Linux 5.10 在 `entry_64.S` 的注释中明确记录 64 位 syscall 入口寄存器约定：

```text
%rax : syscall number
%rcx : user return RIP
%r11 : saved user RFLAGS
%rdi : arg0
%rsi : arg1
%rdx : arg2
%r10 : arg3
%r8  : arg4
%r9  : arg5
%rsp : 仍然是 user RSP
```

这里必须区分两类规则：

1. `%rcx/%r11` 的特殊用途以及 `SYSCALL` 不保存栈，是 x86-64 `SYSCALL` 指令的架构语义；
2. `%rax` syscall number 和 `%rdi/%rsi/%rdx/%r10/%r8/%r9` 参数分配，是 Linux x86-64 syscall ABI。

A13 已从用户态一侧验证第二组约定；A14 从内核入口一侧继续追踪这些值如何变成 `pt_regs`。

## 4. 第一步：`swapgs` 让 `%gs` 可以访问内核 per-CPU 数据

Linux 5.10 的入口首先执行：

```asm
swapgs
```

紧接着的代码要通过 `PER_CPU_VAR(...)` 访问 per-CPU 数据，所以此时必须建立内核所期望的 GS base。

对于这条明确“Only called from user space”的 64 位 syscall 入口，Linux 直接执行 `swapgs`，而不是像某些异常入口那样先判断进入前 CPL。这里不要把 `swapgs` 简化成“切换特权级”的指令：CPU 已经通过 `SYSCALL` 完成了控制转移；`swapgs` 的作用是交换 GS base 相关 MSR 状态，使内核能按自己的 GS base 使用 per-CPU 地址。

## 5. 第二步：先保存 user RSP

入口随后执行：

```asm
movq %rsp, PER_CPU_VAR(cpu_tss_rw + TSS_sp2)
```

源码注释明确写着：

```text
tss.sp2 is scratch space.
```

因此这里不能把 `TSS_sp2` 描述成“硬件为 syscall 自动选择的内核栈”。在这条路径上，它被 Linux 当作临时槽保存 user RSP。

这一时刻可以建立一个重要状态快照：

```text
%rsp                         = user RSP
cpu_tss_rw.TSS_sp2           = user RSP
尚未在 kernel stack 上 push pt_regs
```

为什么需要先保存？因为下一步会把 `%rsp` 当 scratch register 使用，然后再把 `%rsp` 改成内核栈顶。如果不先保存 user RSP，后面构造 `pt_regs->sp` 时就失去了原始值。

## 6. 第三步：必要时切换到 kernel CR3

接下来是：

```asm
SWITCH_TO_KERNEL_CR3 scratch_reg=%rsp
```

这个宏定义在 `arch/x86/entry/calling.h`。

它受 `CONFIG_PAGE_TABLE_ISOLATION` 影响：

- `CONFIG_PAGE_TABLE_ISOLATION=y` 时，宏包含按 PTI/PCID 条件调整并写入 CR3 的代码；其中还使用 `ALTERNATIVE` 根据 CPU feature 选择实际指令序列；
- `CONFIG_PAGE_TABLE_ISOLATION=n` 时，`SWITCH_TO_KERNEL_CR3` 在该头文件中定义为空宏。

所以不能无条件描述成“每次 syscall 都写一次 CR3”。更准确的说法是：**入口在这里执行 Linux 5.10 的 kernel-CR3 切换宏；是否产生实际 CR3 切换指令取决于内核配置和运行 CPU feature。**

这个宏允许使用 `%rsp` 作为 scratch，是因为 user RSP 已经保存在 per-CPU `TSS_sp2` 中，而且此时还没有开始依赖 `%rsp` 指向的内存作为内核栈。

## 7. 第四步：真正把 `%rsp` 切到当前内核栈顶

随后执行：

```asm
movq PER_CPU_VAR(cpu_current_top_of_stack), %rsp
```

到这里才完成本节所说的“用户栈到内核栈切换”：

```text
进入 syscall 后：
    %rsp = user RSP

保存后：
    cpu_tss_rw.TSS_sp2 = user RSP

切换后：
    %rsp = cpu_current_top_of_stack
```

这里同样要避免一个常见误解：这不是 `SYSCALL` 指令替 Linux 自动完成的栈切换，而是 `entry_SYSCALL_64` 软件显式完成的。

`cpu_current_top_of_stack` 是 per-CPU 数据；在这条入口路径上，它给出当前执行上下文所使用的内核栈顶。A14 后续若继续追踪它如何随 task switch 更新，应单独核验，不在本最小单元中凭记忆展开。

## 8. 第五步：手工构造 iret-compatible frame

有了安全的 kernel `%rsp` 后，入口开始：

```asm
pushq $__USER_DS
pushq PER_CPU_VAR(cpu_tss_rw + TSS_sp2)
pushq %r11
pushq $__USER_CS
pushq %rcx
pushq %rax
```

它们依次对应：

```text
pt_regs->ss
pt_regs->sp       <- 刚才保存在 TSS_sp2 的 user RSP
pt_regs->flags    <- syscall 保存到 %r11 的 user RFLAGS
pt_regs->cs
pt_regs->ip       <- syscall 保存到 %rcx 的 user return RIP
pt_regs->orig_ax  <- syscall number
```

注意“iret-compatible frame”是 Linux 软件构造出来的布局，不是说 `SYSCALL` 已经替它压好了这些字段。

`orig_ax` 保存原始 syscall number，而普通 `ax` 字段随后会由 `PUSH_AND_CLEAR_REGS` 单独建立。这两个字段承担不同角色，不能混为一个 `%rax` 快照。

## 9. `PUSH_AND_CLEAR_REGS` 如何补齐 `struct pt_regs`

`arch/x86/entry/calling.h` 定义了 `PUSH_AND_CLEAR_REGS`。在 syscall 路径中调用为：

```asm
PUSH_AND_CLEAR_REGS rax=$-ENOSYS
```

宏继续按与 `struct pt_regs` 匹配的顺序保存：

```text
di, si, dx, cx, ax, r8, r9, r10, r11,
bx, bp, r12, r13, r14, r15
```

其中这里的 `ax` **不是入口时的 syscall number**，而是显式压入 `$-ENOSYS`。入口 syscall number 已经保存在 `orig_ax`。

宏在保存之后还会清零若干工作寄存器，用于降低推测执行利用残留寄存器值的风险。因此“`pt_regs` 已保存某个寄存器”与“CPU 当前寄存器仍保留用户值”是两件不同的事。

宏完成后，当前 `%rsp` 指向完整的 `struct pt_regs` 起始位置，也就是 `r15` 字段。

## 10. `struct pt_regs` 的布局必须与汇编完全一致

Linux 5.10 的 `arch/x86/include/asm/ptrace.h` 在 x86-64 下定义：

```text
r15 r14 r13 r12 bp bx
r11 r10 r9 r8 ax cx dx si di
orig_ax
ip cs flags sp ss
```

`arch/x86/entry/calling.h` 同时给出汇编偏移：

```text
R15      =  0 * 8
...
RDI      = 14 * 8
ORIG_RAX = 15 * 8
RIP      = 16 * 8
CS       = 17 * 8
EFLAGS   = 18 * 8
RSP      = 19 * 8
SS       = 20 * 8
SIZEOF_PTREGS = 21 * 8 = 168 bytes
```

这正是入口 push 顺序最终在“低地址到高地址”方向形成的内存布局。

需要特别注意 push 的时间顺序与结构体的地址顺序相反：栈向低地址增长，所以最后 push 的 `%r15` 位于最低地址，恰好成为 `struct pt_regs` 的第一个字段。

完成后的示意图为：

```text
低地址

%rsp -> +0x00  r15
        +0x08  r14
        +0x10  r13
        +0x18  r12
        +0x20  bp
        +0x28  bx
        +0x30  r11
        +0x38  r10
        +0x40  r9
        +0x48  r8
        +0x50  ax       = -ENOSYS（入口初始化值）
        +0x58  cx
        +0x60  dx
        +0x68  si
        +0x70  di
        +0x78  orig_ax  = syscall number
        +0x80  ip       = user return RIP
        +0x88  cs       = __USER_CS
        +0x90  flags    = saved user RFLAGS
        +0x98  sp       = user RSP
        +0xa0  ss       = __USER_DS

高地址
```

总大小为 21 个 8-byte 字段，即 168 bytes。

## 11. 为什么先令 `pt_regs->ax = -ENOSYS`

入口不是把用户 `%rax` 同时复制到 `orig_ax` 和 `ax`。它先：

```asm
pushq %rax
```

建立 `orig_ax`，然后调用：

```asm
PUSH_AND_CLEAR_REGS rax=$-ENOSYS
```

所以完整现场建立后：

```text
regs->orig_ax = syscall number
regs->ax      = -ENOSYS
```

随后 C 层 syscall 分派会把真正的系统调用返回值写回返回寄存器现场。`-ENOSYS` 因而是入口阶段为返回槽准备的初始值，而不是用户发起 syscall 时 `%rax` 的第二份副本。

本文件暂不继续推演 `do_syscall_64()` 如何覆盖该字段；下一单元应直接从 Linux 5.10 C 源码核验。

## 12. 进入 `do_syscall_64` 前的 C ABI 适配

汇编在完整 `pt_regs` 建立后执行：

```asm
movq %rax, %rdi
movq %rsp, %rsi
call do_syscall_64
```

这里容易误读，因为 `PUSH_AND_CLEAR_REGS rax=$-ENOSYS` 的参数只是指定“压到 `pt_regs->ax` 的值”；宏本身没有把当前 `%rax` 改成 `-ENOSYS`。因此当前 `%rax` 仍可用于把 syscall number 传给 C 层。

于是普通 x86-64 C ABI 下：

```text
%rdi = syscall number
%rsi = struct pt_regs *
```

而 `%rsp` 已经是内核栈，并指向保存好的 `pt_regs`。

这标志着入口汇编完成了第一次关键交接：从“硬件 `SYSCALL` 留下的裸寄存器状态”转换成“C 代码可以消费的 syscall number + `struct pt_regs *`”。

## 13. 配置条件与边界

本单元确认的主要条件如下：

- 讨论的是 `CONFIG_X86_64` 下的 64 位 syscall 入口；
- `entry_SYSCALL_64` 注释明确限定为从 user space 调用；
- `SWITCH_TO_KERNEL_CR3` 的实际行为受 `CONFIG_PAGE_TABLE_ISOLATION` 以及 PTI/PCID CPU feature 影响；
- `CONFIG_PARAVIRT_XXL` 会影响部分用户态返回相关实现，但不改变本文件核验的入口 push 主线；
- 本单元没有把 compat syscall、32 位 `int 0x80` 或异常/中断入口混入这条路径。

## 14. 本单元的精确状态转换

可以把 Linux 5.10 这一段入口压缩成四个状态：

```text
S0: SYSCALL 刚完成硬件控制转移
    rcx=user RIP, r11=user RFLAGS, rsp=user RSP

S1: swapgs + 保存 user RSP
    per-CPU GS 可用于内核访问
    TSS.sp2=user RSP

S2: 必要的 kernel CR3 处理 + kernel stack switch
    rsp=cpu_current_top_of_stack

S3: 软件构造完整 pt_regs
    rsp=&regs->r15
    regs->orig_ax=syscall number
    regs->ax=-ENOSYS
    regs->ip/user flags/user sp 等均已有稳定内存副本
```

下一步才适合进入 `do_syscall_64()`：此时 C 层不需要再从“裸 `%rcx/%r11/%rsp`”重建用户现场，而是直接通过 `struct pt_regs` 读取和修改它。

## 15. 本次核验结论

本单元确认了三个容易混淆的事实：

1. x86-64 `SYSCALL` **不自动切换 `%rsp`，也不自动在内核栈压入返回 frame**；Linux 5.10 在 `entry_SYSCALL_64` 中显式保存 user RSP 并切换内核栈。
2. `cpu_tss_rw.TSS_sp2` 在这条路径上被明确作为保存 user RSP 的 scratch slot；真正的 kernel `%rsp` 来自 `cpu_current_top_of_stack`。
3. `pt_regs` 是 Linux 入口汇编按 C 结构体布局手工构造的稳定现场；`orig_ax` 保存 syscall number，而 `ax` 先初始化为 `-ENOSYS`。

后续 A14 应沿这个已经建立好的边界继续：先核验 `do_syscall_64()` 如何从 syscall number 和 `pt_regs` 完成分派及 exit work，再单独分析 fast `SYSRETQ` 与 slow `IRETQ` 返回条件。
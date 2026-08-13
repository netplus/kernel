# A15 实验：TSS、IST 与特殊异常栈

本实验验证 A15 第二部分的核心结论：Linux 5.10 x86-64 为若干特殊异常准备 per-CPU IST 栈，IDT gate 通过 IST field 选择 TSS 中的对应栈指针；CPU 在执行第一条 Linux entry 指令之前完成 `%rsp` 切换。

实验不主动制造 `#DF` 或 `#MC`。这两类故障可能导致系统不可恢复，基础课程只做静态 descriptor/TSS 核验。动态对照优先选择普通 `#DE` 与可控的 `#DB` single-step；NMI 仅在隔离 guest 中通过安全的虚拟化/调试手段观察。

## 1. 要验证的问题

实验分三层：

1. IDT descriptor：确认普通 `#DE` 的 gate 不使用 IST，而 `#DB`、NMI、`#DF`，以及启用 `CONFIG_X86_MCE` 时的 `#MC` gate 使用 Linux 5.10 配置的 IST。
2. TSS：确认当前 CPU 的 `cpu_tss_rw.x86_tss.ist[]` 中保存对应 exception-stack top，并区分 C 数组下标与 IDT gate 的 1..7 IST 编码。
3. 动态入口：比较普通 `#DE` 与 IST-backed `#DB` 到达第一段 Linux entry code 时 `%rsp` 所属地址范围，验证换栈发生在 Linux entry 指令执行之前。

## 2. 环境要求

动态部分必须在隔离 Linux 5.10 x86-64 guest 中执行，并准备与运行内核完全匹配、带调试符号的 `vmlinux`。推荐 QEMU gdbstub + GDB。

需要能够读取/定位：

```text
arch/x86/kernel/idt.c
arch/x86/kernel/cpu/common.c
arch/x86/include/asm/processor.h
arch/x86/include/asm/page_64_types.h
arch/x86/entry/entry_64.S
```

不要把宿主机当前内核的地址、结构体偏移或较新内核的 entry symbol 直接套到 Linux 5.10 guest。

## 3. 静态核验：先从源码确认 vector 与 IST index

在当前 Linux 5.10 源码树中检查 `idt.c` 的正常运行期 IST IDT 表，并确认：

```text
#DB   -> IST_INDEX_DB
NMI   -> IST_INDEX_NMI
#DF   -> IST_INDEX_DF
#MC   -> IST_INDEX_MCE   (CONFIG_X86_MCE)
```

再检查 `page_64_types.h` 中 Linux 使用的零基 C 数组下标。这里必须保留两个数值空间：

```text
C:    ist[0] ... ist[6]
IDT:  0 = no IST, 1 = IST1, ... 7 = IST7
```

因此不能用 `IST_INDEX_DF == 0` 推导 `#DF` gate 的 IST field 为 0。

## 4. GDB：检查当前 CPU TSS 的 IST pointers

在 guest 停机后，先让 GDB 使用当前 `vmlinux` 的类型信息，不手算 `struct x86_hw_tss` 偏移。根据当前 CPU 的 per-CPU base 定位 `cpu_tss_rw`；具体表达式受调试环境和 per-CPU 符号解析方式影响，应以当前 `vmlinux` 为准。

得到当前 CPU 的 `struct tss_struct` 后检查：

```gdb
p/x <current_cpu_tss>.x86_tss.ist[IST_INDEX_DF]
p/x <current_cpu_tss>.x86_tss.ist[IST_INDEX_NMI]
p/x <current_cpu_tss>.x86_tss.ist[IST_INDEX_DB]
```

若 guest 配置启用 machine check，再检查 MCE slot。

验收点不是要求固定地址，而是确认这些值是当前 CPU 已初始化的 exception-stack top，并能与该 CPU 的 exception-stack 地址范围对应。

## 5. 检查 IDT gate 的 IST field

优先使用 `vmlinux` 类型信息和 Linux 5.10 descriptor 定义解析当前 IDT，而不是把 16-byte gate 手工解释成未经核验的位域。

至少记录以下 vectors：

```text
#DE  vector 0
#DB  vector 1
NMI  vector 2
#DF  vector 8
#MC  vector 18（若 CONFIG_X86_MCE）
```

预期关系：普通 `#DE` 不依赖 IST；`#DB`、NMI、`#DF` 的正常运行期 gate 使用各自 IST。这里观察的是 descriptor 属性，不是 C handler 的属性。

## 6. 动态对照 A：普通 `#DE`

复用第一部分 `labs/15-de-gp-exception-entry/` 的除零触发程序。在匹配 `vmlinux` 中从实际反汇编定位 `#DE` entry 的第一段可安全断点位置。

命中时记录：

```text
RIP
RSP
CS
当前 RSP 所属 stack range
硬件返回 frame 中保存的 user RSP
```

用户态 `#DE` 从 CPL3 进入 CPL0，gate 本身不使用 IST。这里得到的是 privilege transition 所需的 ring-0 entry stack 路径，不能称为 `#DE IST stack`。

## 7. 动态对照 B：可控 `#DB` single-step

使用 GDB 或一个最小用户程序设置 Trap Flag，使用户态执行一条无副作用指令后产生 `#DB`。不要使用会改变实验控制流的复杂 breakpoint 组合。

在 Linux 5.10 实际 `#DB` entry 的第一段可安全位置断下，记录与 `#DE` 相同的项目，尤其是 `%rsp`。

关键验收条件：`#DB` gate 指定 IST 时，CPU 在到达第一条 Linux entry 指令前已经从 TSS 取得 debug IST stack pointer，并在该栈上建立硬件返回 frame。因此此时 `%rsp` 应位于当前 CPU 的 debug exception-stack 范围，而不是普通 task/kernel entry stack。

还要记录 frame 中保存的旧 `%rsp`。IST 切换改变当前 `%rsp`，但不会使被打断现场的旧 stack pointer 消失。

## 8. NMI、`#DF`、`#MC` 的边界

NMI 可以在隔离 guest 中通过 QEMU monitor、调试器或其他已确认不会破坏 guest 的方法注入，再观察 NMI IST；具体注入命令取决于当前虚拟化环境，不在课程中写死。

不要为了得到动态结果主动制造：

```text
double fault
machine check
triple fault
```

对 `#DF/#MC`，完成 IDT descriptor、TSS pointer、入口反汇编和 stack-range 静态核验即可达到本实验基础验收标准。破坏性 fault injection 属于更专门的可靠性实验，不是 A15 基础课程要求。

## 9. 需要记录的结果

建议保存如下表格：

| Vector | IDT IST field | TSS slot | 入口 RSP 所属栈 | 动态执行 |
| --- | ---: | --- | --- | --- |
| `#DE` | 0 | none | privilege-transition/kernel entry path | yes |
| `#DB` | 按 v5.10 descriptor 实测 | debug IST | debug exception stack | yes |
| NMI | 按 v5.10 descriptor 实测 | NMI IST | NMI exception stack | optional |
| `#DF` | 按 v5.10 descriptor 实测 | DF IST | DF exception stack | no destructive trigger |
| `#MC` | 按配置/descriptor 实测 | MCE IST | MCE exception stack | no destructive trigger |

不要在没有读取当前 guest descriptor/TSS 的情况下把具体地址填入表格。

## 10. 常见误判

第一，把“从用户态进入内核会换栈”当成 IST。`#DE` 的 CPL3 -> CPL0 stack switch 与 `#DB` 的 IST 选择是不同硬件机制。

第二，在 Linux entry 已经执行较多指令后才观察 `%rsp`，然后反推 CPU 最初选择的栈。入口代码可能继续调整栈；应尽量在实际反汇编确认的早期安全位置观察，并结合 hardware frame 和 stack range 交叉判断。

第三，把 TSS 中的 `ist[n]` 当作当前 `%rsp`。TSS 保存的是 CPU 入口时使用的 stack top；CPU 建立 hardware frame 后 `%rsp` 已向低地址移动。

第四，把宿主机或其他内核版本的 descriptor 布局、symbol 名称和 IST 使用策略当成 Linux 5.10 事实。

## 11. 当前执行状态

课程维护环境当前没有可停机调试的匹配 Linux 5.10 guest、对应 `vmlinux` 和 kernel-GDB 会话，因此本次完成的是可执行实验设计与源码一致性检查，没有伪造 IDT/TSS 地址或动态 `%rsp` 结果。

获得实验环境后，应先完成 `#DE/#DB` 动态对照，再视虚拟化环境决定是否补充安全 NMI 观测；`#DF/#MC` 不作为动态触发的完成条件。

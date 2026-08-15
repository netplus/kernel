# Linux x86-64 汇编与内核入口

本目录学习 x86-64 汇编，并为阅读 Linux kernel 5.10 的启动、系统调用、异常、中断和上下文切换代码打下基础。

课程主要回答：CPU 如何执行指令，寄存器、内存、栈和标志位如何变化，C 代码如何转换成机器指令，函数调用和 ABI 如何组织现场，以及用户态/内核态和早期启动入口如何交接 CPU 状态。

## 课程大纲

### A00：实验环境与基本工具

GCC、GNU assembler、linker、ELF、`objdump`、`readelf`、`nm`、GDB，AT&T/Intel 语法，以及 `-O0/-Og/-O2` 的基本差异。

### A01：CPU 执行模型、寄存器宽度与 `mov`

`RIP`、通用寄存器、`RSP`、`RFLAGS`、8/16/32/64 位写入、`EAX` 高位清零、立即数/寄存器/内存操作数和扩展规则。

教程：[`docs/01-cpu-execution-model-and-register-width.md`](docs/01-cpu-execution-model-and-register-width.md)；实验：[`labs/01-register-width/`](labs/01-register-width/)。

### A02：地址、解引用、数组、结构体与 `lea`

地址与数据、`disp(base,index,scale)`、数组和结构体、对齐/填充、RIP-relative，以及 `lea` 的地址计算和整数运算用途。

教程：[`docs/02-addressing-dereference-and-lea.md`](docs/02-addressing-dereference-and-lea.md)；实验：[`labs/02-addressing/`](labs/02-addressing/)。

### A03：`RFLAGS`、比较、条件跳转与基本块

`CF/ZF/SF/OF`、`cmp/test`、signed/unsigned 比较、`jcc/setcc/cmovcc`、基本块和循环回边。

教程：[`docs/03-rflags-comparison-and-control-flow.md`](docs/03-rflags-comparison-and-control-flow.md)；实验：[`labs/03-flags-and-branches/`](labs/03-flags-and-branches/)。

### A04：整数算术、位运算、移位、乘法与除法

`add/sub/neg/inc/dec`、位运算、`shl/shr/sar`、`mul/imul/div/idiv`、`RDX:RAX` 和常数运算优化。

教程：[`docs/04-integer-arithmetic-shifts-multiply-divide.md`](docs/04-integer-arithmetic-shifts-multiply-divide.md)；实验：[`labs/04-arithmetic-and-shifts/`](labs/04-arithmetic-and-shifts/)。

### A05：循环、状态机与 `switch`

`while/do-while/for`、数组/指针遍历、状态转换、`break/continue`、稀疏比较结构和稠密跳转表。

教程：[`docs/05-loops-state-machines-and-switch.md`](docs/05-loops-state-machines-and-switch.md)；实验：[`labs/05-loops-state-machines-switch/`](labs/05-loops-state-machines-switch/)。

### A06：栈、`push/pop` 与初始用户栈

第一部分建立向低地址增长的栈、`RSP` 和 `push/pop`；第二部分解析 `_start` 时的 `argc/argv/envp/auxv`、字符串区、`AT_NULL` 与初始栈对齐。

教程：[`docs/06-stack-model-and-push-pop.md`](docs/06-stack-model-and-push-pop.md)、[`docs/06-initial-user-stack.md`](docs/06-initial-user-stack.md)。

实验：[`labs/06-stack-push-pop/`](labs/06-stack-push-pop/)、[`labs/06-initial-user-stack/`](labs/06-initial-user-stack/)。

### A07：`call`、`ret` 与返回地址

覆盖 direct/indirect call、near `ret`、函数指针、递归、多层返回地址和返回地址损坏。

教程：[`docs/07-call-ret-and-return-address.md`](docs/07-call-ret-and-return-address.md)、[`docs/07-indirect-call-and-function-pointers.md`](docs/07-indirect-call-and-function-pointers.md)、[`docs/07-recursion-and-multiple-return-addresses.md`](docs/07-recursion-and-multiple-return-addresses.md)、[`docs/07-damaged-return-address.md`](docs/07-damaged-return-address.md)。

实验：[`labs/07-call-ret/`](labs/07-call-ret/)、[`labs/07-indirect-call/`](labs/07-indirect-call/)、[`labs/07-recursion/`](labs/07-recursion/)、[`labs/07-damaged-return-address/`](labs/07-damaged-return-address/)。A07 已完成。

### A08：System V AMD64 ABI

覆盖 INTEGER 参数/返回值、caller/callee-saved、栈上传参、16-byte alignment、128-byte Red Zone、聚合类型 INTEGER/MEMORY 分类和混合 INTEGER/SSE 聚合。

教程入口：[`docs/08-integer-arguments-and-return-values.md`](docs/08-integer-arguments-and-return-values.md)、[`docs/08-caller-saved-and-callee-saved.md`](docs/08-caller-saved-and-callee-saved.md)、[`docs/08-stack-passed-arguments.md`](docs/08-stack-passed-arguments.md)、[`docs/08-stack-alignment.md`](docs/08-stack-alignment.md)、[`docs/08-red-zone.md`](docs/08-red-zone.md)、[`docs/08-aggregate-arguments-and-returns.md`](docs/08-aggregate-arguments-and-returns.md)、[`docs/08-mixed-integer-sse-aggregate.md`](docs/08-mixed-integer-sse-aggregate.md)。A08 已完成。

### A09：函数栈帧、局部变量与栈展开

覆盖 `%rbp` frame、局部变量和 spill/reload、leaf/frame-pointer omission、DWARF CFI/CFA，以及 CFI 正确/缺失/错误时的展开边界。

教程入口：[`docs/09-rbp-frame-basics.md`](docs/09-rbp-frame-basics.md)、[`docs/09-locals-spills-and-stack-slots.md`](docs/09-locals-spills-and-stack-slots.md)、[`docs/09-leaf-functions-and-frame-pointer-omission.md`](docs/09-leaf-functions-and-frame-pointer-omission.md)、[`docs/09-dwarf-cfi-and-cfa.md`](docs/09-dwarf-cfi-and-cfa.md)、[`docs/09-unwind-boundaries.md`](docs/09-unwind-boundaries.md)。A09 已完成。

### A10：编译器优化后的汇编

覆盖内联、tail/sibling call、公共子表达式、寄存器分配/live range、spill/reload 和优化代码调试限制。

教程入口：[`docs/10-inlining-and-disappearing-call-boundaries.md`](docs/10-inlining-and-disappearing-call-boundaries.md)、[`docs/10-tail-calls-and-sibling-call-optimization.md`](docs/10-tail-calls-and-sibling-call-optimization.md)、[`docs/10-common-subexpressions-and-redundant-computation.md`](docs/10-common-subexpressions-and-redundant-computation.md)、[`docs/10-register-allocation-and-live-ranges.md`](docs/10-register-allocation-and-live-ranges.md)、[`docs/10-optimized-code-debugging-limits.md`](docs/10-optimized-code-debugging-limits.md)。A10 已完成。

### A11：ELF、符号与重定位

覆盖 section/segment、symbol table、strong/weak/undefined symbol resolution、PC-relative relocation 和静态链接主线。

教程入口：[`docs/11-elf-sections-and-segments.md`](docs/11-elf-sections-and-segments.md)、[`docs/11-elf-symbol-table.md`](docs/11-elf-symbol-table.md)、[`docs/11-strong-weak-and-undefined-symbols.md`](docs/11-strong-weak-and-undefined-symbols.md)、[`docs/11-pc-relative-relocations.md`](docs/11-pc-relative-relocations.md)、[`docs/11-static-linking-process.md`](docs/11-static-linking-process.md)。A11 已完成。

### A12：位置无关代码与动态链接基础

覆盖 PIC/PIE、RIP-relative、GOT/GOTPCREL、PLT/JUMP_SLOT、lazy binding 与 eager binding。

教程入口：[`docs/12-pic-pie-and-rip-relative.md`](docs/12-pic-pie-and-rip-relative.md)、[`docs/12-got-and-dynamic-data-relocation.md`](docs/12-got-and-dynamic-data-relocation.md)、[`docs/12-plt-jump-slot-and-binding.md`](docs/12-plt-jump-slot-and-binding.md)。A12 已完成。

### A13：系统调用 ABI

建立 System V AMD64 普通函数 ABI、x86-64 `syscall` 指令语义和 Linux raw syscall ABI 的边界，覆盖 `RAX` syscall number、六参数寄存器、`RCX/R11` 和 raw errno/libc `errno`。

教程：[`docs/13-linux-x86-64-raw-syscall-abi.md`](docs/13-linux-x86-64-raw-syscall-abi.md)；实验：[`labs/13-raw-syscall-abi/`](labs/13-raw-syscall-abi/)；源码：[`source-paths/13-syscall-abi-linux-5.10.md`](source-paths/13-syscall-abi-linux-5.10.md)。A13 已完成。

### A14：系统调用入口与返回

覆盖 `entry_SYSCALL_64`、`swapgs`、user/kernel stack、`pt_regs`、`do_syscall_64()`、系统调用分派，以及 SYSRET/IRET 返回选择。

教程：[`docs/14-entry-syscall-64-stack-and-pt-regs.md`](docs/14-entry-syscall-64-stack-and-pt-regs.md)、[`docs/14-do-syscall-64-dispatch-and-return-value.md`](docs/14-do-syscall-64-dispatch-and-return-value.md)、[`docs/14-syscall-exit-sysret-and-iret.md`](docs/14-syscall-exit-sysret-and-iret.md)。源码与实验位于对应 `source-paths/14-*`、`labs/14-*`。A14 已完成；kernel-GDB 动态现场仍需匹配 v5.10 guest 实测。

### A15：异常与中断入口

覆盖 IDT、GDT/TSS、fault/trap/interrupt、CPU hardware frame、error code normalization、IST、普通 device IRQ、hardirq bookkeeping 与可选 IRQ stack。

教程入口：[`docs/15-idt-exception-entry-and-pt-regs.md`](docs/15-idt-exception-entry-and-pt-regs.md)、[`docs/15-tss-ist-and-special-exception-stacks.md`](docs/15-tss-ist-and-special-exception-stacks.md)、[`docs/15-external-interrupt-entry-and-irq-stack.md`](docs/15-external-interrupt-entry-and-irq-stack.md)、[`docs/15-fault-trap-interrupt-semantics.md`](docs/15-fault-trap-interrupt-semantics.md)。整章复核：[`docs/15-a15-completion-review.md`](docs/15-a15-completion-review.md)。A15 已完成。

### A16：缺页异常入口

覆盖 `#PF`、CR2/error code、`pt_regs`、`exc_page_fault()` 到 memory 子系统的交接、`VM_FAULT_RETRY` 与返回后原指令重新执行的区别。

教程：[`docs/16-page-fault-entry-cr2-and-error-code.md`](docs/16-page-fault-entry-cr2-and-error-code.md)、[`docs/16-page-fault-retry-and-instruction-restart.md`](docs/16-page-fault-retry-and-instruction-restart.md)；实验：[`labs/16-page-fault-demand/`](labs/16-page-fault-demand/)；整章复核：[`docs/16-a16-completion-review.md`](docs/16-a16-completion-review.md)。缺页处理主体放在 [`../memory/`](../memory/)。A16 已完成。

### A17：上下文切换汇编

覆盖 `switch_to`、`__switch_to_asm`、`inactive_task_frame`、callee-saved GPR、kernel stack 切换和 `__switch_to()` 中 FS/GS、TLS、FPU/XSTATE、per-CPU current/TSS 等架构状态。

教程：[`docs/17-switch-to-stack-and-control-flow.md`](docs/17-switch-to-stack-and-control-flow.md)、[`docs/17-switch-to-arch-state.md`](docs/17-switch-to-arch-state.md)；实验：[`labs/17-switch-to-stack-control-flow/`](labs/17-switch-to-stack-control-flow/)、[`labs/17-switch-to-arch-state/`](labs/17-switch-to-arch-state/)；源码：[`source-paths/17-switch-to-linux-5.10.md`](source-paths/17-switch-to-linux-5.10.md)、[`source-paths/17-switch-to-arch-state-linux-5.10.md`](source-paths/17-switch-to-arch-state-linux-5.10.md)。调度决策主体放在 [`../scheduler/`](../scheduler/)。A17 已完成。

### A18：原子指令、内存屏障与内联汇编

本章分三层建立模型，避免把 CPU atomicity、CPU/Linux memory ordering 和 compiler ordering 混为一谈。

第一部分：x86 atomic RMW、`xchg/cmpxchg/xadd`、`lock` 前缀与 Linux 5.10 x86 atomic API。

教程：[`docs/18-atomic-rmw-xchg-cmpxchg-xadd.md`](docs/18-atomic-rmw-xchg-cmpxchg-xadd.md)；实验：[`labs/18-atomic-rmw/`](labs/18-atomic-rmw/)；源码：[`source-paths/18-atomic-rmw-x86-linux-5.10.md`](source-paths/18-atomic-rmw-x86-linux-5.10.md)。

第二部分：x86 TSO、`mfence/lfence/sfence` 与 Linux `mb/rmb/wmb`、`smp_*`、acquire/release 等 barrier API。

教程：[`docs/18-memory-ordering-and-barriers.md`](docs/18-memory-ordering-and-barriers.md)；实验：[`labs/18-memory-ordering-barriers/`](labs/18-memory-ordering-barriers/)；源码：[`source-paths/18-memory-barriers-x86-linux-5.10.md`](source-paths/18-memory-barriers-x86-linux-5.10.md)。

第三部分：GCC extended asm 的 operands、constraints、matching、early-clobber、`cc`/`memory` clobber 与 `volatile`，以及它们和 x86 ISA/CPU ordering 的边界。

教程：[`docs/18-gcc-extended-asm-constraints.md`](docs/18-gcc-extended-asm-constraints.md)；实验：[`labs/18-gcc-extended-asm-constraints/`](labs/18-gcc-extended-asm-constraints/)；源码：[`source-paths/18-gcc-extended-asm-constraints-linux-5.10.md`](source-paths/18-gcc-extended-asm-constraints-linux-5.10.md)。

整章复核：[`docs/18-a18-completion-review.md`](docs/18-a18-completion-review.md)。A18 内容已完成；依赖完整 Linux 5.10 checkout 的 Kbuild/objdump 和部分并发实验仍按各实验文档标记为待实测，不影响课程内容层面的收章。

### A19：早期启动汇编阅读基础

本章只建立阅读 Linux 5.10 x86-64 早期启动汇编所需的机器状态模型；完整 boot protocol、解压和后续启动流程放在 [`../boot-crash/`](../boot-crash/)，完整 paging 机制放在 [`../memory/`](../memory/)。

第一部分：长模式切换。区分 protected mode、IA-32e compatibility execution 与 64-bit execution，建立 `CR4.PAE → early page tables/CR3 → EFER.LME → CR0.PG → far lret reload CS → startup_64` 的依赖关系。

教程：[`docs/19-long-mode-transition-basics.md`](docs/19-long-mode-transition-basics.md)；实验：[`labs/19-long-mode-transition/`](labs/19-long-mode-transition/)；源码：[`source-paths/19-long-mode-transition-linux-5.10.md`](source-paths/19-long-mode-transition-linux-5.10.md)。

第二部分：early boot page tables。核对 `1×L4 + 1×L3 + 4×L2 = 24 KiB`、2048 个 2 MiB leaf、低 4 GiB identity mapping、CR3 装载和 SEV encryption-bit 条件路径。

教程：[`docs/19-early-boot-page-tables.md`](docs/19-early-boot-page-tables.md)；实验：[`labs/19-early-boot-page-tables/`](labs/19-early-boot-page-tables/)；源码：[`source-paths/19-early-boot-page-tables-linux-5.10.md`](source-paths/19-early-boot-page-tables-linux-5.10.md)。

第三部分：protected-mode entry、GDT/segment state、boot stack 与 `verify_cpu()`。明确 `.code32` 不等于模式切换，`lgdt` 不等于 segment reload，`CS` 留到后续 far transfer 更新，并核对 `verify_cpu()` 的 flags 与返回值契约。

教程：[`docs/19-protected-mode-entry-segments-and-cpu-check.md`](docs/19-protected-mode-entry-segments-and-cpu-check.md)；实验：[`labs/19-protected-mode-entry/`](labs/19-protected-mode-entry/)；源码：[`source-paths/19-protected-mode-entry-segments-cpu-check-linux-5.10.md`](source-paths/19-protected-mode-entry-segments-cpu-check-linux-5.10.md)。

整章复核：[`docs/19-a19-completion-review.md`](docs/19-a19-completion-review.md)。A19 内容已完成。early-page-table 算术/边界脚本和 protected-mode-entry checker 自测试已有实际执行记录；真实 Linux 5.10 Kbuild/objdump 以及 QEMU/GDB 动态 GDTR、segment hidden state、CR4/CR3/EFER、CS/RIP 现场仍按实验文档标记为待实测。

A00–A19 的课程内容现已形成连续主线。后续继续推进前，应先依据本 README 和仓库实际内容确定下一章的最小课程单元，不从完整启动流程或完整内存管理机制重复展开已经划归其他领域的内容。

## 默认环境

```text
体系结构：x86-64
操作系统：Linux
内核源码：Linux kernel 5.10
汇编器：GNU assembler
主要语法：AT&T
辅助语法：Intel
ABI：System V AMD64 ABI
```

# Linux x86-64 汇编与内核入口

本目录学习 x86-64 汇编，并为阅读 Linux kernel 5.10 的启动、系统调用、异常、中断和上下文切换代码打下基础。

课程主要回答以下问题：

```text
CPU 如何执行一条指令？
寄存器、内存、栈和标志位如何变化？
C 代码如何转换成机器指令？
函数参数、返回值和局部变量如何保存？
用户态如何进入内核态，又如何返回？
内核入口代码如何保存和恢复执行现场？
```

## 课程大纲

### A00：实验环境与基本工具

- GCC、GNU assembler 和 linker 的分工；
- `.c`、`.s`、`.o` 和 ELF 文件的关系；
- `objdump`、`readelf`、`nm` 和 GDB；
- AT&T 语法与 Intel 语法；
- `-O0`、`-Og` 和 `-O2` 的基本差别。

### A01：CPU 执行模型、寄存器宽度与 `mov`

- `RIP`、通用寄存器、`RSP`、`RFLAGS` 和内存；
- `RAX/EAX/AX/AL/AH` 的关系；
- 8、16、32、64 位写入；
- 写 `EAX` 时高 32 位清零；
- 立即数、寄存器和内存操作数；
- 零扩展与符号扩展。

教程：[`docs/01-cpu-execution-model-and-register-width.md`](docs/01-cpu-execution-model-and-register-width.md)

实验：[`labs/01-register-width/`](labs/01-register-width/)

### A02：地址、解引用、数组、结构体与 `lea`

- 地址与地址处的数据；
- `disp(base,index,scale)`；
- 一维数组、二维数组和指针数组；
- 结构体成员、结构体数组和嵌套结构体；
- 对齐、填充、`sizeof` 和 `offsetof`；
- RIP-relative 寻址；
- `lea` 的地址计算和整数运算用途。

教程：[`docs/02-addressing-dereference-and-lea.md`](docs/02-addressing-dereference-and-lea.md)

实验：[`labs/02-addressing/`](labs/02-addressing/)

### A03：`RFLAGS`、比较、条件跳转与基本块

- `CF`、`ZF`、`SF` 和 `OF`；
- `cmp` 与 `test`；
- 有符号比较与无符号比较；
- `jcc`、`setcc` 和 `cmovcc`；
- 基本块、控制流图和循环回边；
- 分支预测的基本概念。

教程：[`docs/03-rflags-comparison-and-control-flow.md`](docs/03-rflags-comparison-and-control-flow.md)

实验：[`labs/03-flags-and-branches/`](labs/03-flags-and-branches/)

### A04：整数算术、位运算、移位、乘法与除法

- `add`、`sub`、`neg`、`inc` 和 `dec`；
- `and`、`or`、`xor` 和 `not`；
- `shl`、`shr` 和 `sar`；
- `mul`、`imul`、`div` 和 `idiv`；
- `RDX:RAX` 的隐式操作数；
- 常数乘除法的编译器优化。

教程：[`docs/04-integer-arithmetic-shifts-multiply-divide.md`](docs/04-integer-arithmetic-shifts-multiply-divide.md)

实验：[`labs/04-arithmetic-and-shifts/`](labs/04-arithmetic-and-shifts/)

### A05：循环、状态机与 `switch`

- `while`、`do-while` 和 `for`；
- 数组和指针遍历；
- 循环回边；
- 状态分发与状态转换；
- `break` 与 `continue`；
- 稀疏 `switch` 的比较结构；
- 稠密 `switch` 的跳转表和间接跳转。

教程：[`docs/05-loops-state-machines-and-switch.md`](docs/05-loops-state-machines-and-switch.md)

实验：[`labs/05-loops-state-machines-switch/`](labs/05-loops-state-machines-switch/)

### A06：栈、`push/pop` 与初始用户栈

- 栈向低地址增长；
- `RSP` 的变化；
- `push` 和 `pop`；
- `_start` 时的 `argc`、`argv`、`envp` 和 auxiliary vector；
- 初始用户栈的 16 字节对齐。

第一部分：栈模型与 `push/pop`

教程：[`docs/06-stack-model-and-push-pop.md`](docs/06-stack-model-and-push-pop.md)

实验：[`labs/06-stack-push-pop/`](labs/06-stack-push-pop/)

第二部分：`_start` 初始用户栈

教程：[`docs/06-initial-user-stack.md`](docs/06-initial-user-stack.md)

实验：[`labs/06-initial-user-stack/`](labs/06-initial-user-stack/)

普通函数调用边界的 System V AMD64 ABI 栈对齐规则在 A08 中继续展开。

### A07：`call`、`ret` 与返回地址

- 直接调用和间接调用；
- 返回地址如何保存；
- 函数指针；
- 递归；
- 返回地址损坏的基本后果。

第一部分：direct `call`、near `ret` 与返回地址

教程：[`docs/07-call-ret-and-return-address.md`](docs/07-call-ret-and-return-address.md)

实验：[`labs/07-call-ret/`](labs/07-call-ret/)

第二部分：indirect `call` 与函数指针

教程：[`docs/07-indirect-call-and-function-pointers.md`](docs/07-indirect-call-and-function-pointers.md)

实验：[`labs/07-indirect-call/`](labs/07-indirect-call/)

第三部分：递归调用与多层返回地址

教程：[`docs/07-recursion-and-multiple-return-addresses.md`](docs/07-recursion-and-multiple-return-addresses.md)

实验：[`labs/07-recursion/`](labs/07-recursion/)

第四部分：返回地址损坏的基本后果

教程：[`docs/07-damaged-return-address.md`](docs/07-damaged-return-address.md)

实验：[`labs/07-damaged-return-address/`](labs/07-damaged-return-address/)

A07 已完成。下一章进入 A08：System V AMD64 ABI。

### A08：System V AMD64 ABI

- 整数参数寄存器；
- 返回值寄存器；
- caller-saved 与 callee-saved；
- 栈上传递的参数；
- 16 字节栈对齐；
- Red Zone；
- 小结构体和大结构体的参数、返回规则；
- 混合 INTEGER/SSE 聚合的参数、返回规则。

第一部分：INTEGER 参数寄存器与整数返回值

教程：[`docs/08-integer-arguments-and-return-values.md`](docs/08-integer-arguments-and-return-values.md)

实验：[`labs/08-integer-arguments-and-return/`](labs/08-integer-arguments-and-return/)

第二部分：caller-saved 与 callee-saved 寄存器

教程：[`docs/08-caller-saved-and-callee-saved.md`](docs/08-caller-saved-and-callee-saved.md)

实验：[`labs/08-register-preservation/`](labs/08-register-preservation/)

第三部分：寄存器耗尽后的栈上传参

教程：[`docs/08-stack-passed-arguments.md`](docs/08-stack-passed-arguments.md)

实验：[`labs/08-stack-arguments/`](labs/08-stack-arguments/)

第四部分：普通函数调用边界的 16 字节栈对齐

教程：[`docs/08-stack-alignment.md`](docs/08-stack-alignment.md)

实验：[`labs/08-stack-alignment/`](labs/08-stack-alignment/)

第五部分：128-byte Red Zone

教程：[`docs/08-red-zone.md`](docs/08-red-zone.md)

实验：[`labs/08-red-zone/`](labs/08-red-zone/)

第六部分：聚合类型的 INTEGER 与 MEMORY 参数/返回规则

教程：[`docs/08-aggregate-arguments-and-returns.md`](docs/08-aggregate-arguments-and-returns.md)

实验：[`labs/08-aggregate-abi/`](labs/08-aggregate-abi/)

第七部分：混合 INTEGER/SSE 聚合

教程：[`docs/08-mixed-integer-sse-aggregate.md`](docs/08-mixed-integer-sse-aggregate.md)

实验：[`labs/08-mixed-aggregate/`](labs/08-mixed-aggregate/)

A08 已完成。下一章进入 A09：函数栈帧、局部变量与栈展开。

### A09：函数栈帧、局部变量与栈展开

- 函数序言和尾声；
- `RBP` 栈帧；
- 局部变量和寄存器溢出；
- 叶子函数；
- frame pointer omission；
- DWARF CFI 和调用栈展开的基础。

第一部分：`RBP` 栈帧基本模型

教程：[`docs/09-rbp-frame-basics.md`](docs/09-rbp-frame-basics.md)

实验：[`labs/09-rbp-frame/`](labs/09-rbp-frame/)

第二部分：局部变量、spill/reload 与实际栈槽

教程：[`docs/09-locals-spills-and-stack-slots.md`](docs/09-locals-spills-and-stack-slots.md)

实验：[`labs/09-locals-and-spills/`](labs/09-locals-and-spills/)

第三部分：leaf function 与 frame pointer omission

教程：[`docs/09-leaf-functions-and-frame-pointer-omission.md`](docs/09-leaf-functions-and-frame-pointer-omission.md)

实验：[`labs/09-leaf-frame-omission/`](labs/09-leaf-frame-omission/)

第四部分：DWARF CFI、CFA 与基本栈展开

教程：[`docs/09-dwarf-cfi-and-cfa.md`](docs/09-dwarf-cfi-and-cfa.md)

实验：[`labs/09-dwarf-cfi/`](labs/09-dwarf-cfi/)

第五部分：多层调用链与 CFI 展开边界

教程：[`docs/09-unwind-boundaries.md`](docs/09-unwind-boundaries.md)

实验：[`labs/09-unwind-boundaries/`](labs/09-unwind-boundaries/)

A09 已完成。五个部分已经覆盖经典 `%rbp` frame、局部变量与 spill/reload、frame pointer omission、DWARF CFI/CFA，以及 CFI 正确/缺失/错误时的实际展开边界。下一章进入 A10：编译器优化后的汇编。

### A10：编译器优化后的汇编

- 内联；
- 尾调用；
- 公共子表达式；
- 寄存器分配；
- spill 和 reload；
- `-O0`、`-Og` 和 `-O2` 对照；
- 优化代码的调试限制。

第一部分：内联与函数边界消失

教程：[`docs/10-inlining-and-disappearing-call-boundaries.md`](docs/10-inlining-and-disappearing-call-boundaries.md)

实验：[`labs/10-inlining/`](labs/10-inlining/)

第二部分：尾调用与 sibling-call 优化

教程：[`docs/10-tail-calls-and-sibling-call-optimization.md`](docs/10-tail-calls-and-sibling-call-optimization.md)

实验：[`labs/10-tail-calls/`](labs/10-tail-calls/)

第三部分：公共子表达式与重复计算消除

教程：[`docs/10-common-subexpressions-and-redundant-computation.md`](docs/10-common-subexpressions-and-redundant-computation.md)

实验：[`labs/10-common-subexpressions/`](labs/10-common-subexpressions/)

第四部分：寄存器分配与 live range

教程：[`docs/10-register-allocation-and-live-ranges.md`](docs/10-register-allocation-and-live-ranges.md)

实验：[`labs/10-register-allocation-live-ranges/`](labs/10-register-allocation-live-ranges/)

第五部分：优化代码的调试限制

教程：[`docs/10-optimized-code-debugging-limits.md`](docs/10-optimized-code-debugging-limits.md)

实验：[`labs/10-optimized-debugging/`](labs/10-optimized-debugging/)

A10 已完成。五个部分已经覆盖内联、尾调用、公共子表达式与重复计算消除、寄存器分配与 spill/reload，以及优化后源码行、DWARF variable location 与真实机器指令之间的调试边界。下一章进入 A11：ELF、符号与重定位。

### A11：ELF、符号与重定位

- `.text`、`.rodata`、`.data` 和 `.bss`；
- section 与 segment；
- 符号表；
- 强符号、弱符号和未定义符号；
- PC-relative 重定位；
- 静态链接的基本过程。

第一部分：ELF section 基本模型与 section/segment 区分

教程：[`docs/11-elf-sections-and-segments.md`](docs/11-elf-sections-and-segments.md)

实验：[`labs/11-elf-sections/`](labs/11-elf-sections/)

第二部分：ELF 符号表与 section 绑定

教程：[`docs/11-elf-symbol-table.md`](docs/11-elf-symbol-table.md)

实验：[`labs/11-elf-symbol-table/`](labs/11-elf-symbol-table/)

第三部分：强符号、弱符号与未定义符号的链接选择

教程：[`docs/11-strong-weak-and-undefined-symbols.md`](docs/11-strong-weak-and-undefined-symbols.md)

实验：[`labs/11-symbol-binding/`](labs/11-symbol-binding/)

第四部分：x86-64 PC-relative relocation

教程：[`docs/11-pc-relative-relocations.md`](docs/11-pc-relative-relocations.md)

实验：[`labs/11-pc-relative-relocations/`](labs/11-pc-relative-relocations/)

第五部分：静态链接的基本过程

教程：[`docs/11-static-linking-process.md`](docs/11-static-linking-process.md)

实验：[`labs/11-static-linking/`](labs/11-static-linking/)

A11 已完成。五个部分已经把 section/segment、symbol table、symbol resolution、PC-relative relocation 与最终静态链接串成完整主线，并通过 `readelf`、`objdump`、`nm` 和 linker map 实际验证 input section 到 output section、最终 symbol value 和 relocation 消费过程。下一章进入 A12：PIC、PIE、GOT 与 PLT。

### A12：PIC、PIE、GOT 与 PLT

- 位置无关代码；
- RIP-relative 访问；
- PIE 和 ASLR；
- GOT 与 PLT；
- 动态链接和延迟绑定。

第一部分：位置无关代码、PIE 与 RIP-relative 寻址

教程：[`docs/12-pic-pie-and-rip-relative.md`](docs/12-pic-pie-and-rip-relative.md)

实验：[`labs/12-pic-pie-rip-relative/`](labs/12-pic-pie-rip-relative/)

第二部分：GOT、GOTPCREL 与动态数据符号解析

教程：[`docs/12-got-and-dynamic-data-relocation.md`](docs/12-got-and-dynamic-data-relocation.md)

实验：[`labs/12-got-data-access/`](labs/12-got-data-access/)

第三部分：PLT、`JUMP_SLOT` 与动态函数调用

教程：[`docs/12-plt-jump-slot-and-binding.md`](docs/12-plt-jump-slot-and-binding.md)

实验：[`labs/12-plt-dynamic-calls/`](labs/12-plt-dynamic-calls/)

A12 已完成。三个部分已经覆盖位置无关代码与 RIP-relative 寻址、PIE/ASLR、外部数据符号的 GOT/GOTPCREL 动态绑定，以及外部函数调用从 `R_X86_64_PLT32` 经 `.plt/.got.plt` 到 `R_X86_64_JUMP_SLOT` 的完整路径；实验同时对照了默认 lazy binding 与 `-z now` eager binding。下一章进入 A13：Linux x86-64 系统调用 ABI。

### A13：Linux x86-64 系统调用 ABI

- `syscall` 指令；
- 系统调用号和参数寄存器；
- `RCX`、`R11` 和 `R10` 的特殊作用；
- 原始返回值与 `errno`；
- libc 包装函数与直接系统调用。

第一部分：原始 `syscall`、寄存器约定与返回值

教程：[`docs/13-linux-x86-64-raw-syscall-abi.md`](docs/13-linux-x86-64-raw-syscall-abi.md)

实验：[`labs/13-raw-syscall-abi/`](labs/13-raw-syscall-abi/)

Linux 5.10 源码事实核验：[`source-paths/13-syscall-abi-linux-5.10.md`](source-paths/13-syscall-abi-linux-5.10.md)

A13 已完成。本章已经区分 System V AMD64 普通函数 ABI、x86-64 `syscall` 指令的架构语义、Linux x86-64 syscall ABI 和 libc 用户态包装层；实验实际验证了 `%rax` 系统调用号、`%rdi/%rsi/%rdx/%r10/%r8/%r9` 参数约定、`%rcx/%r11` 的特殊角色、六参数 wrapper 的 `%rcx -> %r10` 适配，以及 raw negative errno 与 libc `-1 + errno` 的接口边界。Linux 5.10 的入口寄存器约定和 syscall number 来源已单独完成源码事实核验。下一章进入 A14：Linux 5.10 系统调用入口与返回。

### A14：Linux 5.10 系统调用入口与返回

- `entry_SYSCALL_64`；
- 用户栈与内核栈切换；
- `pt_regs`；
- `do_syscall_64`；
- 返回用户态前的检查；
- `sysretq` 与 `iretq`。

第一部分：`entry_SYSCALL_64`、内核栈切换与 `pt_regs`

教程：[`docs/14-entry-syscall-64-stack-and-pt-regs.md`](docs/14-entry-syscall-64-stack-and-pt-regs.md)

实验：[`labs/14-entry-syscall-pt-regs/`](labs/14-entry-syscall-pt-regs/)

Linux 5.10 源码事实核验：[`source-paths/14-entry-syscall-64-stack-switch-linux-5.10.md`](source-paths/14-entry-syscall-64-stack-switch-linux-5.10.md)

第二部分：`do_syscall_64()`、系统调用表与返回值写回

教程：[`docs/14-do-syscall-64-dispatch-and-return-value.md`](docs/14-do-syscall-64-dispatch-and-return-value.md)

实验：[`labs/14-do-syscall-dispatch/`](labs/14-do-syscall-dispatch/)

Linux 5.10 源码事实核验：[`source-paths/14-do-syscall-64-dispatch-linux-5.10.md`](source-paths/14-do-syscall-64-dispatch-linux-5.10.md)

第三部分：`syscall_exit_to_user_mode()`、SYSRET 快路径与 IRET 回退

教程：[`docs/14-syscall-exit-sysret-and-iret.md`](docs/14-syscall-exit-sysret-and-iret.md)

实验：[`labs/14-syscall-exit-sysret-iret/`](labs/14-syscall-exit-sysret-iret/)

Linux 5.10 源码事实核验：[`source-paths/14-syscall-exit-sysret-iret-linux-5.10.md`](source-paths/14-syscall-exit-sysret-iret-linux-5.10.md)

A14 已完成。三部分已经把 `entry_SYSCALL_64` 入口现场、用户栈到内核栈切换、`pt_regs` 构造、`do_syscall_64()` 分派与 `regs->ax` 写回、exit-to-user work，以及最终基于 `pt_regs` 的 SYSRET eligibility 与 IRET 回退串成完整系统调用进入/返回主线。三组 kernel-GDB 实验都已形成可执行步骤；由于当前维护环境缺少匹配的 Linux 5.10 guest、`vmlinux` 与 kernel-GDB 会话，动态断点结果继续明确标记为待真实环境执行，不作为已实测结论。下一章进入 A15：异常、中断与特权级切换。

### A15：异常、中断与特权级切换

- Ring 0 与 Ring 3；
- IDT、GDT 和 TSS；
- trap、fault 和 interrupt；
- CPU 自动压栈的内容；
- 有错误码和无错误码异常；
- IST 和特殊异常栈。

第一部分：IDT 普通异常入口、error code 与 `pt_regs`

教程：[`docs/15-idt-exception-entry-and-pt-regs.md`](docs/15-idt-exception-entry-and-pt-regs.md)

实验：[`labs/15-de-gp-exception-entry/`](labs/15-de-gp-exception-entry/)

Linux 5.10 基础入口源码事实核验：[`source-paths/15-exception-interrupt-entry-basics-linux-5.10.md`](source-paths/15-exception-interrupt-entry-basics-linux-5.10.md)

Linux 5.10 `#DE/#GP` 专项源码事实核验：[`source-paths/15-de-gp-error-code-pt-regs-linux-5.10.md`](source-paths/15-de-gp-error-code-pt-regs-linux-5.10.md)

第二部分：TSS、IST 与特殊异常栈

教程：[`docs/15-tss-ist-and-special-exception-stacks.md`](docs/15-tss-ist-and-special-exception-stacks.md)

实验：[`labs/15-tss-ist-special-exception-stacks/`](labs/15-tss-ist-special-exception-stacks/)

Linux 5.10 源码事实核验：[`source-paths/15-tss-ist-special-exceptions-linux-5.10.md`](source-paths/15-tss-ist-special-exceptions-linux-5.10.md)

第三部分：普通外部中断入口、hardirq context 与 IRQ stack

教程：[`docs/15-external-interrupt-entry-and-irq-stack.md`](docs/15-external-interrupt-entry-and-irq-stack.md)

实验：[`labs/15-external-interrupt-entry/`](labs/15-external-interrupt-entry/)

Linux 5.10 源码事实核验：[`source-paths/15-external-interrupt-entry-linux-5.10.md`](source-paths/15-external-interrupt-entry-linux-5.10.md)

语义补充：[`docs/15-fault-trap-interrupt-semantics.md`](docs/15-fault-trap-interrupt-semantics.md)

整章一致性复核：[`docs/15-a15-completion-review.md`](docs/15-a15-completion-review.md)

A15 已完成。第一部分建立普通同步异常的 `IDT gate -> CPU hardware frame -> error-code normalization -> error_entry -> pt_regs -> C handler` 主线；第二部分建立 `TSS.ist[] -> IDT gate.IST -> CPU exception-stack switch -> special entry` 主线；第三部分补齐普通 device IRQ 的 vector stub、hardirq bookkeeping 与可选 per-CPU IRQ stack。章节同时独立区分同步/异步、fault/trap、IDT interrupt/trap gate 和 hardware error code 四个分类轴，并明确 task kernel stack、IST stack 与 IRQ stack 是三个不同机制。三组需要 kernel-GDB 的动态入口观测仍因当前环境缺少匹配 Linux 5.10 guest、`vmlinux` 与调试会话而标记为待实测，不作为已运行结论。下一章进入 A16：缺页异常入口。

### A16：缺页异常入口

- `#PF`；
- `CR2` 和错误码；
- 异常入口如何构造寄存器现场；
- 从汇编入口进入内存管理代码；
- 异常处理完成后的返回。

第一部分：`#PF` 入口、CR2 与 page-fault error code

教程：[`docs/16-page-fault-entry-cr2-and-error-code.md`](docs/16-page-fault-entry-cr2-and-error-code.md)

实验：[`labs/16-page-fault-demand/`](labs/16-page-fault-demand/)

Linux 5.10 源码事实核验：[`source-paths/16-page-fault-entry-linux-5.10.md`](source-paths/16-page-fault-entry-linux-5.10.md)

第二部分：page-fault 内部重试、异常返回与原指令重新执行

教程：[`docs/16-page-fault-retry-and-instruction-restart.md`](docs/16-page-fault-retry-and-instruction-restart.md)

Linux 5.10 源码事实核验：[`source-paths/16-page-fault-retry-return-linux-5.10.md`](source-paths/16-page-fault-retry-return-linux-5.10.md)

整章一致性复核：[`docs/16-a16-completion-review.md`](docs/16-a16-completion-review.md)

缺页处理的主体放在 [`../memory/`](../memory/) 中学习。

A16 已完成。本章把 `faulting instruction -> #PF hardware entry -> saved RIP/CR2/error code -> pt_regs -> exc_page_fault() -> handle_page_fault() -> do_user_addr_fault()/do_kern_addr_fault() -> exception return` 串成完整的汇编入口与交接主线，并严格区分 `VM_FAULT_RETRY` 的 fault-handler 内部重试和恢复 faulting RIP 后 CPU 对原指令的重新执行。可运行 demand-fault 实验已经实际验证合法匿名 VMA 首次写访问从 non-resident 变为 resident、产生 minor fault 并最终完成原写指令；CR2、PF error code 和内核 `pt_regs` 的动态现场仍留给匹配 Linux 5.10 kernel-GDB 环境验证。VMA 查找、页表建立、匿名页分配和 Copy-on-Write 等主体继续留在 memory 课程。下一章进入 A17：上下文切换汇编。

### A17：上下文切换汇编

- `switch_to`；
- `__switch_to_asm`；
- callee-saved 寄存器；
- 内核栈切换；
- 从旧任务返回到新任务的过程。

调度主体放在 [`../scheduler/`](../scheduler/) 中学习。

### A18：原子指令、内存屏障与内联汇编

- `xchg`、`cmpxchg` 和 `xadd`；
- `lock` 前缀；
- `mfence`、`lfence` 和 `sfence`；
- GCC 扩展内联汇编；
- 输入、输出和 clobber 约束；
- 内核原子操作和屏障接口的汇编基础。

### A19：早期启动汇编阅读基础

- 实模式、保护模式和长模式；
- 控制寄存器；
- 早期页表；
- 远跳转和模式切换；
- `head_64.S` 所需的汇编基础。

完整启动过程放在 [`../boot-crash/`](../boot-crash/) 中学习。

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

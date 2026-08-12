# A14 实验：验证 syscall 用户现场与内核 `pt_regs` 的对应关系

本实验服务于 [`../../docs/14-entry-syscall-64-stack-and-pt-regs.md`](../../docs/14-entry-syscall-64-stack-and-pt-regs.md)。目标不是再次证明用户态 syscall ABI，而是观察跨过 `SYSCALL` 后 Linux 5.10 如何把用户态返回现场保存为 `struct pt_regs`。

## 1. 要验证的问题

对一次 64 位原生 syscall，重点验证四组对应关系：

```text
用户态 syscall number       -> pt_regs.orig_ax
SYSCALL 保存的 return RIP   -> pt_regs.ip
SYSCALL 保存的 RFLAGS       -> pt_regs.flags
入口时的 user RSP           -> pt_regs.sp
```

同时观察 `pt_regs.ax` 在入口构造阶段先被初始化为 `-ENOSYS`，而 `orig_ax` 保留原始 syscall number。不要把两者视为同一字段。

## 2. 为什么不能只在用户态完成这个实验

用户程序可以在 `syscall` 前记录 RSP/RFLAGS，并可以把 syscall 后的标签地址作为预期 return RIP；但 `pt_regs` 位于内核栈，普通用户进程不能直接读取。因此完整验证需要能够在 Linux 5.10 内核入口暂停 CPU 的调试环境。

推荐使用隔离虚拟机中的 QEMU/KVM + GDB。这样不需要向生产内核加载探针模块，也不会为了教学实验修改 syscall 入口。

本实验不使用 eBPF；eBPF 不属于当前基础课程范围。

## 3. 版本基线与源码断点

实验必须针对 Linux 5.10 构建的 x86-64 内核。源码基线：

```text
arch/x86/entry/entry_64.S
arch/x86/entry/calling.h
arch/x86/include/asm/ptrace.h
```

正文对应的入口顺序是：

```text
entry_SYSCALL_64
  swapgs
  save user RSP in cpu_tss_rw.TSS_sp2
  SWITCH_TO_KERNEL_CR3
  RSP = cpu_current_top_of_stack
  push ss/sp/flags/cs/ip/orig_ax
  PUSH_AND_CLEAR_REGS rax=$-ENOSYS
  RSP -> complete struct pt_regs
```

为了观察完整结构体，断点应放在 `PUSH_AND_CLEAR_REGS` 已经执行完成、调用 `do_syscall_64` 之前的位置，而不是刚进入 `entry_SYSCALL_64` 时。刚进入入口时 `%rsp` 仍是 user RSP，那里还不存在完整 `pt_regs`。

## 4. 建议的最小用户态触发器

在 guest 中使用一段独立汇编触发 `getpid`，并在执行 `syscall` 前保存 user RSP 和 RFLAGS。示意代码：

```asm
    .text
    .globl raw_getpid_marker
    .type raw_getpid_marker,@function
raw_getpid_marker:
    movq %rsp, saved_rsp(%rip)
    pushfq
    popq saved_rflags(%rip)
    movq $39, %rax              # __NR_getpid on x86-64
syscall_site:
    syscall
return_site:
    ret

    .data
    .globl saved_rsp
saved_rsp:
    .quad 0
    .globl saved_rflags
saved_rflags:
    .quad 0
```

这里 `return_site` 的地址是 syscall 成功返回时 `%rcx` 所代表的用户 return RIP 的预期值。`saved_rsp` 是执行 `syscall` 前的 user RSP。`pushfq/popq` 会临时使用用户栈，但在 `syscall` 前已经恢复 RSP，因此不会改变最终入口 RSP。

`getpid` 没有参数，可以把实验注意力集中在入口返回现场，而不是参数寄存器。

## 5. 构建用户态触发器时必须检查什么

无论使用独立 `.S` 文件还是与 C 驱动程序链接，构建后先检查：

```bash
objdump -dr trigger.o
objdump -d trigger | sed -n '/<raw_getpid_marker>/,/^$/p'
nm -n trigger | grep -E 'raw_getpid_marker|syscall_site|return_site'
```

必须确认：

1. `syscall` 前 `%rax` 确实为 39；
2. `return_site` 紧跟 `syscall`；
3. 保存 RSP/RFLAGS 的指令没有在 `syscall` 与 `return_site` 之间插入额外逻辑；
4. 如果最终程序是 PIE，GDB 中比较的是运行时地址，而不是直接把 ELF 中的静态偏移当作虚拟地址。

## 6. 内核 GDB 观察方法

使用带调试符号的 Linux 5.10 `vmlinux` 启动隔离 guest，并通过 QEMU gdbstub 连接。具体 QEMU 磁盘、rootfs 和启动参数依环境而异，本实验不把某个发行版镜像写死。

连接后先定位：

```gdb
(gdb) file vmlinux
(gdb) target remote :1234
(gdb) disassemble /r entry_SYSCALL_64
```

不要根据本文档硬编码某个指令地址。不同配置、编译器和补丁会改变地址和宏展开。应在当前 `vmlinux` 的反汇编中找到 `PUSH_AND_CLEAR_REGS` 展开完成且尚未调用 `do_syscall_64` 的位置，在那里设置断点。

命中目标进程的 syscall 后，此时 `%rsp` 应指向完整 `struct pt_regs` 的最低地址。Linux 5.10 x86-64 布局为：

```text
+0x00 r15       +0x08 r14       +0x10 r13
+0x18 r12       +0x20 bp        +0x28 bx
+0x30 r11       +0x38 r10       +0x40 r9
+0x48 r8        +0x50 ax        +0x58 cx
+0x60 dx        +0x68 si        +0x70 di
+0x78 orig_ax   +0x80 ip        +0x88 cs
+0x90 flags     +0x98 sp        +0xa0 ss
```

可以直接按 8-byte 槽观察：

```gdb
(gdb) x/21gx $rsp
(gdb) p/x *(unsigned long *)($rsp + 0x78)
(gdb) p/x *(unsigned long *)($rsp + 0x80)
(gdb) p/x *(unsigned long *)($rsp + 0x90)
(gdb) p/x *(unsigned long *)($rsp + 0x98)
```

若 GDB 已加载内核类型信息，也可使用 `struct pt_regs` 类型访问字段；但以当前 `vmlinux` 的 DWARF 类型为准，不手工假设 GDB 一定识别 typedef/字段打印语法。

## 7. 预期结果

对上述 `getpid` 触发器，在完整 `pt_regs` 刚构造完成时应观察到：

```text
regs->orig_ax == 39
regs->ip      == runtime address of return_site
regs->sp      == saved_rsp
regs->flags   == SYSCALL 保存到 R11 的用户 RFLAGS
regs->ax      == (unsigned long)-ENOSYS
```

`flags` 比较需要注意实验采样点。用户态 `saved_rflags` 是 `pushfq` 执行时的值；真正进入 `SYSCALL` 时 CPU 保存的是执行 `syscall` 当时的 RFLAGS。只要两者之间的 `mov` 不改变相关 flags，它们应一致；若修改触发器插入会改 flags 的指令，就不能继续把 `saved_rflags` 当作精确期望值。

还应同时确认此时：

```text
RSP != saved_rsp
```

因为 CPU 当前已经运行在内核栈上，而 `saved_rsp` 只作为 `pt_regs.sp` 中的用户返回现场保存。

## 8. 如何避免命中无关 syscall

`entry_SYSCALL_64` 是所有 64 位原生 syscall 的公共入口，系统运行时会频繁命中。实验应在隔离 guest 中进行，并通过以下方式减少噪声：

- 让 guest 尽量只运行测试程序；
- 命中后先检查 `orig_ax == 39`；
- 再检查 `ip` 是否落在测试进程 `return_site` 的运行时地址；
- 条件不匹配时继续执行。

不要只看到 syscall number 39 就认定命中了目标进程，因为其他进程也可能调用 `getpid`。

## 9. 本次环境的执行边界

仓库维护环境可以读取和修改 GitHub 内容，但本次没有可启动的 Linux 5.10 x86-64 guest、对应 `vmlinux`、QEMU gdbstub 或内核 GDB 会话。因此这里完成的是**可执行实验设计和源码/字段偏移复核**，没有伪造 GDB 实测输出。

真正执行时必须记录：

```text
Linux commit / release
.config 中 CONFIG_X86_64 与 CONFIG_PAGE_TABLE_ISOLATION 状态
编译器版本
vmlinux Build ID（如有）
entry_SYSCALL_64 目标断点的反汇编位置
四组字段的实际值
```

如果实测与预期不符，应先检查当前内核是否确为 5.10 基线、断点是否位于完整 `pt_regs` 构造之后，以及 guest 是否命中了目标进程，再修改课程结论。

## 10. 与下一部分的边界

本实验只验证“入口现场如何成为 `pt_regs`”。`do_syscall_64(unsigned long nr, struct pt_regs *regs)` 的 syscall number 检查、`sys_call_table` 分派、`regs->ax` 返回值写回，以及 `syscall_exit_to_user_mode()` 属于 A14 下一部分。

因此本实验到观察完整 `pt_regs` 为止，不继续单步进入系统调用实现或 SYSRET/IRET 返回路径。
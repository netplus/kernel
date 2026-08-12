# A14 第三部分实验：验证 SYSRET 快路径与 IRET 回退

本实验对应 [`../../docs/14-syscall-exit-sysret-and-iret.md`](../../docs/14-syscall-exit-sysret-and-iret.md)，目标不是用用户态程序猜测系统调用最终执行了哪条返回指令，而是在隔离的 Linux 5.10 x86-64 guest 中直接观察 `entry_SYSCALL_64` 返回侧的分流。

## 1. 要验证的问题

Linux 5.10 在 `do_syscall_64()` 和 `syscall_exit_to_user_mode()` 返回后，会根据最终 `struct pt_regs` 判断是否可以使用 SYSRET 快路径。本实验验证：

1. 普通、未被修改的 64-bit syscall 现场可以进入 `syscall_return_via_sysret`；
2. 当最终用户 RFLAGS 含 `X86_EFLAGS_TF` 时，SYSRET eligibility check 失败，并在执行 `sysretq` 之前转入 `swapgs_restore_regs_and_return_to_usermode`；
3. 返回值 `pt_regs->ax` 是否成功或为负 errno，不是 SYSRET/IRET 分流条件；
4. 分流发生在最终架构返回指令之前，IRET 路径不是 SYSRET fault 后的补救。

源码事实基线见 [`../../source-paths/14-syscall-exit-sysret-iret-linux-5.10.md`](../../source-paths/14-syscall-exit-sysret-iret-linux-5.10.md)。

## 2. 为什么需要 kernel-GDB

用户态只能看到 syscall 已经返回，不能可靠地区分最后执行的是 `sysretq` 还是 `iretq`。`strace` 也观察不到这个架构返回选择。因此本实验使用：

```text
Linux kernel 5.10 x86-64 guest
+ 与 guest 完全匹配的 vmlinux
+ QEMU gdbstub
+ GDB
```

这是停机级调试实验，只能在隔离虚拟机中执行。不要在生产系统上使用这些断点。

## 3. 环境要求

至少需要：

- Linux v5.10 x86-64 内核；
- 带调试符号、与运行内核完全匹配的 `vmlinux`；
- QEMU/KVM guest，能够通过 `-s` 或等价参数开启 gdbstub；
- GDB 能加载该 `vmlinux`；
- guest 中可运行一个最小用户态测试程序。

建议关闭 guest KASLR，启动参数加入：

```text
nokaslr
```

如果保留 KASLR，则必须先按当前运行时地址重新定位符号，不能把 `vmlinux` 链接地址直接当作断点地址。

## 4. 先从当前 vmlinux 确认真实指令

不要硬编码本文档中的地址。连接 guest 前先检查当前 `vmlinux`：

```bash
objdump -drS vmlinux | less
```

在 GDB 中：

```gdb
disassemble /r entry_SYSCALL_64
```

确认至少能定位：

```text
call do_syscall_64
...
SYSRET eligibility checks
...
syscall_return_via_sysret
...
swapgs_restore_regs_and_return_to_usermode
```

同时确认当前构建中真正执行 `sysretq` 和 `iretq` 的位置。宏展开受 PTI、paravirt 等配置影响，因此以当前 `vmlinux` 反汇编为准。

## 5. Case A：普通 syscall 观察 SYSRET 快路径

guest 中准备一个持续执行 `getpid()` 或 raw `SYS_getpid` 的最小程序。kernel-GDB 设置：

```gdb
break syscall_return_via_sysret
break swapgs_restore_regs_and_return_to_usermode
continue
```

只统计目标测试进程的命中情况。多任务 guest 中这两个入口会被其他进程频繁触发，实际调试时应结合当前 task/PID 条件断点，或者先在目标 syscall 的 `do_syscall_64()` 调用实例上单步到返回侧。

在命中 `syscall_return_via_sysret` 时检查：

```gdb
info registers rcx r11 rsp
x/21gx $rsp
```

`pt_regs` 的具体字段偏移必须按当前 Linux 5.10 `struct pt_regs` 和当前断点位置确认，不能在恢复了一部分寄存器后仍机械地把 `$rsp` 当作 frame 起点。

预期控制流：

```text
do_syscall_64
  -> syscall_exit_to_user_mode
  -> entry_SYSCALL_64 return side
  -> eligibility checks pass
  -> syscall_return_via_sysret
  -> ...
  -> sysretq
```

## 6. Case B：用 TF 强制 SYSRET eligibility 失败

Linux 5.10 返回侧显式拒绝 `X86_EFLAGS_TF`。因此 TF 是比“制造 non-canonical RIP”安全得多的对照条件。

推荐用用户态 debugger/ptrace 对测试线程建立单步状态，使其最终用户 RFLAGS 中 TF=1；随后让线程执行目标 syscall。不要直接篡改内核栈上的 `pt_regs` 作为第一选择，因为那会把“验证现有机制”变成“调试器人工破坏现场”。

kernel-GDB 在返回侧 eligibility check 附近暂停后，先确认最终 flags：

```gdb
# 下面只表示观察目标；实际偏移按当前 vmlinux/pt_regs 确认
p/x <pt_regs.flags>
```

确认 TF 位存在，再继续执行。预期分流为：

```text
final pt_regs.flags contains TF
        |
        v
SYSRET eligibility check fails
        |
        v
swapgs_restore_regs_and_return_to_usermode
        |
        v
full IRET frame
        |
        v
iretq
```

关键观察点是：**慢路径断点应在任何 `sysretq` 执行之前命中。**

单步会产生调试 trap，用户态 debugger 本身也会改变执行节奏，因此本 case 的目标只是验证 TF 与返回路径选择，不在这里展开 `#DB` 异常处理；异常入口属于 A15。

## 7. Case C：负 errno 不应自动导致 IRET

再增加一个返回普通负 errno 的 syscall，例如对确定无效的参数调用一个不会破坏系统状态的接口。观察 `pt_regs->ax < 0` 时的返回路径。

如果 RIP、CS、SS、flags 等最终现场仍满足快路径条件，负 errno 本身不应阻止进入 `syscall_return_via_sysret`。

这个 case 用来排除一个常见误解：

```text
syscall success/failure
!=
SYSRET/IRET selection
```

## 8. 建议记录表

实际执行时记录：

| Case | `regs->ax` | `regs->ip` | `regs->flags` | SYSRET label | slow-path label | 最终返回指令 |
|---|---:|---:|---:|---|---|---|
| 普通 getpid | 待实测 | 待实测 | 待实测 | 待实测 | 待实测 | 待实测 |
| TF 单步 | 待实测 | 待实测 | TF=1，待实测 | 待实测 | 待实测 | 待实测 |
| negative errno | 待实测 | 待实测 | 待实测 | 待实测 | 待实测 | 待实测 |

不要把预期结果填写成实测结果。

## 9. 配置条件

执行前记录：

```bash
uname -a
cat /proc/cmdline
grep -E 'CONFIG_X86_64|CONFIG_X86_5LEVEL|CONFIG_PAGE_TABLE_ISOLATION|CONFIG_PARAVIRT_XXL|CONFIG_DEBUG_ENTRY' .config
```

重点注意：

- `CONFIG_X86_5LEVEL`/LA57 会影响 canonical RIP 检查；
- PTI 会改变 trampoline stack 和 CR3 切换序列；
- paravirt 会改变部分返回宏展开；
- `CONFIG_DEBUG_ENTRY` 会给慢路径增加额外检查。

因此实验结论应比较**控制流语义**，而不是要求所有构建得到逐字节相同的返回指令序列。

## 10. 当前执行状态

当前课程维护环境没有可停机调试的 Linux 5.10 guest、与运行内核匹配的 `vmlinux` 和 kernel-GDB 会话，因此本实验尚未执行动态断点验证。

本次已经完成：

- 根据 Linux 5.10 已核验源码确定 SYSRET/IRET 分流观察点；
- 设计普通 SYSRET、TF 强制慢路径和 negative errno 三组对照；
- 明确 KASLR、PTI、paravirt 与 `pt_regs` 断点位置对实验的影响；
- 明确禁止把预期控制流伪装为实测结果。

具备匹配的 Linux 5.10 kernel-debug 环境后，按本文件记录真实断点、寄存器和最终返回指令即可完成动态验收。

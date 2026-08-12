# A14 实验：观察 `do_syscall_64()` 分派前后的 `pt_regs`

本实验对应 A14 第二部分 [`../../docs/14-do-syscall-64-dispatch-and-return-value.md`](../../docs/14-do-syscall-64-dispatch-and-return-value.md)。目标不是再次验证用户态 syscall ABI，而是在 Linux 5.10 内核入口内部直接观察：

```text
entry_SYSCALL_64 预置 regs->ax = -ENOSYS
        |
        v
do_syscall_64(nr, regs)
        |
        +-- 有效 nr：sys_call_table[nr](regs) 的返回值覆盖 regs->ax
        |
        `-- 无效 nr：没有正常表项调用，regs->ax 保留 -ENOSYS
```

同时验证 `orig_ax` 与 `ax` 的生命周期不同。

> 本实验需要隔离的 Linux 5.10 x86-64 guest、与正在运行内核严格匹配且带调试符号的 `vmlinux`，以及 QEMU gdbstub/GDB 或等价的内核级调试环境。不要在生产系统上为本实验停住内核。

## 1. 要验证的问题

至少完成下面四项观察：

1. 有效 syscall 进入 `do_syscall_64()` 时，`regs->orig_ax` 保存原始 syscall number；
2. 在 syscall table 调用前，`regs->ax` 仍是入口预置的 `-ENOSYS`；
3. 有效 syscall 返回后，`regs->ax` 被具体系统调用返回值覆盖，而 `regs->orig_ax` 仍保留原始请求号；
4. 对一个超出原生 syscall table 范围、且不命中启用时 x32 分支的编号，不发生正常 `sys_call_table[nr]` 调用，`regs->ax` 保持 `-ENOSYS`。

这里观察的是 raw kernel return slot。libc 把负 errno 转成 `-1` 并设置 `errno` 的行为属于用户态接口，不在本实验的内核断点中发生。

## 2. 为什么需要内核调试器

用户态程序只能看到返回后的 `%rax`，无法证明 `regs->ax` 在入口时先被预置为 `-ENOSYS`，也无法直接区分：

```text
orig_ax = 原始请求号
ax      = 可被系统调用结果覆盖的返回槽
```

因此本实验把观察点放在 Linux 5.10 `arch/x86/entry/common.c:do_syscall_64()` 内部。源码行断点只是起点；实际断点地址必须以当前 `vmlinux` 的反汇编为准，因为优化、编译器和配置都会改变机器指令布局。

## 3. 准备 guest

建议条件：

```text
Linux kernel 5.10.x
CONFIG_DEBUG_INFO=y
x86-64
QEMU/KVM guest
与 guest 完全匹配的未剥离 vmlinux
```

启动 QEMU 时可使用 gdbstub，例如加入：

```text
-s -S
```

其中 `-s` 在 TCP 1234 提供 gdbstub，`-S` 让 CPU 在启动时暂停。完成启动调试配置后再让 guest 正常进入用户态。

若启用了 KASLR，需要让 GDB 获得正确的运行时符号地址；教学环境最简单的做法通常是在隔离 guest 的 kernel command line 临时加入 `nokaslr`。这只是为了降低符号定位复杂度，不是 syscall 机制要求。

## 4. 用户态触发器

在 guest 中准备下面的最小程序：

```c
#include <errno.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <unistd.h>

static long raw_syscall0(long nr)
{
    register long rax asm("rax") = nr;

    asm volatile("syscall"
                 : "+a"(rax)
                 :
                 : "rcx", "r11", "memory");
    return rax;
}

int main(void)
{
    long good = raw_syscall0(SYS_getpid);
    long bad = raw_syscall0(0x7fffffffL);

    printf("good=%ld bad=%ld expected_bad=%d\n",
           good, bad, -ENOSYS);
    return 0;
}
```

构建：

```bash
gcc -O0 -g -Wall -Wextra -o trigger trigger.c
```

运行时预期用户态结果满足：

```text
good > 0
bad == -ENOSYS
```

不要用 shell `$?` 验证 `-ENOSYS`；shell 退出状态不能完整表达 64 位有符号 syscall 返回值。

## 5. 先从当前 `vmlinux` 找实际观察点

在 host 上：

```bash
gdb vmlinux
(gdb) target remote :1234
(gdb) disassemble /m do_syscall_64
```

也可以先用：

```bash
objdump -drS vmlinux | less
```

定位 `do_syscall_64`。

需要找到两个语义观察点，而不是复制某台机器的固定地址：

```text
A. 原生 syscall table 调用之前
B. sys_call_table[nr](regs) 返回并写入 regs->ax 之后
```

Linux 5.10 源码基线对应：

```c
if (likely(nr < NR_syscalls)) {
    nr = array_index_nospec(nr, NR_syscalls);
    regs->ax = sys_call_table[nr](regs);
}
```

`CONFIG_X86_X32_ABI=y` 时后面还有 x32 分派，所以无效编号必须同时避开该分支；`0x7fffffff` 用于本实验就是为了清楚地落入无有效分派的情况。

## 6. 观察 `pt_regs`

在 `do_syscall_64()` 入口停住后，优先让 GDB 使用类型信息，而不是手算偏移：

```gdb
p/x nr
p/x *regs
p/d regs->orig_ax
p/d regs->ax
```

对 `SYS_getpid`，在 table call 之前应看到类似关系：

```text
regs->orig_ax == SYS_getpid
regs->ax      == -ENOSYS
```

单步越过实际 table call 和 `regs->ax` 写回后再次检查：

```gdb
p/d regs->orig_ax
p/d regs->ax
```

应看到：

```text
regs->orig_ax == SYS_getpid
regs->ax      == 当前任务 pid
```

关键点不是 pid 的具体数值，而是 `orig_ax` 没有被返回值覆盖，而 `ax` 已从 `-ENOSYS` 变为系统调用结果。

## 7. 观察无效 syscall

让 trigger 执行第二次 raw syscall，并再次在 `do_syscall_64()` 停住。

入口应满足：

```text
regs->orig_ax == 0x7fffffff
regs->ax      == -ENOSYS
```

继续执行并确认原生：

```c
if (likely(nr < NR_syscalls))
```

不成立。若内核启用了 `CONFIG_X86_X32_ABI`，还应确认该编号没有进入 x32 有效表项。到 `syscall_exit_to_user_mode(regs)` 前再次查看：

```gdb
p/d regs->orig_ax
p/d regs->ax
```

预期：

```text
regs->orig_ax == 0x7fffffff
regs->ax      == -ENOSYS
```

这直接验证了 `-ENOSYS` 并不是“无效编号分支最后额外赋值”的简单模型，而是入口默认值在没有有效 table call 覆盖时继续保留下来。

## 8. 需要记录的结果

实验记录至少包含：

```text
Linux 版本：
内核 .config 中 CONFIG_X86_X32_ABI：
编译器版本：
GDB 版本：
有效 syscall number：
有效 syscall table call 前 orig_ax/ax：
有效 syscall table call 后 orig_ax/ax：
无效 syscall number：
无效 syscall exit 前 orig_ax/ax：
```

如果实际内核启用了 ptrace/seccomp/audit 等 entry work，并导致工作 `nr` 被修改，不要把这种现象改写成普通主线。记录 `nr` 与 `orig_ax` 的实际差异，再回到 `syscall_enter_from_user_mode()` 分析原因。

## 9. 当前维护环境的执行边界

本实验文档已经按 Linux 5.10 的 `do_syscall_64()` 主线和 `pt_regs` 字段语义设计，但当前仓库维护环境没有可启动并停机调试的 Linux 5.10 guest、匹配 `vmlinux` 和 kernel GDB 会话，因此本次不能诚实地给出实际内核断点输出。

这不影响实验成为可执行步骤，但下面这些结果仍属于**待真实环境验证**：

```text
当前具体 vmlinux 中两个观察点的机器地址
当前配置下 nr 所在的实际寄存器/栈位置
真实断点中的 orig_ax/ax 数值
CONFIG_X86_X32_ABI 的实际配置值
```

后续一旦具备匹配环境，应优先执行本实验，而不是根据教程预期值补写“实测结果”。

## 10. 与后续返回路径的边界

本实验停在 `syscall_exit_to_user_mode(regs)` 前后对返回槽的观察。它不试图验证：

```text
exit-to-user work
SYSRETQ 快路径条件
IRETQ 回退条件
返回侧寄存器恢复
```

这些属于 A14 下一部分。这样可以保持一个实验只回答一个明确问题：**syscall number 如何经过分派，`orig_ax` 与 `ax` 又如何经历不同的生命周期。**

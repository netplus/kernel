# A15 `#DE/#GP` 实验预期分析

本文对应 [`README.md`](README.md) 与 [`../../docs/15-idt-exception-entry-and-pt-regs.md`](../../docs/15-idt-exception-entry-and-pt-regs.md)。这里固定实验的验收基线，不把尚未执行的 kernel-GDB 观察写成实测结果。

## 1. 先区分三个现场

本实验会看到三个不同阶段的状态，不能混为一谈：

1. CPU 刚完成异常入口后的 hardware frame；
2. Linux 5.10 普通异常入口完成规范化并形成 `struct pt_regs` 后的内核现场；
3. Linux 将同步异常转换成 signal 后，用户态 handler 收到的 `ucontext_t`。

第 1、2 阶段需要匹配 Linux 5.10 `vmlinux` 的 kernel-GDB 才能直接观察。第 3 阶段可以由 `trigger` 在普通用户态直接打印。

## 2. `#DE`：没有 hardware error code

`trigger_de()` 中的关键指令是：

```asm
idivq %rcx
```

实验把 `%rcx` 清零，因此整数除法触发 divide error (`#DE`)。x86-64 对 `#DE` 不压入 error code。

从 CPL3 进入 CPL0 时，在 Linux 软件入口补槽之前，硬件返回现场应包含：

```text
低地址 / 当前 RSP
+0   RIP
+8   CS
+16  RFLAGS
+24  user RSP
+32  user SS
高地址
```

Linux 5.10 的普通 no-error-code `idtentry` 再执行 synthetic：

```asm
pushq $-1
```

因此进入共同错误入口前应变成：

```text
+0   -1                 <- Linux synthetic slot
+8   RIP
+16  CS
+24  RFLAGS
+32  user RSP
+40  user SS
```

随后保存 GPR 并形成 `struct pt_regs`。本实验应验收：

```text
regs->orig_ax == -1
regs->ip      == faulting idivq 的用户 RIP
regs->cs      == 用户代码段 selector
regs->flags   == fault 时用户 RFLAGS
regs->sp      == fault 时用户 RSP
regs->ss      == 用户数据段 selector
```

这里的 `orig_ax == -1` 不是 CPU 提供的 `#DE` error code；它是 Linux 为统一普通异常入口布局使用的 sentinel。

## 3. `#GP`：CPU 提供 hardware error code

`trigger_gp()` 执行：

```asm
mov $0xffff, %eax
mov %ax, %ds
```

在 CPL3 尝试把不合法 selector 装入 `%ds`，预期触发 general protection (`#GP`)。与 `#DE` 不同，`#GP` 属于 CPU 提供 error code 的异常。

从 CPL3 进入 CPL0 后，在 Linux 尚未整理参数时，入口栈应是：

```text
低地址 / 当前 RSP
+0   hardware error code
+8   RIP
+16  CS
+24  RFLAGS
+32  user RSP
+40  user SS
高地址
```

因此本路径不应再出现第二个 synthetic `pushq $-1`。hardware error code 的具体数值以实际 guest 观察为准；课程验收点是它确实来自 CPU 提供的 slot，而不是把某个数值写死。

Linux 5.10 在进入 `exc_general_protection()` 前会把该 slot 的值取作 C handler 的第二参数，并把对应 `pt_regs` 槽规范化为 `-1`。因此在 C handler 调用边界应验收：

```text
%rdi          == struct pt_regs *regs
%rsi          == 原 hardware error code
regs->orig_ax == -1
regs->ip      == faulting mov %ax,%ds 的用户 RIP
```

这说明 `orig_ax` 这个槽在异常入口中的作用不能简单解释为“保存 error code”：hardware error code 只是在入口早期暂时占用该位置，随后被转移为显式 C 参数。

## 4. `#DE` 与 `#GP` 的关键对照

| 观察点 | `#DE` | `#GP` |
| --- | --- | --- |
| CPU 是否压 error code | 否 | 是 |
| Linux 是否补 synthetic `-1` | 是 | 否 |
| 共同入口前栈顶 | `-1` | hardware error code |
| C handler 是否有 error-code 参数 | 否 | 是 |
| handler 调用前 `regs->orig_ax` | `-1` | 已规范化为 `-1` |
| 最终 `pt_regs` 布局 | 相同 | 相同 |

统一布局的意义在于：后续公共入口代码可以按固定偏移访问 GPR 和 `ip/cs/flags/sp/ss`，而不必让整个 `pt_regs` 结构随异常类型变化。

## 5. signal frame 能证明什么

用户态 handler 打印的 `REG_RIP/REG_RSP/REG_EFL` 来自 Linux 构造的 signal context，而不是 CPU 最初的异常入口栈。

对于本实验中的同步 fault，在 handler 尚未修改 `REG_RIP` 之前，预期：

```text
REG_RIP = faulting instruction 的地址
REG_RSP = fault 时用户 RSP
REG_EFL = fault 时用户 RFLAGS
```

它们应能与 kernel-GDB 中最终 `pt_regs->ip/sp/flags` 对应。这个对照可以支持“Linux 保留了用户 fault 现场”这一结论，但不能单独证明：

- `#DE` 没有 hardware error code；
- `#DE` 的 `-1` 是 Linux synthetic slot；
- `#GP` error code 曾位于入口栈顶；
- `#GP` error code 后来被移动到 `%rsi`。

这些结论必须由架构规则、Linux 5.10 源码核验和内核侧观察共同支持。

## 6. handler 跳过 faulting instruction 的边界

当前 `trigger.c` 在 signal handler 中直接增加 `REG_RIP`：

```text
#DE: +3
#GP: +2
```

因此运行前必须用 `make disasm` 确认当前 binary 中真正的 faulting instruction 仍分别编码为：

```text
48 f7 f9    idivq %rcx
8e d8       mov %ax,%ds
```

只有确认编码长度后，继续执行第二个 case 才是有效实验。源码注释不是机器码事实的替代品。

## 7. 当前执行状态

课程维护环境当前没有匹配的 Linux 5.10 guest、带调试信息的对应 `vmlinux` 和 kernel-GDB 会话，因此本文只给出可验收的预期关系，没有填写伪造的寄存器值、selector 值或 `#GP` error code。

具备环境后，实验完成标准是同时保存：

1. `make disasm` 的实际两条 faulting instruction；
2. 用户态 `SIGFPE/SIGSEGV` context 输出；
3. `#DE` 入口 synthetic `-1` slot；
4. `#GP` hardware error-code slot；
5. `#GP` C handler 调用前 `%rsi` 与 `regs->orig_ax`；
6. 两个 case 的 `pt_regs->ip/sp/flags` 与用户态 signal context 对照。

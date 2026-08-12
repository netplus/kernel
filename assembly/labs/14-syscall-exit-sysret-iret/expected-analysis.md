# A14 第三部分实验预期分析：SYSRET 快路径与 IRET 回退

本文对应 [`README.md`](README.md) 中的 Linux 5.10 kernel-GDB 实验。这里记录的是根据 Linux v5.10 源码得到的**预期控制流和验收条件**，不是当前环境的动态实测结果。真实运行时应把断点命中、寄存器值和最终返回指令单独记录，不能用本文内容代替实验数据。

## 1. 源码基线

本实验只以 Linux kernel v5.10 x86-64 为基线。关键位置是：

```text
arch/x86/entry/entry_64.S
    entry_SYSCALL_64
    syscall_return_via_sysret
    swapgs_restore_regs_and_return_to_usermode
    native_irq_return_iret

arch/x86/entry/common.c
    do_syscall_64()

kernel/entry/common.c
    syscall_exit_to_user_mode()
```

详细源码事实见 [`../../source-paths/14-syscall-exit-sysret-iret-linux-5.10.md`](../../source-paths/14-syscall-exit-sysret-iret-linux-5.10.md)。

## 2. Case A：普通 syscall

对一个未被 ptrace、signal 或其他 exit-to-user work 修改最终用户现场的普通 64-bit syscall，预期在 `do_syscall_64()` 返回后依次满足：

```text
RCX == pt_regs->ip
candidate RIP is canonical
pt_regs->cs == __USER_CS
R11 == pt_regs->flags
(R11 & (RF | TF)) == 0
pt_regs->ss == __USER_DS
```

这些条件全部成立时，控制流应落到：

```text
syscall_return_via_sysret
```

该 label 位于 `POP_REGS pop_rdi=0 skip_r11rcx=1` 之前，因此**刚命中该 label 时** `%rsp` 仍指向尚未弹出的 `struct pt_regs`。此时可以按当前 v5.10 `pt_regs` 布局检查 frame。单步执行 `POP_REGS` 以后，不能继续把新的 `%rsp` 当作原始 `pt_regs` 起点。

随后 Linux 恢复普通 GPR，保留 SYSRET 所需的 `%rcx/%r11`，切到 trampoline stack，在需要时切换 user CR3，恢复 user `%rdi/%rsp` 和 GS 状态，最终执行 SYSRET 返回动作。

验收条件：

- 目标 syscall 的返回实例命中 `syscall_return_via_sysret`；
- 在该实例上没有先进入 `swapgs_restore_regs_and_return_to_usermode`；
- 当前构建的反汇编确认后续最终执行 SYSRET 路径；
- 记录命中时的 `ip/flags/sp/orig_ax/ax`，而不是只记录 label 名称。

## 3. Case B：最终 RFLAGS 中 TF=1

Linux v5.10 在返回侧显式执行等价于：

```text
testq $(X86_EFLAGS_RF | X86_EFLAGS_TF), %r11
jnz swapgs_restore_regs_and_return_to_usermode
```

因此，如果 ptrace/debug single-step 使**最终** `pt_regs->flags` 中 TF=1，预期 SYSRET eligibility check 失败，并在任何 SYSRET 指令执行之前进入：

```text
swapgs_restore_regs_and_return_to_usermode
```

慢路径随后恢复普通寄存器，把：

```text
RIP
CS
RFLAGS
RSP
SS
```

复制成完整 IRET frame；native x86-64 路径最终到达 `native_irq_return_iret` 的 `iretq`。

这里需要验证的是“最终现场导致返回路径改变”，而不是调试异常 `#DB` 本身。TF 引发的异常处理属于 A15。

验收条件：

- 在 eligibility check 前确认目标线程最终 `pt_regs->flags` 的 TF 位确实为 1；
- 目标实例进入 slow-path label；
- 在进入 slow path 之前没有执行 SYSRET；
- 当前 native 构建最终观察到 IRET 返回动作。

## 4. Case C：negative errno

系统调用返回值保存在 `pt_regs->ax`，但 Linux v5.10 的 SYSRET eligibility checks 检查的是返回 RIP、CS、RFLAGS、SS 等最终用户现场，并不以 `regs->ax` 的正负决定 SYSRET/IRET。

因此，一个安全地返回普通负 errno、同时没有改变其他返回现场的 syscall，预期仍可满足 Case A 的快路径条件：

```text
regs->ax < 0
        |
        | does not itself select IRET
        v
SYSRET eligibility checks
        |
        +--> pass -> syscall_return_via_sysret
```

验收条件不是“负 errno 必须 SYSRET”，而是确认：**负 errno 本身不是 slow-path 条件**。如果实验中同时存在 signal、ptrace、TF/RF 或其他现场修改，仍可能因为那些独立条件进入 IRET。

## 5. 三组实验应形成的对照

| 观察维度 | Case A：普通 syscall | Case B：TF=1 | Case C：negative errno |
|---|---|---|---|
| `regs->ax` | 正常返回值 | 与目标 syscall 相符 | 负 errno |
| 最终 TF | 0 | 1 | 通常为 0 |
| SYSRET eligibility | 预期通过 | 必须失败 | 不由 errno 决定 |
| `syscall_return_via_sysret` | 预期命中 | 不应作为该实例的最终分支 | 若其余条件干净则可命中 |
| slow path | 不应因普通现场触发 | 应命中 | 不应仅因负 errno 触发 |
| 架构返回 | SYSRET 路径 | native IRET 路径 | 取决于最终现场 |

## 6. 配置和观测边界

以下因素会改变具体指令序列，但不改变本实验要验证的控制流语义：

- `CONFIG_X86_5LEVEL` 与运行 CPU 的 LA57 能力影响 canonical-address 检查；
- `CONFIG_PAGE_TABLE_ISOLATION` 影响 trampoline stack 与 CR3 切换；
- `CONFIG_PARAVIRT_XXL` 影响部分 user-GS/SYSRET 宏展开；
- `CONFIG_DEBUG_ENTRY` 会给慢路径增加检查；
- KASLR 会改变运行时符号地址。

因此断点必须来自**正在运行的 v5.10 内核对应的 `vmlinux` 反汇编**。不能从另一台机器或另一份配置复制固定地址。

## 7. 当前执行状态

当前课程维护环境没有可停机调试的 Linux 5.10 guest、与运行内核完全匹配的 `vmlinux` 和 kernel-GDB 会话，因此本文只完成源码驱动的预期分析，没有填写任何动态观测值。

具备实验环境后，第三部分的动态验收应以 `README.md` 的记录表为准，补充实际断点命中、`pt_regs` 字段和最终返回指令；若实测与本文不一致，应优先重新核对运行内核版本、配置、反汇编位置和断点时刻，而不是修改结果去迎合预期。
# Linux 5.10 x86-64 `#DE` / `#GP` 入口、error code 与 `pt_regs` 源码事实核验

本文继续 A15 的入口事实核验，选择两个普通、非 IST 的代表性异常做逐条对照：

- `#DE`（Divide Error，vector 0）：CPU **不压入** error code；
- `#GP`（General Protection，vector 13）：CPU **压入** error code。

目标不是展开异常的业务处理，而是确认 Linux 5.10 如何把两种不同的硬件入口现场规范化为同一种 `struct pt_regs` 布局，并把真正的 `#GP` error code 作为第二个 C 参数交给 handler。

缺页 `#PF` 留给 A16；`#DB/#MC/#DF` 等 IST/paranoid 路径留给 A15 后续单元。

## 1. 版本与源码基线

本文件只以 upstream Linux v5.10 为实现基线：

```text
arch/x86/include/asm/idtentry.h
arch/x86/entry/entry_64.S
arch/x86/entry/calling.h
arch/x86/include/asm/ptrace.h
arch/x86/kernel/traps.c
```

关键生成关系为：

```text
DECLARE_IDTENTRY(...)
        ↓ __ASSEMBLY__ 形式展开
idtentry vector, asm_<func>, <func>, has_error_code=0

DECLARE_IDTENTRY_ERRORCODE(...)
        ↓ __ASSEMBLY__ 形式展开
idtentry vector, asm_<func>, <func>, has_error_code=1
```

因此具体入口符号不是手写的独立函数，而是 `entry_64.S` 包含 `asm/idtentry.h` 后由宏生成。

## 2. 代表一：`#DE` 没有硬件 error code

Linux 5.10 在 `arch/x86/include/asm/idtentry.h` 中声明：

```text
DECLARE_IDTENTRY(X86_TRAP_DE, exc_divide_error)
```

这属于文件明确标注的 `No hardware error code` 一组。64 位汇编侧因此生成的核心形态可简化为：

```text
asm_exc_divide_error:
        ASM_CLAC
        pushq $-1
        call error_entry
        ...
        movq %rsp, %rdi
        call exc_divide_error
        jmp error_return
```

这里的 `pushq $-1` 很关键：它**不是 CPU 的 error code**，而是 Linux 为统一入口布局补出的 `ORIG_RAX` 槽。注释直接写为 `ORIG_RAX: no syscall to restart`。

所以从 CPL3 发生 `#DE` 时，可以先把入口栈抽象为：

```text
CPU 已建立的返回 frame
    RIP
    CS
    RFLAGS
    RSP
    SS

Linux 再补
    -1          <- 后续 pt_regs.orig_ax
```

注意：上图表达字段关系，不表示地址由低到高的绘图方向；x86 栈仍向低地址增长。

`idtentry_body` 对 `has_error_code=0` 不读取第二参数，C handler 原型只有：

```c
void exc_divide_error(struct pt_regs *regs)
```

`arch/x86/kernel/traps.c` 中 `DEFINE_IDTENTRY(exc_divide_error)` 最终进入 `do_error_trap(..., 0, ...)`；这里传入的 0 是 Linux C 层针对 `#DE` 的语义值，不能反推成“CPU 压了一个 0 error code”。CPU 根本没有为 `#DE` 压 error code。

## 3. 代表二：`#GP` 由 CPU 提供 error code

同一头文件把 `#GP` 放在 `Error code pushed by hardware` 一组：

```text
DECLARE_IDTENTRY_ERRORCODE(X86_TRAP_GP, exc_general_protection)
```

因此生成入口使用 `has_error_code=1`。此时 `idtentry` **不会**执行 `pushq $-1`，因为硬件 error code 已经占据了统一布局中 `ORIG_RAX` 所在的位置。

从 CPL3 进入时，进入 Linux stub 时可抽象为：

```text
CPU 已建立
    error code  <- 暂时占用后续 pt_regs.orig_ax 的槽
    RIP
    CS
    RFLAGS
    RSP
    SS
```

随后 `error_entry` 保存 GPR 后，`idtentry_body` 执行：

```text
movq ORIG_RAX(%rsp), %rsi
movq $-1, ORIG_RAX(%rsp)
```

第一条把 CPU 提供的 `#GP` error code 取出作为 System V AMD64 C ABI 的第二参数 `%rsi`；第二条再把 `pt_regs.orig_ax` 改写为 `-1`，表示这里不是一个可重启的 syscall。

之后调用：

```c
void exc_general_protection(struct pt_regs *regs,
                            unsigned long error_code)
```

因此必须区分两个时刻：

```text
刚进入 error-code exception stub：
    ORIG_RAX 位置暂存 CPU error code

进入 C handler 前：
    %rsi             = CPU error code
    regs->orig_ax    = -1
```

不能在 C handler 中把 `regs->orig_ax` 当作 `#GP` error code；真正的 error code 已经通过第二参数传递。

## 4. 两条路径为什么最终可以共用 `pt_regs`

`error_entry` 的共同入口首先执行：

```text
cld
PUSH_AND_CLEAR_REGS save_ret=1
```

随后根据保存的 CS 判断异常来自用户态还是内核态。来自用户态时，它完成 `SWAPGS`、必要的 kernel CR3 切换，并通过 `sync_regs` 把入口现场同步到真正的 thread stack，最终让 `%rsp` 指向可作为 `struct pt_regs *` 使用的布局。

这里的设计要点是：在 `error_entry` 保存 GPR **之前**，`idtentry` 已经保证硬件 frame 前方总有一个 8-byte 槽：

```text
#DE: Linux pushq $-1
#GP: CPU pushed error code
```

于是 `PUSH_AND_CLEAR_REGS` 可以对两者使用相同的寄存器保存布局。

Linux 5.10 x86-64 `struct pt_regs` 的相关尾部字段为：

```text
r15 ... di
orig_ax
ip
cs
flags
sp
ss
```

从 `%rsp == &regs->r15` 时按 8-byte 槽计算：

```text
orig_ax : 15 * 8 = 120
ip      : 16 * 8 = 128
cs      : 17 * 8 = 136
flags   : 18 * 8 = 144
sp      : 19 * 8 = 152
ss      : 20 * 8 = 160
sizeof  : 21 * 8 = 168 bytes
```

这与 A14 使用的 `pt_regs` 布局一致，但 `orig_ax` 的入口语义不同：

```text
syscall: syscall number
exception before normalization: hardware error code or Linux synthetic -1
ordinary exception C handler: -1
```

因此 `orig_ax` 是一个为了统一 entry frame 而复用的位置，不能脱离入口类型解释。

## 5. `error_entry` 不是 CPU 自动动作

这一点需要在 A15 正文中反复保持清晰：

```text
CPU / x86-64 architecture
    根据 IDT gate 转移控制
    保存返回控制状态
    特定异常额外压 error code

Linux idtentry stub
    无 error code 时补 -1

Linux error_entry
    保存 GPR
    判断 user/kernel 来源
    处理 GS/CR3
    必要时同步到 task stack

Linux idtentry_body
    构造 C ABI 参数
    error-code 异常把 error code 从 orig_ax 槽搬到 %rsi
    把 orig_ax 规范化为 -1
```

把 `PUSH_AND_CLEAR_REGS`、`swapgs` 或 `sync_regs` 描述成“CPU 自动压栈”都是错误的。

## 6. `#DE` 与 `#GP` 的逐步对照

| 阶段 | `#DE` | `#GP` |
| --- | --- | --- |
| CPU 是否提供 error code | 否 | 是 |
| Linux `idtentry` 的 `has_error_code` | 0 | 1 |
| stub 是否 `pushq $-1` | 是 | 否 |
| `error_entry` 前统一槽内容 | `-1` | CPU error code |
| GPR 保存 | `PUSH_AND_CLEAR_REGS` | `PUSH_AND_CLEAR_REGS` |
| C handler 参数 1 | `%rdi = regs` | `%rdi = regs` |
| C handler 参数 2 | 无 | `%rsi = error_code` |
| handler 前 `regs->orig_ax` | `-1` | 被改写为 `-1` |

这个对照是 A15 后续理解所有普通异常入口的基础。特殊 vector 不能机械套用这张表；例如 `#PF` 是 raw error-code entry，而 `#DB/#MC/#DF` 还有 IST/paranoid 特殊处理。

## 7. user -> kernel 与 kernel -> kernel 的边界

本文件用 CPL3 -> CPL0 作为最直观的 frame 示例，因为此时硬件返回 frame 包含用户 `SS:RSP`。但同一异常也可能发生在内核态。

Linux 5.10 `error_entry` 会检查保存的 CS：

```text
testb $3, CS+8(%rsp)
```

用户态来源会走 `SWAPGS`、kernel CR3 和 `sync_regs` 路径；内核态来源则进入 `.Lerror_kernelspace` 的专门判断。也就是说：

- `idtentry` 的 error-code 规范化思想对两类入口都成立；
- 不能把 CPL3 -> CPL0 时的 `SS:RSP` 保存/栈切换过程直接泛化到 kernel -> kernel；
- `swapgs` 也不是“每次异常入口固定执行一次”，必须由实际来源和特殊入口状态决定。

A15 正文第一部分只需要先建立普通 user-mode exception 的完整模型，再用这一边界提醒读者，不应在此提前展开 paranoid entry。

## 8. 本次核验结论

Linux 5.10 对普通 `#DE` 与 `#GP` 的入口差异可以压缩为一句话：

> `#DE` 没有硬件 error code，因此 Linux 先压入 `-1` 占据统一的 `orig_ax` 槽；`#GP` 已有 CPU error code，因此直接利用该槽，保存完 GPR 后再把 error code 搬到 C handler 的第二参数，并把 `orig_ax` 规范化为 `-1`。

这说明“有无硬件 error code”的差异主要存在于进入统一 entry frame **之前和参数交接时**；一旦完成规范化，后续 C 代码可以稳定地接收 `struct pt_regs *`。

下一最小单元应基于这份事实核验编写 A15 第一部分正式教程，把 IDT gate、CPL3 -> CPL0 硬件 frame、`#DE/#GP` 对照、`error_entry` 与 `pt_regs` 连成一条教学主线。TSS/IST 仍留给后续部分。
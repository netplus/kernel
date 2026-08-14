# A19 实验：x86-64 长模式切换的静态与动态验证

本实验服务于 [`../../docs/19-long-mode-transition-basics.md`](../../docs/19-long-mode-transition-basics.md)，验证的不是完整 Linux 启动，而是 Linux 5.10 `arch/x86/boot/compressed/head_64.S` 中 `startup_32 -> startup_64` 所依赖的最小模式切换关系。

源码事实基线见 [`../../source-paths/19-long-mode-transition-linux-5.10.md`](../../source-paths/19-long-mode-transition-linux-5.10.md)。

## 1. 要验证的问题

需要把下面几件事分别取证，而不是寻找一条“进入 64 位”的神奇指令：

1. `startup_32` 在打开 paging 前已经准备 GDT、`CR4.PAE`、early page tables、`CR3` 和 `IA32_EFER.LME`；
2. 写 `CR0.PG|CR0.PE` 后 IA-32e 条件已经激活，但当前 instruction stream 仍受旧 `CS` 属性约束；
3. Linux 5.10 这条具体路径实际通过预构造 far-return frame 和 `lret` 重新装载 `CS`；
4. `lret` 的目标是 `.code64 startup_64`；
5. 进入 `startup_64` 后，当前 code segment 必须具有 `L=1` 的 64-bit code 属性。

实验分为静态验证和可选的 QEMU/GDB 动态验证。静态部分可以在具有 Linux 5.10 源码及正常 x86 Kbuild 工具链的环境中完成；动态部分需要可启动的对应 compressed kernel 或专门的隔离启动 guest。

## 2. 环境

建议：

```text
Linux kernel source: upstream v5.10
architecture: x86-64
binutils: objdump/readelf/nm
QEMU: qemu-system-x86_64（动态部分）
GDB: 支持 x86/x86-64 remote debugging（动态部分）
```

先确认源码版本，不要用当前发行版的新内核源码替代：

```bash
git describe --tags --always
# 目标应为 v5.10 或明确基于 v5.10 的工作树
```

## 3. 静态验证一：从源码固定状态转换顺序

在 v5.10 源码树中：

```bash
cd arch/x86/boot/compressed
sed -n '/SYM_FUNC_START(startup_32)/,/SYM_FUNC_START_LOCAL_NOALIGN(.Lrelocated)/p' head_64.S
```

不要只 grep 单条指令。按控制流顺序记录以下证据：

```text
lgdt
CR4.PAE write
page-table construction
CR3 write
MSR_EFER rdmsr/wrmsr and LME set
push __KERNEL_CS
push startup_64 target
CR0 write enabling PE|PG
lret
.code64 startup_64
```

验收重点是先后依赖，而不是源码行号；行号可能随发行版 backport 改变。

## 4. 静态验证二：检查 GDT 与 64-bit code descriptor

定位 compressed boot path 使用的 GDT 和 `__KERNEL_CS` 定义：

```bash
grep -nE 'gdt|__KERNEL_CS|startup_64' arch/x86/boot/compressed/head_64.S
grep -n '__KERNEL_CS' arch/x86/include/asm/segment.h
```

需要回答：

- `lgdt` 加载的是哪一个 descriptor table；
- far-return frame 中压入的 selector 是什么；
- selector 对应的 code descriptor 为什么能用于 64-bit execution。

这里不要把“GDT 存在”当成已经完成 mode switch。GDT 只提供 descriptor；真正让新 descriptor 成为当前 `CS` 的动作是后续 far control transfer。

## 5. 静态验证三：检查实际机器码和反汇编

先按当前 v5.10 工作树的正常方式构建 x86 bzImage/compressed kernel。具体配置可以使用一个可启动的最小配置，也可以使用已有有效 `.config`：

```bash
make olddefconfig
make -j"$(nproc)" bzImage
```

构建完成后，先确认 compressed 目录实际生成的 ELF/目标文件，再以当前构建产物为准使用 `nm`/`objdump`，不要硬编码某个发行版的地址：

```bash
find arch/x86/boot/compressed -maxdepth 1 -type f -print
nm -n arch/x86/boot/compressed/vmlinux | grep -E 'startup_32|startup_64'
objdump -drwC -Mintel arch/x86/boot/compressed/vmlinux | less
objdump -drwC -M att   arch/x86/boot/compressed/vmlinux | less
```

在反汇编中找到 `startup_32` 到 `startup_64` 的转换区域，确认实际指令仍与本工作树源码对应。重点检查：

```text
mov to CR4
mov to CR3
rdmsr / wrmsr
mov to CR0
far return
startup_64 target
```

### 为什么必须看反汇编

`.code32` 和 `.code64` 是 assembler 的编码上下文，不是运行时 CPU 自己读取的元数据。反汇编可以验证构建产物中切换点两侧实际生成了什么机器码，但“CPU 当前处于哪个 execution mode”仍必须结合控制寄存器和 `CS` 状态判断。

## 6. 动态验证：在 QEMU/GDB 中观察状态边界

动态部分只能在隔离 guest 中进行。不要在正在使用的宿主机上尝试修改 CR0/CR4/EFER。

### 6.1 启动调试 guest

具体启动命令取决于本地 bzImage/initrd/boot 方法。核心要求是让 QEMU 停在早期启动并开放 gdbstub，例如：

```text
-s -S
```

然后从 GDB 连接：

```gdb
target remote :1234
```

若调试 compressed image 时符号重定位导致源码符号地址与运行地址不一致，必须先根据当前镜像实际装载地址修正 symbol/load address；不要用未经核验的固定地址下断点。

### 6.2 观察点 A：写 CR0 之前

在 `startup_32` 最后一次写 CR0、打开 PG 之前停住，记录：

```text
CR0
CR3
CR4
EFER
CS
RIP/EIP
RSP/ESP
```

预期关系：

```text
CR4.PAE = 1
CR3 points at prepared early paging root
EFER.LME = 1
CR0.PG has not yet been enabled by this transition step
current CS is still the 32-bit execution segment
```

不同 GDB/QEMU 版本读取 MSR 的命令可能不同。若 GDB 不能直接显示 EFER，可使用 QEMU monitor 或在 `rdmsr/wrmsr` 周围观察 `%eax/%edx`，但必须记录实际使用的方法。

### 6.3 观察点 B：写 CR0 后、执行 `lret` 前

单步越过 CR0 write，但不要越过 `lret`。再次记录 CR0/CR3/CR4/EFER/CS 和 instruction pointer。

这是本实验最重要的中间现场：

```text
paging/IA-32e activation conditions are active
but CS has not yet been reloaded by lret
```

因此不要因为 CR0.PG 已经为 1 就把这一现场标成“已经在 startup_64 执行”。

### 6.4 观察 far-return frame

在 `lret` 前检查当前 mini stack，确认它包含目标 offset 与 `__KERNEL_CS` selector。必须结合当前 32-bit operand/stack semantics 和实际反汇编解释槽宽，不要直接套用 64-bit `iretq`/`retq` 的栈模型。

记录：

```text
current SP
far-return target offset
far-return CS selector
symbol-resolved startup_64 address
```

### 6.5 观察点 C：单步越过 `lret`

单步执行 far return 后立即停止，确认：

```text
instruction pointer == startup_64 runtime target
CS == __KERNEL_CS
current instruction stream is decoded as 64-bit code
```

如果调试器能够显示 descriptor/cache 属性，再核对当前 CS 的 long bit；如果不能，不要伪造 `CS.L` 数值，可以用 selector + GDT descriptor + 已进入 `.code64 startup_64` 三者交叉验证。

## 7. 必须区分的状态

实验记录至少使用下面四列，避免把状态压成一个布尔值：

| 观察时刻 | CR4.PAE | EFER.LME | CR0.PG | 当前 CS / execution context |
| --- | --- | --- | --- | --- |
| transition 准备阶段 | 1 | 最终置 1 | 0 | 32-bit protected-mode context |
| CR0 write 后、`lret` 前 | 1 | 1 | 1 | IA-32e 已激活，但旧 CS 尚未被 far transfer 替换 |
| `lret` 后 `startup_64` | 1 | 1 | 1 | `__KERNEL_CS`，64-bit execution |

表格描述的是本节关注的依赖关系；真实 CPU 还存在其他控制位和 descriptor 状态，不应把表格当成完整 architectural state dump。

## 8. 不应作为验收标准的现象

以下说法都不足以单独证明模式切换正确：

- “看到了 `EFER.LME=1`”；
- “看到了 `CR0.PG=1`”；
- “源码中出现 `.code64`”；
- “GDT 中存在 64-bit descriptor”；
- “QEMU 最终启动成功”。

独立验收要求把 **控制寄存器/MSR 条件、有效页表、far transfer、CS descriptor 和目标指令流** 连成同一条证据链。

## 9. 与 Linux 完整启动课程的边界

本实验只验证模式切换机制。以下内容不在这里展开：

```text
boot protocol
KASLR
解压器主体
最终内核页表
5-level paging trampoline 的完整实现
startup_64 后续初始化
start_kernel()
```

这些内容属于 `boot-crash/` 或 `memory/`。

## 10. 本次维护环境的执行状态

本实验文件已经给出静态构建/反汇编和 QEMU/GDB 动态验证步骤，但本次维护环境没有可执行的 Linux 5.10 git checkout，也没有可启动的对应 QEMU guest，因此本次未执行 `make bzImage`、`objdump` 或早期启动 GDB 单步。

后续在具备工作树的环境中执行时，应把实际 compiler/binutils/QEMU 版本、kernel config、`startup_32/startup_64` runtime address 和三个观察点的寄存器状态记录下来；在此之前不能把上述预期值写成实测结果。

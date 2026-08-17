# B03 实验预期分析：formal `head_64.S` 与早期页表交接

本文给出 `README.md` 中 B03 实验的验收基线。它用于判断观察结果是否支持正文结论，不代替真实 Linux 5.10 源码、构建产物或 QEMU/GDB 现场。

## 1. 先固定证据边界

B03 只讨论 formal kernel 入口阶段的页表和执行环境交接。完整多级页表机制属于 `memory/`；long-mode transition、GDT、CR0/CR3/CR4 指令语义属于 `assembly/`。

实验按三层证据解释：

- **L1 源码事实**：证明 Linux 5.10 中符号、公式、静态对象、源码顺序和 CONFIG 条件；
- **L2 ELF/机器码**：证明本次实际构建中的符号地址和机器指令顺序；
- **L3 运行现场**：证明某次启动时寄存器、CR3、RIP、RSP、GDTR 和 far-return frame 的实际值。

L1 不能冒充 L2/L3。当前没有真实 Linux 5.10 build/QEMU 数据时，动态数值必须保持“未执行”。

## 2. formal `startup_64` 的入口状态

Linux 5.10 `arch/x86/kernel/head_64.S:startup_64` 的正确入口模型是：

```text
CPU 已在 64-bit mode
CS.L = 1, CS.D = 0
已有至少覆盖 kernel pages 的 identity mapping
%rsi = real_mode_data / boot_params 的物理指针
```

因此以下说法判定为错误：

- “formal `startup_64` 负责第一次打开 long mode”；
- “进入 formal kernel 时还没有任何页表”；
- “`%rsi` 已经是普通 C ABI 第一个参数”。

`%rsi` 要一直保存到后面的 assembly 环境建立完成，最终才通过 `movq %rsi,%rdi` 转换为 C ABI 参数。

## 3. `load_delta` 的含义

`__startup_64()` 接收当前 `_text` 的实际物理执行位置，并计算：

```text
load_delta = physaddr - (_text - __START_KERNEL_map)
```

它比较的是：

```text
本次实际 kernel physical load
        vs
由 link-time virtual layout 推导的默认 physical position
```

Linux 5.10 formal early mapping 要求该差值满足 PMD 对齐约束。`load_delta` 不是 KASLR 随机数，也不是虚拟地址与物理地址的一般转换公式。

## 4. 三个 early paging 对象的职责

### `early_top_pgt`

BSP formal entry 在切换阶段使用的 top-level page table。`__startup_64()` 会按本次实际装载位置修正其相关引用和 kernel mapping。

### `early_dynamic_pgts`

为 switchover identity mapping 提供临时页表页。其目的不是建立最终 Linux 地址空间，而是保证装入新 CR3 后、RIP 尚未切换到完整 kernel virtual address 的短暂阶段仍可执行。

### `phys_base`

记录本次 kernel image 的实际物理基址状态。启用 SME 时，必须区分真实物理基址与带 encryption modifier 的页表/CR3 地址值。

若把三者统一描述为“页表地址”，实验不通过。

## 5. `__startup_64()` 的返回值与 CR3 必须分开

Linux 5.10 `__startup_64()` 最终返回：

```text
sme_get_me_mask()
```

因此 `call __startup_64` 刚返回时 `%rax` 的 C 语义是 **SME modifier**，不是 CR3。

assembly 随后才形成 CR3：

```text
%rax = SME modifier
     + (early_top_pgt - __START_KERNEL_map)
     + phys_base
        ↓
sev_verify_cbit(...)
        ↓
mov %rax,%cr3
```

动态实验 P1 的断点必须精确放在 `call __startup_64` 返回之后、第一条相关 `addq` 之前；如果已经执行了地址加法，就不能再把 `%rax` 标成纯 C 返回值。

## 6. CR3 switch 与 virtual-address jump 是两个状态变化

预期机器码/源码顺序包含：

```asm
movq %rax, %cr3
movq $1f, %rax
jmp *%rax
```

语义分别是：

1. `mov %cr3`：新的 translation context 生效；
2. indirect jump：后续 RIP 明确进入 formal kernel 的完整虚拟地址语境。

因此 P2 应至少有两个观察时刻。不能写成“加载 CR3 自动把 RIP 改成高半区地址”。

switchover identity mapping 正是为了保证这两个动作之间的执行连续性。

## 7. 地址语境稳定后仍需建立普通 C 所需环境

virtual-address jump 后仍应看到以下类别的状态建立：

```text
kernel-space GDT
segment selector cleanup
MSR_GS_BASE
initial_stack → RSP
early IDT
EFER.SCE / 条件性的 NX
CR0 startup state
pushq $0; popfq
%rsi → %rdi
```

这里 `pushq $0; popfq` 的验收语义是清理 RFLAGS，并且发生在新的 kernel stack 已经可用之后；不能只把它当作普通 push/pop 示例。

## 8. `initial_code` 与 far return

Linux 5.10 formal head 中：

```text
initial_code = x86_64_start_kernel
```

最终 assembly 构造目标 CS/RIP 并执行 `lretq`。正确的交接结果应是：

```text
CS  = __KERNEL_CS
RIP = x86_64_start_kernel
RSP = initial_stack 上的当前位置
RDI = 原先由 RSI 保存的 boot_params 指针
```

P3 的 far-return frame 必须根据本次真实反汇编和断点位置读取；源码只能说明构造逻辑，不能提供某次运行的实际栈地址。

## 9. BSP、secondary CPU 与特殊入口

BSP 主线：

```text
startup_64
→ __startup_64()
→ early_top_pgt
```

secondary CPU 主线：

```text
secondary_startup_64
→ __startup_secondary_64()
→ init_top_pgt
```

两条路径会复用后续部分 assembly，但入口前提和 early page-table ownership 不相同。

`secondary_startup_64_no_verify` 只能按 Linux 5.10 的 SEV-ES 特殊 secondary bring-up 条件解释，不能写成普通 AP 默认入口。

## 10. LA57 与 SME/SEV 条件

### 5-level paging

在 `CONFIG_X86_5LEVEL` 相关构建中，formal kernel 接管此前 decompression stage 已经决定的 LA57 状态。`check_la57_support()` 检查 CR4.LA57 并同步 early paging 参数；它不是第一次决定是否进入 5-level paging。

### SME/SEV

SME modifier 会参与 early page-table/CR3 地址形成。SEV-ES 还影响 secondary CPU 特殊入口。没有相应配置和硬件/虚拟化环境时，只能验证源码条件，不能宣称动态路径已经执行。

## 11. L2 反汇编的最低验收顺序

真实 `vmlinux` 上至少应确认：

```text
startup_64
→ verify_cpu
→ __startup_64
→ early_top_pgt / phys_base 地址形成
→ sev_verify_cbit
→ mov ...,%cr3
→ indirect jump
→ lgdt
→ initial_stack
→ early_setup_idt
→ popfq
→ mov %rsi,%rdi
→ lretq
```

具体指令编码、寄存器临时使用和宏展开必须以匹配 `.config`、compiler/binutils 的实际构建为准。

## 12. L3 P0–P3 的预期结论

### P0：formal `startup_64`

应证明“已经在 64-bit formal entry”，并保存旧 CR3、`%rsi`、RSP、RFLAGS 等基线。源码不能替代这些动态值。

### P1：`__startup_64()` 刚返回

应观察 `%rax` 的 SME-modifier 语义；随后逐指令观察地址加法，直到形成将写入 CR3 的值。

### P2：CR3 write 与 indirect jump

应分别记录 CR3 和 RIP，证明页表根切换与地址语境跳转是两个时刻。

### P3：`lretq` 前后

应记录真实 far-return frame、GDTR、RFLAGS、RSI/RDI，以及执行后的 CS/RIP/RSP/RDI，证明最终进入 `x86_64_start_kernel()`。

## 13. 常见错误判定

出现以下任一表述时应回到源码或实验重新核验：

1. formal `startup_64` 第一次开启 long mode；
2. `__startup_64()` 返回 CR3；
3. `mov %cr3` 自动把 RIP 切到高半区；
4. `early_dynamic_pgts` 是最终页表分配器；
5. `early_top_pgt` 与 `init_top_pgt` 在 BSP/AP 入口中没有区别；
6. formal entry 重新决定是否启用 LA57；
7. `lretq` 前 `%rsi` 已天然符合 C ABI；
8. 仅凭源码给出某次启动的 CR3、RIP、RSP、GDTR 或栈地址；
9. 把 `arch/x86/mm/ident_map.c` 写成 Linux 5.10 BSP `startup_64 → __startup_64()` switchover mapping 的直接主调用链。

## 14. 当前验证状态

当前课程材料已经完成 Linux 5.10 源码事实核验，并据此固定了 L1/L2/L3 实验设计和本验收基线。

当前维护环境尚未提供可执行的 Linux v5.10 build tree 与 QEMU/GDB 启动现场，因此以下项目仍明确为未执行：

- 匹配配置的 formal `vmlinux` 上 `nm/readelf/objdump` 验证；
- P0–P3 的 CR3、RIP、RSP、RFLAGS、GDTR、RSI/RDI 动态记录；
- LA57、SME/SEV 条件路径的实际运行观察。

下一步应先把本章可静态判断的 L1 条件转换成自动 source-contract checker，并用正/负 fixture 验证 matcher 本身；真实构建和动态实验在具备环境后补充。
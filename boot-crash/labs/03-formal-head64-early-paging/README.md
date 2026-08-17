# B03 实验：formal `head_64.S` 与早期页表交接

本实验服务于 B03 正文，目标不是重新学习多级页表，而是验证 Linux 5.10 formal kernel 入口的几个启动事实：进入 `arch/x86/kernel/head_64.S:startup_64` 时 CPU 已经处于 64-bit mode 并拥有可执行当前 kernel 的 identity mapping；formal kernel 随后根据实际物理装载位置修正 early page tables，切换 CR3 和地址语境，最后把 `boot_params` 交给 `x86_64_start_kernel()`。

对应材料：

- `../../docs/03-formal-head64-and-early-paging.md`
- `../../source-paths/03-formal-head64-early-paging-linux-5.10.md`
- `expected-analysis.md`

完整页表结构和页表项格式属于 `memory/`；long-mode transition、GDT 和控制寄存器机器语义属于 `assembly/`。本实验只观察启动阶段的状态交接。

## 1. 要验证的问题

实验至少回答以下问题：

1. formal `startup_64` 的入口契约是什么，`%rsi` 此时保存什么？
2. `__startup_64()` 如何从实际 `_text` 物理位置得到 `load_delta`？
3. `early_top_pgt`、`early_dynamic_pgts` 和 `phys_base` 在 BSP 路径中分别承担什么职责？
4. 为什么 `__startup_64()` 的返回值不能直接称为 CR3？
5. assembly 如何在返回值基础上形成真正写入 `%cr3` 的值？
6. `mov %cr3` 与随后进入 kernel virtual-address execution 为什么是两个不同动作？
7. `%rsi` 中的 `boot_params` 何时转换为 C ABI 的 `%rdi`？
8. `initial_code` 为什么能够把 formal assembly entry 交给 `x86_64_start_kernel()`？
9. BSP `startup_64` 与 `secondary_startup_64` 为什么不能视为同一入口？

## 2. 证据等级与执行顺序

实验把证据分成四类。工具自测试只证明 checker 自身能够接受完整 fixture、拒绝已知破坏，不属于 Linux 事实证据；Linux 事实仍按 L1/L2/L3 分层。

### 工具证据：先验证 checker 自身

本目录包含：

```text
verify_source_contract.py
    对 Linux v5.10 source tree 执行 L1 source-contract 检查。

test_verify_source_contract.py
    使用最小正/负 fixture 验证 checker 的 acceptance/rejection 行为。
```

先在本目录执行：

```bash
python3 -m unittest -v test_verify_source_contract.py
```

当前维护记录：该 self-test 已实际执行，8 个 unittest 全部通过（1 个完整正例 + 7 个负例），exit code 为 0。完整正例返回 6 组 source-contract。负例分别破坏 formal-entry identity-map 契约、`load_delta` 公式、SME return、CR3/virtual-target 顺序、`initial_code` 目标、AP 的 `init_top_pgt` ownership 和 early dynamic page-table pool size。

这项结果只能说明测试工具对这些 fixture 的行为符合预期，不能据此声称真实 Linux v5.10 checkout、某个 `vmlinux` 或某次启动已经通过验证。

### L1：真实 Linux 5.10 源码事实

需要 Linux v5.10 源码树。主要文件：

```text
arch/x86/kernel/head_64.S
arch/x86/kernel/head64.c
arch/x86/include/asm/page_64_types.h
arch/x86/include/asm/pgtable_64_types.h
```

在真实 checkout 上先运行：

```bash
python3 verify_source_contract.py /path/to/linux-5.10
```

checker 当前自动检查 6 组契约：

1. formal `startup_64` 的 64-bit/identity-map/`%rsi` 入口条件，以及 `verify_cpu → __startup_64 → early_top_pgt` 的 BSP 顺序；
2. `load_delta`、PMD 对齐、`early_top_pgt`/`early_dynamic_pgts`、non-global switchover mapping、`phys_base` 和 SME-modifier return；
3. `EARLY_DYNAMIC_PAGE_TABLES == 64`；
4. `phys_base → sev_verify_cbit → CR3 write → virtual-address target/jump → GDT → stack → early IDT → RFLAGS → %rsi→%rdi → lretq`，以及 `initial_code == x86_64_start_kernel`；
5. secondary CPU 的 `__startup_secondary_64 → init_top_pgt` ownership 与 SEV-ES no-verify 特例；
6. LA57 是从 decompressor 阶段接管的状态，而不是在 formal entry 首次启用。

自动检查通过后仍要阅读对应源码上下文。正则匹配用于防止关键事实漂移，不替代对条件分支、注释语义和周边控制流的人工核验。这一层可以证明符号、源码顺序、公式、配置条件和静态数据归属，但不能证明某次启动时寄存器的实际值。

### L2：实际构建产物和机器码

需要与源码和 `.config` 匹配的 `vmlinux`。使用：

```bash
nm -n vmlinux
readelf -Ws vmlinux
objdump -dr vmlinux
```

这一层用于确认符号实际存在、链接地址和关键机器指令顺序。它仍不能证明某次机器启动时 CR3/RIP/RSP 的动态值。

### L3：QEMU/GDB 运行现场

在隔离虚拟机中观察 formal entry 的寄存器和控制流。重点记录：

```text
RIP / RSI / RDI / RSP / RAX
CR3 / CR4
RFLAGS
GDTR
```

如果当前环境没有可调试的 Linux 5.10 build/QEMU，本层明确记录“未执行”，不要填写推测值。

当前维护环境尚未在真实 Linux v5.10 checkout 上运行 checker，也没有匹配的 `vmlinux` 与 QEMU/GDB 现场，因此当前已执行证据仅为 checker fixture self-test；L1 的源码事实已通过课程编写时的 upstream v5.10 阅读核验，但本实验的真实-checkout CLI 记录、L2、L3 仍保留为未执行增强证据。

## 3. L1：验证 formal `startup_64` 的入口契约

在 Linux v5.10 源码树执行：

```bash
git grep -n 'SYM_CODE_START_NOALIGN(startup_64)' -- arch/x86/kernel/head_64.S
git grep -n 'real_mode_data' -- arch/x86/kernel/head_64.S
```

阅读入口注释并记录：

```text
CPU mode:
CS.L / CS.D:
已有 page-table 条件:
%rsi:
可能的上一阶段:
```

预期应确认：formal entry 已处于 64-bit mode，已有覆盖 kernel pages 的 identity mapping，`%rsi` 是 `real_mode_data` / `boot_params` 的物理指针。不要把这里写成“formal kernel 打开 long mode”。

## 4. L1：验证 `load_delta` 和 early page-table 修正

定位：

```bash
git grep -n '__startup_64' -- arch/x86/kernel/head64.c arch/x86/kernel/head_64.S
git grep -n 'load_delta' -- arch/x86/kernel/head64.c
git grep -n '__START_KERNEL_map' -- arch/x86/include/asm/page_64_types.h arch/x86/kernel/head64.c
git grep -n 'early_dynamic_pgts' -- arch/x86/kernel/head64.c arch/x86/kernel/head_64.S
git grep -n 'phys_base' -- arch/x86/kernel/head64.c arch/x86/kernel/head_64.S
```

必须把公式写清楚：

```text
load_delta = actual physaddr of _text
           - (_text link-time VA - __START_KERNEL_map)
```

并检查 Linux 5.10 对 `load_delta` 的 PMD 对齐约束。

随后分别记录：

- `early_top_pgt`：BSP formal entry 切换使用的 top-level table；
- `early_dynamic_pgts`：构造 switchover identity mapping 所使用的早期页表池；
- `phys_base`：记录 kernel image 本次实际物理基址的状态；
- kernel high-half PMD：只修正实际 kernel image 所占范围，并清理范围外 present entries。

这里不要把 `__startup_64()` 描述成“建立最终 Linux 地址空间”。

## 5. L1：验证 `__startup_64()` 的返回语义与 CR3 形成

定位 C 返回值：

```bash
git grep -n 'return sme_get_me_mask' -- arch/x86/kernel/head64.c
```

再检查 assembly：

```bash
git grep -n -A35 'call.*__startup_64' -- arch/x86/kernel/head_64.S
```

把数据流写成：

```text
__startup_64() return
    = SME modifier
        ↓
+ (early_top_pgt - __START_KERNEL_map)
        ↓
+ phys_base
        ↓
sev_verify_cbit(...)
        ↓
mov %rax, %cr3
```

验收重点：不能因为 `%rax` 最终写入 CR3，就说 `__startup_64()` “返回 CR3”。中间 assembly 的地址形成是语义的一部分。

## 6. L1：验证 CR3 switch 与 virtual-address jump

在 `head_64.S` 中找到：

```asm
movq %rax, %cr3
movq $1f, %rax
jmp *%rax
```

记录两个动作分别改变什么：

```text
mov %cr3:
    改变当前页表根，新的 translation context 生效。

indirect jump:
    让后续 RIP 按 formal kernel 的完整虚拟地址继续执行。
```

如果把二者合成“切页表后就已经自动跳到高地址”，实验判定为不通过。

## 7. L1：验证进入 C 前的执行环境

继续阅读 virtual-address jump 之后的代码，至少确认：

```text
lgdt early_gdt_descr
DS/SS/ES/FS/GS 清理
MSR_GS_BASE
initial_stack → RSP
early_setup_idt
EFER.SCE / 可选 NX
CR0_STATE
pushq $0; popfq
%rsi → %rdi
initial_code
lretq
```

对每一项记录它解决的问题，不只抄指令。例如 `pushq $0; popfq` 应记录为在已经建立新栈之后清零 RFLAGS，而不是普通的栈操作演示。

## 8. L1：验证 BSP/AP 边界

定位：

```bash
git grep -n 'secondary_startup_64' -- arch/x86/kernel/head_64.S
git grep -n '__startup_secondary_64' -- arch/x86/kernel/head64.c
git grep -n 'init_top_pgt' -- arch/x86/kernel/head_64.S
git grep -n 'early_top_pgt' -- arch/x86/kernel/head_64.S
```

记录：

```text
BSP:
startup_64 → __startup_64() → early_top_pgt

secondary CPU:
secondary_startup_64 → __startup_secondary_64() → init_top_pgt
```

`secondary_startup_64_no_verify` 还要注明 SEV-ES 特殊条件，不能当作一般 AP 默认入口。

## 9. L2：用真实 `vmlinux` 验证符号和机器码

如果有与 Linux 5.10 源码匹配的 build tree：

```bash
nm -n vmlinux | grep -E ' startup_64$| secondary_startup_64$| x86_64_start_kernel$| early_top_pgt$| init_top_pgt$| phys_base$'
readelf -Ws vmlinux | grep -E 'startup_64|x86_64_start_kernel|early_top_pgt|phys_base'
objdump -dr vmlinux > formal-vmlinux.objdump.txt
```

在反汇编中核对 BSP 主线的关键顺序：

```text
verify_cpu
→ __startup_64
→ CR3 address formation
→ sev_verify_cbit
→ mov ...,%cr3
→ indirect jump
→ lgdt
→ initial_stack
→ early_setup_idt
→ popfq
→ %rsi,%rdi
→ lretq
```

由于宏、链接和具体配置会影响机器码，必须以本次构建产物为准；不要用源码行号代替实际反汇编证据。

## 10. L3：QEMU/GDB 动态观察点

建议在带符号的 Linux 5.10 QEMU 环境设置以下观察点。

### P0：formal `startup_64`

记录：

```text
RIP
RSI
RSP
CR3
CR4
RFLAGS
```

目标：证明 CPU 已在 64-bit formal entry，`%rsi` 指向本次 `boot_params`，并保存进入 formal kernel 时的旧 CR3 基线。

### P1：`__startup_64()` 返回后、写 CR3 前

记录：

```text
RAX
phys_base
early_top_pgt 地址
CR3(old)
```

目标：区分 `RAX == SME modifier` 的 C 返回语义与 assembly 后续逐步形成 CR3 的过程。断点位置必须精确到 `call __startup_64` 返回后的具体指令；不要在已经执行 `addq` 后仍把 `%rax` 标成纯返回值。

### P2：`mov %rax,%cr3` 后与 indirect jump 后

分别记录：

```text
CR3
RIP
```

目标：观察“页表根切换”和“RIP 进入 kernel virtual-address execution”是两个时间点。

### P3：`lretq` 前后

`lretq` 前记录：

```text
RSP
[RSP] / [RSP+8] 等实际 far-return frame
RSI
RDI
RFLAGS
GDTR
```

执行后记录：

```text
CS
RIP
RSP
RDI
```

目标：验证最终目标是 `x86_64_start_kernel()`，并确认 `%rdi` 接收到原先由 `%rsi` 保存的 `boot_params` 指针。

注意：必须按真实反汇编和断点位置解释 far-return frame，不要仅凭源码伪造栈地址。

## 11. 结果记录模板

```text
Kernel commit/tag:
.config:
Compiler/binutils:
QEMU/GDB:

Checker self-test:
- command:
- positive fixture:
- negative fixtures:
- result:

L1 source facts:
- checker command/result:
- startup_64 entry contract:
- load_delta formula/alignment:
- early_top_pgt:
- early_dynamic_pgts:
- phys_base:
- __startup_64 return:
- CR3 formation:
- CR3 switch vs virtual jump:
- BSP/AP boundary:
- CONFIG/SME/LA57 conditions:

L2 build evidence:
- startup_64 symbol:
- early_top_pgt / init_top_pgt:
- CR3 write disassembly:
- indirect jump:
- lretq / x86_64_start_kernel handoff:

L3 runtime:
- P0:
- P1:
- P2:
- P3:

Unexecuted items / environment limits:
```

## 12. 通过标准

本实验达到通过标准时，至少应能够证明：

1. checker self-test 已通过，且该结果只作为工具证据；
2. 在真实 Linux v5.10 checkout 上运行 L1 checker，并结合源码上下文确认 formal `startup_64` 接收的是已经处于 64-bit mode 的 CPU 和临时 identity mapping；
3. `%rsi` 是 `boot_params` 的物理指针，并在最终 C handoff 前转到 `%rdi`；
4. `load_delta` 描述实际 kernel physical load 与 link-time 假定之间的差值，并满足 Linux 5.10 early mapping 的对齐要求；
5. `early_top_pgt` 和 `early_dynamic_pgts` 分别承担 BSP top-level table 与 switchover identity mapping 页表池职责；
6. `__startup_64()` 返回 SME modifier，而 assembly 再形成 CR3；
7. CR3 switch 与 virtual-address indirect jump 是两个独立状态变化；
8. virtual-address execution 后还要建立 GDT、stack、early IDT、RFLAGS 和 C ABI 参数状态；
9. `initial_code == x86_64_start_kernel`，最终通过 far return 完成 formal assembly → early C 交接；
10. BSP 与 secondary CPU 使用不同 early page-table ownership，SEV-ES 特殊入口也被正确限定；
11. 所有动态数值都来自实际构建/运行证据，没有把源码推导或 fixture 结果写成 GDB 实测。

当前维护环境如果缺少真实 Linux 5.10 checkout、匹配的 build tree 或 QEMU/GDB，则相应的 L1 CLI 记录、L2/L3 必须明确保留为未执行项。
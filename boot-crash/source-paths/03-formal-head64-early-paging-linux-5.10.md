# B03：formal `head_64.S` 与早期页表——Linux 5.10 源码事实核验

本文只固定 Linux kernel v5.10 x86-64 **正式内核映像（formal kernel）**入口阶段的源码事实，为 B03 正文和实验提供基线。完整的多级页表结构、页表 API 和内存管理机制属于 `memory/`；这里关心的是 compressed kernel/64-bit loader 把控制权交给 formal kernel 后，CPU 已具备什么状态，formal kernel 为什么仍要修正并切换页表，以及何时进入 `x86_64_start_kernel()`。

## 1. 本章解决的问题

B02 的终点不是 `start_kernel()`，而是 formal kernel 的 64-bit entry。此时 CPU 已经处于 long mode，并且已有一套能够执行当前代码的映射，但这套映射仍带有“装载位置”和早期切换所需的临时性质。

Linux 5.10 formal entry 的核心任务可以概括为：

```text
已有 long mode + 可执行当前代码的 identity mapping
        ↓
formal arch/x86/kernel/head_64.S:startup_64
        ↓
建立可调用早期 C 的栈/环境，verify_cpu()
        ↓
__startup_64(physaddr, boot_params)
        ↓
按实际物理装载位置修正 early_top_pgt / kernel mapping
并建立 switchover identity mapping
        ↓
把 early_top_pgt 的物理地址（含 SME modifier）装入 CR3
        ↓
跳到虚拟地址继续执行，换 kernel-space GDT/栈/early IDT
        ↓
通过 secondary_startup_64 共用尾部
        ↓
initial_code == x86_64_start_kernel
```

这里的“修正页表”不是重新讲一遍页表机制，而是解决一个启动阶段特有的问题：**formal kernel 被编译到固定的高半区虚拟地址，但其实际物理装载地址可能发生变化。**

## 2. 入口状态：`startup_64`

源码：

```text
arch/x86/kernel/head_64.S
SYM_CODE_START_NOALIGN(startup_64)
```

Linux 5.10 源码注释明确规定该入口的前提：

- CPU 已处于 64-bit mode，`CS.L=1`、`CS.D=0`；
- 已有人为它加载 identity-mapped page tables；
- 这些 identity mappings 至少覆盖 kernel pages，可能覆盖更多内存；
- `%rsi` 保存指向 `real_mode_data` / `boot_params` 的**物理指针**；
- 入口可能来自 64-bit boot loader，也可能来自 `arch/x86/boot/compressed/head_64.S`。

因此，formal `startup_64` 的职责不是“第一次打开 long mode”。这一机器状态在进入本映像前已经成立。B03 只解释 formal kernel 如何接管并替换早期映射。

## 3. 为什么要计算实际物理装载地址

`startup_64` 先用 RIP-relative 地址取得 `_text`：

```asm
leaq _text(%rip), %rdi
```

随后调用：

```text
startup_64_setup_env
verify_cpu
__startup_64
```

`__startup_64()` 定义于：

```text
arch/x86/kernel/head64.c
unsigned long __head __startup_64(unsigned long physaddr,
                                  struct boot_params *bp)
```

其中 `physaddr` 表示当前 formal kernel `_text` 的实际物理地址语境。函数计算：

```c
load_delta = physaddr - (unsigned long)(_text - __START_KERNEL_map);
```

`__START_KERNEL_map` 在 Linux 5.10 x86-64 中定义为：

```text
arch/x86/include/asm/page_64_types.h
#define __START_KERNEL_map 0xffffffff80000000UL
```

这里必须区分三个概念：

1. link-time kernel virtual address：例如 `_text` 所在的高半区地址；
2. link-time 假定的物理位置：`_text - __START_KERNEL_map`；
3. 本次启动实际物理位置：`physaddr`。

`load_delta` 描述 2 与 3 的差值。Linux 5.10 要求该 delta 满足 PMD（2 MiB）对齐，否则 `__startup_64()` 进入不可恢复循环。

## 4. `__startup_64()` 如何修正早期页表

主要源码：

```text
arch/x86/kernel/head64.c
__startup_64()
```

### 4.1 5-level paging 状态不是在这里首次决定

`check_la57_support()` 的注释明确说明：5-level paging 已在 kernel decompression stage 检测和启用；formal kernel 这里只检查 CR4.LA57 是否已经开启，并据此设置：

```text
__pgtable_l5_enabled
pgdir_shift
ptrs_per_p4d
page_offset_base
vmalloc_base
vmemmap_base
```

相关代码受：

```text
CONFIG_X86_5LEVEL
CONFIG_DYNAMIC_MEMORY_LAYOUT
```

影响。

### 4.2 修正高半区 kernel mapping

`__startup_64()` 使用 `fixup_pointer()`，在仍以早期物理/identity 语境运行时取得页表对象的可访问地址，然后修正：

```text
early_top_pgt
[level4_kernel_pgt]
level3_kernel_pgt
level2_fixmap_pgt
level2_kernel_pgt
```

关键逻辑不是“创建完整 Linux 地址空间”，而是把静态页表中基于 link-time 地址写入的物理引用加上 `load_delta`，使它们指向本次真正的物理装载位置。

`level2_kernel_pgt` 的静态定义位于 `arch/x86/kernel/head_64.S`。Linux 5.10 使用 2 MiB large PMD entries 为 kernel image 预留映射；`KERNEL_IMAGE_SIZE` 在 `page_64_types.h` 中受 `CONFIG_RANDOMIZE_BASE` 影响：启用时为 1 GiB，否则为 512 MiB。

`__startup_64()` 还会清除 kernel image 实际范围之外的 present bit，并只对 `_text.._end` 范围内有效的 PMD 加 `load_delta`。这一步不能描述成“映射所有 RAM”。

### 4.3 建立 switchover identity mapping

formal kernel 不能立即只保留最终高半区映射，因为 CPU 当前仍需要安全完成 CR3 切换并从当前执行地址过渡到 kernel virtual address。

Linux 5.10 为此从：

```text
early_dynamic_pgts[EARLY_DYNAMIC_PAGE_TABLES]
```

分配早期页表页，构造覆盖当前 kernel physical image 的 identity mapping。`EARLY_DYNAMIC_PAGE_TABLES` 在 `pgtable_64_types.h` 中为 64。

PMD entry 使用：

```text
__PAGE_KERNEL_LARGE_EXEC & ~_PAGE_GLOBAL
```

并按 `__supported_pte_mask` 过滤 CPU 不支持的位。源码明确强调 switchover identity entries 不应带 global bit。

### 4.4 SME/内存加密条件

`__startup_64()` 会调用：

```text
sme_enable(bp)
sme_get_me_mask()
sme_encrypt_kernel(bp)
```

并把 SME encryption mask 纳入页表地址修正和最终 CR3 modifier。这里的“真实物理地址”与带 C-bit 的页表地址值不能简单混为一个整数。

B03 只记录这一启动约束；完整 SME/SEV 机制不在基础课程中展开。

## 5. `__startup_64()` 的返回值不是 CR3 本身

Linux 5.10 `__startup_64()` 返回：

```text
sme_get_me_mask()
```

assembly 随后执行：

```asm
addq $(early_top_pgt - __START_KERNEL_map), %rax
...
addq phys_base(%rip), %rax
...
movq %rax, %cr3
```

因此 `%rax` 的形成过程应理解为：

```text
SME modifier
+ early_top_pgt 的 link-time physical offset
+ phys_base
= 要装入 CR3 的 early_top_pgt physical address/modifier
```

不能把 `__startup_64()` 写成“返回页表地址”。

`phys_base` 初始在 `head_64.S` 中为 0；`__startup_64()` 会按 `load_delta`（扣除 SME mask）修正它，使后续代码能够表达本次 kernel image 的真实物理基址。

## 6. BSP `startup_64` 与 AP `secondary_startup_64` 的边界

Linux 5.10 在同一文件中定义：

```text
startup_64
secondary_startup_64
secondary_startup_64_no_verify
```

BSP 初始启动走 `startup_64`，执行 `__startup_64()` 并使用 `early_top_pgt`。

`secondary_startup_64` 用于 secondary CPU 路径；它执行 `verify_cpu()` 后调用 `__startup_secondary_64()`，最终使用 `init_top_pgt`。源码注释指出 secondary entry 可以由 `startup_64`（物理地址语境）或 `trampoline.S`（虚拟地址语境）进入。

`secondary_startup_64_no_verify` 仅用于 SEV-ES guest 的特殊 secondary CPU bring-up，原因是这一阶段调用 `verify_cpu()` 会产生尚无法处理的 `#VC`。因此它不能写成一般 AP 的默认入口。

B03 应把 BSP/AP 看作**入口和早期页表所有权不同、但复用部分 assembly 尾部初始化**，而不是两条完全独立的启动实现。

## 7. CR3 切换后的关键状态交接

BSP/AP 路径汇合后，assembly：

1. 设置 CR4.PAE/PGE；若 `CONFIG_X86_5LEVEL` 且 `__pgtable_l5_enabled` 为真，再设置 CR4.LA57；
2. 形成新的 CR3 值并调用 `sev_verify_cbit()`；
3. `movq %rax, %cr3` 切换到 formal kernel 修正后的 early page tables；
4. 用间接跳转确保后续 RIP 位于 kernel virtual-address 语境；
5. 加载 kernel-space `early_gdt_descr`；
6. 清理数据段选择子和 stale FS/GS selector；
7. 设置 `MSR_GS_BASE`；
8. 切换到 `initial_stack`；
9. 安装 early IDT；
10. 设置 EFER.SCE，并在 CPU 支持时设置 EFER.NX；
11. 设置 CR0 并清零 RFLAGS；
12. 把 `%rsi` 中的 real-mode-data/`boot_params` 指针移到 `%rdi`；
13. 通过 far return 跳到 `initial_code`。

`initial_code` 在同一文件中定义为：

```text
.quad x86_64_start_kernel
```

因此 formal assembly 入口的直接 C 交接点是 `x86_64_start_kernel()`。

这里应区分两次控制流转换：

```text
identity-address execution
  -- CR3 + indirect jump --> kernel virtual-address execution
  -- lretq via initial_code --> x86_64_start_kernel()
```

二者不是同一个动作。

## 8. `x86_64_start_kernel()` 之前和之后的责任边界

源码：

```text
arch/x86/kernel/head64.c
x86_64_start_kernel()
```

B03 的终点是 assembly 已经建立足够稳定的 formal-kernel early environment，并把 `boot_params` 交给 `x86_64_start_kernel()`。

`head64.c` 后续还有：

```text
reset_early_page_tables()
__early_make_pgtable()
```

它们属于进入 early C 后继续管理 early page tables 的机制。B03 可以用它们说明“早期页表并非在 `mov %cr3` 后就永久定型”，但不应提前展开 B04 的架构初始化主线，也不应替代 `memory/` 中完整页表课程。

## 9. 关键数据和配置条件

| 对象/条件 | Linux 5.10 位置 | B03 中的作用 |
|---|---|---|
| `startup_64` | `arch/x86/kernel/head_64.S` | BSP formal-kernel 入口 |
| `secondary_startup_64` | 同上 | secondary CPU 64-bit 入口 |
| `__startup_64()` | `arch/x86/kernel/head64.c` | 按实际物理位置修正 early page tables |
| `early_top_pgt` | `head_64.S` | BSP 切换使用的 early top-level table |
| `init_top_pgt` | `head_64.S` | 后续/secondary 路径使用的 top-level table |
| `early_dynamic_pgts` | `head_64.S` | switchover identity mapping 的临时页表池 |
| `phys_base` | `head_64.S` | kernel image 实际物理基址状态 |
| `__START_KERNEL_map` | `page_64_types.h` | kernel image link-time virtual base |
| `CONFIG_X86_5LEVEL` | 多处 | LA57 与 5-level early table layout |
| `CONFIG_DYNAMIC_MEMORY_LAYOUT` | `head64.c` / headers | 5-level 下动态 direct-map/vmalloc/vmemmap base |
| `CONFIG_RANDOMIZE_BASE` | `page_64_types.h` | `KERNEL_IMAGE_SIZE` 1 GiB vs 512 MiB |
| `CONFIG_PAGE_TABLE_ISOLATION` | `head_64.S` | early/init PGD 的 PTI alignment/fill 形式 |
| `CONFIG_AMD_MEM_ENCRYPT` / SEV | early head path | C-bit、SME/SEV early-boot 条件 |

## 10. 本轮未采用 `ident_map.c` 作为主线入口

B03 大纲原先列出 `arch/x86/mm/ident_map.c` 作为建议阅读文件。对 Linux 5.10 formal `startup_64 → __startup_64` 主线核验后可以确认：**BSP formal entry 的 switchover identity mapping 是直接在 `head64.c::__startup_64()` 中构造的**，并不沿 `ident_map.c` 形成主调用链。

因此 B03 正文应以 `head_64.S`、`head64.c` 和页表/地址常量头文件为主。`ident_map.c` 可以在后续确有对应调用关系时作为关联源码阅读，但不能为了符合大纲文件列表而虚构 `startup_64 → ident_map.c` 调用路径。

## 11. B03 后续实验应验证什么

后续实验至少分三层：

### L1：Linux 5.10 source contract

自动/人工核验：

- formal `startup_64` 的 `.code64` 与 `%rsi` boot-params 契约；
- `startup_64 → __startup_64`；
- `load_delta` 计算与 PMD alignment；
- `early_top_pgt`、`early_dynamic_pgts`、kernel PMD fixup；
- CR3 switch 后的 virtual-address jump；
- `initial_code == x86_64_start_kernel`；
- BSP/AP 对 `early_top_pgt` / `init_top_pgt` 的不同使用；
- `CONFIG_X86_5LEVEL` 等条件。

### L2：ELF / disassembly

在真实 Linux 5.10 build tree 中用 `nm/readelf/objdump` 核验：

- `startup_64`、`secondary_startup_64`、`early_top_pgt`、`init_top_pgt`、`phys_base` 的符号归属；
- `_text`、`__START_KERNEL_map` 与 kernel image layout；
- `call __startup_64`、`mov %cr3`、间接 jump、最终 `lretq` 的实际机器码顺序。

### L3：QEMU/GDB runtime

动态记录至少四个观察点：

```text
P0 formal startup_64 entry
P1 __startup_64 return
P2 mov %cr3 before/after
P3 x86_64_start_kernel entry
```

每个点记录 RIP、RSP、RSI/RDI、RAX、CR3、CR4、RFLAGS，并结合页表内容解释地址语境变化。

当前维护环境没有 Linux v5.10 可执行 checkout/build/QEMU 现场，因此本文件只记录已经对 upstream v5.10 源码核验的事实；L2/L3 不写成已执行结果。

## 12. 本轮源码基线

主要核验：

```text
arch/x86/kernel/head_64.S
arch/x86/kernel/head64.c
arch/x86/include/asm/page_64_types.h
arch/x86/include/asm/pgtable_64_types.h
```

关联配置/机制：

```text
CONFIG_X86_5LEVEL
CONFIG_DYNAMIC_MEMORY_LAYOUT
CONFIG_RANDOMIZE_BASE
CONFIG_PAGE_TABLE_ISOLATION
CONFIG_AMD_MEM_ENCRYPT
SEV / SEV-ES early boot paths
```

下一单元应基于这些已核验事实编写 B03 正式教程；教程重点是“formal kernel 为什么仍需一次早期页表修正和地址语境切换”，而不是重复多级页表基础。
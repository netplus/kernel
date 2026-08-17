# B03：formal `head_64.S` 与早期页表

B02 的 compressed kernel 已经完成 payload 解压、ELF `PT_LOAD` 放置和必要的 relocation，并把控制权交给正式内核映像。一个容易产生的误解是：既然 CPU 此时已经进入 64 位模式，而且已经有页表能够执行 formal kernel，为什么 `arch/x86/kernel/head_64.S` 还要再次处理页表并重载 CR3？

关键原因是：**“当前代码暂时可执行”不等于“正式内核已经处在自己长期使用的虚拟地址语境中”。** formal kernel 的入口页表首先承担交接职责；Linux 还必须根据本次实际物理装载位置修正高半区 kernel mapping，建立切换期间需要的 identity mapping，然后才能安全地从当前地址语境过渡到正式的 kernel virtual address。

本章只解释启动阶段的页表状态和交接。多级页表结构、页表项格式和完整内存管理机制放在 [`memory/`](../../memory/) 中；long-mode transition、GDT 和控制寄存器的机器机制由 [`assembly/`](../../assembly/) 解释。

对应 Linux 5.10 源码事实核验见 [`source-paths/03-formal-head64-early-paging-linux-5.10.md`](../source-paths/03-formal-head64-early-paging-linux-5.10.md)。

## 1. 先建立完整工作模型

Linux 5.10 x86-64 的 formal-kernel BSP 入口可以先抽象成：

```text
CPU 已在 64-bit mode
+ 已有覆盖 kernel 的 identity mapping
+ %rsi = boot_params / real_mode_data 的物理指针
        ↓
arch/x86/kernel/head_64.S:startup_64
        ↓
准备临时栈和早期执行环境
verify_cpu()
        ↓
__startup_64(actual _text physical address, boot_params)
        ↓
计算 load_delta
修正高半区 kernel mapping
建立 switchover identity mapping
更新 phys_base
        ↓
assembly 形成 early_top_pgt 的 CR3 值
        ↓
mov %rax, %cr3
        ↓
间接跳转到 kernel virtual-address 语境
        ↓
加载 kernel-space GDT、initial_stack、early IDT 等
        ↓
%rsi → %rdi
lretq → initial_code → x86_64_start_kernel()
```

这里至少存在三种不同的“地址”概念：

1. kernel 在链接时使用的高半区虚拟地址；
2. 链接布局隐含的物理位置；
3. 本次启动中 kernel image 实际所在的物理位置。

B03 的核心就是理解 Linux 如何把第 3 项重新接到第 1 项上。

## 2. formal `startup_64` 接收到什么状态

Linux 5.10 `arch/x86/kernel/head_64.S:startup_64` 的源码注释明确规定入口前提：CPU 已经运行在 64-bit mode，`CS.L=1`、`CS.D=0`，并且已经有人安装了 identity-mapped page tables。这些映射至少覆盖 kernel pages。

因此 formal `startup_64` 不是“打开 long mode 的入口”。它可能由 compressed kernel 进入，也可能由符合 Linux boot protocol 的 64-bit boot loader 直接进入。

入口时 `%rsi` 保存 `real_mode_data`，也就是本次启动的 `boot_params` 物理指针。这个值在早期调用周围被显式保存和恢复，最后才转换为 C ABI 的第一个参数寄存器 `%rdi`。

这一点决定了两个责任边界：

- compressed kernel / loader 必须先提供足以进入 formal image 的执行环境；
- formal kernel 再把这种临时环境转换为自身可继续初始化的地址空间和 CPU 状态。

## 3. 为什么已经有页表还要修正页表

formal kernel 按固定高半区虚拟地址链接，但它的实际物理装载位置并不一定等于链接布局默认假定的位置。KASLR 是造成差异的重要来源，但即使不把问题限定为 KASLR，formal entry 本身也不能假定“实际装载物理地址 == 编译时假定物理地址”。

`startup_64` 用 RIP-relative addressing 取得当前 `_text`：

```asm
leaq _text(%rip), %rdi
```

随后把它作为 `physaddr` 传给：

```c
__startup_64(unsigned long physaddr, struct boot_params *bp)
```

Linux 5.10 在 `arch/x86/kernel/head64.c` 中计算：

```c
load_delta = physaddr - (unsigned long)(_text - __START_KERNEL_map);
```

其中：

```c
#define __START_KERNEL_map 0xffffffff80000000UL
```

`_text - __START_KERNEL_map` 表示从链接虚拟地址推导出的默认物理偏移，而 `physaddr` 是本次真正执行位置。两者之差就是后续早期页表修正所需的 `load_delta`。

Linux 5.10 要求这个差值满足 PMD，也就是 2 MiB 对齐。这里不是在定义一般意义上的页表对齐规则，而是在约束这一套 early kernel image mapping 的启动实现。

## 4. `__startup_64()` 不是“重新建立完整页表”

`__startup_64()` 的职责更准确地说是**修正和补充 formal entry 所需的早期映射**。

它首先通过 `fixup_pointer()` 访问仍处于早期地址语境中的全局对象，然后修正 `early_top_pgt`、`level3_kernel_pgt`、`level2_fixmap_pgt`、`level2_kernel_pgt` 等静态页表结构中的物理引用。

对 kernel image 的高半区 mapping，Linux 只保留实际 `_text.._end` 需要的范围，并对有效 PMD entry 加上 `load_delta`；映像范围之外的 present bit 会被清除。因此不能把这一阶段描述成“映射全部 RAM”。

`level2_kernel_pgt` 使用 large PMD entries 覆盖 kernel image 的预留窗口。Linux 5.10 中 `KERNEL_IMAGE_SIZE` 受 `CONFIG_RANDOMIZE_BASE` 影响：启用时窗口为 1 GiB，否则为 512 MiB。这是 kernel-image 虚拟窗口的启动布局约束，不是物理内存容量限制。

## 5. 为什么还需要 switchover identity mapping

如果新的页表只保留高半区 kernel mapping，CPU 在 `mov %cr3` 的瞬间可能失去当前指令流仍依赖的地址映射。页表切换本身发生在旧地址语境与新地址语境的交界处，因此必须保证切换后的最短过渡路径仍然可执行。

Linux 5.10 的 `__startup_64()` 从：

```text
early_dynamic_pgts[EARLY_DYNAMIC_PAGE_TABLES]
```

取得临时页表页，为当前 kernel physical image 建立 switchover identity mapping。`EARLY_DYNAMIC_PAGE_TABLES` 在该版本为 64。

identity PMD 使用可执行 large-page 权限，但显式去掉 `_PAGE_GLOBAL`。这是有意的切换期映射，不是最终运行期地址空间。

因此这一阶段同时存在两种重要映射：

```text
identity mapping
    让 CPU 能安全完成 CR3 和地址语境切换

high-half kernel mapping
    让 formal kernel 最终按链接虚拟地址继续执行
```

理解这一点，比记住某一级页表的具体索引更重要。

## 6. 5-level paging 在这里是“接管”，不是“决定”

当 `CONFIG_X86_5LEVEL=y` 时，`head64.c:check_la57_support()` 检查 CR4.LA57。

Linux 5.10 源码明确说明：5-level paging 的检测和启用已经发生在 kernel decompression stage；formal kernel 这里只确认这一状态，并据此更新：

```text
__pgtable_l5_enabled
pgdir_shift
ptrs_per_p4d
page_offset_base
vmalloc_base
vmemmap_base
```

因此不能写成“formal `startup_64` 决定是否开启 LA57”。这里做的是跨阶段状态接管。

相关实现还受 `CONFIG_DYNAMIC_MEMORY_LAYOUT` 影响。

## 7. SME/SEV 为什么会影响早期页表地址

在支持 AMD memory encryption 的配置中，页表地址值可能需要包含 SME C-bit modifier。`__startup_64()` 会执行 `sme_enable()`、取得 `sme_get_me_mask()`，并在必要时调用 `sme_encrypt_kernel()`。

这带来一个重要的表达边界：

**CPU 页表项/CR3 中使用的地址值，不应在所有情况下都直接称为“裸物理地址”。**

`phys_base` 保存 kernel image 的真实物理基址时会扣除 SME mask，而页表项和 CR3 的形成又需要在适当位置加入 modifier。

本课程不在 B03 展开 SME/SEV 的完整机制，只保留理解 early paging 所必需的条件。

## 8. `__startup_64()` 的返回值为什么不是 CR3

这是阅读这段代码时最容易产生的错误之一。

`__startup_64()` 最终返回：

```c
return sme_get_me_mask();
```

也就是说 `%rax` 此时只是 SME modifier；没有启用 SME 时通常就是 0。

回到 `head_64.S` 后，assembly 才继续形成 CR3：

```asm
addq $(early_top_pgt - __START_KERNEL_map), %rax
...
addq phys_base(%rip), %rax
...
movq %rax, %cr3
```

概念上可以写成：

```text
SME modifier
+ early_top_pgt 的 link-time physical offset
+ 本次 phys_base
= 要装入 CR3 的 early top-level page-table address/modifier
```

因此，看到 `call __startup_64` 后 `%rax` 最终流入 `%cr3`，不能反推成“`__startup_64()` 返回 CR3”。中间的 assembly 计算是语义的一部分。

## 9. CR3 切换和虚拟地址跳转是两个动作

形成 CR3 后，Linux 执行：

```asm
movq %rax, %cr3
```

但“新页表已经生效”和“RIP 已经进入正式 kernel virtual-address 语境”仍然不是同一件事。

紧接着源码使用一个间接跳转：

```asm
movq $1f, %rax
jmp *%rax
```

它确保后续 RIP 按 kernel virtual address 继续执行。

所以应把交接拆成：

```text
修正/建立 early mappings
        ↓
load CR3
        ↓
新页表生效
        ↓
indirect jump
        ↓
RIP 进入 kernel virtual-address execution
```

这也是为什么 Linux 源码注释说不能“一步”切到最终 kernel address space：切换过程本身需要 identity-mapped pages。

## 10. 地址语境稳定后还必须重建哪些执行条件

进入 kernel virtual-address 语境后，`head_64.S` 继续完成一组不能省略的状态交接：

- `lgdt early_gdt_descr(%rip)`，换用 kernel-space GDT；
- 清理 `%ds/%ss/%es/%fs/%gs` selector；
- 设置 `MSR_GS_BASE`；
- `movq initial_stack(%rip), %rsp`，切到 boot-time kernel stack；
- `early_setup_idt`，安装早期 IDT；
- 设置 EFER.SCE；CPU 支持 NX 时设置 EFER.NX 并更新 `early_pmd_flags`；
- 写入启动所需的 CR0 状态；
- 在新 `%rsp` 建立后执行 `pushq $0; popfq`，清零 RFLAGS；
- `movq %rsi, %rdi`，把 `boot_params` 转成 C ABI 第一个参数。

这说明“地址空间已经能工作”仍不等于“可以直接执行普通 C 初始化”。formal assembly entry 还必须准备栈、描述符、异常入口和 ABI 参数。

## 11. 为什么最后使用 `lretq`

Linux 5.10 中：

```text
initial_code = x86_64_start_kernel
```

进入 C 代码前，assembly 把 `initial_code` 取到 `%rax`，压入 `__KERNEL_CS` 和目标地址，然后执行 `lretq`。

源码特别解释了为什么没有改成 64-bit offset 的 indirect far jump：AMD64 对相应 far-jump memory operand 的支持与 Intel64 不同。这里使用 far return 同时完成正确的 CS 和目标 RIP 交接。

最终：

```text
%rdi = boot_params
CS = __KERNEL_CS
RIP = x86_64_start_kernel
RSP = initial_stack
```

这才是 B03 的 formal assembly → early C 边界。

## 12. BSP 与 secondary CPU 不能混成一条入口

BSP 初始启动从：

```text
startup_64
```

进入，调用 `__startup_64()`，修正 `early_top_pgt`。

secondary CPU 走：

```text
secondary_startup_64
```

调用 `__startup_secondary_64()`，使用 `init_top_pgt`。两条路径在后续 assembly 中复用大量状态建立代码，但它们的入口前提和 early page-table ownership 不相同。

Linux 5.10 还存在：

```text
secondary_startup_64_no_verify
```

它是 SEV-ES secondary bring-up 的特殊入口，因为该阶段执行 `verify_cpu()` 可能产生尚不能处理的 `#VC`；不能把它写成一般 AP 默认入口。

B03 的主线仍然是 BSP `startup_64`。secondary 路径只用于建立边界，为后续 SMP 学习保留正确模型。

## 13. `mov %cr3` 之后页表也没有“永久完成”

进入 `x86_64_start_kernel()` 后，`head64.c` 仍包含：

```text
reset_early_page_tables()
__early_make_pgtable()
```

说明 early page tables 是启动基础设施，而不是内存管理初始化完成后的最终状态。

后续 `setup_arch()`、memblock、direct map 建立和正式页表管理属于 B04 与 `memory/` 的课程范围。B03 到这里停止，避免把“formal entry 页表交接”扩展成完整内存管理课程。

## 14. 配置条件必须放回正确语境

B03 阅读 Linux 5.10 源码时至少要注意：

| 配置/条件 | 对本章的影响 |
|---|---|
| `CONFIG_X86_64` | 本章整体架构前提 |
| `CONFIG_X86_5LEVEL` | 是否包含 LA57/5-level early paging 状态 |
| `CONFIG_DYNAMIC_MEMORY_LAYOUT` | 5-level 下部分虚拟布局基址的动态状态 |
| `CONFIG_RANDOMIZE_BASE` | `KERNEL_IMAGE_SIZE` 为 1 GiB 或 512 MiB |
| `CONFIG_PAGE_TABLE_ISOLATION` | early/init PGD 的对齐与填充形式 |
| `CONFIG_AMD_MEM_ENCRYPT` / SEV | SME modifier、early encryption 与特殊 secondary 路径 |
| `CONFIG_HOTPLUG_CPU` | `start_cpu0` 等后续 CPU 入口存在性 |

配置条件应描述“这段实现是否存在或如何变化”，不能从源码中存在 `#ifdef` 推断当前运行内核一定启用了该配置。

## 15. `ident_map.c` 为什么不是本章主调用链

领域大纲曾把 `arch/x86/mm/ident_map.c` 列为建议源码之一。重新核对 Linux 5.10 后，formal BSP entry 所需的 switchover identity mapping 是直接在：

```text
arch/x86/kernel/head64.c::__startup_64()
```

中使用 `early_dynamic_pgts` 构造的。

因此 B03 不虚构：

```text
startup_64 → ident_map.c
```

这样的调用链。`ident_map.c` 可以作为其他 identity-map 使用场景的关联源码阅读，但不是本章 formal-entry 主线。

## 16. 把整章压缩成状态交接

B03 最终应形成下面的状态模型：

```text
入口：
  CPU 已在 long mode
  当前代码由早期 identity mapping 支撑
  %rsi = boot_params physical pointer

__startup_64：
  根据实际 physaddr 计算 load_delta
  修正 high-half kernel mapping
  建立 switchover identity mapping
  更新 phys_base
  处理 5-level/SME 等配置状态

assembly：
  形成 early_top_pgt 的 CR3 value
  写 CR3
  indirect jump 到 kernel VA
  换 kernel GDT / stack / early IDT
  建立 EFER/CR0/RFLAGS 状态
  %rsi → %rdi

出口：
  lretq → x86_64_start_kernel(boot_params)
```

最重要的结论不是“Linux 又建了一次页表”，而是：**formal kernel 必须把前一阶段提供的临时可执行地址空间，转换成与本次实际物理装载位置一致、能够按正式 kernel virtual address 继续执行的早期地址空间。**

下一章 B04 将从这里继续，分析 `x86_64_start_kernel()` 如何接管 BSS、early page tables、`boot_params` 和架构初始化状态，并最终进入通用 `start_kernel()`。

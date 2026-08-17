# B04 Linux 5.10 源码核验：从 `x86_64_start_kernel()` 到 `start_kernel()`

本文件只记录 Linux kernel v5.10 的实现事实，供 B04 正文和实验引用。B04 关注 formal kernel 已经建立可执行的高地址环境之后，x86 早期 C 代码如何接管启动数据，并把控制权交给通用 `start_kernel()`；完整内存管理、调度、时间子系统分别留在对应领域展开。

## 1. 本次核验范围

直接核对 upstream Linux v5.10：

```text
arch/x86/kernel/head64.c
arch/x86/kernel/setup.c
init/main.c
```

主要入口：

```text
x86_64_start_kernel()
x86_64_start_reservations()
start_kernel()
setup_arch()
mm_init()
arch_call_rest_init()
```

## 2. 第一条边界：`x86_64_start_kernel()` 不是 `start_kernel()` 的薄包装

`arch/x86/kernel/head64.c` 中：

```text
x86_64_start_kernel(real_mode_data)
  → cr4_init_shadow()
  → reset_early_page_tables()
  → clear_bss()
  → clear_page(init_top_pgt)
  → sme_early_init()
  → kasan_early_init()
  → idt_setup_early_handler()
  → copy_bootdata(__va(real_mode_data))
  → load_ucode_bsp()
  → init_top_pgt[511] = early_top_pgt[511]
  → x86_64_start_reservations(real_mode_data)
```

这段代码仍属于 x86-64 的 very-early C 环境。它先清理 BSS、重置/整理 early page-table 状态、建立早期异常处理环境，再复制 boot data，之后才进入下一层。

### 2.1 `real_mode_data` 与 `boot_params`

`x86_64_start_kernel()` 的参数仍是早期阶段传来的 `real_mode_data`。`copy_bootdata()` 执行：

```text
memcpy(&boot_params, real_mode_data, sizeof(boot_params));
sanitize_boot_params(&boot_params);
```

并从 `boot_params.hdr.cmd_line_ptr` 与 `boot_params.ext_cmd_line_ptr` 合成 command-line 物理地址，把命令行复制到 `boot_command_line`。

因此 B04 应区分三个对象/阶段：

```text
real_mode_data
    早期入口传下来的 boot-data 位置

boot_params
    formal kernel 内部持有的 4 KiB 全局副本

boot_command_line
    从 boot protocol 指针指向的字符串复制出的内核缓冲区
```

不能把 `%rsi/%rdi` 中的 `real_mode_data` 指针与全局 `boot_params` 本身视为同一个对象。

`copy_bootdata()` 完成后还调用 `sme_unmap_bootdata(real_mode_data)`；源码注释明确指出旧 boot data 不再需要，也不会继续被保留。这是一次明显的 ownership/lifetime 交接。

## 3. `x86_64_start_reservations()` 是架构入口到通用入口的最后一层

Linux 5.10 实现为：

```text
x86_64_start_reservations(real_mode_data)
  → if (!boot_params.hdr.version)
        copy_bootdata(__va(real_mode_data))
  → x86_early_init_platform_quirks()
  → [hardware_subarch == X86_SUBARCH_INTEL_MID]
        x86_intel_mid_early_setup()
  → start_kernel()
```

在通常的 x86-64 BSP 路径中，`x86_64_start_kernel()` 已经执行过 `copy_bootdata()`，所以这里的 version 检查不会再次复制；该防御性路径仍应保留在源码模型中。

这里之后进入 `init/main.c:start_kernel()`，控制流从 x86 专属入口进入通用内核初始化主线。

## 4. `start_kernel()` 的入口状态与第一阶段

Linux 5.10 `init/main.c:start_kernel()` 开头首先建立 init task 的栈尾 magic、processor id 和 early debug object 状态，然后：

```text
cgroup_init_early()
local_irq_disable()
early_boot_irqs_disabled = true
boot_cpu_init()
page_address_init()
...
setup_arch(&command_line)
```

这里必须准确描述中断状态：`start_kernel()` 显式执行 `local_irq_disable()` 并把 `early_boot_irqs_disabled` 置为 true。源码注释也明确说明，在完成必要初始化之前 interrupts remain disabled。

B04 只需要把 `cgroup_init_early()` 作为真实顺序中的一个调用点记录下来；当前基础课程不展开 cgroup 机制。

## 5. `setup_arch()` 是 `start_kernel()` 内部的架构初始化，不在它之前

这是 B04 最重要的调用关系之一：

```text
x86_64_start_kernel()
  → x86_64_start_reservations()
    → start_kernel()
      → setup_arch(&command_line)
```

不能写成：

```text
x86_64_start_kernel() → setup_arch() → start_kernel()
```

`arch/x86/kernel/setup.c` 对 `setup_arch()` 的注释直接称其为 architecture-specific boot-time initializations。

### 5.1 `setup_arch()` 开始时仍依赖 memblock/boot data

函数开头先 reserve kernel image、page 0 和 initrd；随后建立 early traps/CPU/ioremap 状态，从 `boot_params` 接管 root device、screen/EDID、loader 信息，处理 E820/setup_data，并形成 command line：

```text
strlcpy(command_line, boot_command_line, COMMAND_LINE_SIZE);
*cmdline_p = command_line;
```

它还在 early-param 解析后继续处理 E820/EFI/DMI/hypervisor、确定 `max_pfn`、准备 early page-table buffer，最终执行：

```text
reserve_brk()
e820__memblock_setup()
...
init_mem_mapping()
...
initmem_init()
...
x86_init.paging.pagetable_init()
...
```

所以 `setup_arch()` 不是“普通设备初始化”，而是把 boot protocol / firmware memory description 转换为后续通用内核能够使用的架构内存、CPU、页表和平台基础状态。

完整 E820→memblock、direct map 和 allocator 机制属于 `memory/`；B04 只说明这些步骤为何必须发生在通用 allocator 初始化之前。

## 6. `start_kernel()` 在 `setup_arch()` 之后建立通用运行基础

从 Linux 5.10 `init/main.c` 可以固定下面的关键顺序：

```text
setup_arch(&command_line)
setup_boot_config(command_line)
setup_command_line(command_line)
setup_nr_cpu_ids()
setup_per_cpu_areas()
smp_prepare_boot_cpu()
...
build_all_zonelists(NULL)
page_alloc_init()
...
trap_init()
mm_init()
...
sched_init()
preempt_disable()
...
rcu_init()
...
early_irq_init()
init_IRQ()
tick_init()
rcu_init_nohz()
init_timers()
hrtimers_init()
softirq_init()
timekeeping_init()
...
local_irq_enable()
```

这条顺序给出几个重要约束：

1. `setup_arch()` 先把架构和早期物理内存基础准备好，之后通用页分配器/zone 才进入初始化；
2. `mm_init()` 中才执行 `mem_init()`、`kmem_cache_init()`、`vmalloc_init()` 等，不能把这些能力假定为 `setup_arch()` 一开始就已经完整可用；
3. `sched_init()` 明确发生在 timer interrupt 等普通中断开始工作之前；源码注释说明此时需要先有 functioning scheduler；
4. `start_kernel()` 在 `sched_init()` 后显式 `preempt_disable()`，因为首次进入 idle 之前 early boot scheduling 很脆弱；
5. IRQ/tick/timer/hrtimer/softirq/timekeeping 的初始化均发生在 `local_irq_enable()` 之前；真正开放本地中断是在这些基础设施建立之后。

B04 只解释这些顺序依赖；scheduler、timekeeping、RCU 的内部算法分别留给对应章节。

## 7. `mm_init()` 的边界

Linux 5.10 `init/main.c:mm_init()` 包含：

```text
page_ext_init_flatmem()
init_debug_pagealloc()
report_meminit()
mem_init()
kmem_cache_init()
kmemleak_init()
pgtable_init()
debug_objects_mem_init()
vmalloc_init()
ioremap_huge_init()
init_espfix_bsp()
pti_init()
```

因此应区分：

```text
setup_arch()/memblock 阶段
    早期发现、描述、保留和映射物理内存

page_alloc_init()/mm_init() 及其周边
    逐步把系统推进到常规页分配、slab/vmalloc 等运行环境
```

不能笼统写成“进入 `start_kernel()` 后内存分配器已经可用”。具体 allocator 何时可用应按所需 allocator 单独判断。

## 8. B04 的结束边界

Linux 5.10 `start_kernel()` 在大量通用初始化后调用：

```text
arch_call_rest_init();
```

弱默认实现只是：

```text
rest_init();
```

`rest_init()`、PID 1、`kthreadd`、`kernel_init()`、initcall 和用户态 init 属于 B05。B04 到这里结束，不提前展开用户空间启动。

## 9. CONFIG 与架构条件

B04 正文至少应保留下列条件意识：

- `CONFIG_X86_64`：本章主线限定 x86-64；`setup_arch()` 内仍包含大量 x86-32 条件分支，不能把这些分支写成 x86-64 实际执行路径；
- `CONFIG_AMD_MEM_ENCRYPT`/SME：影响 early boot-data mapping、page-table flags 和早期初始化；
- `CONFIG_X86_5LEVEL`：早期页表状态来自前一阶段，B04 不重复解释 LA57 transition；
- `CONFIG_BLK_DEV_INITRD`：initrd reserve/relocation 路径受配置控制；
- `CONFIG_EFI` 与实际 `efi_enabled(EFI_BOOT)`：EFI 初始化既有编译条件，也有本次启动的 runtime 条件；
- `CONFIG_CMDLINE_BOOL` / `CONFIG_CMDLINE_OVERRIDE`：决定 built-in command line 与 loader command line 的组合语义。

## 10. 执行上下文

这一阶段仍是 boot CPU 的单线程 early-boot 初始化上下文。不能把它当成已经具有普通进程运行环境的常规内核线程上下文。

在 `start_kernel()` 的早期阶段：

- local IRQ 被显式关闭；
- scheduler 尚未初始化，随后才执行 `sched_init()`；
- slab/vmalloc 等常规分配能力在 `mm_init()` 中逐步建立；
- 普通 IRQ/timer/timekeeping 基础设施随后才初始化；
- `local_irq_enable()` 明确晚于这些初始化步骤。

## 11. B04 正文应保持的主线

```text
formal head_64.S
  → x86_64_start_kernel(real_mode_data)
      ├─ reset early state / clear BSS / early IDT
      ├─ copy_bootdata(): real_mode_data → boot_params + boot_command_line
      └─ x86_64_start_reservations()
           → x86 platform quirks
           → start_kernel()
                ├─ disable local IRQ / establish generic early state
                ├─ setup_arch(&command_line)
                │    └─ consume boot_params, E820, memblock, paging/platform state
                ├─ generic memory/CPU/scheduler/RCU/IRQ/timer/timekeeping init
                ├─ local_irq_enable()
                └─ ... → arch_call_rest_init()
```

本章要解释的是“架构早期 C 环境如何变成通用内核运行基础”，而不是逐行枚举 `start_kernel()` 的所有初始化函数。

## 12. 已核验但尚未实测的证据边界

本文件完成的是 Linux v5.10 source-level fact check。当前没有在匹配的 v5.10 build tree 上执行：

- `nm/readelf/objdump` 对 `x86_64_start_kernel` / `start_kernel` 的实际符号和机器码核验；
- GDB 对 `real_mode_data`、`boot_params`、`boot_command_line` 的动态观察；
- 在 `setup_arch()`、`sched_init()`、`local_irq_enable()` 等观察点检查 IRQ/preempt/allocator 状态。

这些应在 B04 实验中作为更高等级证据设计，不把源码核验写成动态实测。
# B04：从 `x86_64_start_kernel()` 到 `start_kernel()`

B03 结束时，formal kernel 已经完成早期页表修正、切换到内核虚拟地址执行环境，并通过 `lretq` 进入 `x86_64_start_kernel()`。从这里开始，CPU 已经能够执行普通 C 代码，但这还不是我们熟悉的“完整内核运行环境”。

这一章要回答的问题是：**Linux 如何把一个仍受早期启动条件约束的 x86 专属 C 环境，逐步变成可以初始化通用内核子系统的运行环境？**

主线不是逐项背诵 `start_kernel()` 中的函数，而是观察能力如何按依赖关系建立：

```text
formal startup_64
  → x86_64_start_kernel(real_mode_data)
      → 整理 x86 early state
      → copy_bootdata()
          real_mode_data → boot_params
                         → boot_command_line
      → x86_64_start_reservations()
          → x86 early platform quirks
          → start_kernel()
              → 关闭并保持 local IRQ
              → setup_arch(&command_line)
                  → 消费 boot_params / E820
                  → 建立 memblock / paging / platform 基础
              → 建立通用 memory / scheduler / RCU / IRQ / timer 基础
              → local_irq_enable()
              → ... → arch_call_rest_init()
```

B04 到 `arch_call_rest_init()` 为止。`rest_init()`、PID 1、`kthreadd`、initcall 和用户态 init 留到 B05。

---

## 1. 为什么进入 C 代码后仍然属于 early boot

能够执行 C 函数，只说明当前已经具备了 C 代码所需的基本机器环境。它并不意味着内核的普通服务已经可用。

在这一阶段，很多后来习以为常的能力仍不存在或只处于早期形态：

- scheduler 尚未初始化；
- slab、vmalloc 等常规分配能力尚未全部建立；
- 普通 IRQ、tick、timer、hrtimer、softirq、timekeeping 尚未完成初始化；
- CPU、固件和物理内存信息仍要从启动参数与平台描述中接管；
- local IRQ 会在 `start_kernel()` 很早的位置显式关闭，并在大量基础设施建立后才重新打开。

因此不能用“已经进入 C”作为 early boot 与 normal kernel environment 的分界。

更准确的理解是：这一段代码正在**逐步解除 early boot 的约束**。

---

## 2. 第一层交接：`real_mode_data` 不能长期作为内核启动数据

### 2.1 `real_mode_data` 从哪里来

B03 中 formal `head_64.S` 把早期阶段传下来的 boot-data 物理指针从 `%rsi` 转为 SysV AMD64 C ABI 的第一个参数 `%rdi`，随后进入：

```c
x86_64_start_kernel(real_mode_data)
```

这里的 `real_mode_data` 仍指向早期启动阶段留下的参数区。它不是 formal kernel 自己长期拥有的普通全局对象。

如果后续所有代码都继续依赖这个外部位置，会产生两个问题：

1. 生命周期和 ownership 不清楚；
2. 后续内存布局变化时，内核仍被迫保留并依赖早期映射关系。

Linux 因此会尽早把需要长期使用的信息复制到 formal kernel 自己控制的对象中。

### 2.2 `copy_bootdata()` 完成 ownership 交接

Linux 5.10 的 `x86_64_start_kernel()` 在清理 early state 后调用：

```text
copy_bootdata(__va(real_mode_data))
```

其中最重要的动作是：

```text
real_mode_data
    │
    ├── memcpy → 全局 boot_params
    │              └── sanitize_boot_params()
    │
    └── command-line physical address
                    └── copy → boot_command_line
```

于是必须区分三个对象：

```text
real_mode_data
    早期入口传来的 boot-data 位置

boot_params
    formal kernel 持有的 4 KiB 全局副本

boot_command_line
    formal kernel 自己保存的命令行字符串缓冲区
```

它们不是三个名字指向同一个对象。

命令行尤其值得注意。`boot_params` 保存的是 boot protocol 提供的 command-line 地址信息，而 `boot_command_line` 保存的是实际复制出的字符串内容。后续 `setup_arch()` 再基于这个副本形成通用初始化所使用的 command line。

`copy_bootdata()` 完成后还会执行 `sme_unmap_bootdata(real_mode_data)`。从阶段模型上看，这意味着 formal kernel 已经取得需要长期保存的信息，旧 boot-data mapping 不再承担长期 ownership。

---

## 3. `x86_64_start_kernel()` 为什么不是一个薄包装

Linux 5.10 中的 `x86_64_start_kernel()` 在进入通用初始化前还要整理一批 x86 very-early state。主线可以概括为：

```text
x86_64_start_kernel(real_mode_data)
  → cr4_init_shadow()
  → reset_early_page_tables()
  → clear_bss()
  → clear_page(init_top_pgt)
  → SME/KASAN early setup
  → idt_setup_early_handler()
  → copy_bootdata()
  → load_ucode_bsp()
  → 衔接 init_top_pgt 与 early_top_pgt
  → x86_64_start_reservations()
```

这些动作说明 `x86_64_start_kernel()` 仍处于 architecture-owned 的 very-early C 阶段。

BSS 清零、early page-table 整理、early IDT、microcode 与 boot-data 接管，都必须在更广泛的通用内核代码开始依赖这些状态之前完成。

这里不要把 B03 与 B04 混为一章：B03 解释“CPU 怎样得到可执行 formal kernel C 的机器状态”；B04 解释“formal kernel C 怎样取得启动数据 ownership，并建立通用内核初始化所需的基础”。

---

## 4. `x86_64_start_reservations()`：进入通用入口前的最后一层

Linux 5.10 的调用关系是：

```text
x86_64_start_kernel()
  → x86_64_start_reservations()
      → start_kernel()
```

`x86_64_start_reservations()` 仍保留一个防御性条件：如果 `boot_params.hdr.version` 尚未建立，它会再次执行 `copy_bootdata()`。在正常 x86-64 BSP 主线上，前面的 `x86_64_start_kernel()` 已经完成复制，因此通常不会走这条分支。

随后它执行 x86 early platform quirks，并在特定 subarchitecture 下执行相应 early setup，最后调用：

```c
start_kernel();
```

从这里开始，控制流进入 `init/main.c` 的通用初始化主线。

“通用”不等于“与架构无关”。`start_kernel()` 仍会调用 architecture-specific hook。区别在于：从现在开始，初始化流程由通用内核框架组织，架构代码作为其中的阶段参与。

---

## 5. 一个重要调用关系：`setup_arch()` 位于 `start_kernel()` 内部

容易形成的错误模型是：

```text
x86_64_start_kernel()
  → setup_arch()
  → start_kernel()
```

Linux 5.10 的真实关系却是：

```text
x86_64_start_kernel()
  → x86_64_start_reservations()
      → start_kernel()
          → setup_arch(&command_line)
```

这个顺序反映了 Linux 的初始化组织方式。

`start_kernel()` 是通用的顶层 orchestrator；`setup_arch()` 则是其中负责 architecture-specific boot-time initialization 的阶段。换言之，架构初始化没有在进入 `start_kernel()` 时结束，而是被纳入通用初始化主线继续推进。

---

## 6. `start_kernel()` 入口时有哪些能力，哪些还没有

`start_kernel()` 开头会建立一些最基本的通用状态，随后很早执行：

```text
local_irq_disable()
early_boot_irqs_disabled = true
```

因此 B04 中观察任何函数时，都不能默认“中断已经正常工作”。

此时仍处于 boot CPU 的 early-boot 执行上下文：

```text
scheduler       尚未初始化
normal IRQ      尚未完成初始化
slab/vmalloc    尚未完整建立
timekeeping     尚未初始化
ordinary task   尚不是这里的执行模型
```

这也解释了为什么 early boot 代码大量依赖静态对象、memblock、early mapping 和专门的 early helper，而不能随意调用后来才建立的服务。

`start_kernel()` 的意义不是“所有基础设施已经可用”，而是从这里开始由一个统一的主线按依赖关系把这些基础设施逐个建立起来。

---

## 7. `setup_arch()`：把启动描述转换为内核可继续使用的架构状态

### 7.1 它消费什么

到 `setup_arch()` 时，formal kernel 已经有自己的 `boot_params` 和 `boot_command_line` 副本，但这些仍主要是“启动输入”。

`setup_arch()` 要把它们转化为后续初始化真正依赖的架构状态，例如：

- kernel image、page 0、initrd 等保留区；
- root device、screen/EDID、loader 等启动信息；
- E820 与 setup_data；
- command line；
- EFI/DMI/hypervisor 等平台信息；
- 物理内存边界与 PFN 信息；
- early page-table buffer 与 direct mapping 基础。

它开始时仍然处于 memblock/early mapping 世界，而不是普通 allocator 世界。

### 7.2 命令行再次发生一次“接口转换”

`setup_arch()` 中可以看到：

```text
strlcpy(command_line, boot_command_line, COMMAND_LINE_SIZE)
*cmdline_p = command_line
```

于是 command line 的阶段可以画成：

```text
boot loader 指向的字符串
        ↓
boot_params 中的地址元数据
        ↓ copy_bootdata()
boot_command_line
        ↓ setup_arch()
command_line / cmdline_p
        ↓
通用参数解析
```

这比简单说“命令行存在于 `boot_params`”更准确：不同阶段持有的是地址元数据、字符串副本和通用解析入口。

### 7.3 E820 到 memblock 是能力转换，不只是数据复制

`setup_arch()` 中的关键步骤包括：

```text
e820 / platform memory description
        ↓
e820__memblock_setup()
        ↓
memblock 描述 early usable/reserved physical memory
        ↓
init_mem_mapping()
        ↓
建立后续初始化所需的映射基础
```

完整的 E820、memblock 和 direct-map 算法属于 `memory/`。B04 只需要理解依赖关系：**通用页分配器要建立，首先必须知道哪些物理内存存在、哪些可用、哪些已被占用，并且 CPU 必须能够通过适当映射访问它们。**

因此 `setup_arch()` 必须发生在普通页分配环境成熟之前。

---

## 8. 从 memblock 世界走向普通 allocator 世界

`setup_arch()` 返回后，`start_kernel()` 继续推进通用内存初始化。关键顺序包括：

```text
setup_arch()
  ↓
build_all_zonelists()
  ↓
page_alloc_init()
  ↓
...
mm_init()
```

Linux 5.10 的 `mm_init()` 中进一步执行：

```text
mem_init()
kmem_cache_init()
...
vmalloc_init()
```

这里应避免一句模糊的“内存管理初始化完成”。不同 allocator 的可用时刻并不相同。

更合适的能力模型是：

```text
boot protocol / E820
    描述启动时看到的物理内存

memblock
    early boot 阶段记录、保留和分配物理区域

page allocator / zones
    建立常规物理页分配基础

slab / vmalloc
    在更晚阶段建立常用内核分配能力
```

这些阶段之间存在依赖，因此 early boot 代码不能把后面的 allocator 当成已经存在。

具体 buddy、SLUB、vmalloc 的内部机制在 `memory/` 中展开；本章只保留启动顺序和能力边界。

---

## 9. scheduler 为什么要早于普通 timer interrupt 工作

`start_kernel()` 在内存基础建立后继续初始化 scheduler：

```text
...
mm_init()
...
sched_init()
preempt_disable()
...
```

随后才进入 RCU、IRQ、tick、timer、hrtimer、softirq、timekeeping 等基础设施的初始化。

这不是任意排列。

一旦 timer interrupt 等事件开始参与系统运行，内核就可能需要维护运行时间、处理调度相关状态，并最终触发调度决策。scheduler 的核心数据结构和基本运行条件因此必须先准备好。

这里仍不要提前展开调度算法。B04 关注的是初始化依赖：**不能先让依赖 scheduler 的异步事件体系开始正常工作，再去建立 scheduler。**

`sched_init()` 后出现的 `preempt_disable()` 也提醒我们，early boot 仍不是普通可抢占任务环境。Linux 会显式约束这一段的执行状态，直到首次进入正常 idle/task 运行模型。

---

## 10. 为什么 IRQ、timer 和 timekeeping 建立后才打开 local IRQ

Linux 5.10 中可以观察到这样的关键顺序：

```text
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

如果在这些基础设施准备好之前开放普通中断，CPU 可能进入一个 handler 已经能够被硬件触发、但其依赖的数据结构和软件机制还没有准备好的状态。

所以这里的设计原则是：

```text
先建立处理异步事件所需的基础设施
        ↓
再允许异步事件真正打断当前执行
```

需要注意，`local_irq_disable()` / `local_irq_enable()` 描述的是当前 CPU 的 local interrupt state，不等同于“系统里所有中断硬件在这两条指令之间都完全不存在”。本章关注 boot CPU 的执行约束。

---

## 11. 一张能力建立时间线

把 B04 的重点压缩成能力变化，可以得到：

```text
进入 x86_64_start_kernel()
│
├─ CPU 已能执行 formal kernel C
├─ early page tables / stack / IDT 基础存在
├─ 普通 scheduler/allocator/IRQ/timer 尚不可假定可用
│
├─ copy_bootdata()
│    └─ formal kernel 取得 boot_params / command-line ownership
│
├─ start_kernel()
│    └─ local IRQ 保持关闭
│
├─ setup_arch()
│    ├─ 消费 boot_params / E820 / platform data
│    ├─ 建立 memblock 与架构内存基础
│    └─ 建立后续 paging/platform 状态
│
├─ page allocator / mm_init()
│    └─ 常规 memory allocation 能力逐步建立
│
├─ sched_init()
│    └─ scheduler 基础建立
│
├─ RCU / IRQ / tick / timer / softirq / timekeeping init
│
└─ local_irq_enable()
     └─ boot CPU 开始允许普通本地中断进入
```

这张图比完整抄写 `start_kernel()` 的函数列表更有用，因为它表达了每个阶段**新增了什么能力，以及为什么下一阶段依赖它**。

---

## 12. CONFIG 与运行条件不能从主线中抹掉

上面的主线以 x86-64 Linux 5.10 为基准，但部分步骤受配置或本次启动环境影响。

至少要保留这些条件意识：

- `CONFIG_X86_64`：本章主线限定 x86-64；`setup_arch()` 中的 x86-32 分支不能写成当前主线；
- `CONFIG_AMD_MEM_ENCRYPT` / SME：影响 early boot-data mapping、页表属性和相关 early setup；
- `CONFIG_X86_5LEVEL`：LA57 状态来自前一阶段，本章只接管，不重新解释 transition；
- `CONFIG_BLK_DEV_INITRD`：initrd 的 reserve/relocation 路径受该配置控制；
- `CONFIG_EFI` 与 `efi_enabled(EFI_BOOT)`：既存在编译期条件，也存在本次启动的运行时条件；
- `CONFIG_CMDLINE_BOOL` / `CONFIG_CMDLINE_OVERRIDE`：影响 built-in command line 与 loader command line 的组合语义。

因此教材中的“主线”表示典型控制流和依赖关系，不意味着所有可选分支在每个 kernel configuration 中都会执行。

---

## 13. 常见误区

### 误区一：进入 `x86_64_start_kernel()` 后就是普通内核环境

不是。它仍处于 boot CPU 的 very-early C 阶段，很多通用基础设施尚未建立。

### 误区二：`real_mode_data`、`boot_params` 和 `boot_command_line` 是同一个对象

不是。前者是早期启动数据位置；`boot_params` 是 formal kernel 的 4 KiB 全局副本；`boot_command_line` 是命令行字符串副本。

### 误区三：`setup_arch()` 在 `start_kernel()` 之前调用

不是。Linux 5.10 的真实关系是 `start_kernel() → setup_arch()`。

### 误区四：进入 `start_kernel()` 就已经可以随意 `kmalloc()` / `vmalloc()`

不能这样推断。allocator 能力是分阶段建立的，`mm_init()` 中才继续建立 `mem_init()`、slab、vmalloc 等环境。

### 误区五：`local_irq_disable()` 意味着 IRQ 子系统已经初始化，只是暂时关闭

不是。early `start_kernel()` 中普通 IRQ 基础设施本身还在后面才初始化。

### 误区六：`start_kernel()` 中的函数顺序只是代码组织习惯

不是。很多顺序反映真实依赖，例如 memory 基础先于 scheduler，scheduler 基础先于普通异步事件运行条件，而 IRQ/timer/timekeeping 基础先于 `local_irq_enable()`。

---

## 14. B04 与其他章节的边界

本章只解释启动阶段的能力交接：

- early page-table 机器状态来自 B03；
- E820、memblock、buddy、SLUB、vmalloc 的内部机制放在 `memory/`；
- scheduler 内部算法放在 `scheduler/`；
- clocksource、clockevent、tick、timer/hrtimer 放在 `timekeeping/`；
- `rest_init()`、PID 1、`kthreadd`、initcall 和用户态 init 放在 B05。

因此读完 B04 后，应该能够回答的不是“`start_kernel()` 有多少个调用”，而是：

> formal kernel 怎样取得启动数据 ownership，并按依赖顺序建立 memory、scheduler 和 interrupt/time 基础，使 early boot 环境逐步具备运行普通内核代码的条件？

---

## 15. Linux 5.10 源码入口

本章实现事实已经按 Linux v5.10 单独核验，详见：

- [`../source-paths/04-x86-start-kernel-linux-5.10.md`](../source-paths/04-x86-start-kernel-linux-5.10.md)

主要源码：

```text
arch/x86/kernel/head64.c
    x86_64_start_kernel()
    x86_64_start_reservations()
    copy_bootdata()

arch/x86/kernel/setup.c
    setup_arch()

init/main.c
    start_kernel()
    mm_init()
    arch_call_rest_init()
```

下一步实验将把这些源码事实分成 source-level、实际构建产物和 QEMU/GDB 动态状态三层验证，重点观察 boot-data ownership、IRQ state 与各类基础能力的建立顺序。
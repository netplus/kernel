# B04 实验预期分析：从 x86 early C 到通用内核初始化

本文件给出 `04-x86-start-kernel` 实验的独立验收基线。它不要求把 `start_kernel()` 的所有调用逐项背下来，而是要求能够用 Linux 5.10 的源码、匹配构建产物和运行现场说明：启动数据的 ownership 如何交接，架构初始化如何嵌入通用初始化主线，以及普通 allocator、scheduler、IRQ 和时间基础为什么只能按依赖关系逐步建立。

## 1. 先固定阶段模型

B04 的主线应能够归纳为：

```text
formal head_64.S
  → x86_64_start_kernel(real_mode_data)
      → 整理 x86 very-early state
      → copy_bootdata()
          real_mode_data → global boot_params
                         → boot_command_line
      → x86_64_start_reservations()
          → x86 early platform quirks
          → start_kernel()
              → local_irq_disable()
              → setup_arch(&command_line)
                  → 消费 boot_params / E820 / platform description
                  → 建立 memblock / paging / architecture foundation
              → generic memory / scheduler / RCU / IRQ / time foundation
              → local_irq_enable()
              → ... → arch_call_rest_init()
```

这个模型有两个不能混淆的边界：

1. 进入 `x86_64_start_kernel()` 只说明 CPU 已能执行 formal-kernel C 代码，不说明普通内核服务已经可用；
2. `setup_arch()` 是 `start_kernel()` 内部的 architecture-specific boot-time initialization，而不是 `start_kernel()` 之前的独立阶段。

## 2. boot data ownership 的预期结论

实验应区分：

```text
real_mode_data
    早期入口传来的 boot-data 位置

boot_params
    formal kernel 持有的 4 KiB 全局结构副本

boot_command_line
    formal kernel 持有的命令行字符串副本
```

Linux 5.10 的 `copy_bootdata()` 应能支持下面的结论：

```text
memcpy(&boot_params, real_mode_data, sizeof boot_params)
  → sanitize_boot_params(&boot_params)
  → 根据 hdr.cmd_line_ptr/ext_cmd_line_ptr 得到 command-line 地址
  → memcpy(boot_command_line, ...)
  → sme_unmap_bootdata(real_mode_data)
```

因此不能把 `real_mode_data` 指针、全局 `boot_params` 和命令行字符串视为同一个对象。`boot_params` 中保存的 command-line 字段主要是地址元数据，而 `boot_command_line` 才是 formal kernel 复制出的字符串内容。

`x86_64_start_reservations()` 中 `!boot_params.hdr.version` 时再次 `copy_bootdata()` 是防御性路径；正常 BSP 主线已经在 `x86_64_start_kernel()` 中复制过一次，不能据此写成“正常路径复制两次”。

## 3. `start_kernel()` 与 `setup_arch()` 的调用层次

必须接受：

```text
x86_64_start_kernel()
  → x86_64_start_reservations()
      → start_kernel()
          → setup_arch(&command_line)
```

必须拒绝：

```text
x86_64_start_kernel() → setup_arch() → start_kernel()
```

这不是单纯的函数排列问题。`start_kernel()` 是通用初始化的顶层组织者，而 `setup_arch()` 是被它调用的架构启动阶段。进入通用主线以后仍然会回到 architecture-specific code 完成启动状态转换。

## 4. command line 的阶段性 ownership

预期模型是：

```text
boot loader 提供的字符串
        ↓
boot_params 中的地址元数据
        ↓ copy_bootdata()
boot_command_line
        ↓ setup_arch()
command_line / cmdline_p
        ↓
通用参数解析
```

所以“命令行在 `boot_params` 中”只是对协议元数据的简化说法，不能代替对实际字符串副本和后续接口转换的说明。

## 5. early memory 到普通 allocator 的能力边界

B04 只验收初始化依赖，不在本章重新讲 buddy、SLUB 或 vmalloc 内部算法。

应建立：

```text
boot_params / E820 / platform description
  → setup_arch()
      → e820__memblock_setup()
      → init_mem_mapping()
      → architecture memory/paging foundation
  → build_all_zonelists()
  → page_alloc_init()
  → ...
  → mm_init()
      → mem_init()
      → kmem_cache_init()
      → ...
      → vmalloc_init()
```

这里必须避免两个过度简化：

- 不能说“进入 `start_kernel()` 时普通 allocator 已经可用”；
- 不能说“`page_alloc_init()` 一个调用就等于 buddy/slab/vmalloc 全部可用”。

正确结论是：不同内存能力在不同阶段逐步建立；具体 allocator 的完整可用条件要在 `memory/` 中分别分析。

## 6. IRQ 软件状态与硬件 IF 必须分开

Linux 5.10 `start_kernel()` 早期显式执行：

```text
local_irq_disable()
early_boot_irqs_disabled = true
```

实验必须区分：

```text
early_boot_irqs_disabled
    Linux early-boot 软件状态/一致性标记

RFLAGS.IF
    x86 CPU 的硬件 interrupt-enable flag
```

因此只观察 `early_boot_irqs_disabled == true`，不能单独证明某个断点处硬件 IF 的值；L3 应在精确断点位置读取 `RFLAGS`。反过来，只观察 IF 也不能替代 Linux 软件状态的核对。

B04 应接受的能力结论是：基础设施建立期间 local IRQ 保持关闭，IRQ/tick/timer/hrtimer/softirq/timekeeping 等关键基础初始化完成后才执行 `local_irq_enable()`。

## 7. scheduler、RCU、IRQ 与时间基础的顺序

实验至少应确认下面的源码偏序：

```text
local_irq_disable()
  < setup_arch()
  < mm_init()
  < sched_init()
  < rcu_init()
  < early_irq_init()/init_IRQ()
  < tick_init()/init_timers()/hrtimers_init()/softirq_init()/timekeeping_init()
  < local_irq_enable()
  < arch_call_rest_init()
```

这里的 `<` 只表示 `start_kernel()` 主线中的先后约束，不表示每一对相邻函数之间都有直接调用关系。

`sched_init()` 后的 `preempt_disable()` 也属于 early-boot 约束的一部分。B04 不据此展开 scheduler 算法，只要求理解：在 IRQ/timer 等普通异步活动开放之前，其依赖的核心运行基础必须先建立。

## 8. CONFIG 与 runtime 条件

验收结果至少要保留以下条件意识：

- `CONFIG_X86_64`：本章主线是 x86-64；
- `CONFIG_AMD_MEM_ENCRYPT`：影响 early boot-data mapping 与 SME 路径；
- `CONFIG_X86_5LEVEL`：页表模式来自前一启动阶段，B04 接管而不重复解释 transition；
- `CONFIG_BLK_DEV_INITRD`：initrd 处理路径受编译条件控制；
- `CONFIG_EFI` 与 `efi_enabled(EFI_BOOT)`：同时存在 build-time 与 runtime 条件；
- `CONFIG_CMDLINE_BOOL` / `CONFIG_CMDLINE_OVERRIDE`：影响 built-in 与 loader command line 的组合。

源码中存在条件路径，不等于某次实际启动执行了它。L2/L3 结果必须同时记录 `.config` 和 runtime 条件。

## 9. L1 / L2 / L3 证据等级

### L1：Linux v5.10 source contract

L1 可以证明：

- 函数、对象和调用关系在 v5.10 源码中存在；
- ownership copy 与 sanitize/unmap 的源码顺序；
- `setup_arch()` 位于 `start_kernel()` 内；
- memory/scheduler/IRQ/time 初始化的源码偏序；
- CONFIG/runtime guard 在源码中的存在方式。

L1 不能证明某个实际构建是否 inline/消除了函数边界，也不能证明某次启动现场的寄存器和状态值。

### L2：匹配构建的 `vmlinux`

L2 使用 `nm/readelf/objdump` 验证：

- 本次构建中相关符号是否存在；
- `x86_64_start_kernel()`、reservations、`start_kernel()`、`setup_arch()` 的实际 call/control-flow；
- 编译优化是否改变静态函数的可见边界。

符号地址大小关系不能替代调用关系证据。

### L3：QEMU/GDB runtime

L3 才能观察：

- P0 `%rdi` 中的 early boot-data 参数以及 `RSP/RIP/RFLAGS`；
- P1 `boot_params` 与 `boot_command_line` 的实际内容；
- P2 `start_kernel()` / `setup_arch()` 附近的 IF 与 `early_boot_irqs_disabled`；
- P3 `sched_init()`、`local_irq_enable()` 与 `arch_call_rest_init()` 附近的动态状态。

源码推导不能冒充这些运行时结果。

## 10. 当前验收状态

当前仓库已经完成：

- Linux v5.10 source-level fact check；
- B04 正式教程；
- B04 L1/L2/L3 实验设计；
- 本 expected analysis 的独立验收基线。

当前环境尚未执行：

- 真实 Linux v5.10 checkout 上的命令级 L1 复核；
- 匹配构建的 `nm/readelf/objdump`；
- QEMU/GDB P0–P3 动态观察。

因此当前可以把 source-level 结论作为 B04 的实现基线，但不能把 L2/L3 描述写成已实测事实。

## 11. B04 收章前的下一项工作

下一最小单元应把适合机器判断的 L1 条件转换成自动 source-contract checker，至少覆盖：

```text
copy_bootdata() ownership copy/sanitize/unmap
x86_64_start_reservations() → start_kernel()
start_kernel() → setup_arch()
early local IRQ disable/software flag
setup_arch → mm_init → sched_init → IRQ/time → local_irq_enable 的关键偏序
arch_call_rest_init() 的结束边界
```

checker 只能提升 L1 的可重复性；它仍不能替代 L2 build artifact 或 L3 runtime 证据。
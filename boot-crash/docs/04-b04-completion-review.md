# B04 收章复核：从 `x86_64_start_kernel()` 到 `start_kernel()`

本文件对 B04 的正式教程、Linux 5.10 source-path、实验、expected analysis 与自动 source-contract checker 做收章前一致性复核。复核目标不是增加新的 `start_kernel()` 调用列表，而是确认本章已经形成一个可独立验收的模型：formal kernel 进入 early C 后，如何取得启动数据 ownership，并按依赖关系逐步建立普通内核运行基础。

## 1. 复核材料

本次交叉检查：

```text
boot-crash/docs/04-x86-start-kernel-to-start-kernel.md
boot-crash/source-paths/04-x86-start-kernel-linux-5.10.md
boot-crash/labs/04-x86-start-kernel/README.md
boot-crash/labs/04-x86-start-kernel/expected-analysis.md
boot-crash/labs/04-x86-start-kernel/verify_source_contract.py
boot-crash/labs/04-x86-start-kernel/test_verify_source_contract.py
```

Linux 5.10 实现基线仍限定为：

```text
arch/x86/kernel/head64.c
arch/x86/kernel/setup.c
init/main.c
```

## 2. 主调用层次一致

各材料都采用同一条主线：

```text
formal head_64.S
  → x86_64_start_kernel(real_mode_data)
      → copy_bootdata()
      → x86_64_start_reservations(real_mode_data)
          → start_kernel()
              → setup_arch(&command_line)
              → generic initialization
              → local_irq_enable()
              → ... → arch_call_rest_init()
```

这里最重要的层次边界已经一致：`setup_arch()` 是 `start_kernel()` 内部的 architecture-specific boot-time initialization，不是 `start_kernel()` 之前的独立阶段。B04 因而没有把“进入通用入口”错误理解成“架构初始化已经结束”。

## 3. boot-data ownership 与 lifetime 一致

教程、source-path、实验和 checker 都区分三个对象：

```text
real_mode_data
    早期阶段传入的 boot-data 位置

boot_params
    formal kernel 自己持有的 4 KiB 全局结构副本

boot_command_line
    formal kernel 自己持有的命令行字符串副本
```

`copy_bootdata()` 的验收顺序统一为：

```text
copy boot_params
→ sanitize_boot_params()
→ 取得 command-line 地址
→ copy boot_command_line
→ sme_unmap_bootdata(real_mode_data)
```

因此本章没有把 `%rdi`/`real_mode_data`、全局 `boot_params` 和命令行字符串混成同一个对象，也没有把 `x86_64_start_reservations()` 中的 version 防御分支误写成正常 BSP 路径一定发生第二次复制。

## 4. early memory 到普通 allocator 的能力边界一致

各材料都把 `setup_arch()` 视为仍处于 boot data、memblock 和 early mapping 世界的阶段，并把后续能力建立表示为：

```text
boot_params / E820
  → setup_arch()
      → e820__memblock_setup()
      → init_mem_mapping()
  → build_all_zonelists()
  → page_alloc_init()
  → ...
  → mm_init()
      → mem_init()
      → kmem_cache_init()
      → ...
      → vmalloc_init()
```

这一模型只说明启动阶段的依赖和能力边界，不把 `page_alloc_init()` 简化成“所有 allocator 的单一启用点”，也不在 boot-crash 中重复 buddy、SLUB、vmalloc 的内部机制；这些内容继续由 `memory/` 完整讲解。

## 5. IRQ 软件状态与硬件状态没有混淆

B04 已统一区分：

```text
early_boot_irqs_disabled
    Linux early-boot 软件状态/一致性标记

RFLAGS.IF
    x86 CPU 的硬件 interrupt-enable flag
```

源码层可以确认 `local_irq_disable()`、software flag 和后续 `local_irq_enable()` 的顺序；但某个动态断点处 IF 的实际值必须由 L3 读取 RFLAGS。实验因此要求分别观察软件变量和硬件标志，没有用其中一个替代另一个。

## 6. 通用初始化偏序一致

source-path、正文、实验、expected analysis 与 checker 对 B04 所需的关键偏序保持一致：

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

这里的 `<` 是 `start_kernel()` 主线中的源码先后约束，不表示相邻项互为直接 caller/callee。正文也没有借此提前展开 scheduler、RCU 或 timekeeping 的内部算法。

## 7. CONFIG 与执行上下文边界一致

B04 已保留下列条件意识：

```text
CONFIG_X86_64
CONFIG_AMD_MEM_ENCRYPT
CONFIG_X86_5LEVEL
CONFIG_BLK_DEV_INITRD
CONFIG_EFI + efi_enabled(EFI_BOOT)
CONFIG_CMDLINE_BOOL / CONFIG_CMDLINE_OVERRIDE
```

源码中存在条件路径不等于某次启动执行了该路径；实验要求 L2/L3 同时记录 `.config` 和 runtime 条件。

执行上下文也保持一致：本章仍是 boot CPU 的 early-boot 初始化上下文。进入 C 或进入 `start_kernel()` 都不能被解释成普通任务、普通 allocator、IRQ/timer 等服务已经全部可用。

## 8. B04/B05 章节边界一致

B04 统一在：

```text
start_kernel()
  → ...
  → arch_call_rest_init()
```

处结束。Linux 5.10 的弱默认 `arch_call_rest_init()` 调用 `rest_init()`，但 `rest_init()`、PID 1、`kthreadd`、`kernel_init()`、initcall、initramfs/rootfs 和用户态 init 均留给 B05。

这使 B04 的问题保持单一：early C 如何建立通用内核运行基础；B05 再解释已经具备这些基础后如何创建内核启动任务并跨越用户态 `exec` 边界。

## 9. 自动验收与证据等级复核

当前 checker 固定 7 组 L1 source-contract：

```text
1. boot-data ownership copy/sanitize/command-line/unmap
2. x86_64_start_kernel() → reservations → start_kernel()
3. setup_arch() 位于 start_kernel() 内部
4. early local-IRQ disable/software flag 位于 setup_arch() 之前
5. memory → scheduler/RCU → IRQ/time → IRQ enable → rest-init 偏序
6. mm_init(): mem_init → kmem_cache_init → vmalloc_init
7. arch_call_rest_init() → rest_init() 章节边界
```

fixture self-test 已实际执行 8 个 unittest：1 个完整正例 + 7 个负例，全部通过，exit code 0。该结果只证明 checker 的 matcher/ordering 行为符合设计。

证据等级保持为：

```text
工具证据
    checker fixture self-test

L1
    真实 Linux v5.10 checkout 上的源码契约与人工上下文复核

L2
    匹配构建的 vmlinux / nm / readelf / objdump

L3
    QEMU/GDB 动态启动现场
```

当前尚未在本环境执行真实 checkout 上的 checker CLI、匹配构建的 L2 或 QEMU/GDB L3。这些是增强证据，不冒充为已完成结果，也不阻塞当前内容层面的收章。

## 10. 收章结论

B04 当前能够独立回答：

- 为什么进入 formal-kernel C 后仍属于 early boot；
- `real_mode_data` 如何转化为 formal kernel 自己持有的启动数据；
- `x86_64_start_kernel()`、reservations、`start_kernel()` 与 `setup_arch()` 的真实层次；
- memblock/early mapping 与普通 allocator 的能力边界；
- scheduler、RCU、IRQ、timer/timekeeping 与 local IRQ enable 的顺序约束；
- software IRQ state 与 `RFLAGS.IF` 为什么需要不同证据；
- B04 为什么应在 `arch_call_rest_init()` 处结束；
- 哪些结论已经有 source/tool 证据，哪些仍需要构建和运行时证据。

因此 B04 的 source-path、正式教程、实验、expected analysis 和自动验收在内容层面已经一致，可以进入领域 README 收章接入。下一最小单元应更新 `boot-crash/README.md`，将 B04 标记为已完成并接入本 completion review；之后再进入 B05。
# B04 实验：从 x86 early C 到通用内核初始化

本实验对应 B04《从 `x86_64_start_kernel()` 到 `start_kernel()`》。目标不是证明“内核已经进入 C”，而是验证 Linux 5.10 如何逐步取得 boot data ownership，并按依赖关系建立普通内核运行所需的内存、调度、中断和时间基础。

## 1. 要验证的问题

本实验围绕五个问题组织：

1. `real_mode_data` 如何变成 formal kernel 自己持有的 `boot_params` 与 `boot_command_line`；
2. `setup_arch()` 究竟位于 `start_kernel()` 之前还是内部；
3. `start_kernel()` 早期的 local IRQ 状态是什么；
4. memblock/early mapping 如何先于普通 page/slab/vmalloc allocator；
5. scheduler、IRQ、tick/timer/timekeeping 与 `local_irq_enable()` 为什么具有明确顺序。

验证分三层：

```text
L1：Linux v5.10 源码契约
L2：匹配构建的 vmlinux / 符号 / 反汇编
L3：QEMU/GDB 动态启动现场
```

当前仓库已经完成 L1 源码事实核验；本实验先把可复核的 L1 检查步骤固定下来。当前执行环境没有匹配的 Linux v5.10 build tree/QEMU，因此 L2/L3 只定义操作与验收点，不填写虚构结果。

## 2. 环境

推荐准备：

```text
Linux kernel v5.10 源码树
对应 .config 和完成构建的 vmlinux
GNU grep / sed / awk
nm / readelf / objdump
GDB
QEMU x86_64
```

源码树记为：

```bash
export K510=/path/to/linux-5.10
```

先确认版本，不要在其他版本源码上把结果标成 Linux 5.10：

```bash
cd "$K510"
git describe --tags --exact-match HEAD
```

预期基线为 `v5.10`。

## 3. L1：验证 boot data ownership 交接

查看：

```bash
grep -n -A90 'void __init x86_64_start_kernel' \
    "$K510/arch/x86/kernel/head64.c"
grep -n -A55 'static void __init copy_bootdata' \
    "$K510/arch/x86/kernel/head64.c"
```

应确认主线包含：

```text
x86_64_start_kernel(real_mode_data)
  → copy_bootdata(__va(real_mode_data))
      → memcpy(&boot_params, real_mode_data, sizeof boot_params)
      → sanitize_boot_params(&boot_params)
      → 根据 hdr.cmd_line_ptr/ext_cmd_line_ptr 得到命令行物理地址
      → memcpy(boot_command_line, __va(cmd_line_ptr), COMMAND_LINE_SIZE)
      → sme_unmap_bootdata(real_mode_data)
```

验收重点不是记住 `memcpy`，而是能解释三个对象的 ownership：

```text
real_mode_data       早期阶段传来的 boot-data 位置
boot_params          formal kernel 持有的全局结构副本
boot_command_line    formal kernel 持有的命令行字符串副本
```

特别检查 `x86_64_start_reservations()`：

```bash
grep -n -A35 'x86_64_start_reservations' \
    "$K510/arch/x86/kernel/head64.c"
```

应看到 `!boot_params.hdr.version` 时的防御性 `copy_bootdata()`，随后是 early platform quirks，最后才调用 `start_kernel()`。不要把这个防御分支误写成正常 BSP 主线一定复制两次。

## 4. L1：证明 `setup_arch()` 在 `start_kernel()` 内部

执行：

```bash
grep -n '^asmlinkage __visible void __init start_kernel' \
    "$K510/init/main.c"
grep -n 'setup_arch(&command_line)' "$K510/init/main.c"
grep -n '^void __init setup_arch' "$K510/arch/x86/kernel/setup.c"
```

应建立真实调用关系：

```text
x86_64_start_kernel()
  → x86_64_start_reservations()
      → start_kernel()
          → setup_arch(&command_line)
```

以下模型必须判错：

```text
x86_64_start_kernel() → setup_arch() → start_kernel()
```

继续查看 `setup_arch()` 中命令行接口转换：

```bash
grep -n -E 'strlcpy\(command_line|\*cmdline_p = command_line' \
    "$K510/arch/x86/kernel/setup.c"
```

观察：

```text
boot_params 中的地址元数据
  → copy_bootdata()
boot_command_line 字符串副本
  → setup_arch()
command_line / cmdline_p
  → 通用参数解析
```

## 5. L1：验证 early memory 能力建立顺序

先在 `setup_arch()` 中定位：

```bash
grep -n -E 'e820__memblock_setup|init_mem_mapping|initmem_init|pagetable_init' \
    "$K510/arch/x86/kernel/setup.c"
```

再在 `start_kernel()` / `mm_init()` 中定位：

```bash
grep -n -E 'setup_arch\(&command_line\)|build_all_zonelists|page_alloc_init\(\)|mm_init\(\)' \
    "$K510/init/main.c"
grep -n -A35 '^static void __init mm_init' "$K510/init/main.c"
```

验收模型应是：

```text
boot_params / E820
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

这不是在声称 `page_alloc_init()` 单独就是 buddy allocator 的全部“启用点”；实验只验证 B04 所需的初始化依赖和能力边界。buddy、SLUB、vmalloc 的完整生命周期留在 `memory/`。

## 6. L1：验证 IRQ、scheduler 与时间基础的顺序

从 `start_kernel()` 抽取关键调用：

```bash
grep -n -E 'local_irq_disable\(\)|early_boot_irqs_disabled = true|sched_init\(\)|preempt_disable\(\)|rcu_init\(\)|early_irq_init\(\)|init_IRQ\(\)|tick_init\(\)|init_timers\(\)|hrtimers_init\(\)|softirq_init\(\)|timekeeping_init\(\)|local_irq_enable\(\)|arch_call_rest_init\(\)' \
    "$K510/init/main.c"
```

必须确认至少下面的偏序关系：

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

这里的 `<` 表示源码主线中的先后关系，不表示每个相邻函数之间都有直接调用。

另外检查：

```text
early_boot_irqs_disabled = true
```

与 `local_irq_disable()` 的位置。B04 的结论是“基础设施建立期间 local IRQ 保持关闭，之后显式打开”，而不是“进入 `start_kernel()` 时中断已经正常运行”。

`cgroup_init_early()` 可能出现在这条真实源码顺序中，但当前基础课程不展开 cgroup；不要为了课程范围而篡改真实调用顺序，也不要把它扩写成专题。

## 7. CONFIG / runtime 条件核验

阅读 B04 时至少保留以下条件：

```text
CONFIG_X86_64
CONFIG_AMD_MEM_ENCRYPT
CONFIG_X86_5LEVEL
CONFIG_BLK_DEV_INITRD
CONFIG_EFI + efi_enabled(EFI_BOOT)
CONFIG_CMDLINE_BOOL / CONFIG_CMDLINE_OVERRIDE
```

实验不要求所有配置都实际构建一遍，但结果记录必须写明所用 `.config`。如果观察某条条件路径，必须同时给出对应 config/runtime 条件；不能只凭源码中“存在该函数”声称本次启动执行了它。

## 8. L2：用实际 `vmlinux` 核对符号和机器码

在匹配的 v5.10 build tree 中：

```bash
nm -n vmlinux | grep -E ' x86_64_start_kernel$| x86_64_start_reservations$| start_kernel$| setup_arch$| mm_init$| sched_init$'

readelf -Ws vmlinux | grep -E 'x86_64_start_kernel|start_kernel|setup_arch'

objdump -dr --no-show-raw-insn vmlinux \
  | less
```

L2 要回答：

1. 这些符号是否确实存在于本次构建；
2. `x86_64_start_kernel()` 的 call site 是否能对应到 `copy_bootdata()`/reservations 主线；
3. `x86_64_start_reservations()` 是否最终进入 `start_kernel()`；
4. `start_kernel()` 是否实际包含对 `setup_arch()` 的调用；
5. 编译优化、静态函数 inline/消除是否改变了源码层面函数边界的可见性。

不要用两个符号地址的大小关系代替控制流证据。链接地址排序不能证明调用顺序。

## 9. L3：QEMU/GDB 动态观察

建议关闭 KASLR 以降低断点地址变化带来的干扰，并保留本次 `.config`、kernel command line 与 QEMU 命令。

建议观察点：

```text
P0  x86_64_start_kernel() 入口
P1  copy_bootdata() 返回后
P2  start_kernel() / setup_arch() 前后
P3  sched_init()、local_irq_enable()、arch_call_rest_init() 附近
```

### P0：入口 ownership 尚未完成

记录：

```gdb
info registers rdi rsp rip rflags
p/x real_mode_data
p/x &boot_params
p/x &boot_command_line
```

要确认 `%rdi` 是 early boot-data 参数，而不是 `&boot_params`。

### P1：`copy_bootdata()` 后

比较：

```gdb
p/x boot_params.hdr.version
x/s boot_command_line
```

如环境允许，再比较 early boot-data 对应字段与 global copy。不要在 `sme_unmap_bootdata()` 后继续假设旧地址一定可安全解引用。

### P2：`start_kernel()` 与 `setup_arch()`

记录：

```gdb
info registers rflags rsp rip
p early_boot_irqs_disabled
```

x86 RFLAGS.IF 位应结合断点精确位置解释。不要只看 `early_boot_irqs_disabled` 软件变量就声称硬件 IF 状态；两者应分别观察。

在 `setup_arch()` 前后还可记录 memblock 状态，但完整 memblock 数据结构解释留给 `memory/`。

### P3：scheduler 与 IRQ 开放边界

分别在 `sched_init()` 前后和 `local_irq_enable()` 前后观察：

```gdb
info registers rflags
p early_boot_irqs_disabled
```

预期是源码所定义的初始化顺序能够在运行现场复现。若编译配置或断点位置使某个符号不可直接断下，应记录实际机器码位置，不要伪造函数级观察结果。

## 10. 结果记录模板

```text
kernel commit/tag:
.config hash:
compiler/binutils:
QEMU command:
kernel command line:

L1:
- copy_bootdata ownership:
- reservations → start_kernel:
- start_kernel → setup_arch:
- memory-init ordering:
- IRQ/scheduler/time ordering:
- CONFIG/runtime conditions:

L2:
- symbols:
- call sites / disassembly:
- optimization differences:

L3:
- P0 rdi/rsp/rip/rflags:
- P1 boot_params / boot_command_line:
- P2 IF + early_boot_irqs_disabled:
- P3 scheduler/IRQ boundary:
```

## 11. 通过标准

实验达到基础通过标准时，应能够用证据说明：

1. `real_mode_data`、global `boot_params` 和 `boot_command_line` 是不同阶段/ownership 的对象；
2. `x86_64_start_reservations()` 才把 x86 early-C 主线交给 `start_kernel()`；
3. `setup_arch()` 是 `start_kernel()` 内部的 architecture-specific boot-time initialization；
4. memblock/early mapping 先建立，普通 page/slab/vmalloc 能力随后逐步形成；
5. scheduler/RCU/IRQ/timer/timekeeping 基础在 `local_irq_enable()` 前按依赖建立；
6. 软件变量 `early_boot_irqs_disabled` 与硬件 RFLAGS.IF 必须分别观察；
7. L1 源码事实、L2 build artifact 和 L3 runtime 证据不能互相冒充。

## 12. 当前验证状态

已完成：

- Linux v5.10 source-level fact check；
- B04 正式教程；
- 本实验的 L1/L2/L3 验收设计。

当前环境未执行：

- 真实 v5.10 checkout 上的命令级 L1 复核；
- 匹配构建的 `nm/readelf/objdump`；
- QEMU/GDB P0–P3 动态观察。

下一最小实验单元应补 `expected-analysis.md`，把 ownership、调用层次、allocator/IRQ 能力边界与证据等级固定为独立验收基线；随后再将适合机器判断的 L1 条件转换成 source-contract checker。
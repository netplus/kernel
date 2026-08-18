# B06 Linux 5.10 源码路径：Kexec 的基本模型

本文只核验 B06 需要的 Kexec 总体架构：Kexec 为什么把“准备下一内核”与“真正切换机器状态”分开，`struct kimage` 在两阶段之间承担什么角色，以及 normal kexec 与 crash kexec 从一开始就有哪些不同约束。具体的 `kexec_load` / `kexec_file_load` 映像布局细节留给 B07，最终 `machine_kexec()` / `relocate_kernel` 切换过程留给 B08，purgatory 留给 B09。

源码基线：upstream Linux v5.10，x86-64。

## 1. 配置与入口边界

Kexec 不是无条件存在的启动路径。Linux 5.10 的核心代码由 Kexec 配置控制；file-based syscall 还要求 `CONFIG_KEXEC_FILE`。x86-64 的 file loader 在 `arch/x86/kernel/machine_kexec_64.c` 中通过 `kexec_file_loaders[]` 注册 `kexec_bzImage64_ops`。

本章需要区分两种“加载接口”和两种“映像用途”：

```text
传统 segment 接口：kexec_load
file 接口：        kexec_file_load

normal image：      KEXEC_TYPE_DEFAULT，安装到 kexec_image
crash image：       KEXEC_TYPE_CRASH，安装到 kexec_crash_image
```

`kexec_load` 与 `kexec_file_load` 不是“normal 与 crash 各一个 syscall”。两种接口都能表达 crash image；传统接口使用 `KEXEC_ON_CRASH`，file 接口使用 `KEXEC_FILE_ON_CRASH`。因此课程后续不能把“file-based Kexec”与“crash Kexec”画成互斥分支。

相关源码：

```text
kernel/kexec.c
kernel/kexec_file.c
kernel/kexec_core.c
include/linux/kexec.h
arch/x86/kernel/machine_kexec_64.c
arch/x86/kernel/kexec-bzimage64.c
```

## 2. 为什么加载和切换必须分开

Kexec 的目标是绕过 firmware reboot，让当前 Linux 直接把 CPU 控制权交给另一个 kernel。这个目标带来一个关键矛盾：

- 准备映像时，希望当前内核仍然完整可用，可以分配内存、复制用户数据、解析映像、做安全检查并处理失败；
- 真正切换时，当前内核正在主动拆除自己的运行环境，设备、CPU、中断、页表和普通内核服务逐步不再适合依赖，而且最终阶段必须尽可能短、确定、不可失败。

Linux 5.10 因此把工作拆成两个生命周期不同的阶段：

```text
load / prepare phase
    在当前内核正常运行期间构造并安装 struct kimage

execute / transition phase
    使用已经安装好的 kimage 收缩旧环境并进入 arch transition code
```

这一点在 x86-64 `machine_kexec()` 的注释中非常明确：进入该函数时已经越过 point of no return，不能再分配内存，也不应再出现可恢复失败。与之对应，`machine_kexec_prepare()` 在加载阶段就预先构造 transition page table。

所以“加载成功”只表示下一映像已经被当前内核接受并保存，不表示 CPU 已经跳入下一内核；反过来，真正切换阶段也不应该再临时完成大量可能失败的映像解析和资源分配。

## 3. `struct kimage` 是两阶段之间的 ownership 对象

Linux 5.10 的 generic Kexec core 用 `struct kimage` 保存一份已准备映像的执行描述。`do_kimage_alloc_init()` 首先建立基础对象，并默认设置：

```text
image->head = 0
image->entry = &image->head
image->last_entry = &image->head
image->control_page = ~0
image->type = KEXEC_TYPE_DEFAULT
```

同时初始化 control/destination/unusable page lists。

传统 `kexec_load` 路径随后写入 `image->start`、segment list，并分配 `control_code_page`；normal image 还分配 `swap_page`。如果带 `KEXEC_ON_CRASH`，则把：

```text
image->control_page = crashk_res.start
image->type = KEXEC_TYPE_CRASH
```

file path 同样从 `do_kimage_alloc_init()` 开始，但设置 `image->file_mode = 1`，由内核读取 kernel/initrd/command line、探测 image format，并通过 architecture loader 形成 segment list。

这里最重要的 ownership 不是“syscall 栈帧持有 image”。加载成功时，generic code 用 `xchg()` 把新对象安装到全局槽位：

```text
normal → kexec_image
crash  → kexec_crash_image
```

被替换的旧 image 才由 `kimage_free()` 回收。这样 syscall 返回用户空间后，准备好的下一内核仍由当前 kernel 持有，等待未来独立发生的 execute/crash 事件。

## 4. traditional load path 的 B06 级调用骨架

Linux 5.10 `kernel/kexec.c` 的 normal/crash 共用主骨架是：

```text
SYSCALL_DEFINE4(kexec_load)
  → kexec_load_check()
  → mutex_trylock(&kexec_mutex)
  → do_kexec_load()
      → choose kexec_image or kexec_crash_image
      → kimage_alloc_init()
          → do_kimage_alloc_init()
          → copy_user_segment_list()
          → crash type/control-page policy if KEXEC_ON_CRASH
          → sanity_check_segment_list()
          → kimage_alloc_control_pages()
          → normal only: allocate swap_page
      → machine_kexec_prepare()
      → kimage_crash_copy_vmcoreinfo()
      → kimage_load_segment() for every segment
      → kimage_terminate()
      → machine_kexec_post_load()
      → xchg(dest_image, image)
```

`kexec_load_check()` 还要求 `CAP_SYS_BOOT`、检查 `kexec_load_disabled`、LSM/IMA 和 lockdown，并校验 flags 与 segment 数量。这些属于“当前内核仍然完整可用时完成”的 policy/validation 工作。

B06 只需要看清上述阶段边界；segment descriptor、source/destination page 链表和最终 relocation copy 留给 B07/B08。

## 5. file load path 与传统路径在哪里汇合

Linux 5.10 `kernel/kexec_file.c` 的 file path 大体为：

```text
SYSCALL_DEFINE5(kexec_file_load)
  → capability / flags / kexec_mutex
  → choose kexec_image or kexec_crash_image
  → kimage_file_alloc_init()
      → do_kimage_alloc_init()
      → image->file_mode = 1
      → crash type/control-page policy if requested
      → kimage_file_prepare_segments()
          → kernel_read_file_from_fd(kernel)
          → arch_kexec_kernel_image_probe()
          → [CONFIG_KEXEC_SIG] signature validation
          → optional initrd + command line
          → arch_kexec_kernel_image_load()
      → sanity_check_segment_list()
      → allocate control_code_page
      → normal only: allocate swap_page
  → machine_kexec_prepare()
  → kimage_crash_copy_vmcoreinfo()
  → kexec_calculate_store_digests()
  → kimage_load_segment() for every segment
  → kimage_terminate()
  → machine_kexec_post_load()
  → discard temporary file-load buffers
  → xchg(dest_image, image)
```

因此两种 syscall 的前半段不同：traditional path 接收用户空间已经组织好的 segments；file path 让 kernel 自己读取并解析 kernel image。但它们最终都形成 `struct kimage`、准备 architecture transition state、装入 segment backing pages，并安装到 normal/crash 全局 image slot。

这也是 B06 应采用的抽象层次：Kexec 的核心不是某一个 userspace command，而是“当前内核预先建立一份可执行的下一内核描述，并在稍后独立事件中消费它”。

## 6. normal 与 crash image 从加载时就不是同一种资源假设

`KEXEC_TYPE_DEFAULT` 与 `KEXEC_TYPE_CRASH` 的差别不只是最终由谁触发。

### 6.1 crash destination 必须落在预留区

`sanity_check_segment_list()` 对 `KEXEC_TYPE_CRASH` 额外验证每个 segment 的目标范围必须位于 `crashk_res` 内。传统 `kexec_load` 在 crash 模式下还先检查 entry 是否位于 crash reserved range。

这反映了 crash kernel 的基本设计：生产内核仍健康时就把捕获内核放进预留区域；发生 panic 后不能再假设能够像 normal Kexec load 一样寻找和准备任意普通内存。

### 6.2 control page allocator 不同

`kimage_alloc_control_pages()` 会根据 image type 选择 normal 或 crash control-page allocation policy。`kernel/kexec_core.c` 对 crash allocator 的注释指出，加载 crash kernel 时除了 control pages 外，其他页面都由 segments 指定并直接复制到预留区域。

### 6.3 normal image 才需要 swap page

`kernel/kexec.c` 和 `kernel/kexec_file.c` 都只在 `!kexec_on_panic` 时分配 `image->swap_page`。这是后续 relocation/copy 算法的实现要求，不应泛化为 crash image 也具有同样对象。

这些差异说明 normal/crash 两条路径必须从 load phase 就分开核验，不能到 `panic()` 或 `machine_kexec()` 才第一次区分。

## 7. x86-64 在加载阶段已经准备 transition state

Linux 5.10 x86-64 的：

```text
machine_kexec_prepare(struct kimage *image)
```

不是执行最终跳转。它在 load phase 根据 `image->control_code_page` 取得 transition page-table 起点，并调用 `init_pgtable()` 建立 identity mappings。`init_pgtable()` 不只覆盖已有 `pfn_mapped` 范围，也覆盖 `image->segment[]` 的目标范围，并准备 EFI/ACPI 所需映射，最后通过 `init_transition_pgtable()` 保证 `relocate_kernel` transition code 有可执行映射。

这进一步证明“准备”和“执行”分离并非用户空间工具层面的方便做法，而是 Linux 5.10 内核实现本身的结构：真正进入 point of no return 之前，连 transition page tables 这类可能分配失败的工作都应提前完成。

`machine_kexec()` 中则明确写着：不要再分配内存，也不要再失败。它关闭本地中断、准备 control code/page list、处理 GDT/IDT，最终调用复制到 control page 的 `relocate_kernel()`。这些机器切换细节属于 B08，本章只把它作为阶段边界的源码证据。

## 8. normal execute path 与 crash execute path 的前置假设

B06 只建立语义差异，不展开 B08/B13 的完整调用链。

### normal Kexec

normal Kexec 的设计前提是当前 kernel 仍处于可控状态。它可以主动进入 reboot/kexec 流程，停止 ordinary activity、协调 CPU 和设备，再进入 `machine_kexec()`。因此 normal path 能依赖“旧内核有机会按计划收缩自己的运行环境”。

### crash Kexec

crash Kexec 的触发前提相反：生产 kernel 已经发生 fatal failure。它使用预先安装的 `kexec_crash_image`，不能把普通 reboot 的设备 shutdown、锁、调度和内存分配能力当成可靠前提。正因为如此，crash image 必须预加载到 `crashkernel=` 预留资源中，并从加载阶段就使用不同的 destination/control-page 约束。

后续课程边界：

```text
B06：解释为什么有两种前置假设
B07：解释 image 如何被装入并成为 kimage
B08：解释 normal execute / relocation / control transfer
B10-B13：解释 crash reserved memory 与 panic/crash execute path
```

## 9. 几个必须避免的误区

### 误区一：`kexec_load()` 调用成功后马上跳转

错误。load syscall 成功后 image 被安装到 `kexec_image` 或 `kexec_crash_image`，当前 kernel 继续运行；execute 是之后的独立事件。

### 误区二：`kexec_load` 是 normal Kexec，`kexec_file_load` 是 crash Kexec

错误。两种 syscall 是两种加载 API；二者都能加载 normal 或 crash image。

### 误区三：Kexec 完全不需要 boot protocol

错误。Kexec 绕过的是 firmware reboot，不是新 kernel 自身的启动 ABI。x86 file loader 仍需为 bzImage 构造新 kernel 可接受的 boot parameters、command line、initrd 等状态。具体内容在 B07 展开。

### 误区四：crash Kexec 只是 normal Kexec 换了一个触发函数

错误。crash image 从加载时就受 `crashk_res`、特殊 control-page allocator、无 normal swap page 等约束；执行时又面对已经损坏的旧 kernel，前置假设不同。

### 误区五：`machine_kexec_prepare()` 已经开始关机

错误。它属于 load phase，在 x86-64 上主要提前准备 transition page tables。真正 point of no return 的机器切换阶段由后续 execute path 进入 `machine_kexec()`。

## 10. B06 源码核验结论

Linux 5.10 的 Kexec 可以先用下面的状态机理解：

```text
userspace supplies image
        |
        v
load syscall while old kernel is healthy
        |
        +--> validate / parse / allocate / prepare transition state
        |
        v
installed struct kimage
   |                 |
normal slot       crash slot
kexec_image       kexec_crash_image
   |                 |
future normal      future fatal
execute event      crash event
   |                 |
old kernel can     old kernel cannot be
quiesce normally   assumed healthy
   \                 /
    +--> arch transition --> next kernel
```

其中 `struct kimage` 是 load phase 留给未来 transition phase 的核心 ownership 对象；normal/crash 的差异从 load phase 已经开始，而不是在最后一跳才出现。

下一步 B06 正文应以这个状态模型为基础，先解释 Kexec 解决的问题和设计理由，再用少量 Linux 5.10 源码把模型落地。B07 才继续深入 image loader、segments、purgatory 和具体加载布局。
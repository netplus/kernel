# B06：Kexec 解决什么问题

Kexec 的核心目标不是“更快地执行一次 reboot 命令”，而是让一个正在运行的 Linux 内核在不重新经过 firmware 的情况下，把 CPU 控制权交给另一份已经准备好的 Linux 内核映像。

这个目标看似可以简化成“找到新内核入口然后跳过去”，但真正的问题恰恰在跳转之前：新内核需要自己的代码、数据、启动参数和可用的物理内存布局；旧内核此时仍占用 CPU、页表、中断、设备和大量内存；而一旦旧内核开始拆除自己的运行环境，就不能再依赖普通的内存分配、复杂错误恢复或用户空间帮助。

Linux 5.10 因此把 Kexec 设计成两个生命周期明显不同的阶段：

```text
load / prepare
    当前内核仍然健康
    → 校验输入
    → 构造 struct kimage
    → 准备 segments 和 transition state
    → 安装到全局 image slot

execute / transition
    未来某个独立事件触发
    → 收缩旧内核运行环境
    → 进入 machine_kexec()
    → relocation / control transfer
    → 新内核
```

理解这个分离，是后续理解 Kexec、Kdump 和 crash kernel 的基础。

---

## 1. firmware reboot、normal Kexec 与 crash Kexec

先区分三个不同问题。

### 1.1 firmware reboot

普通重启通常把机器控制权重新交给 firmware，再由 firmware、boot loader 和 Linux boot protocol 启动下一内核。旧 Linux 不需要亲自为下一内核维护一条直接的机器状态交接路径。

抽象地看：

```text
old Linux
  → reboot
  → firmware
  → boot loader
  → new Linux
```

firmware 可以重新初始化大量平台状态，但代价是启动路径较长，而且旧内核不能直接把已经准备好的下一映像作为一次内核内控制转移来消费。

### 1.2 normal Kexec

normal Kexec 绕过 firmware reboot：当前 Linux 在自己仍然健康时准备下一映像，并在之后的正常重启流程中主动停止 ordinary activity、协调 CPU/设备，最后进入 architecture-specific transition code。

```text
healthy old Linux
  → load next image
  → continue running
  → later kexec execute
  → quiesce old environment
  → machine transition
  → new Linux
```

这里的重要前提是：旧内核仍然可以按计划收缩自己的运行环境。

### 1.3 crash Kexec

crash Kexec 使用同一套 Kexec 基础能力，但前置假设完全不同：触发切换时生产内核已经发生 fatal failure。锁、调度器、设备状态乃至部分内存都可能不可信。

因此 crash kernel 不能等到 panic 以后再像 normal load 一样临时寻找内存、解析映像和完成大量可能失败的准备工作。捕获内核必须在生产内核健康时就装入预留资源，并等待未来的 crash event。

这就是 Kdump 为什么建立在 Kexec 上，却不能被解释成“normal Kexec 换了一个触发函数”。

---

## 2. 为什么不能只做一次 `jmp`

假设旧内核已经知道新内核入口地址，直接执行跳转仍然不够。

新内核至少需要面对这些问题：

- 它的各个 segment 应放到哪些物理地址；
- 启动参数、command line、initrd 等输入由谁准备；
- transition code 自己在切换页表和复制页面时从哪里执行；
- 旧内核与新内核的目标物理区域发生覆盖时如何安全搬运；
- 切换过程中还能不能分配内存；
- 中断、其他 CPU、GDT/IDT、页表和设备处于什么状态；
- 如果准备工作失败，系统应该在什么时候还能安全返回用户空间。

这些工作有一个共同特点：其中很多操作可能失败，而且需要完整的旧内核服务。

所以正确的设计不是：

```text
execute request
→ 临时解析新内核
→ 临时分配所有资源
→ 希望全部成功
→ jump
```

而是：

```text
old kernel still healthy
→ 完成可能失败的准备
→ 保存一份已经可执行的 image description

later
→ 进入尽量短且确定的 transition
```

Linux 5.10 x86-64 的 `machine_kexec()` 源码注释明确把这一阶段视为已经越过 point of no return：这里不应再分配内存，也不应设计新的可恢复失败路径。相应地，`machine_kexec_prepare()` 在 load phase 就提前准备 transition page tables。

---

## 3. `struct kimage`：两个阶段之间的 ownership 对象

Linux 5.10 generic Kexec core 使用 `struct kimage` 表示一份已经被当前内核接受并准备的下一映像。

它不是简单的“kernel 文件缓冲区”。从 B06 的抽象层次看，它同时承担：

```text
下一映像的类型
下一映像入口
segment 描述
control/transition 资源
page-list / relocation 所需状态
file-loader 相关状态（file mode 时）
```

基础对象由 `do_kimage_alloc_init()` 建立。不同加载 API 随后继续补充内容。

加载成功后，新的 `struct kimage` 通过 `xchg()` 安装到全局槽位：

```text
normal image → kexec_image
crash image  → kexec_crash_image
```

这一步非常重要，因为 syscall 随后会返回用户空间。也就是说：

> syscall 的调用栈已经消失，但 image 的生命周期必须继续存在。

因此 ownership 属于当前 kernel 的全局 Kexec 状态，而不是某次 syscall 的临时栈帧。未来 normal execute 或 crash event 再消费相应 image。

如果新 image 替换旧 image，被替换对象才进入 `kimage_free()` 回收流程。

---

## 4. 两种加载 API 不等于 normal/crash 两种用途

Linux 5.10 需要同时区分两个维度。

第一个维度是**输入接口**：

```text
kexec_load
    userspace 提供组织好的 segments

kexec_file_load
    kernel 读取 kernel/initrd/command line，探测并加载映像格式
```

第二个维度是**映像用途**：

```text
KEXEC_TYPE_DEFAULT
    normal image

KEXEC_TYPE_CRASH
    crash image
```

因此不能画成：

```text
kexec_load      = normal
kexec_file_load = crash
```

这是错误模型。

传统接口可以通过 `KEXEC_ON_CRASH` 构造 crash image；file 接口也可以通过 `KEXEC_FILE_ON_CRASH` 构造 crash image。两种 API 的前半段输入处理方式不同，但最后都会形成 `struct kimage`，完成 architecture preparation 和 segment loading，并安装到 normal/crash 全局槽位。

B07 会继续展开两种 loader 如何形成 segments；B06 只需要先建立这个二维模型。

---

## 5. Linux 5.10 的 load phase 在做什么

传统 `kexec_load` 的 B06 级主线可以压缩为：

```text
SYSCALL_DEFINE4(kexec_load)
  → policy / capability / flags checks
  → do_kexec_load()
      → kimage_alloc_init()
      → machine_kexec_prepare()
      → load segments
      → terminate image description
      → machine_kexec_post_load()
      → xchg() install image
```

file path 的输入准备不同：

```text
SYSCALL_DEFINE5(kexec_file_load)
  → policy / flags checks
  → kimage_file_alloc_init()
      → read kernel image
      → probe format
      → optional signature validation
      → prepare initrd / command line
      → architecture image loader
  → machine_kexec_prepare()
  → load segments
  → xchg() install image
```

这里应该关注的不是每个 helper 的细节，而是它们发生时的执行条件：

- 当前内核仍正常运行；
- 可以进行权限、安全和格式检查；
- 可以分配内存；
- 可以因为错误而放弃本次加载；
- 可以回收临时对象；
- 可以在成功后返回用户空间继续运行旧内核。

所以 `kexec_load()` 或 `kexec_file_load()` 成功的语义是：

> 当前内核已经持有一份准备好的下一映像。

它不是：

> CPU 已经开始执行下一内核。

---

## 6. x86-64 为什么在 load phase 就准备 transition page tables

Linux 5.10 x86-64 的 `machine_kexec_prepare(struct kimage *image)` 属于加载阶段，而不是最终跳转阶段。

它会围绕 `image->control_code_page` 准备 transition page-table 状态，并通过 `init_pgtable()` / `init_transition_pgtable()` 建立切换过程需要的映射，包括新映像目标区域和 transition code 所需的可执行映射。

为什么要提前做？

因为建立页表本身可能需要分配页面，也可能失败。如果把这件事拖到 `machine_kexec()` 以后，就会出现一个危险状态：旧内核已经开始不可逆地关闭自己，却突然发现 transition page table 无法建立。

因此这里体现的是一个普遍的系统设计原则：

```text
可能失败、可能分配资源的工作
        ↓
尽量放在 point of no return 之前

不可逆的机器状态切换
        ↓
只消费已经准备好的状态
```

B08 会继续分析 CR3、control page、`relocate_kernel` 和最终 control transfer；这里先固定生命周期边界。

---

## 7. normal image 与 crash image 从加载时就已经不同

normal/crash 的区别不是等到 execute 时才出现。

### 7.1 crash destination 受 `crashk_res` 约束

Linux 5.10 对 crash image 的 segment destination 做额外检查，目标范围必须落入 crash reserved resource。

这与 `crashkernel=` 的基本设计一致：生产内核健康时就为未来捕获内核保留一块资源，使 panic 以后不需要依赖普通内存分配来寻找下一内核的落脚点。

### 7.2 control-page allocation policy 不同

`kimage_alloc_control_pages()` 根据 image type 使用不同的分配约束。crash path 必须尊重预留区域及其特殊生命周期，不能简单复用 normal image 的全部资源假设。

### 7.3 normal image 才有 `swap_page`

Linux 5.10 的 traditional/file load path 都只为非-crash image 分配 `image->swap_page`。

这里先不要把 `swap_page` 理解成普通交换空间。它属于后续 relocation/copy 算法使用的 Kexec 内部对象；具体为什么需要它，放到 B07/B08 结合 page list 和复制算法再解释。

这三个差异共同说明：

> crash Kexec 从“映像如何被准备”开始就已经采用不同的资源假设。

---

## 8. execute phase 的能力为什么必须更少

真正 execute 时，旧内核要开始主动放弃自己原本提供的运行环境。

normal Kexec 可以在进入最终 architecture transition 前做有计划的 shutdown/quiesce；但越接近 `machine_kexec()`，越不能继续假定普通内核服务可用。

x86-64 `machine_kexec()` 会进入关闭本地中断、准备 control code/page-list、处理 descriptor-table/transition 状态并最终调用 relocation code 的路径。

这时的正确心智模型不是“另一个普通内核函数”，而是：

```text
ordinary kernel environment
        |
        | progressively removed
        v
minimal transition environment
        |
        v
new kernel execution environment
```

因此 load/execute 分离同时也是一种**能力收缩设计**：前半段拥有完整 Linux 服务，后半段只允许依赖事先明确保留下来的最小状态。

---

## 9. crash path 为什么对这种分离要求更强

normal execute 的旧内核至少被假定为健康，因此它有机会主动协调 CPU、设备和软件状态。

crash path 没有这个保证。发生 panic 时可能已经存在：

- 锁状态损坏；
- 某些 CPU 无法正常响应；
- scheduler 或普通 workqueue 不适合继续依赖；
- 设备仍在 DMA；
- 部分内存已经遭到破坏。

所以 crash Kexec 更依赖“健康时期已经完成的准备”：

```text
healthy production kernel
→ reserve crash memory
→ preload crash image
→ install kexec_crash_image

fatal failure later
→ consume prebuilt crash image
→ minimize dependence on damaged kernel
```

B10 以后会系统展开 `crashkernel=`、生产内核/捕获内核、panic 与 vmcore；B06 只需要理解为什么 Kexec 的两阶段模型是 Kdump 能成立的前提之一。

---

## 10. Kexec 绕过 firmware，但没有取消新内核的启动 ABI

“Kexec 不经过 firmware”容易引出另一个误解：既然不经过 boot loader，新内核是不是也不需要 boot protocol？

不是。

Kexec 改变的是**谁来准备和交接下一内核**。在 x86 上，新 kernel 仍需要能够理解的启动参数、command line、initrd 和内存布局描述。file-based loader 甚至明确由 kernel 自己解析 bzImage 并构造下一内核所需状态。

所以更准确的关系是：

```text
firmware boot:
firmware / boot loader prepares Linux boot state

Kexec:
old Linux prepares Linux boot state
```

新内核入口所要求的 ABI 并不会因为准备者从 boot loader 换成旧 Linux 就自动消失。

---

## 11. Linux 5.10 源码定位

B06 对应的主要源码为：

```text
kernel/kexec.c
kernel/kexec_core.c
kernel/kexec_file.c
include/linux/kexec.h
arch/x86/kernel/machine_kexec_64.c
arch/x86/kernel/kexec-bzimage64.c
```

关键对象和入口包括：

```text
struct kimage
kexec_image
kexec_crash_image

do_kimage_alloc_init()
kimage_alloc_init()
kimage_file_alloc_init()
machine_kexec_prepare()
machine_kexec()
```

配置边界至少要注意：

```text
CONFIG_KEXEC_CORE
CONFIG_KEXEC_FILE
CONFIG_KEXEC_SIG
```

不同配置会改变 file loader、安全校验和可用 syscall/path，不能把所有 helper 写成无条件调用。

更详细的 Linux 5.10 调用路径和字段核验见：

- [`../source-paths/06-kexec-model-linux-5.10.md`](../source-paths/06-kexec-model-linux-5.10.md)

---

## 12. 本章应形成的状态模型

可以把 B06 压缩成下面的状态机：

```text
                    healthy old kernel
                           |
                           v
                  load / prepare phase
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
     normal kimage                      crash kimage
     kexec_image                        kexec_crash_image
          |                                 |
 old kernel continues               old kernel continues
          |                                 |
 future normal execute                future fatal event
          |                                 |
          v                                 v
 planned environment                 damaged environment
     contraction                         assumptions
          |                                 |
          +---------------+-----------------+
                          v
                architecture transition
                          |
                          v
                     new kernel
```

其中最关键的四条结论是：

1. **load 成功不等于 execute 已发生。**
2. **`struct kimage` 是 load 与未来 transition 之间由旧内核持有的生命周期对象。**
3. **traditional/file 是加载接口维度，normal/crash 是映像用途维度，两者不能混为一谈。**
4. **normal/crash 从加载阶段就具有不同资源约束，而 crash path 对预先准备的依赖更强。**

---

## 13. 常见误区

### `kexec -l` 成功后 CPU 已经进入新内核

错误。加载和执行是独立事件；加载成功后旧内核仍可以继续运行。

### `kexec_file_load` 就是 crash-kernel syscall

错误。它是 file-based 加载 API，本身也可以准备 normal image。

### crash Kexec 只是 normal Kexec 在 `panic()` 中调用一次

错误。crash image 从 destination、control-page policy 到 `swap_page` 等资源条件，在 load phase 就已经与 normal image 不同；panic 后的旧内核运行假设也更弱。

### `machine_kexec_prepare()` 已经越过 point of no return

错误。它故意发生在 load phase，用来提前完成可能分配资源、可能失败的 architecture preparation。真正不可逆的机器切换在后续 execute path。

### Kexec 完全绕过 Linux boot protocol

错误。它绕过 firmware reboot；新 x86 Linux 的启动 ABI 仍需要由旧 kernel/loader 准备。

---

## 14. 与后续章节的边界

B06 到这里停止，不提前展开后续实现细节：

```text
B07
  kexec_load / kexec_file_load
  segments、destination、page list 与映像装载

B08
  machine_kexec()
  control page、relocate_kernel、最终机器状态切换

B09
  purgatory 的角色和验证边界

B10-B13
  crashkernel、生产/捕获内核、panic 与 crash_kexec
```

因此读完 B06 后，应先能够回答“为什么 Kexec 必须先准备、后切换，以及 normal/crash 的假设为什么不同”；至于具体页面如何搬运、寄存器如何进入下一入口，则在后续章节逐层展开。
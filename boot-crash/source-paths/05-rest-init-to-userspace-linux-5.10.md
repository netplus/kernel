# B05 Linux 5.10 源码事实核验：从 `rest_init()` 到用户空间

本文只记录 B05 正文需要依赖的 Linux kernel v5.10 实现事实。章节主线是：`start_kernel()` 的基础设施初始化结束后，内核如何创建 PID 1 与 `kthreadd`，如何完成 initcall/rootfs 准备，并最终由 PID 1 `exec` 用户态 init。

## 1. 本次核验范围

主要源码：

```text
init/main.c
init/do_mounts.c
include/linux/init.h
```

核心路径：

```text
arch_call_rest_init()
  -> rest_init()
       -> kernel_thread(kernel_init, NULL, CLONE_FS)
       -> kernel_thread(kthreadd, NULL, CLONE_FS | CLONE_FILES)
       -> system_state = SYSTEM_SCHEDULING
       -> complete(&kthreadd_done)
       -> schedule_preempt_disabled()
       -> cpu_startup_entry(CPUHP_ONLINE)

PID 1: kernel_init()
  -> kernel_init_freeable()
       -> wait_for_completion(&kthreadd_done)
       -> smp_prepare_cpus()
       -> workqueue_init()
       -> do_pre_smp_initcalls()
       -> smp_init()
       -> sched_init_smp()
       -> do_basic_setup()
            -> driver_init()
            -> do_initcalls()
       -> console_on_rootfs()
       -> [没有可执行 /init] prepare_namespace()
  -> async_synchronize_full()
  -> free_initmem()
  -> mark_readonly()
  -> pti_finalize()
  -> system_state = SYSTEM_RUNNING
  -> run_init_process(...)
       -> kernel_execve(...)
```

## 2. PID 0、PID 1 与 PID 2 不是同一种启动对象

`rest_init()` 运行时，当前任务仍是 boot idle task，也就是传统上称为 PID 0 / swapper 的任务。它不会通过 `exec` 变成用户态 init，而是在创建早期任务后进入 `cpu_startup_entry(CPUHP_ONLINE)`，成为 boot CPU 的 idle execution path。

`rest_init()` 明确先调用：

```c
pid = kernel_thread(kernel_init, NULL, CLONE_FS);
```

源码注释直接说明必须先 spawn init，使其取得 PID 1。随后才创建：

```c
pid = kernel_thread(kthreadd, NULL, CLONE_FS | CLONE_FILES);
```

因此正常初始 PID namespace 中的基本角色是：

```text
PID 0  boot idle / swapper
PID 1  kernel_init 创建出来的 init task
PID 2  kthreadd
```

这里必须区分两个事件：

1. `kernel_thread(kernel_init, ...)` 成功后，PID 1 这个 task 已经存在；
2. 很晚以后 `kernel_init()` 调用 `kernel_execve()` 成功，PID 1 才跨过 kernel-thread -> user-space program 的 exec 边界。

所以“PID 1 被创建”绝不等于“用户态 init 已经启动”。

## 3. 为什么先创建 PID 1，却不能让它立即自由运行

`rest_init()` 的源码注释说明了一个依赖环：init task 后续会需要创建 kernel threads，但此时 `kthreadd` 尚未建立。Linux 5.10 的处理不是改成先创建 kthreadd，因为那会占用 PID 1；而是：

```text
先创建 kernel_init -> 保证 PID 1
再创建 kthreadd     -> 通常取得 PID 2
complete(kthreadd_done)
```

`kernel_init_freeable()` 一开始执行：

```c
wait_for_completion(&kthreadd_done);
```

因此即使调度使 PID 1 较早获得 CPU，它也会在 completion 上等待，直到 `rest_init()` 已经建立 `kthreadd_task` 并发出 completion。

`rest_init()` 还暂时把 init task 固定在 boot CPU；源码说明在 `sched_init_smp()` 之前 task migration 尚未正确工作，后者之后才会建立适当的 allowed CPU mask。

## 4. `system_state` 与第一次显式调度

在 PID 1 与 kthreadd 创建后，`rest_init()` 执行：

```text
system_state = SYSTEM_SCHEDULING
complete(&kthreadd_done)
schedule_preempt_disabled()
cpu_startup_entry(CPUHP_ONLINE)
```

源码明确要求 boot idle thread 至少执行一次 `schedule()` 才能让系统真正运转起来。因此不能把 `kernel_thread()` 的创建动作和新 task 已经获得 CPU 执行混为一谈。

`rest_init()` 最终不返回到 `start_kernel()`；boot task 转入 idle path。PID 1 则独立执行 `kernel_init()`。

## 5. `kernel_init_freeable()`：PID 1 仍在内核态完成剩余启动工作

`kernel_init()` 首先调用 `kernel_init_freeable()`。此时当前 task 已经是 PID 1，但仍执行 kernel code；它尚未 exec 用户程序。

`kernel_init_freeable()` 的关键顺序是：

```text
wait_for_completion(kthreadd_done)
gfp_allowed_mask = __GFP_BITS_MASK
set_mems_allowed(...)
smp_prepare_cpus()
workqueue_init()
init_mm_internals()
do_pre_smp_initcalls()
smp_init()
sched_init_smp()
padata_init()
page_alloc_init_late()
page_ext_init()
do_basic_setup()
console_on_rootfs()
[必要时] prepare_namespace()
integrity_load_keys()
```

B05 只关心这些步骤对“能否进入用户空间”的意义，不在本章展开 scheduler、workqueue、driver model 或文件系统内部机制。

## 6. initcall 的真实层次

Linux 5.10 `do_basic_setup()` 中执行：

```text
cpuset_init_smp()
driver_init()
init_irq_proc()
do_ctors()
usermodehelper_enable()
do_initcalls()
```

`do_initcalls()` 按 `initcall_levels[]` 遍历：

```text
pure -> core -> postcore -> arch -> subsys -> fs -> device -> late
```

每一级通过 `do_initcall_level()` 遍历对应 linker section 中的 initcall entries，并调用 `do_one_initcall()`。

因此“initcall”不是 `rest_init()` 直接调用的一串任意函数；在 Linux 5.10 主线上，它们由 PID 1 的 `kernel_init_freeable()` 经 `do_basic_setup() -> do_initcalls()` 执行。

## 7. rootfs、`/init` 与 `prepare_namespace()` 的条件关系

`ramdisk_execute_command` 的初始值是：

```c
static char *ramdisk_execute_command = "/init";
```

它可以由 `rdinit=` 修改。

在 `kernel_init_freeable()` 中，`console_on_rootfs()` 后检查这个 early userspace init 是否可访问：

```text
if (init_eaccess(ramdisk_execute_command) != 0) {
    ramdisk_execute_command = NULL;
    prepare_namespace();
}
```

所以 Linux 5.10 主线不是无条件 `prepare_namespace()`：

- 若 rootfs 中存在可执行的 `/init`（或 `rdinit=` 指定程序），保留 `ramdisk_execute_command`，让后面的 `kernel_init()` 优先 exec 它；
- 若不存在，则清空该指针并执行 `prepare_namespace()`，走传统 root-device/root-filesystem 准备路径。

这里的 rootfs/initramfs 解包细节和 VFS/root mount 内部机制不属于当前基础章节；B05 只记录决定用户态入口选择所需的边界。

## 8. `kernel_init()` 在 exec 前还会释放启动期资源

`kernel_init_freeable()` 返回后，`kernel_init()` 并不是立即 `exec`。Linux 5.10 还依次进行：

```text
async_synchronize_full()
kprobe_free_init_mem()
ftrace_free_init_mem()
free_initmem()
mark_readonly()
pti_finalize()
system_state = SYSTEM_RUNNING
numa_default_policy()
rcu_end_inkernel_boot()
do_sysctl_args()
```

因此 `SYSTEM_RUNNING` 也不能简单解释为“用户态 PID 1 已 exec”；它在真正尝试用户态 init 之前就已经设置。

## 9. 用户态 init 的选择顺序

`run_init_process(path)` 做两件与本章直接相关的事情：

```text
argv_init[0] = path
kernel_execve(path, argv_init, envp_init)
```

默认 `argv_init` 从 `"init"` 开始，默认环境至少包含：

```text
HOME=/
TERM=linux
```

真正尝试 exec 的顺序是：

```text
1. ramdisk_execute_command        默认 /init，可由 rdinit= 修改；若不存在会在 freeable 阶段被清空
2. execute_command                init= 指定；若指定但 exec 失败则 panic
3. CONFIG_DEFAULT_INIT            非空时尝试
4. /sbin/init
5. /etc/init
6. /bin/init
7. /bin/sh
8. 全部失败 -> panic("No working init found ...")
```

`try_to_run_init_process()` 对 fallback 路径把 `-ENOENT` 与“文件存在但不能执行”的错误日志区分开，但仍把返回值交给 fallback 链决定是否继续。

## 10. `kernel_execve()` 成功意味着什么

`run_init_process()` 返回 `kernel_execve()` 的结果。成功 exec 时，当前 PID 1 的 task identity 不因为 exec 而变成一个新 PID；变化的是它的执行映像和用户态地址空间/入口状态。

从 B05 的课程模型看，最重要的边界是：

```text
kernel_thread(kernel_init) 成功
    => PID 1 task 已存在，仍是内核启动线程

kernel_init_freeable + initcalls/rootfs 准备
    => PID 1 仍在内核态完成启动尾声

kernel_execve(init_path) 成功
    => 同一个 PID 1 跨过 exec 边界，开始执行用户态 init 映像
```

用户程序 `_start` 所看到的初始用户栈、`argc/argv/envp/auxv` 属于 `assembly/` 已完成的 ABI 内容；B05 只负责解释内核为什么、何时把 PID 1 交给该用户态入口。

## 11. 配置与实现边界

本章后续正文/实验必须保留以下边界：

- `CONFIG_SMP` 会影响 CPU bring-up 相关实现；非 SMP 下存在 stub；
- `CONFIG_INIT_ENV_ARG_LIMIT` 决定 init argv/env 数组容量；
- `CONFIG_DEFAULT_INIT` 参与用户态 init fallback 顺序；
- `CONFIG_STRICT_KERNEL_RWX` / `CONFIG_ARCH_HAS_STRICT_KERNEL_RWX` 影响 `mark_readonly()`；
- rootfs 中 `/init` 是否存在是运行时事实，不是单靠 `.config` 能决定；
- initramfs/rootfs、VFS、driver model、scheduler 内部机制只解释 B05 所需交接，不在本章扩展为独立专题。

## 12. B05 后续实验应验证什么

建议按三层证据设计：

### L1：Linux v5.10 source contract

静态核验：

- `rest_init()` 中 PID 1 必须先于 kthreadd 创建；
- `kernel_init_freeable()` 必须等待 `kthreadd_done`；
- `system_state = SYSTEM_SCHEDULING`、completion、第一次 schedule 与 idle handoff 的顺序；
- `do_basic_setup() -> do_initcalls()` 与 initcall level 顺序；
- `/init` 检查与 conditional `prepare_namespace()`；
- `SYSTEM_RUNNING` 位于用户态 exec 尝试之前；
- init fallback 顺序与最终 panic。

### L2：匹配 Linux 5.10 build

使用 `nm/readelf/objdump` 确认 `rest_init`、`kernel_init`、`kernel_init_freeable` 等符号/控制流。initcall section 应结合 linker layout 与实际配置观察，不能只按符号地址猜调用顺序。

### L3：QEMU/GDB 或 boot log

动态观察 PID 0/PID 1/PID 2、`rest_init()`、`kernel_init_freeable()`、initcall 和 `kernel_execve()` 前后的 current/task 状态。可结合 `initcall_debug` 观察 initcall，但日志只能证明实际运行过的配置路径。

当前仓库环境没有在本次核验中执行匹配 Linux 5.10 build 或 QEMU/GDB，因此 L2/L3 保留为后续增强证据，不把源码推导写成运行结果。

## 13. 本轮核验结论

B05 的正确主线不是简单的：

```text
rest_init -> kernel_init -> /sbin/init
```

而应理解为：

```text
boot task / PID 0
  -> rest_init
     -> 先创建 PID 1(kernel_init)
     -> 再创建 kthreadd(PID 2)
     -> completion 解锁 PID 1 的后续初始化
     -> boot task 首次 schedule 后进入 idle

PID 1 / kernel_init
  -> kernel_init_freeable
     -> SMP/workqueue/pre-SMP initcalls
     -> do_basic_setup -> do_initcalls
     -> rootfs / early /init 决策
  -> free init memory / finalize protections
  -> SYSTEM_RUNNING
  -> kernel_execve(selected init)
     -> 成功后同一个 PID 1 进入用户态 init
```

这个模型将“task 创建”“task 获得 CPU”“内核初始化完成”“系统状态设为 running”和“成功 exec 用户态 init”分成不同事件，是 B05 后续正文和实验必须保持的核心边界。

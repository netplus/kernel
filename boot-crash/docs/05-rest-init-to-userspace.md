# B05：从 `rest_init()` 到用户空间

B04 停在 `arch_call_rest_init()`。到这里，内核已经完成了大量架构和通用基础设施初始化，但系统还没有用户态 PID 1。B05 关注最后一段启动交接：boot task 如何创建长期存在的几个基本角色，PID 1 如何在内核态完成剩余初始化，以及它何时真正越过 `exec` 边界进入用户空间。

本章最重要的不是记住一条函数链，而是把下面几个事件分开：

```text
创建 PID 1
≠ PID 1 第一次获得 CPU
≠ initcall 执行完成
≠ system_state 变成 SYSTEM_RUNNING
≠ PID 1 成功 exec 用户态 init
```

这些事件发生在不同时间点，也代表不同的系统能力。

## 1. 为什么启动尾声需要三个长期角色

在 `start_kernel()` 结束前，主要工作一直由最初的 boot task 执行。系统最终不能一直保持这种单线程启动形态，因为正常运行至少需要三类角色：

```text
PID 0 / swapper
    boot CPU 的 idle task；没有普通工作可运行时执行 idle path。

PID 1 / init
    先作为 kernel thread 执行启动尾声；随后 exec 用户态 init。

PID 2 / kthreadd
    为内核线程创建提供长期基础设施。
```

因此 `rest_init()` 不是简单地“启动 init”。它负责把单一 boot execution context 拆成 idle、init 和 kernel-thread infrastructure 三种长期角色，并完成第一次调度交接。

## 2. `arch_call_rest_init()` 到 `rest_init()`

Linux 5.10 的 `init/main.c` 提供默认实现：

```text
arch_call_rest_init()
    -> rest_init()
```

B04 已经解释了 `start_kernel()` 为什么在基础设施建立后调用 `arch_call_rest_init()`。从 B05 开始，关注点从“建立基础设施”转成“建立长期任务并进入正常运行”。

`rest_init()` 运行时当前任务仍是 boot idle task。它首先调用 `rcu_scheduler_starting()`，然后开始创建新 task。

## 3. 为什么必须先创建 PID 1

Linux 5.10 在 `rest_init()` 中明确先执行：

```c
kernel_thread(kernel_init, NULL, CLONE_FS)
```

然后才执行：

```c
kernel_thread(kthreadd, NULL, CLONE_FS | CLONE_FILES)
```

这个顺序不是偶然的。内核希望 init task 获得初始 PID namespace 中的 PID 1。如果先创建 `kthreadd`，PID 1 就会被它占用。

因此正常情况下形成：

```text
PID 0  boot idle / swapper
PID 1  kernel_init task
PID 2  kthreadd
```

这里必须注意：`kernel_thread(kernel_init, ...)` 成功只说明 PID 1 task 已经创建。此时 PID 1 仍然执行内核代码，并没有进入用户空间。

## 4. 先创建 PID 1 又带来了一个依赖问题

PID 1 后续启动过程会需要 kernel-thread infrastructure，但创建 PID 1 时 `kthreadd` 还不存在。Linux 5.10 没有通过交换创建顺序解决，因为那会破坏 PID 1 的身份约束；它使用 completion 建立同步点。

`rest_init()` 创建 `kthreadd` 并取得 `kthreadd_task` 后执行：

```text
system_state = SYSTEM_SCHEDULING
complete(&kthreadd_done)
```

而 `kernel_init_freeable()` 的第一项关键动作是：

```text
wait_for_completion(&kthreadd_done)
```

所以即使 PID 1 很早被调度到 CPU，它也不能越过这个同步点继续启动尾声。这样同时满足两个要求：

1. init 先创建，因此取得 PID 1；
2. init 真正依赖 kernel threads 之前，`kthreadd` 已经准备完成。

Linux 5.10 还暂时把 init task 固定在 boot CPU。源码说明，在 `sched_init_smp()` 之前 task migration 尚未完全准备好；后续才重新建立合适的 CPU allowed mask。

## 5. task 被创建不等于 task 已经运行

`kernel_thread()` 建立可调度 task，但创建动作本身不能证明新 task 已经取得 CPU。

在创建 PID 1 和 `kthreadd` 后，boot task 执行：

```text
system_state = SYSTEM_SCHEDULING
complete(kthreadd_done)
schedule_preempt_disabled()
cpu_startup_entry(CPUHP_ONLINE)
```

源码注释明确指出 boot idle thread 至少必须执行一次 `schedule()` 才能让系统运转起来。

这形成一个重要的执行上下文转换：

```text
原 boot task
    创建 PID 1 / PID 2
    -> 第一次显式 schedule
    -> 进入 boot CPU idle path

PID 1
    被调度后执行 kernel_init()

PID 2
    运行 kthreadd 主循环
```

`rest_init()` 不会像普通函数一样返回到 `start_kernel()` 后继续启动主线；boot task 最终进入 idle execution path。

## 6. PID 1 的第一阶段仍然完全在内核态

PID 1 的入口是 `kernel_init()`，它首先调用：

```text
kernel_init_freeable()
```

这时 `current` 已经是 PID 1，但 CPU 仍在执行内核代码。PID 1 要负责完成许多不适合继续塞在 `start_kernel()` 中的启动尾声。

Linux 5.10 的关键顺序可以简化为：

```text
wait_for_completion(kthreadd_done)
-> 放开正常 GFP allocation mask
-> smp_prepare_cpus()
-> workqueue_init()
-> init_mm_internals()
-> do_pre_smp_initcalls()
-> smp_init()
-> sched_init_smp()
-> page_alloc_init_late()
-> page_ext_init()
-> do_basic_setup()
-> console_on_rootfs()
-> [必要时] prepare_namespace()
```

这里不应把每个函数理解成彼此无关的初始化清单。主线是系统逐渐从 early-boot restrictions 进入正常运行环境：kernel threads 已可依赖、SMP 和 scheduler topology 完善、workqueue 可以实际执行工作、后期 page allocator 状态完成，然后才能大规模执行 initcalls 并准备用户态所需的 root environment。

## 7. initcall 是由 PID 1 执行的启动尾声

Linux 5.10 的 `do_basic_setup()` 调用：

```text
cpuset_init_smp()
driver_init()
init_irq_proc()
do_ctors()
usermodehelper_enable()
do_initcalls()
```

其中 `do_initcalls()` 按 linker 中组织的 initcall level 依次执行：

```text
pure
-> core
-> postcore
-> arch
-> subsys
-> fs
-> device
-> late
```

每一级最终通过 `do_one_initcall()` 调用对应函数。

因此更准确的模型是：

```text
PID 1
  kernel_init_freeable()
    -> do_basic_setup()
       -> do_initcalls()
```

而不是把 initcall 想成 `start_kernel()` 或 `rest_init()` 直接展开的一串函数。

完整 driver model、VFS 和各子系统内部初始化不属于本章。B05 只关心这些 initcalls 必须在用户态 init 之前完成这一启动依赖。

## 8. rootfs 与 `/init`：`prepare_namespace()` 不是无条件执行

Linux 5.10 中：

```text
ramdisk_execute_command = "/init"
```

`rdinit=` 可以修改它。

`kernel_init_freeable()` 在 `console_on_rootfs()` 后检查 early userspace init 是否可访问。其逻辑是：

```text
如果 /init（或 rdinit= 指定程序）可访问
    保留 ramdisk_execute_command
    后续优先 exec 它

否则
    ramdisk_execute_command = NULL
    prepare_namespace()
```

因此不能把 Linux 启动统一画成：

```text
initramfs -> prepare_namespace -> /sbin/init
```

如果 rootfs 中已有可执行 early `/init`，它可以承担后续 root setup 工作，内核不会在这里无条件调用 `prepare_namespace()`。

本章不展开 initramfs 解包、mount namespace 或 VFS 内部机制；这里只保留决定“PID 1 最终 exec 谁”所需的分支。

## 9. `kernel_init_freeable()` 返回后仍然没有进入用户空间

`kernel_init()` 在 freeable 阶段结束后还要完成启动期资源和保护状态的收尾：

```text
async_synchronize_full()
-> kprobe_free_init_mem()
-> ftrace_free_init_mem()
-> free_initmem()
-> mark_readonly()
-> pti_finalize()
-> system_state = SYSTEM_RUNNING
-> numa_default_policy()
-> rcu_end_inkernel_boot()
-> do_sysctl_args()
```

这里另一个常见误区是把：

```text
system_state = SYSTEM_RUNNING
```

理解成“用户态 init 已经启动”。

这不成立。Linux 5.10 在设置 `SYSTEM_RUNNING` 之后才开始尝试 `run_init_process()`。因此 `SYSTEM_RUNNING` 表示内核启动状态机已经进入正常运行阶段，而不是一个用户态 exec 完成事件。

## 10. 用户态 init 的选择顺序

`run_init_process(path)` 会把：

```text
argv_init[0] = path
```

然后调用：

```text
kernel_execve(path, argv_init, envp_init)
```

Linux 5.10 默认的 init argv/env 基础状态包括：

```text
argv_init[0] = "init"
envp_init = { "HOME=/", "TERM=linux", ... }
```

启动参数还可以补充 init arguments/environment。

实际选择顺序是：

```text
1. ramdisk_execute_command
   默认 /init，可由 rdinit= 修改

2. execute_command
   init= 指定；若明确指定却 exec 失败，kernel panic

3. CONFIG_DEFAULT_INIT
   非空时尝试

4. /sbin/init
5. /etc/init
6. /bin/init
7. /bin/sh

全部失败
-> panic("No working init found ...")
```

`try_to_run_init_process()` 还会区分 `-ENOENT` 与“文件存在但不能执行”等错误，以提供更准确的诊断信息。

## 11. `exec` 改变执行映像，不创建新的 PID 1

这是 B05 最重要的用户态交接点。

成功的 `kernel_execve()` 不会再创建一个“用户态 PID 1”。执行 exec 的仍然是之前由 `kernel_thread(kernel_init, ...)` 创建的那个 PID 1 task。exec 改变的是它的程序映像和用户态执行上下文。

可以把 PID 1 的生命周期画成：

```text
rest_init()
  |
  | kernel_thread(kernel_init, ...)
  v
PID 1 task 创建
  |                         仍在内核态
  | 被调度
  v
kernel_init()
  |
  v
kernel_init_freeable()
  |  kthreadd / SMP / workqueue / initcalls / rootfs
  v
free init memory / finalize protection
  |
  | system_state = SYSTEM_RUNNING
  v
run_init_process()
  |
  | kernel_execve() 成功
  v
同一个 PID 1 开始执行用户态 init 映像
```

所以“PID 1 出现”和“用户空间开始”之间存在一段很长的内核态启动过程。

## 12. 与用户态 `_start` 的交接

`kernel_execve()` 成功后，后续 exec machinery 会建立新的用户态地址空间、程序入口和初始用户栈，最终返回用户模式执行 ELF entry。

这里需要严格划分领域：

- B05 负责解释内核为什么选择某个 init、何时执行 exec，以及 PID 1 task identity 如何跨过 exec 边界；
- `argc/argv/envp/auxv`、字符串区、`AT_NULL`、初始 `%rsp` 和用户 `_start` 的解析属于 `assembly/` 中已经完成的用户态 ABI 内容；
- ELF loader、VFS/path lookup 的完整内部机制不在当前 boot-crash 基础章节展开。

因此 B05 的终点不是重新解释用户 `_start`，而是明确内核已经把同一个 PID 1 交给了用户态 ELF entry。

## 13. 几个时间点必须严格区分

### 13.1 PID 1 创建

```text
kernel_thread(kernel_init, ...)
```

含义：init task 存在，并取得 PID 1。

不代表：它已经运行，更不代表用户态 init 已经运行。

### 13.2 PID 1 第一次运行

scheduler 第一次选择该 task 后，它从 `kernel_init()` 开始执行内核代码。

不代表：initcall 已经结束。

### 13.3 `SYSTEM_SCHEDULING`

在 `rest_init()` 创建早期 tasks 后设置，并配合第一次 schedule/idle handoff。

不代表：整个 kernel initialization 已完成。

### 13.4 `SYSTEM_RUNNING`

在 `kernel_init_freeable()` 返回、init memory/protection 等收尾后设置。

不代表：用户态 init 已 exec。

### 13.5 `kernel_execve()` 成功

这是 PID 1 从启动 kernel thread 跨入用户程序映像的真正 exec 边界。

## 14. 配置与运行时条件

阅读 Linux 5.10 时还要保留以下条件：

- `CONFIG_SMP` 影响 CPU bring-up；非 SMP 构建存在对应 stub；
- `CONFIG_INIT_ENV_ARG_LIMIT` 决定 init argv/env 数组容量；
- `CONFIG_DEFAULT_INIT` 参与 fallback 顺序；
- `CONFIG_STRICT_KERNEL_RWX` 与 `CONFIG_ARCH_HAS_STRICT_KERNEL_RWX` 影响 `mark_readonly()` 的具体实现；
- `rdinit=`、`init=` 和 rootfs 中 `/init` 是否真实存在是启动参数/运行时条件，不能只从 `.config` 推断；
- initcall 的实际集合取决于当前构建配置和链接结果。

## 15. 如何验证这一章

后续 B05 实验应把证据分层。

### L1：Linux 5.10 source contract

至少验证：

```text
kernel_init 创建早于 kthreadd
kernel_init_freeable 等待 kthreadd_done
SYSTEM_SCHEDULING -> completion -> first schedule -> idle
PID 1 -> do_basic_setup -> do_initcalls
initcall level 顺序
/init 检查 -> conditional prepare_namespace
SYSTEM_RUNNING 早于用户态 exec 尝试
init fallback 顺序与最终 panic
```

### L2：匹配构建产物

用 `nm`、`readelf`、`objdump` 确认 `rest_init`、`kernel_init`、`kernel_init_freeable` 等实际符号和控制流。不能通过几个符号的地址排序推导运行顺序；initcall 也必须结合 linker sections 和实际配置观察。

### L3：运行现场

在可控 QEMU 环境中可用 GDB、boot log 和 `initcall_debug` 观察：

```text
rest_init 前后的 current
PID 1 / PID 2 的建立
kernel_init_freeable 的 current
initcall 的执行 task
kernel_execve 前的 PID 1
成功 exec 后的用户态 PID 1
```

动态结果只能证明当前构建和当前启动路径，不应反过来覆盖 Linux 5.10 源码中的配置条件。

## 16. 本章工作模型

把整个阶段压缩成一张状态图：

```text
start_kernel
  -> arch_call_rest_init
     -> rest_init                     [boot task / PID 0]
        -> create kernel_init          [PID 1 exists]
        -> pin init temporarily
        -> create kthreadd             [PID 2 exists]
        -> SYSTEM_SCHEDULING
        -> complete(kthreadd_done)
        -> first schedule
        -> cpu_startup_entry           [PID 0 -> idle]

PID 1 scheduled
  -> kernel_init
     -> kernel_init_freeable
        -> wait kthreadd_done
        -> SMP/workqueue/scheduler late setup
        -> pre-SMP initcalls
        -> do_basic_setup
           -> do_initcalls
        -> console/rootfs
        -> [/init unavailable] prepare_namespace
     -> free init resources
     -> finalize protections
     -> SYSTEM_RUNNING
     -> select init path
     -> kernel_execve
        -> success: same PID 1 enters user space
        -> all candidates fail: panic
```

理解这张图后，启动尾声就不再是“`start_kernel()` 最后启动 `/sbin/init`”这样过度简化的一句话，而是一次明确的 task-role 分化、调度启动、内核初始化收尾和 exec 状态转换。

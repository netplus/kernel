# B05 收章复核：从 `rest_init()` 到用户空间

本文对 B05 的正式教程、Linux 5.10 source-path、实验、expected analysis 与自动 source-contract checker 做收章前一致性复核。复核目标不是增加新的启动分支，而是确认本章已经形成一个可独立验收、边界清楚且不会把源码推导冒充运行现场的课程单元。

## 1. 收章结论

B05 当前已经能够回答本章的核心问题：`start_kernel()` 的通用基础设施初始化结束后，boot task 如何建立 PID 1 与 `kthreadd`，PID 1 为什么仍需在内核态完成启动尾声，以及成功 `exec` 用户态 init 为什么是一个晚于 PID 1 创建、initcall 和 `SYSTEM_RUNNING` 的独立事件。

本章稳定主线为：

```text
PID 0 / boot task
  arch_call_rest_init()
    -> rest_init()
       -> kernel_thread(kernel_init, ...)
       -> kernel_thread(kthreadd, ...)
       -> system_state = SYSTEM_SCHEDULING
       -> complete(&kthreadd_done)
       -> schedule_preempt_disabled()
       -> cpu_startup_entry(CPUHP_ONLINE)

PID 1
  kernel_init()
    -> kernel_init_freeable()
       -> wait_for_completion(&kthreadd_done)
       -> SMP/workqueue/late allocator setup
       -> do_basic_setup()
          -> do_initcalls()
       -> console_on_rootfs()
       -> [early /init 不可访问] prepare_namespace()
    -> free init memory / finalize protections
    -> system_state = SYSTEM_RUNNING
    -> run_init_process(...)
       -> kernel_execve(...)
       -> 成功后同一个 PID 1 进入用户态 init 映像
```

该模型在正文、source-path、实验和 expected analysis 中保持一致。

## 2. PID 0、PID 1、PID 2 的生命周期边界一致

各材料均明确区分三类长期角色：

- PID 0 是原 boot task，最终进入 boot CPU idle path；
- PID 1 由 `kernel_thread(kernel_init, NULL, CLONE_FS)` 创建，先在内核态执行启动尾声；
- `kthreadd` 在 PID 1 之后创建，正常初始 PID namespace 中通常取得 PID 2。

本章没有把“`kernel_thread()` 返回”写成“新 task 已经获得 CPU”。这一区分很重要，因为 task 创建、task 第一次被调度以及用户态 exec 是三个不同事件。

同时，正文和实验均保留了 `kthreadd_done` 的准确语义：它建立 PID 1 后续初始化对 kernel-thread infrastructure 的同步边界；源码可以证明 wait/complete 的关系，但不能静态证明某次启动中 PID 1 一定真的在 completion 上睡眠。是否观察到阻塞属于运行时调度事实。

## 3. 第一次调度与 idle handoff 的边界一致

`rest_init()` 中的源码偏序在各材料中统一为：

```text
SYSTEM_SCHEDULING
-> complete(&kthreadd_done)
-> schedule_preempt_disabled()
-> cpu_startup_entry(CPUHP_ONLINE)
```

因此 B05 的表述没有把 `rest_init()` 当作普通函数“返回到 `start_kernel()` 后继续执行”。boot task 在完成第一次显式调度后进入 idle execution path；PID 1 和 `kthreadd` 则成为独立可调度任务。

这里讲的是启动阶段的 ownership 和 handoff。scheduler 如何选择具体 task、运行队列如何组织以及上下文切换细节仍属于 `scheduler/` 与 `assembly/`，B05 没有重复展开。

## 4. initcall ownership 与 level 顺序一致

正文、source-path、实验与 checker 均把 initcall ownership 固定为：

```text
PID 1
  -> kernel_init()
     -> kernel_init_freeable()
        -> do_basic_setup()
           -> do_initcalls()
```

因此本章明确拒绝两种错误模型：initcalls 由 `rest_init()` 直接执行，或由已经进入用户态的 init 执行。

Linux 5.10 的 level 名称顺序统一记录为：

```text
pure -> core -> postcore -> arch -> subsys -> fs -> device -> late
```

本章同时保持源码/链接契约与具体构建结果的区别：level 组织属于源码与 linker contract；某个具体 initcall 是否存在、属于哪一级以及本次是否成功运行，还取决于 `.config`、链接结果和运行现场。

## 5. `/init` 与 `prepare_namespace()` 的条件关系一致

各材料均没有把 `prepare_namespace()` 写成无条件启动步骤。B05 固定的 Linux 5.10 模型是：

```text
ramdisk_execute_command 默认 "/init"

console_on_rootfs()
if (init_eaccess(ramdisk_execute_command) != 0) {
    ramdisk_execute_command = NULL;
    prepare_namespace();
}
```

因此 early `/init` 可访问时，后续优先尝试该路径；不可访问时才进入 `prepare_namespace()`。某个 guest 实际走哪一侧属于 L3 运行时事实。

完整 initramfs 解包、VFS/path lookup 和 root mount 机制不在本章展开，符合基础课程的领域边界。

## 6. `SYSTEM_RUNNING` 与用户态 exec 的边界一致

B05 各材料均明确：

```text
system_state = SYSTEM_RUNNING
-> 后续才开始用户态 init exec attempts
```

所以 `SYSTEM_RUNNING` 只说明内核启动状态机已经进入 running 阶段，不能作为“用户态 PID 1 已经运行”的证据。

用户态交接的真正边界是 PID 1 成功执行 `kernel_execve()` 并进入 exec/return-to-user machinery。成功 exec 不创建新的 PID 1；task identity/PID 保持，变化的是执行映像、地址空间和用户态入口状态。

这也与 `assembly/` 的职责边界保持一致：B05 到“同一个 PID 1 被交给用户态 ELF entry”为止；初始 `%rsp`、`argc/argv/envp/auxv`、字符串区、`AT_NULL` 和 `_start` 解析不在这里重复讲解。

## 7. init fallback 模型一致

正文、source-path、实验与 checker 均使用同一顺序：

```text
ramdisk_execute_command
-> execute_command (init=)
-> CONFIG_DEFAULT_INIT
-> /sbin/init
-> /etc/init
-> /bin/init
-> /bin/sh
-> panic
```

其中明确指定的 `init=` 失败具有不同的错误处理语义；fallback 的 ownership 仍在 `kernel_init()`。`try_to_run_init_process()` 对 `-ENOENT` 与其他 exec 错误的诊断差异没有被误写成改变整个 fallback ownership。

## 8. 自动 checker 与实验状态复核

B05 当前的 `verify_source_contract.py` 固定 8 组 L1 source-contract：

1. PID 1 / `kernel_init` 创建先于 `kthreadd`；
2. `SYSTEM_SCHEDULING -> completion -> schedule -> idle`；
3. PID 1 在 `do_basic_setup()` 前等待 `kthreadd_done`；
4. `do_basic_setup() -> do_initcalls()`；
5. initcall level 顺序；
6. 默认 `/init` 与 conditional `prepare_namespace()`；
7. `SYSTEM_RUNNING` 先于 init exec attempts；
8. init fallback 顺序。

checker 的 fixture self-test 已实际执行：

```text
9 tests
1 complete positive fixture
8 targeted negative fixtures
OK
exit code 0
```

这 9 个测试属于**工具证据**：它们证明 checker 能接受完整 fixture，并拒绝八类有意破坏的契约。它们不能替代真实 Linux v5.10 checkout 上执行 checker 的 L1 证据。

## 9. 证据等级复核

B05 当前保持四级证据边界：

```text
工具证据
  checker fixture self-test

L1
  真实 Linux v5.10 source contract

L2
  与源码/.config/工具链匹配的 vmlinux、nm/readelf/objdump、initcall section

L3
  QEMU/GDB/initcall_debug 的实际 PID、调度、rootfs 和 exec 现场
```

当前已经实际取得的是工具证据。完整 Linux v5.10 checkout 上的 checker CLI、匹配构建的 L2 和可控 guest 的 L3 仍未执行，因此本章没有把这些项目标成 PASS。

这不阻止基础章节收口：当前 source-path 已完成 Linux 5.10 事实核验，L2/L3 被明确定位为后续增强证据，而不是用推测结果填空。

## 10. 配置与运行时条件复核

B05 已保留与本章直接相关的主要条件：

- `CONFIG_SMP` 影响 CPU bring-up 路径；
- `CONFIG_INIT_ENV_ARG_LIMIT` 影响 init argv/env 容量；
- `CONFIG_DEFAULT_INIT` 参与 init fallback；
- strict kernel RWX 相关配置影响 `mark_readonly()`；
- early `/init` 是否可访问是运行时 rootfs 事实，而不是单靠 `.config` 可以确定。

这些条件没有被扩展成 scheduler、VFS、driver model 或文件系统专题。

## 11. 常见误区复核

收章时确认正文和实验没有保留以下错误表述：

```text
创建 PID 1 == 用户态 init 已启动
kernel_thread() 返回 == 新 task 已经运行
kthreadd 可以先创建而不影响 PID 1 身份
initcalls 由 rest_init() 或用户态 init 直接执行
prepare_namespace() 无条件执行
SYSTEM_RUNNING == 用户态 PID 1 已开始执行
exec 会创建一个新的用户态 PID 1
源码预期可以替代实际调度/rootfs/exec 现场
```

这些误区均已在正文或 expected analysis 中明确拒绝。

## 12. 与前后章节的交接

B04 停在 `arch_call_rest_init()`，B05 从 `rest_init()` 接管，因此 B04/B05 的边界清楚。

B05 的终点是成功 init exec 所形成的 kernel-to-userspace handoff。用户态 `_start` 的 ABI 已由 `assembly/` 讲解，不在 B05 重复；因此正常启动主线到这里已经完成从 boot task 到用户态 PID 1 的闭环。

领域大纲中 B05 之后应继续进入 Kexec/Kdump 部分，而不是继续扩展 initramfs、VFS、namespace 或用户态 init 内部实现。

## 13. 最终验收

按照根 `AGENTS.md` 的章节完成标准，B05 当前已经能够回答：

- 机制解决什么问题：把单一 boot execution context 交接为 idle、PID 1、kthreadd，并最终进入用户空间；
- 基本模型是什么：task 创建、第一次调度、启动尾声、`SYSTEM_RUNNING` 和 exec 是不同事件；
- Linux 5.10 入口在哪里：`init/main.c` 的 `rest_init()`、`kernel_init()`、`kernel_init_freeable()` 等；
- 主要过程如何运行：PID 0 handoff 与 PID 1 启动尾声两条主线；
- 执行上下文是什么：PID 0 boot/idle context 与 PID 1 kernel-thread context，直到 exec 越过用户态边界；
- 如何验证：8 组 source contract、fixture self-test、L2 build 与 L3 runtime 观察方案；
- 重要限制和误区是什么：completion 的动态睡眠、conditional rootfs 分支、`SYSTEM_RUNNING` 与 exec、PID identity across exec 等。

因此 B05 **内容层面达到收章标准**。下一最小单元应更新 `boot-crash/README.md`，将 B05 标记为【已完成】，接入正式教程、source-path、实验与本 completion review，并记录当前 8 组 checker / 9-case self-test 与未执行增强证据。完成 README 收口后，再根据领域大纲的最新状态进入下一章。
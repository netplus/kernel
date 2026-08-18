# B05 实验预期分析：从 `rest_init()` 到用户空间

本文是 `README.md` 中 B05 实验的独立验收基线。它回答的不是“某次机器一定会看到哪些 PID 调度时序”，而是：哪些结论由 Linux v5.10 源码直接保证，哪些必须由匹配构建或运行现场证明，以及观察结果应如何解释。

## 1. 验收时首先区分五个事件

B05 最容易出现的错误，是把下面五个事件压缩成“启动 init”一个动作：

```text
E1  PID 1 task 被创建
E2  PID 1 第一次获得 CPU
E3  PID 1 完成 initcall/rootfs 等内核态启动尾声
E4  system_state = SYSTEM_RUNNING
E5  PID 1 成功 exec 用户态 init
```

正确关系是：这些事件含义不同，不能互相作为证据。源码可以确定部分偏序，但实际的第一次调度时刻仍取决于运行时调度。

## 2. PID 0、PID 1、PID 2 的预期模型

进入 `rest_init()` 时，当前执行者仍是 boot task / boot CPU idle task。Linux v5.10 在 `rest_init()` 中先创建 `kernel_init`，再创建 `kthreadd`。

基础验收必须得到：

```text
kernel_thread(kernel_init, NULL, CLONE_FS)
    occurs before
kernel_thread(kthreadd, NULL, CLONE_FS | CLONE_FILES)
```

这个顺序保证 init task 取得初始 PID namespace 中的 PID 1。正常启动中 `kthreadd` 随后取得 PID 2，但“PID 2”应视为正常主线结果，不应把一个运行时 PID 数值替代源码中的创建顺序契约。

还必须明确：`kernel_thread()` 成功返回表示 task/PID 已创建，不表示该 task 已经获得 CPU。

## 3. completion 与第一次调度

`rest_init()` 创建早期 task 后的关键源码偏序是：

```text
system_state = SYSTEM_SCHEDULING
-> complete(&kthreadd_done)
-> schedule_preempt_disabled()
-> cpu_startup_entry(CPUHP_ONLINE)
```

PID 1 的 `kernel_init_freeable()` 则在继续启动工作前执行：

```text
wait_for_completion(&kthreadd_done)
```

因此验收结论应写成：

- PID 1 必须先创建，以保留 PID 1 身份；
- `kthreadd` 随后创建；
- completion 为 PID 1 后续依赖 kernel-thread infrastructure 建立同步边界；
- PID 1 如果在 completion 之前获得 CPU，会在该等待点阻塞；
- 是否真的动态观察到这次阻塞取决于调度时序，不能由源码静态断言“本次启动一定发生了睡眠”。

boot task 执行第一次显式 schedule 后进入 idle path。这里也不能从两个 `kernel_thread()` 的返回值直接推导 PID 1/PID 2 的实际首次运行先后。

## 4. initcall 的 ownership 与 level 顺序

B05 的正确 ownership 是：

```text
PID 1
  kernel_init()
    -> kernel_init_freeable()
       -> do_basic_setup()
          -> do_initcalls()
```

所以基础验收必须拒绝“initcalls 由 `rest_init()` 直接执行”或“initcalls 是用户态 init 执行的”这两种说法。

Linux v5.10 的 initcall level 顺序应核验为：

```text
pure
core
postcore
arch
subsys
fs
device
late
```

这里要区分两层事实：level 的组织和遍历顺序属于源码/链接契约；某个具体 initcall 是否出现在实际构建、是否执行成功以及耗时多少，取决于 `.config`、链接结果和本次运行，需要 L2/L3 证据。

## 5. `/init` 与 `prepare_namespace()` 是条件分支

静态源码应得到以下模型：

```text
ramdisk_execute_command 初始为 "/init"

console_on_rootfs()
if (init_eaccess(ramdisk_execute_command) != 0) {
    ramdisk_execute_command = NULL;
    prepare_namespace();
}
```

因此：

### early `/init` 可访问

预期保留 `ramdisk_execute_command`，后续 `kernel_init()` 优先尝试它。不能要求该条件块中的 `prepare_namespace()` 必然执行。

### early `/init` 不可访问

预期清空 `ramdisk_execute_command`，并执行 `prepare_namespace()`，随后进入传统 root-device/root-filesystem 路径。

“某次启动到底走哪条分支”是运行时事实。仅有 Linux v5.10 源码只能证明分支条件，不能证明某个 guest image 实际选择了哪一侧。

## 6. `SYSTEM_RUNNING` 不是用户态 exec 证据

`kernel_init_freeable()` 返回后，PID 1 仍在内核态。`kernel_init()` 还会释放 init memory、完成只读保护/PTI 等收尾，然后设置：

```text
system_state = SYSTEM_RUNNING
```

之后才开始用户态 init 的 exec 尝试。

因此必须得到偏序：

```text
SYSTEM_RUNNING
-> init exec attempts
```

在刚执行 `system_state = SYSTEM_RUNNING` 的观察点上，正确描述是“内核启动状态机进入 running 状态”；错误描述是“用户态 PID 1 已经运行”。后者只有在成功 exec 并完成返回用户模式交接后才成立。

## 7. init fallback 的预期顺序

Linux v5.10 主线应解释为：

```text
1. ramdisk_execute_command        # 默认 /init，可由 rdinit= 修改
2. execute_command                # init=；明确指定而 exec 失败会 panic
3. CONFIG_DEFAULT_INIT            # 配置为非空时尝试
4. /sbin/init
5. /etc/init
6. /bin/init
7. /bin/sh
8. 全部失败 -> panic
```

`try_to_run_init_process()` 对 `-ENOENT` 与其他 exec 错误的诊断差异，不改变 fallback ownership 仍在 `kernel_init()` 这一事实。

成功的 `kernel_execve()` 也不是“创建一个新的用户态 PID 1”。task identity/PID 保持，变化的是执行映像和用户态执行上下文。

## 8. L1、L2、L3 分别能够证明什么

### L1：Linux v5.10 source contract

L1 可以证明：

- PID 1 创建先于 `kthreadd`；
- `SYSTEM_SCHEDULING -> completion -> first explicit schedule -> idle` 的源码顺序；
- PID 1 在 `kernel_init_freeable()` 等待 `kthreadd_done`；
- `do_basic_setup() -> do_initcalls()` 与 initcall level 顺序；
- `prepare_namespace()` 的条件关系；
- `SYSTEM_RUNNING` 先于用户态 init exec 尝试；
- init fallback 的源码顺序。

L1 不能证明：某次启动中 PID 1 具体在哪个时刻第一次获得 CPU、是否实际在 completion 上睡眠、实际执行了哪些配置相关 initcalls、实际 rootfs 走哪条分支或哪个 init path 最终 exec 成功。

### L2：匹配构建产物

匹配源码、`.config` 和工具链的 `vmlinux` 可以进一步证明：

- 相关符号确实存在于该构建；
- 编译后的 control flow 与当前配置相符；
- 实际 initcall section/linker layout 中包含哪些 entries。

不能仅按符号地址排序推导调用顺序。

### L3：QEMU/GDB/boot log

L3 才能证明某次启动现场，例如：

- P0 的 `current` 确为 PID 0；
- PID 1/PID 2 的实际创建和首次调度时序；
- PID 1 是否实际等待 completion；
- `initcall_debug` 中本次执行的 initcalls/current PID；
- early `/init` 分支的实际选择；
- `SYSTEM_RUNNING` 与成功 exec/return-to-user 的实际时间关系。

`initcall_debug`、GDB 和 QEMU 结果必须与本次 `.config`、Build ID 和启动参数绑定记录。

## 9. 常见错误的拒绝标准

出现以下任一表述且未被修正时，B05 不应收章：

1. “创建 PID 1 就意味着用户态 init 已启动”；
2. “`kernel_thread()` 返回证明新 task 已经运行”；
3. “`kthreadd` 可以先于 init 创建而不影响 PID 1”；
4. “initcalls 由 `rest_init()` 或用户态 init 直接执行”；
5. “Linux 启动总会无条件调用 `prepare_namespace()`”；
6. “`SYSTEM_RUNNING` 表示用户态 PID 1 已开始执行”；
7. “exec 会创建一个新的用户态 PID 1”；
8. 用源码推导的预期 PID/调度/rootfs 分支冒充 L3 实测结果。

## 10. 基础验收矩阵

```text
PID 1 before kthreadd creation                    PASS/FAIL
SYSTEM_SCHEDULING -> completion -> schedule       PASS/FAIL
PID 1 waits for kthreadd_done                     PASS/FAIL
do_basic_setup -> do_initcalls                    PASS/FAIL
initcall level order                              PASS/FAIL
conditional prepare_namespace                     PASS/FAIL
SYSTEM_RUNNING before init exec attempts          PASS/FAIL
init fallback order                               PASS/FAIL
PID/task identity preserved across successful exec PASS/FAIL
L1/L2/L3 evidence kept separate                   PASS/FAIL
```

基础验收要求前述源码事实均能在 Linux v5.10 中定位并解释，且所有未执行的 L2/L3 项明确标注为未执行。增强验收是在匹配构建和可控 guest 中补齐 L2/L3，而不是改变 L1 的结论。

## 11. 当前执行状态

本章当前已经完成 Linux v5.10 source-path、正式教程和实验主体。本文件补齐独立 expected-analysis 验收基线。

当前环境没有匹配 Linux v5.10 build tree、`vmlinux` 和可控 QEMU guest，因此尚未执行 L2 `nm/readelf/objdump` 或 L3 GDB/`initcall_debug`；这些项目继续保留为增强证据，不能以源码预期代替。

下一最小单元是把稳定的 L1 条件转换成自动 source-contract checker，并为 checker 建立正例与针对性负例自测试。
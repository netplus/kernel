# B05 实验：从 `rest_init()` 到用户空间

本实验验证 Linux 5.10 启动尾声最容易混淆的几个状态边界：PID 1 何时被创建、PID 2 何时建立、boot task 何时第一次调度并进入 idle、initcall 由谁执行、`prepare_namespace()` 何时才会发生，以及 `SYSTEM_RUNNING` 与“PID 1 已经成功 exec 用户态 init”为什么不是同一个事件。

实验不展开 scheduler、VFS、initramfs 或 ELF loader 的内部机制；这些机制只作为 B05 状态交接所需的背景。

## 1. 要验证的问题

先建立下面的事件序列：

```text
PID 0 / boot task
  rest_init()
    -> kernel_thread(kernel_init, NULL, CLONE_FS)       # 先创建 PID 1
    -> pin init on boot CPU
    -> kernel_thread(kthreadd, ..., CLONE_FS|CLONE_FILES)
    -> kthreadd_task = ...                              # 正常主线中通常为 PID 2
    -> system_state = SYSTEM_SCHEDULING
    -> complete(&kthreadd_done)
    -> schedule_preempt_disabled()
    -> cpu_startup_entry(CPUHP_ONLINE)                  # PID 0 进入 idle path

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
       -> 成功：同一个 PID 1 换成用户态 init 映像
```

本实验必须能回答：

1. 为什么 `kernel_init` 必须先于 `kthreadd` 创建；
2. 为什么 PID 1 即使先得到 CPU，也不能越过 `kthreadd_done`；
3. 为什么 `kernel_thread()` 返回不能证明新 task 已经运行；
4. initcall 为什么属于 PID 1 的 `kernel_init_freeable()` 主线；
5. 为什么 `prepare_namespace()` 是运行时条件分支，而不是固定启动步骤；
6. 为什么 `SYSTEM_RUNNING` 不能作为用户态 init 已经运行的证据；
7. 成功 exec 后为什么仍是同一个 PID 1。

## 2. 证据等级

本实验严格区分四类证据。不要用后一类的预期去冒充前一类已经执行，也不要用 fixture self-test 冒充 Linux 源码本身已经通过检查。

### 工具证据：checker fixture self-test

仓库提供：

```text
verify_source_contract.py
  B05 的自动 L1 source-contract checker

test_verify_source_contract.py
  checker 的正/负 fixture self-test

selftest-results.md
  已实际执行的 self-test 结果
```

推荐先执行：

```bash
cd boot-crash/labs/05-rest-init-to-userspace
python3 -m unittest -v test_verify_source_contract.py
```

当前已实际执行的结果为：

```text
Ran 9 tests
OK
exit code: 0

1 complete positive fixture
8 targeted negative fixtures
positive fixture covers all 8 contract groups
```

这只能证明 checker 能接受当前完整 fixture，并拒绝八类有意破坏的契约。详细覆盖范围和执行边界见 [`selftest-results.md`](selftest-results.md)。

### L1：Linux v5.10 source contract

在真实 Linux v5.10 checkout 上运行：

```bash
python3 verify_source_contract.py /path/to/linux-v5.10
```

checker 固定八组契约：

1. `kernel_init` / PID 1 创建先于 `kthreadd`；
2. `SYSTEM_SCHEDULING -> complete(&kthreadd_done) -> schedule_preempt_disabled() -> cpu_startup_entry()`；
3. PID 1 在 `do_basic_setup()` 前等待 `kthreadd_done`；
4. `do_basic_setup()` 拥有 `do_initcalls()`；
5. initcall level 为 pure/core/postcore/arch/subsys/fs/device/late；
6. 默认 `/init` 与 conditional `prepare_namespace()`；
7. `SYSTEM_RUNNING` 位于用户态 init exec 尝试之前；
8. early `/init`、`init=`、`CONFIG_DEFAULT_INIT`、`/sbin/init`、`/etc/init`、`/bin/init`、`/bin/sh` 到 panic 的 fallback 顺序。

自动 checker 之后仍应阅读完整源码上下文，至少核验：

```text
init/main.c
include/linux/init.h
init/do_mounts.c
```

源码检查只能证明源码契约，不能证明某次启动实际走过某个条件分支。

### L2：匹配 Linux v5.10 构建产物

准备与源码 checkout、`.config`、编译器匹配的 `vmlinux`，记录：

```bash
nm -n vmlinux | egrep ' (rest_init|kernel_init|kernel_init_freeable|do_basic_setup|do_initcalls|run_init_process|try_to_run_init_process)$'

readelf -Ws vmlinux | egrep 'rest_init|kernel_init|do_basic_setup|do_initcalls|run_init_process'

objdump -drS vmlinux > vmlinux.dis
```

在 `vmlinux.dis` 中分别检查 `rest_init`、`kernel_init`、`kernel_init_freeable` 的实际 control flow。不要根据几个函数的符号地址大小推导调用顺序；编译器布局与调用关系不是同一个概念。

initcall level 还应结合链接结果检查 `__initcall*_start` 边界。不同 `.config` 会改变实际 initcall 集合，因此不要把某个构建的函数列表写成所有 Linux 5.10 构建的固定集合。

### L3：QEMU/GDB 与启动日志

建议使用隔离的 QEMU guest，并保留匹配 `vmlinux`。可加入：

```text
console=ttyS0 initcall_debug
```

`initcall_debug` 可以观察实际运行的 initcall 及其耗时，但它只证明本次配置/启动路径实际执行过的函数。

若使用 GDB，建议观察下面几个阶段。

#### P0：进入 `rest_init()`

记录：

```text
current PID / comm
system_state
```

预期仍是 boot task/PID 0 上下文。

#### P1：两个 `kernel_thread()` 之后、completion 之前

记录返回 PID，并检查：

```text
kernel_init task -> PID 1
kthreadd_task    -> 正常主线中通常 PID 2
system_state     -> 尚未写入 SYSTEM_SCHEDULING 或正处于写入点
```

不要仅凭 PID 已分配就声称 task 已经运行。

#### P2：`kernel_init_freeable()` 开头

记录：

```text
current PID / comm
kthreadd_done completion 状态
system_state
```

观察 `wait_for_completion(&kthreadd_done)`。若 PID 1 在 completion 发出前被调度，它应在这里等待；具体是否真的观察到等待取决于本次调度时序。

#### P3：`do_one_initcall()` / `initcall_debug`

确认实际执行 initcall 的 `current` 是 PID 1。Linux 5.10 的 `initcall_debug` 日志会打印调用函数和当前 PID，因此可把日志与 GDB 观察交叉验证。

#### P4：`SYSTEM_RUNNING` 与 exec 边界

在 `kernel_init()` 中分别观察：

```text
system_state = SYSTEM_RUNNING
run_init_process()
kernel_execve()
```

必须得到下面的偏序：

```text
SYSTEM_RUNNING
    -> 后续才开始尝试用户态 init exec
```

因此在刚写入 `SYSTEM_RUNNING` 的断点上，不能声称用户态 PID 1 已经开始执行。

若 `kernel_execve()` 成功，正常控制流不会以“成功返回到 `kernel_init()` 后继续 fallback”的形式出现；应从 exec/return-to-user machinery 观察同一个 task 的用户态入口交接。

## 3. 推荐执行顺序

为了避免把 checker 自身错误、源码契约、构建结果和运行现场混在一起，推荐按下面顺序执行：

```text
1. python3 -m unittest -v test_verify_source_contract.py
   -> 验证 checker 自身的 acceptance/rejection 行为

2. python3 verify_source_contract.py /path/to/linux-v5.10
   -> 验证真实 Linux v5.10 checkout 的八组 L1 source contract

3. 人工阅读命中函数的完整上下文
   -> 检查正则没有掩盖条件、宏或 ownership 语义

4. nm/readelf/objdump 匹配构建
   -> 建立 L2 证据

5. QEMU/GDB/initcall_debug
   -> 建立本次启动的 L3 证据
```

只有第 1 步通过，不能写成“Linux v5.10 L1 已通过”；只有源码 checker 通过，也不能写成“本次 guest 已走过该分支”。

## 4. L1 手工源码核验步骤

在 Linux v5.10 checkout 中：

```bash
git describe --tags --always

grep -n 'noinline void __ref rest_init' init/main.c
grep -n 'kernel_thread(kernel_init' init/main.c
grep -n 'kernel_thread(kthreadd' init/main.c
grep -n 'kthreadd_done' init/main.c

grep -n 'static void __init do_initcalls' init/main.c
grep -n 'initcall_level_names' init/main.c
grep -n 'static void __init do_basic_setup' init/main.c

grep -n 'init_eaccess(ramdisk_execute_command)' init/main.c
grep -n 'prepare_namespace' init/main.c
grep -n 'system_state = SYSTEM_RUNNING' init/main.c
grep -n 'run_init_process' init/main.c
```

然后阅读完整函数上下文，而不是只保留 grep 命中行。特别检查：

```text
rest_init()
kernel_init_freeable()
kernel_init()
do_basic_setup()
do_initcalls()
do_initcall_level()
run_init_process()
try_to_run_init_process()
```

## 5. initcall level 的静态验证

Linux v5.10 `init/main.c` 中 `initcall_levels[]` 与 `initcall_level_names[]` 必须一一对应。名称顺序应为：

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

`do_initcalls()` 逐 level 调用 `do_initcall_level()`；后者遍历相邻 `initcall_levels[level]` 与 `[level + 1]` 之间的 entries，再调用 `do_one_initcall()`。

这说明“level 顺序”是源码/链接契约；而“某个具体驱动 initcall 是否存在、位于哪一级、是否成功”则还取决于实际构建和运行路径。

## 6. rootfs 分支验证

静态源码必须得到：

```text
ramdisk_execute_command 初始为 "/init"

console_on_rootfs()
if (init_eaccess(ramdisk_execute_command) != 0) {
    ramdisk_execute_command = NULL;
    prepare_namespace();
}
```

动态实验建议做两种 guest image：

### 情形 A：rootfs 中存在可执行 `/init`

预期 `ramdisk_execute_command` 被保留，后续优先尝试它；不能预期该条件块中的 `prepare_namespace()` 必然执行。

### 情形 B：early `/init` 不可访问

预期清空 `ramdisk_execute_command` 并进入 `prepare_namespace()`，之后再走传统 init fallback。

这两个实验涉及 rootfs/image 构造；若当前环境不能可靠构造，不应以源码推导冒充动态结果。

## 7. init fallback 验证

静态核验 `kernel_init()` 的顺序：

```text
ramdisk_execute_command
execute_command                  # init=；失败直接 panic
CONFIG_DEFAULT_INIT              # 非空时尝试
/sbin/init
/etc/init
/bin/init
/bin/sh
全部失败 -> panic
```

注意 `try_to_run_init_process()` 对 `-ENOENT` 与“存在但不可执行”的错误只影响诊断；fallback 的控制流仍由 `kernel_init()` 决定。

## 8. 结果记录模板

```text
Checker self-test:
  command:
  tests run:
  positive fixture:
  negative fixtures:
  exit code:

Kernel source:
  tag/commit:
  git describe:
  .config:

L1 source:
  checker command/result:
  PID 1 before kthreadd: PASS/FAIL
  SYSTEM_SCHEDULING -> completion -> first schedule -> idle: PASS/FAIL
  PID 1 waits for kthreadd_done: PASS/FAIL
  do_basic_setup -> do_initcalls: PASS/FAIL
  initcall level order: PASS/FAIL
  conditional prepare_namespace: PASS/FAIL
  SYSTEM_RUNNING before exec attempts: PASS/FAIL
  init fallback order: PASS/FAIL

L2 build:
  vmlinux Build ID:
  symbols checked:
  disassembly observations:
  initcall section observations:

L3 runtime:
  P0 current/system_state:
  P1 created PIDs:
  P2 completion observation:
  P3 initcall PID/log:
  P4 SYSTEM_RUNNING/exec observation:
  early /init branch:

Unexecuted / environment limitations:
```

## 9. 通过标准

本实验达到基础通过标准时，至少应满足：

1. checker fixture self-test 通过，并明确其只属于工具证据；
2. L1 的八项源码事实均能在 Linux v5.10 中定位并解释其上下文；
3. 能明确说出 PID 1 创建、PID 1 第一次运行、initcall 完成、`SYSTEM_RUNNING` 和成功 exec 是不同事件；
4. 不把 `kernel_thread()` 返回值当作 task 已经获得 CPU 的证据；
5. 不把 `prepare_namespace()` 写成无条件路径；
6. 不把 `SYSTEM_RUNNING` 写成用户态 init 已运行；
7. L2/L3 未执行时明确记录，而不是填写预期值冒充观测结果。

增强通过标准是在匹配 Linux v5.10 build/QEMU 环境中补齐 L2 与 L3，并把实际 `.config`、Build ID、断点和日志保存下来。

## 10. 当前执行状态

当前已经完成：

```text
B05 Linux v5.10 source-path
B05 正式教程
本实验主体
expected-analysis.md
verify_source_contract.py          # 8 组 L1 source contract
test_verify_source_contract.py     # 1 个完整正例 + 8 个负例
selftest-results.md                # 实际 self-test 记录
```

checker fixture self-test 已实际执行：

```text
Ran 9 tests
OK
exit code: 0
```

该结果属于工具证据。当前仍未取得完整 Linux v5.10 source checkout，因此没有把真实 checkout 上的 checker CLI 标记为已执行；当前环境也没有匹配的 `vmlinux` 与可控 QEMU guest，因此 L2 `nm/readelf/objdump` 和 L3 GDB/`initcall_debug` 仍为未执行增强证据。

下一最小单元是同步检查并修正 `expected-analysis.md` 中 checker 建立前的陈旧状态，然后进行 B05 正文、source-path、实验与 expected analysis 的整章一致性复核。
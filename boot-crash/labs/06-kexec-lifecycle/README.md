# B06 实验：Kexec load / execute 生命周期与 normal / crash 资源边界

本实验服务于 B06《Kexec 解决什么问题》。目标不是提前展开 B07 的 segment/page-list 算法或 B08 的 `relocate_kernel` 指令级切换，而是把 B06 的核心模型变成可复核的证据：**Kexec 的映像准备和机器切换是两个独立生命周期，`struct kimage` 是它们之间的 ownership 对象；加载 API 与 normal/crash 用途是两个不同维度。**

源码基线：upstream Linux v5.10，x86-64。

相关正文与源码记录：

- [`../../docs/06-kexec-why-and-lifecycle.md`](../../docs/06-kexec-why-and-lifecycle.md)
- [`../../source-paths/06-kexec-model-linux-5.10.md`](../../source-paths/06-kexec-model-linux-5.10.md)
- [`expected-analysis.md`](expected-analysis.md)
- [`verify_source_contract.py`](verify_source_contract.py)
- [`test_verify_source_contract.py`](test_verify_source_contract.py)
- [`selftest-results.md`](selftest-results.md)

> 本实验包含可能导致系统切换内核的命令。L3 execute/crash 部分只能在可丢弃的虚拟机或专用测试机中执行，不要在生产环境运行。

---

## 1. 要验证的问题

实验按四级证据组织。工具证据用于验证 checker 自身；L1/L2/L3 分别验证真实源码、匹配构建和运行现场，不能互相替代。

### 工具证据：source-contract checker self-test

`verify_source_contract.py` 固定 7 组 B06 L1 契约；`test_verify_source_contract.py` 包含 1 个完整正例和 8 个针对性负例。

执行：

```bash
cd boot-crash/labs/06-kexec-lifecycle
python3 -m unittest -v test_verify_source_contract.py
```

2026-08-19 已实际执行当前 GitHub 版本的 checker/fixture pair，结果为：

```text
Ran 9 tests

OK
```

exit code 为 `0`。完整记录见 [`selftest-results.md`](selftest-results.md)。这一结果只证明 checker 对合成 fixture 的接受/拒绝行为，不代表真实 Linux v5.10 L1 已通过。

### L1：Linux v5.10 source contract

在完整 Linux v5.10 source tree 上确认：

1. traditional `kexec_load` 与 file-based `kexec_file_load` 都能选择 normal 或 crash image；不能把两种 syscall 等同于两种用途；
2. load path 在健康旧内核中构造 `struct kimage`，调用 `machine_kexec_prepare()`，完成 segment loading/termination/post-load 后才用 `xchg()` 安装到 `kexec_image` 或 `kexec_crash_image`；
3. syscall 成功返回时 image 已被全局 Kexec 状态持有，但 execute 尚未发生；
4. crash image 的 destination 受 `crashk_res` 约束；
5. normal/crash 使用不同的 control-page allocation policy，且 normal image 才分配 `image->swap_page`；
6. x86-64 `machine_kexec_prepare()` 在 load phase 建立 transition page-table 状态；
7. x86-64 `machine_kexec()` 位于 execute/transition phase，源码明确把它放在 point of no return 之后，不应再分配内存或设计可恢复失败。

自动检查可在真实 v5.10 checkout 上运行：

```bash
python3 boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py /path/to/linux-v5.10
```

### L2：匹配构建的符号与机器码

在实际 Linux 5.10 构建产物上确认 generic/arch 边界确实进入当前配置编译结果。重点不是根据符号地址排序推断调用顺序，而是检查实际 call/control-flow 与配置裁剪结果。

### L3：运行时生命周期

在隔离 VM 中分别观察：

```text
load image
→ old kernel continues running
→ later explicit execute
→ new kernel boots
```

如果测试 crash image，还要单独证明 crash image 可以在生产内核健康时预加载，而真正消费发生在之后的 fatal/crash event。B06 只观察生命周期，不在这里分析 panic/NMI 的完整 crash path。

---

## 2. L1：准备 Linux v5.10 源码

建议使用干净 checkout：

```bash
git clone --depth 1 --branch v5.10 https://github.com/torvalds/linux.git linux-v5.10
cd linux-v5.10
git describe --tags --always
```

应确认版本指向 `v5.10`。本章主要查看：

```text
kernel/kexec.c
kernel/kexec_core.c
kernel/kexec_file.c
include/linux/kexec.h
arch/x86/kernel/machine_kexec_64.c
arch/x86/kernel/kexec-bzimage64.c
```

配置至少要区分：

```text
CONFIG_KEXEC_CORE
CONFIG_KEXEC
CONFIG_KEXEC_FILE
CONFIG_CRASH_DUMP
```

不要因为某个发行版内核暴露了 `/sbin/kexec` 就反推所有内核配置路径都存在。

---

## 3. L1-A：证明“加载接口”和“映像用途”是二维关系

先定位两个 syscall 与 crash flags：

```bash
grep -n "SYSCALL_DEFINE.*kexec_load" kernel/kexec.c
grep -n "SYSCALL_DEFINE.*kexec_file_load" kernel/kexec_file.c
grep -R -n "KEXEC_ON_CRASH\|KEXEC_FILE_ON_CRASH" \
    kernel include arch/x86 | head -80
```

人工核对时回答：

```text
traditional + normal  是否可表达？
traditional + crash   是否可表达？
file + normal         是否可表达？
file + crash          是否可表达？
```

预期结论是四种组合在接口模型上都成立；具体是否可用还受内核配置、安全策略、签名要求和 userspace 工具能力影响。

这一观察用于排除错误模型：

```text
kexec_load      = normal
kexec_file_load = crash
```

---

## 4. L1-B：沿 traditional load path 观察 ownership handoff

从 `kernel/kexec.c` 沿主线阅读：

```text
SYSCALL_DEFINE4(kexec_load)
  → do_kexec_load()
      → kimage_alloc_init()
      → machine_kexec_prepare()
      → kimage_crash_copy_vmcoreinfo()
      → kimage_load_segment()
      → kimage_terminate()
      → machine_kexec_post_load()
      → xchg(dest_image, image)
```

建议定位：

```bash
grep -n "do_kexec_load\|kimage_alloc_init\|machine_kexec_prepare\|machine_kexec_post_load" kernel/kexec.c
grep -n "xchg.*kexec_image\|xchg.*kexec_crash_image\|xchg.*dest_image" kernel/kexec.c
```

需要记录两个时间点：

```text
Tload-entry：syscall 尚在执行，image 是本次 load operation 正在构造的对象
Tload-success：xchg 安装完成，syscall 可以返回，但 image 生命周期继续存在
```

验收关键不是变量名本身，而是 ownership：成功 load 以后，`struct kimage` 不依赖 syscall 栈帧继续存活。

---

## 5. L1-C：沿 file load path 找到相同的生命周期汇合点

从 `kernel/kexec_file.c` 阅读：

```text
SYSCALL_DEFINE5(kexec_file_load)
  → kimage_file_alloc_init()
      → do_kimage_alloc_init()
      → file-mode image preparation
      → architecture image loader
      → control-code/swap-page preparation
  → machine_kexec_prepare()
  → kimage_load_segment()
  → kimage_terminate()
  → machine_kexec_post_load()
  → xchg(dest_image, image)
```

建议：

```bash
grep -n "kimage_file_alloc_init\|machine_kexec_prepare\|machine_kexec_post_load" kernel/kexec_file.c
grep -n "xchg" kernel/kexec_file.c
```

把它与上一节并排比较。两条路径的输入处理不同，但 B06 关心的后半段语义相同：都形成可由旧内核长期持有的 `struct kimage`，并把 execute 留给未来事件。

---

## 6. L1-D：验证 normal/crash 从 load phase 就使用不同资源假设

### 6.1 crash destination

在 `kernel/kexec_core.c` 中定位 `sanity_check_segment_list()`，确认 crash image 的目标范围要接受 `crashk_res` 约束。

```bash
grep -n "sanity_check_segment_list\|crashk_res" kernel/kexec_core.c kernel/kexec.c
```

这里验证的是 destination constraint，不是 B10 对 `crashkernel=` 参数解析和 reserved-memory 建立过程的完整讲解。

### 6.2 control pages

定位：

```bash
grep -n "kimage_alloc_control_pages" kernel/kexec_core.c kernel/kexec.c kernel/kexec_file.c
```

人工检查 allocator 如何根据 `image->type` / crash state 选择不同策略。记录“normal 与 crash 的 control page policy 不同”，不要把具体 allocator 细节扩展成 B07/B08 的 relocation 算法。

### 6.3 `swap_page`

```bash
grep -R -n "swap_page" kernel/kexec.c kernel/kexec_file.c kernel/kexec_core.c include/linux/kexec.h
```

确认 traditional/file 两条 load path 都只在 non-crash 情况为 image 准备 `swap_page`。

预期结论：crash Kexec 不是到 panic 时才第一次变成特殊路径；它从映像准备阶段就使用不同资源约束。

---

## 7. L1-E：验证 `machine_kexec_prepare()` 与 `machine_kexec()` 属于不同阶段

查看 x86-64：

```bash
grep -n "machine_kexec_prepare\|machine_kexec(" arch/x86/kernel/machine_kexec_64.c
```

对 `machine_kexec_prepare()`，继续定位：

```bash
grep -n "init_pgtable\|init_transition_pgtable" arch/x86/kernel/machine_kexec_64.c
```

需要确认它在 load path 被调用，并提前建立 transition 所需映射。这里仍允许分配失败并回滚本次 load。

再查看 `machine_kexec()` 周围注释和函数体。记录：

```text
进入前：prepare 已完成，旧 kernel 开始进入不可逆 transition
进入后：不应再依赖新的普通内存分配或可恢复错误路径
```

这就是 B06 的 point-of-no-return 边界。

---

## 8. L2：在匹配 Linux 5.10 构建上检查编译结果

如果已有匹配配置的 `vmlinux`：

```bash
nm -n vmlinux | grep -E ' (machine_kexec|machine_kexec_prepare|kimage_alloc_control_pages|sanity_check_segment_list)$'

objdump -drS vmlinux | less
```

建议分别定位 generic load helper 与 `machine_kexec_prepare()`/`machine_kexec()` 的 call sites。

L2 要回答：

- 当前构建是否包含 traditional/file Kexec 对应代码；
- `machine_kexec_prepare()` 是否确实从 load path 进入；
- 当前配置下 crash-specific 分支是否被编译；
- arch transition 函数是否与源码核验的 x86-64 实现匹配。

不要用函数在 ELF 中的地址先后代替控制流分析。编译器可以重排函数布局，inline、LTO 或配置裁剪也会改变可见符号。

---

## 9. L3-A：证明 load 成功后旧 kernel 继续运行

以下步骤只在隔离 VM 中执行。准备与当前 VM 兼容的 kernel/initrd 后：

```bash
uname -a
sudo kexec -l /boot/<kernel> \
    --initrd=/boot/<initrd> \
    --command-line="<known-good-command-line>"
```

load 成功后，**不要立即执行 `kexec -e`**。先记录：

```bash
date
cat /proc/uptime
cat /proc/cmdline
ps -p 1 -o pid,comm,args
```

等待数秒再重复一次 `cat /proc/uptime`。如果旧 kernel 仍在继续运行，说明 load 与 execute 不是同一事件。

然后才执行：

```bash
sudo kexec -e
```

系统将离开旧 kernel。新 kernel 启动后记录：

```bash
uname -a
cat /proc/uptime
cat /proc/cmdline
```

这组证据只证明生命周期分离。`machine_kexec()` 内部 CR3、page list 和 relocation 过程留给 B08。

---

## 10. L3-B：crash image 的预加载观察

只有已经正确配置 `crashkernel=`、并且确认测试 VM 可以丢弃时才做这一节。

先检查：

```bash
cat /proc/cmdline
grep -i crash /proc/iomem
```

使用发行版支持的 kdump/kexec 工具把 crash kernel **预加载**到生产 kernel 中，然后在触发 crash 之前记录工具状态和 `/proc/iomem` 中的 reserved region。

B06 的验收点只有：

```text
crash image preparation 发生在生产 kernel 仍健康时
fatal event               发生在以后
```

不要在本章把“触发 panic 后的 CPU stopping、`crash_kexec()`、elfcorehdr、capture kernel”全部展开；这些分别属于 B10–B13。

如果没有可靠的隔离 VM、串口日志和自动恢复手段，**不要触发 panic**，只记录 crash image preload 已完成以及动态 crash transition 未执行。

---

## 11. 结果记录模板

```text
Kernel source:
  tag/commit:
  architecture:
  relevant CONFIG_KEXEC*:
  CONFIG_CRASH_DUMP:

L1 traditional/file × normal/crash:
  traditional normal:
  traditional crash:
  file normal:
  file crash:

L1 ownership:
  traditional install point:
  file install point:
  normal slot:
  crash slot:

L1 resource differences:
  crashk_res destination check:
  control-page policy:
  normal-only swap_page:

L1 phase boundary:
  machine_kexec_prepare load-phase evidence:
  machine_kexec point-of-no-return evidence:

L2 build:
  vmlinux Build ID/config:
  symbols checked:
  call/control-flow checked:

L3 normal runtime:
  load command:
  old-kernel uptime after load:
  execute command:
  new-kernel evidence:

L3 crash preload/runtime:
  crashkernel reservation:
  preload evidence:
  crash transition executed: yes/no
```

---

## 12. 通过标准

### 工具证据通过

当前已完成：7 组 checker contract，1 个完整正例 + 8 个负例，实际执行 `9 / 9 PASS`、`OK`、exit code `0`。该结果不能替代真实 Linux v5.10 L1。

### L1 通过

能够用 Linux v5.10 源码证明：

- load API 与 image purpose 是二维关系；
- load path 构造并安装 `struct kimage`，syscall return 不等于 execute；
- normal/crash 分别由 `kexec_image` / `kexec_crash_image` 持有；
- crash destination/control-page policy 与 normal 不同；
- `swap_page` 是 normal-only；
- `machine_kexec_prepare()` 属于可失败的 load phase；
- `machine_kexec()` 属于 point-of-no-return transition phase。

### L2 通过

匹配构建的符号与实际 call/control-flow 和 L1 相符，并准确记录配置裁剪造成的差异。

### L3 通过

normal Kexec 至少观察到：load 成功后旧 kernel 继续运行，之后的 execute 才发生内核切换。crash 部分如果执行，则必须能区分 healthy-time preload 与 later fatal-event consumption。

---

## 13. 当前执行状态

自动验收已经完成工具层闭环：

```text
checker implementation:                  complete (7 contract groups)
fixture source:                          complete (1 positive + 8 negative)
fixture/checker self-test:               9 / 9 PASS, OK, exit code 0
real Linux v5.10 L1 checker execution:   not executed
matching-build L2:                       not executed
isolated-VM L3:                          not executed
```

fixture 的实际执行记录见 [`selftest-results.md`](selftest-results.md)。当前环境仍没有完整 upstream v5.10 checkout、匹配 `vmlinux` 和安全的 Kexec/Kdump VM，因此没有填写推测性的 L1/L2/L3 结果。

下一最小单元是 B06 整章一致性复核：对照正文、source-path、实验、expected analysis、checker 与 self-test，检查 load/execute 生命周期、`kimage` ownership、normal/crash 资源边界、point-of-no-return 和证据等级是否一致；发现具体问题则先修正，否则生成 B06 completion review。

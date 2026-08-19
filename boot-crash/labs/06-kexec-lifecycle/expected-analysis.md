# B06 实验预期分析：Kexec 生命周期与 normal/crash 资源边界

本文给出 B06 实验的独立验收基线。源码事实基线是 **upstream Linux v5.10，x86-64**。任何 Linux 具体实现结论都必须回到该版本源码核实；fixture、二手资料和等价写法都不能替代真实 v5.10 源码。

相关材料：[`README.md`](README.md)、[`verify_source_contract.py`](verify_source_contract.py)、[`test_verify_source_contract.py`](test_verify_source_contract.py)、[`selftest-results.md`](selftest-results.md)、[`../../docs/06-kexec-why-and-lifecycle.md`](../../docs/06-kexec-why-and-lifecycle.md)、[`../../source-paths/06-kexec-model-linux-5.10.md`](../../source-paths/06-kexec-model-linux-5.10.md)。

---

## 1. 证据等级

B06 使用四级证据，不能互相冒充。

### 工具证据：checker / fixture

`verify_source_contract.py` 固定 7 组 L1 契约；当前 `test_verify_source_contract.py` 包含 **1 个完整正例和 21 个负例，共 22 cases**。工具证据只回答 checker 是否能够接受满足约束的合成 fixture、拒绝被故意破坏的 fixture，不能证明真实 Linux v5.10 源码满足这些契约。

必须把 PASS 绑定到具体 checker/fixture revision。此前 blob pair：

```text
verify_source_contract.py
  cd38c6c849d8c1d33449b4d01f0039c0de23c1bc

test_verify_source_contract.py
  74dc63d9e4bba24c5278224513b5a640be267478
```

曾实际执行得到 `Ran 9 tests / OK / exit code 0`。但是随后再次核对 upstream v5.10 `kernel/kexec_core.c`，发现真实 `kimage_alloc_control_pages()` 使用 `switch (image->type)` 与 `case KEXEC_TYPE_CRASH`，而旧 checker 错误要求函数体出现 `image->type == KEXEC_TYPE_CRASH`。checker 随后按真实 v5.10 源码修正，fixture 也继续扩展到当前 22-case regression suite，因此旧 9/9 PASS **不能继承给当前 revision**。

当前最新 blob：

```text
verify_source_contract.py
  5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py
  f18918cfbe0b01ffba59be3ac083a9971295a2f8
```

当前准确工具状态：

```text
latest checker source:                     present
latest fixture source:                     present
latest fixture case count:                 22 (1 positive + 21 negative)
latest exact-pair self-test:                not yet executed
latest exact-pair PASS:                     not established
historical superseded exact-pair PASS:      9/9, exit 0
```

fixture-expansion 子任务已经收口；后续不再为了增加 case 数继续扩 synthetic fixture。详细 provenance 与负例覆盖矩阵见 [`selftest-results.md`](selftest-results.md)。

### L1：真实 upstream Linux v5.10 source contract

L1 必须让当前 checker 面对真实 upstream v5.10 源码。人工源码复核已经重新确认 7 组 checker 所依赖的实现事实，但完整自动 L1 PASS 仍未建立。

因此不能把“checker 语义看起来等价”或“人工核过实现事实”写成“7 组真实 v5.10 contract 已自动通过”。

### L2：匹配构建

L2 使用与被测 kernel 匹配的 `.config`、`vmlinux`、`nm/readelf/objdump` 检查配置裁剪、符号和真实 call/control-flow。函数在 ELF 中的地址排列不能代替调用关系。

### L3：隔离 VM runtime

L3 才能证明某次运行中的：

```text
load 成功 → old kernel 继续运行 → 后续独立 execute → new kernel 启动
```

crash image 动态实验还要求可靠 `crashkernel=`、可丢弃 VM、串口日志和恢复手段；条件不足时不得为了补实验结果主动 panic。

---

## 2. load API 与 image purpose 是两个维度

upstream v5.10 必须分别证明 traditional `kexec_load` 和 file-based `kexec_file_load` 都能够表达 normal/crash purpose。traditional path 使用 `KEXEC_ON_CRASH`，file path 使用 `KEXEC_FILE_ON_CRASH`。

错误模型是：

```text
kexec_load      == normal Kexec
kexec_file_load == crash Kexec
```

接口维度和 image purpose 维度不能合并。实际发行版是否允许某种组合，还可能受配置、签名、lockdown、LSM/IMA 和 userspace 工具影响；这不能反推 upstream v5.10 的接口模型。

---

## 3. `struct kimage` 跨越 load syscall 生命周期

traditional/file 的输入阶段不同，但 B06 验收关注相同的 ownership 语义：旧 kernel 在 load phase 构造和准备 `struct kimage`，调用 `machine_kexec_prepare()`，完成相应 load/post-load 工作，再通过 `xchg()` 安装到 persistent global slot。normal/crash 最终分别由 `kexec_image` / `kexec_crash_image` 持有。

因此：

```text
load success != CPU control transfer
```

upstream v5.10 的 `kimage_alloc_init()` 与 `kimage_file_alloc_init()` 都返回 `int`，image 通过 `struct kimage **` out-parameter 返回。不得按其他版本或记忆改写接口形态。

---

## 4. normal/crash 在 load phase 已采用不同资源假设

B06 至少要求证明三项事实：

1. crash image 的 destination 受 `crashk_res` 约束；
2. control-page allocation 对 normal/crash 采用不同 policy；
3. traditional/file 两条 load path 都只为 non-crash image 准备 `image->swap_page`。

其中第二项必须尊重 upstream v5.10 的真实源码形态：`kimage_alloc_control_pages()` 使用 `switch (image->type)`，`case KEXEC_TYPE_CRASH:` 调用 `kimage_alloc_crash_control_pages()`。不能因为 `if (image->type == KEXEC_TYPE_CRASH)` 在语义上等价，就把并不存在的表达式写进自动验收条件。

`sanity_check_segment_list()` 在 upstream v5.10 是全局 `int` 函数，不应强制匹配成 `static`。

---

## 5. prepare 与 execute 之间的 point-of-no-return

x86-64 `machine_kexec_prepare(struct kimage *image)` 属于 load phase，并通过 `init_pgtable()` 等逻辑预先准备 transition state；此阶段仍允许失败并回滚本次 load。

`machine_kexec()` 属于之后的 execute/transition phase。upstream v5.10 中“Do not allocate memory ... point of no return”注释位于 `machine_kexec()` 定义之前，不是函数体内部。

B06 只固定阶段边界；具体 CR3/page-list/`relocate_kernel` 指令级过程留给 B08。

---

## 6. normal execute 与 crash execute 的前置假设不同

normal execute 假设旧 kernel 仍健康，可以按计划收缩 ordinary activity 并进入 architecture transition。crash execute 面对的生产 kernel 已发生 fatal failure，不能继续把普通锁、scheduler、workqueue、设备 shutdown 或普通内存分配当作可靠前提。

B06 只建立下面的生命周期：

```text
healthy production kernel
→ reserve/preload crash image
→ install kexec_crash_image
→ production kernel continues running

fatal event later
→ consume already prepared crash image
```

完整 `crash_kexec()`、CPU stopping、capture kernel 与 vmcore 交给后续章节。

---

## 7. 当前 checker 的七组契约

当前 checker 固定：

1. traditional/file load API 与 normal/crash purpose 分离；
2. `struct kimage` 通过 `xchg()` 安装到 persistent global slot；
3. crash destination 受 `crashk_res` 约束；
4. `kimage_alloc_control_pages()` 通过 v5.10 的 type dispatch 将 crash image 交给 crash-specific control-page allocator；
5. traditional/file 两条路径都只为 normal image 准备 `swap_page`；
6. load path 中 `machine_kexec_prepare()` 位于 image installation 之前；
7. x86 `machine_kexec_prepare()` 预先建立 transition page-table state，且 point-of-no-return 注释与 `machine_kexec()` 定义的位置关系符合 upstream v5.10。

fixture suite 当前为 **1 个完整正例 + 21 个独立负例，共 22 cases**。21 个负例已经覆盖上述 7 组 contract 中 checker 独立作出的各项 assertion；详细矩阵见 `selftest-results.md`。fixture coverage 已收口，但当前 exact 22-case revision 尚未实际执行，因此不能写成 22/22 PASS。

---

## 8. L2/L3 的最小通过条件

L2 至少记录 kernel tag/commit、Kexec/Kdump 相关 `.config`、`vmlinux` Build ID（如存在）、相关符号以及关键 call/control-flow。symbol 因配置或优化不可见时，先结合 `.config` 和反汇编判断。

L3 normal Kexec 至少记录三个时间点：T0 load 前；T1 `kexec -l` 成功后但 execute 前，确认旧 kernel uptime/PID 1/cmdline 仍继续；T2 显式 execute 后，在新 kernel 中重新记录 release、uptime 和 command line。最好让新旧 kernel 有可识别差异。

B06 不要求在这里观察 `relocate_kernel` 的 CR3、GDT/IDT 或 page-list copy；这些属于 B08。

---

## 9. B06 独立通过标准与当前状态

B06 在当前层次必须能够由正文、upstream v5.10 source-path 和实验相互印证：load/execute 为什么分离；`kimage` ownership；API/purpose 二维模型；normal/crash load-time 资源差异；prepare/point-of-no-return 边界；normal/crash execute 的不同前置假设；以及工具证据、L1、L2、L3 的证明范围。

当前状态：

```text
B06 source-path / tutorial / experiment model:          present
7-group L1 checker:                                     present
1 positive + 21 negative fixtures (22 cases):           present
fixture-expansion coverage review:                      closed
latest exact-pair fixture PASS:                         not established
historical superseded fixture PASS:                     9/9, exit 0
manual upstream-v5.10 7-contract source revalidation:   done
full upstream-v5.10 automated L1 checker PASS:          not established
matching-vmlinux L2:                                    not executed
isolated-VM L3:                                         not executed
```

下一独立验收单元：

```text
A. 原样执行当前最新 checker/fixture pair，要求 22 tests / OK / exit 0；
B. 在 upstream Linux v5.10 源码上执行同一 checker，要求 7 组 contract 全部 PASS；
C. 记录 checker blob SHA、fixture blob SHA 和 upstream v5.10 ref；
D. 任一失败都优先按真实 v5.10 源码修正，不能放宽 checker 绕过。
```

A-C 成立后才能进入 B06 completion review。

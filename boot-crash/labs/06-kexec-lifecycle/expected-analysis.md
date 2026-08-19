# B06 实验预期分析：Kexec 生命周期与 normal/crash 资源边界

本文给出 B06 实验的独立验收基线。它回答“观察到什么才足以支持 B06 的结论”，不提前展开 B07 的 segment/page-list 算法、B08 的 `relocate_kernel` 机器切换或 B10 之后的完整 Kdump crash path。

源码事实基线：**upstream Linux v5.10，x86-64**。任何 Linux 具体实现结论都必须回到该版本源码核实。

相关材料：[`README.md`](README.md)、[`verify_source_contract.py`](verify_source_contract.py)、[`test_verify_source_contract.py`](test_verify_source_contract.py)、[`selftest-results.md`](selftest-results.md)、[`../../docs/06-kexec-why-and-lifecycle.md`](../../docs/06-kexec-why-and-lifecycle.md)、[`../../source-paths/06-kexec-model-linux-5.10.md`](../../source-paths/06-kexec-model-linux-5.10.md)。

---

## 1. 证据等级

B06 使用四级证据，不能互相冒充。

### 工具证据：checker / fixture

当前 `verify_source_contract.py` 固定 7 组 L1 契约；`test_verify_source_contract.py` 包含 1 个完整正例和 8 个负例。工具证据只回答 checker 是否能接受满足约束的合成 fixture、拒绝被故意破坏的 fixture，不能证明真实 Linux v5.10 源码满足这些契约。

必须按 revision 记录工具证据。较早 checker/fixture revision 曾实际得到：

```text
Ran 9 tests
OK
exit code 0
```

随后依据 upstream Linux v5.10 源码对 checker 与 positive fixture 做了**实质修正**：

```text
kernel/kexec.c
  kimage_alloc_init() 返回 int，通过 struct kimage **rimage 输出 image

kernel/kexec_file.c
  kimage_file_alloc_init() 同样采用 int + struct kimage **
  kexec_file_load() 先令 dest_image = &kexec_image，
  KEXEC_FILE_ON_CRASH 时再覆盖为 &kexec_crash_image

kernel/kexec_core.c
  sanity_check_segment_list() 在 upstream v5.10 中是全局 int 函数，不是 static

arch/x86/kernel/machine_kexec_64.c
  point-of-no-return / 不再分配内存的注释位于 machine_kexec() 定义之前
```

因此旧的 9/9 PASS **不能继承给当前修正版**。当前准确状态为：

```text
current corrected checker source:               present
current corrected fixture source:               present
historical earlier-revision 9/9 PASS:            observed
current corrected exact-pair self-test:          not executed
current corrected exact-pair PASS:               not established
current corrected exact-pair PASS count:         not established
current corrected exact-pair exit code:          not established
```

详细 provenance 见 [`selftest-results.md`](selftest-results.md)。

### L1：真实 upstream Linux v5.10 source contract

L1 必须在完整 upstream Linux v5.10 tree 上执行当前 checker，或逐项人工核对同一组契约。上述 checker 修正点已经人工回到 v5.10 源码核实，但当前 checker 尚未在完整 tree 上取得自动 PASS。因此不能把“人工核过修正点”写成“7 组 full-tree checker 已通过”。

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

因此下面两条都属于错误模型：

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

特别要避免按其他版本或记忆错误描述 allocator API：upstream v5.10 的 `kimage_alloc_init()` 与 `kimage_file_alloc_init()` 都返回 `int`，image 通过 `struct kimage **` out-parameter 返回。

---

## 4. normal/crash 在 load phase 已采用不同资源假设

B06 至少要求证明三项事实：crash image 的 destination 受 `crashk_res` 约束；control-page allocation 对 normal/crash 采用不同 policy；traditional/file 两条 load path 都只为 non-crash image 准备 `image->swap_page`。

这里的 `swap_page` 是 Kexec relocation/copy 内部资源，不是普通 VM swap。`kernel/kexec_core.c` 中 `sanity_check_segment_list()` 在 upstream v5.10 是全局 `int` 函数，checker 不得错误要求 `static`。

这些事实共同说明 crash Kexec 的特殊资源约束在 healthy-time load phase 就已经存在，而不是 fatal event 到来后才临时产生。

---

## 5. prepare 与 execute 之间的 point-of-no-return

x86-64 `machine_kexec_prepare(struct kimage *image)` 属于 load phase，并通过 `init_pgtable()` 等逻辑预先准备 transition state；此阶段仍允许失败并回滚本次 load。

`machine_kexec()` 属于之后的 execute/transition phase。upstream v5.10 中“Do not allocate memory ... point of no return”注释位于 `machine_kexec()` 定义**之前**，不是函数体内部。验收既要检查这个真实源码布局，也要保持语义边界：不能因为两个函数都叫 `machine_kexec*` 就把 prepare 当成已经开始执行下一内核。

---

## 6. normal execute 与 crash execute 的前置假设不同

normal execute 假设旧 kernel 仍健康，可以按计划收缩 ordinary activity 并进入 architecture transition。crash execute 面对的生产 kernel 已发生 fatal failure，不能继续把普通锁、scheduler、workqueue、设备 shutdown 或普通内存分配当作可靠前提。

B06 只建立这个生命周期：

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
4. crash image 使用 crash-specific control-page policy；
5. traditional/file 两条路径都只为 normal image 准备 `swap_page`；
6. load path 中 `machine_kexec_prepare()` 位于 image installation 之前；
7. x86 `machine_kexec_prepare()` 预先建立 transition page-table state，且 point-of-no-return 注释与 `machine_kexec()` 定义的位置关系符合 upstream v5.10。

fixture suite 仍是 1 个完整正例 + 8 个负例，但当前修正版尚未重新取得 exact-pair PASS。历史 9/9 PASS 只能作为旧 revision 的工具证据。

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
1 positive + 8 negative fixtures:                       present
historical earlier-revision fixture PASS:               9/9, exit 0
current corrected exact-pair fixture PASS:              not established
manual upstream-v5.10 correction-point revalidation:    done
full upstream-v5.10 automated L1 checker PASS:          not established
matching-vmlinux L2:                                    not executed
isolated-VM L3:                                         not executed
```

下一独立验收单元必须按顺序完成：

```text
A. 原样执行当前 exact checker/fixture pair；
B. 要求 9 tests、OK、exit code 0；
C. 在完整 upstream Linux v5.10 tree 上执行同一 checker；
D. 要求全部 7 组 source-contract PASS；
E. 只有 A-D 都成立后，才能恢复当前 revision 的 PASS 状态并进入 B06 completion review。
```

若任一测试失败，失败本身就是下一修正单元。不得通过放宽契约、引用网上结论或沿用旧 revision 的 PASS 绕过失败。

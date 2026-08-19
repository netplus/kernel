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

## 1. 证据等级与当前状态

实验按四级证据组织。工具证据用于验证 checker 自身；L1/L2/L3 分别验证真实源码、匹配构建和运行现场，不能互相替代。

### 工具证据：source-contract checker self-test

`verify_source_contract.py` 固定 7 组 B06 L1 契约；`test_verify_source_contract.py` 包含 1 个完整正例和 8 个针对性负例。

执行：

```bash
cd boot-crash/labs/06-kexec-lifecycle
python3 -m unittest -v test_verify_source_contract.py
```

当前必须区分两代 checker/fixture：

```text
较早 revision：                 9 tests / OK / exit code 0 已观察到
当前 upstream-v5.10 修正版：    尚未重新取得 exact-pair unittest PASS
```

较早结果只能证明当时那一版 fixture framework 可以执行。随后依据 upstream Linux v5.10 源码修正了 checker 与 positive fixture，包括 `kimage_alloc_init()`/`kimage_file_alloc_init()` 的真实 `int + struct kimage **` 形态、`sanity_check_segment_list()` 的可见性、file loader 的 destination-slot 源码顺序，以及 x86 `machine_kexec()` 前 point-of-no-return 注释的位置。因此旧的 9/9 PASS **不能继承给当前修正版**。

完整 provenance 见 [`selftest-results.md`](selftest-results.md)。只有当前 exact checker/fixture pair 重新得到 `Ran 9 tests`、`OK`、exit code `0`，才能把当前工具证据标记为 PASS。

### L1：真实 upstream Linux v5.10 source contract

当前已对上述 checker 修正点做过 upstream v5.10 人工源码复核，但尚未在完整 upstream Linux v5.10 checkout 上执行当前 `verify_source_contract.py`。因此：

```text
manual upstream-v5.10 revalidation of corrected facts: yes
full-tree automated L1 checker PASS:                  not established
```

L1 自动验收必须使用完整 upstream Linux v5.10 source tree；网上资料或其他内核版本不能替代这一事实基线。

### L2：匹配构建的符号与机器码

尚未执行。需要匹配 Linux v5.10 的 `.config` 与 `vmlinux`，再用 `nm/readelf/objdump` 检查实际编译结果和 call/control-flow。

### L3：运行时生命周期

尚未执行。需要隔离 VM；normal Kexec 要观察 load 后旧 kernel 继续运行以及后续独立 execute，crash 路径只有在具备可靠恢复、串口日志和可丢弃环境时才允许触发。

---

## 2. L1 要验证的七组源码事实

在完整 upstream Linux v5.10 source tree 上确认：

1. traditional `kexec_load` 与 file-based `kexec_file_load` 都能选择 normal 或 crash image；不能把两种 syscall 等同于两种用途；
2. load path 在健康旧内核中构造 `struct kimage`，调用 `machine_kexec_prepare()`，完成 segment loading/termination/post-load 后才用 `xchg()` 安装到 `kexec_image` 或 `kexec_crash_image`；
3. crash image 的 destination 受 `crashk_res` 约束；
4. normal/crash 使用不同的 control-page allocation policy；
5. traditional/file 两条路径都只为 non-crash image 准备 `image->swap_page`；
6. `machine_kexec_prepare()` 位于 image installation 之前，仍属于可失败的 load phase；
7. x86-64 `machine_kexec_prepare()` 预先建立 transition page-table state，而 `machine_kexec()` 前的源码注释明确给出 point-of-no-return / 不再分配内存的阶段边界。

自动检查：

```bash
python3 boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py /path/to/linux-v5.10
```

checker PASS 只能说明这七组源码契约与被检查的 tree 匹配；仍不能证明发行版配置或某次运行时机器状态。

---

## 3. 准备 upstream Linux v5.10 源码

建议使用干净 checkout，并确认 tag/commit：

```bash
git clone --depth 1 --branch v5.10 https://github.com/torvalds/linux.git linux-v5.10
cd linux-v5.10
git describe --tags --always
```

本章主要查看：

```text
kernel/kexec.c
kernel/kexec_core.c
kernel/kexec_file.c
include/linux/kexec.h
arch/x86/kernel/machine_kexec_64.c
arch/x86/kernel/kexec-bzimage64.c
```

配置至少区分：

```text
CONFIG_KEXEC_CORE
CONFIG_KEXEC
CONFIG_KEXEC_FILE
CONFIG_CRASH_DUMP
```

不要因为某个发行版暴露了 `/sbin/kexec` 就反推所有源码配置路径都存在。

---

## 4. L1-A：加载 API 与 image purpose 是二维关系

定位两个 syscall 与 crash flags：

```bash
grep -n "SYSCALL_DEFINE.*kexec_load" kernel/kexec.c
grep -n "SYSCALL_DEFINE.*kexec_file_load" kernel/kexec_file.c
grep -R -n "KEXEC_ON_CRASH\|KEXEC_FILE_ON_CRASH" kernel include arch/x86 | head -80
```

人工核对 traditional/file × normal/crash 四种组合。四种组合在接口模型上都可表达；实际可用性还受配置、安全策略、签名要求和 userspace 工具影响。错误模型是把 `kexec_load` 等同 normal、把 `kexec_file_load` 等同 crash。

---

## 5. L1-B：traditional load path 的 ownership handoff

沿 `kernel/kexec.c` 主线阅读：

```text
SYSCALL_DEFINE4(kexec_load)
  → do_kexec_load()
      → kimage_alloc_init(..., struct kimage **rimage)
      → machine_kexec_prepare()
      → kimage_crash_copy_vmcoreinfo()
      → kimage_load_segment()
      → kimage_terminate()
      → machine_kexec_post_load()
      → xchg(dest_image, image)
```

注意：upstream v5.10 的 `kimage_alloc_init()` 返回 `int`，通过 `struct kimage **rimage` 输出 image；不要按其他版本或记忆写成直接返回 `struct kimage *`。

成功 `xchg()` 后，`struct kimage` 不依赖 syscall 栈帧继续存活，因此 `load success != CPU control transfer`。

---

## 6. L1-C：file load path 的同一生命周期语义

upstream v5.10 中 `kimage_file_alloc_init()` 同样返回 `int` 并通过 out-parameter 返回 image。file loader 先把 `dest_image` 初始化为 `&kexec_image`，在 `KEXEC_FILE_ON_CRASH` 时再覆盖为 `&kexec_crash_image`。验收应检查 normal/crash 两个目标都能表达，而不是虚构 traditional/file 两条路径必须具有相同文本顺序。

后半段仍汇合到 `machine_kexec_prepare()`、segment loading/termination/post-load 和 `xchg(dest_image, image)`，所以 B06 关心的是 ownership/lifecycle 汇合。

---

## 7. L1-D：normal/crash 的不同资源假设

在 `kernel/kexec_core.c` 定位 `sanity_check_segment_list()` 和 `crashk_res`。upstream v5.10 中 `sanity_check_segment_list()` 是全局 `int` 函数，不应强制匹配成 `static`。

继续定位 `kimage_alloc_control_pages()`，检查 normal/crash 的 allocation policy；再检查 traditional/file 两条 load path，确认只有 non-crash image 准备 `image->swap_page`。

这三项共同证明 crash Kexec 的特殊资源约束在 healthy-time load phase 已经存在，而不是 panic 到来时才临时产生。

---

## 8. L1-E：prepare 与 execute 的 point-of-no-return 边界

`arch/x86/kernel/machine_kexec_64.c` 中，`machine_kexec_prepare()` 在 load phase 调用 `init_pgtable()` 等逻辑准备 transition mapping；这里仍允许失败并回滚本次 load。

upstream Linux v5.10 中，“Do not allocate memory ... point of no return” 的注释位于 `machine_kexec()` **定义之前**，不是函数体内部。进入 `machine_kexec()` 后不应再设计新的普通内存分配或可恢复失败路径。具体 CR3/page-list/relocation 指令级过程留给 B08。

---

## 9. L2：匹配构建的 ELF / 机器码

如果已有匹配构建：

```bash
nm -n vmlinux | grep -E ' (machine_kexec|machine_kexec_prepare|kimage_alloc_control_pages|sanity_check_segment_list)$'
objdump -drS vmlinux | less
```

记录 `.config` 中 Kexec/Kdump 相关配置，并检查真实 call/control-flow。不要用函数地址在 ELF 中的排列顺序代替调用关系。

---

## 10. L3-A：证明 load 后旧 kernel 继续运行

只在隔离 VM 中执行。`kexec -l` 成功后不要立即 `kexec -e`，先重复观察 `/proc/uptime`、`/proc/cmdline` 和 PID 1，确认旧 kernel 仍继续运行；之后才显式 execute，并在新 kernel 中重新记录 `uname -a`、uptime 和 command line。最好让新旧 kernel release 或 command line 有可识别差异。

---

## 11. L3-B：crash image 预加载观察

只有正确配置 `crashkernel=` 且 VM 可丢弃时才执行。B06 只验证 healthy production kernel 中预加载 crash image 与以后 fatal event 的时间分离。没有可靠隔离、串口日志和恢复手段时不要主动 panic；`crash_kexec()`、CPU stopping、`elfcorehdr` 和 capture kernel 属于后续章节。

---

## 12. 当前验收状态

```text
B06 source-path / tutorial / experiment model:           present
7-group L1 checker:                                      present
1 positive + 8 negative fixtures:                        present
historical earlier-revision fixture PASS:                9/9, exit 0
current corrected exact-pair fixture PASS:               not established
manual upstream-v5.10 correction-point revalidation:     done
full upstream-v5.10 automated L1 checker PASS:           not established
matching-vmlinux L2:                                     not executed
isolated-VM L3:                                          not executed
```

下一独立验收单元不是继续写新理论，而是重新建立当前 checker 的 provenance：原样执行当前 exact checker/fixture pair并要求 9 tests / OK / exit code 0；随后在完整 upstream Linux v5.10 tree 上执行同一 checker并要求全部 7 组 contract PASS。两项均成立后，才能恢复 PASS 状态并进入 B06 completion review。若任一测试失败，失败本身就是下一修正单元；不得通过放宽契约或引用网上结论绕过。
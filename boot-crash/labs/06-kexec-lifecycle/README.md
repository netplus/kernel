# B06 实验：Kexec load / execute 生命周期与 normal / crash 资源边界

本实验服务于 B06《Kexec 解决什么问题》。目标不是提前展开 B07 的 segment/page-list 算法或 B08 的 `relocate_kernel` 指令级切换，而是把 B06 的核心模型变成可复核证据：**Kexec 的映像准备和机器切换是两个独立生命周期，`struct kimage` 是它们之间的 ownership 对象；加载 API 与 normal/crash 用途是两个不同维度。**

源码基线：**upstream Linux v5.10，x86-64**。

相关材料：

- [`../../docs/06-kexec-why-and-lifecycle.md`](../../docs/06-kexec-why-and-lifecycle.md)
- [`../../source-paths/06-kexec-model-linux-5.10.md`](../../source-paths/06-kexec-model-linux-5.10.md)
- [`expected-analysis.md`](expected-analysis.md)
- [`verify_source_contract.py`](verify_source_contract.py)
- [`test_verify_source_contract.py`](test_verify_source_contract.py)
- [`selftest-results.md`](selftest-results.md)

> L3 中真正执行 Kexec/crash 的命令只能在可丢弃虚拟机或专用测试机中运行。

---

## 1. 证据等级与当前状态

实验按四级证据组织：

```text
工具证据  checker / fixture 自身是否可靠
L1        upstream Linux v5.10 源码是否满足契约
L2        匹配构建的 ELF / 符号 / 机器码
L3        隔离 VM 中真实 load / execute / crash 生命周期
```

四级证据不能互相替代。

### 工具证据

执行：

```bash
cd boot-crash/labs/06-kexec-lifecycle
python3 -m unittest -v test_verify_source_contract.py
```

当前 checker 固定 7 组 L1 契约，fixture 已完成负例覆盖收口，包含 **1 个完整正例和 21 个负例，共 22 cases**。21 个负例分别覆盖 checker 对 load-purpose、persistent slot ownership、`crashk_res`、control-page policy、normal-only `swap_page`、prepare-before-install 和 x86 point-of-no-return 的独立断言；不再为了增加 case 数继续扩 synthetic fixture。完整覆盖矩阵见 [`selftest-results.md`](selftest-results.md)。

曾实际执行通过的历史 checker/fixture blob pair 为：

```text
verify_source_contract.py
  cd38c6c849d8c1d33449b4d01f0039c0de23c1bc

test_verify_source_contract.py
  74dc63d9e4bba24c5278224513b5a640be267478
```

历史结果：

```text
Ran 9 tests
OK
exit code 0
```

之后重新核对 upstream v5.10 源码，发现并修正了 checker 对函数签名、file-loader destination-slot 排列、`sanity_check_segment_list()` 可见性、control-page type dispatch 以及 x86 point-of-no-return 注释位置等假设；fixture 也随之扩展。因此旧 9/9 只保留为**历史工具证据**，不能给当前 revision 背书。

当前 exact blob pair：

```text
verify_source_contract.py
  5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py
  f18918cfbe0b01ffba59be3ac083a9971295a2f8
```

当前 22-case exact pair 尚未在能够 materialize committed files 的执行环境中重新执行。详细 provenance 见 [`selftest-results.md`](selftest-results.md)。

### L1：真实 upstream Linux v5.10 source contract

当前 checker 所依赖的源码事实已经针对 upstream `v5.10` tag（commit `2c85ebc57b3e1817b6ce1a6b703928e113a90442`）逐项人工复核；这属于人工 L1 源码证据，不等价于自动 checker PASS。当前 checker 尚未在 materialized upstream v5.10 source tree 上取得 7/7 自动 PASS。

当前状态：

```text
manual upstream-v5.10 source revalidation:             yes
current exact-pair fixture PASS:                       not established
full-tree automated L1 checker PASS:                   not established
```

### L2：匹配构建

尚未执行。需要匹配 Linux v5.10 的 `.config` 与 `vmlinux`，再用 `nm/readelf/objdump` 检查真实编译结果和 call/control-flow。

### L3：运行时生命周期

尚未执行。需要隔离 VM；normal Kexec 要观察 load 后旧 kernel 继续运行以及后续独立 execute。crash 路径只有在具备可靠恢复、串口日志和可丢弃环境时才允许触发。

---

## 2. L1 要验证的七组源码事实

在 upstream Linux v5.10 source tree 上确认：

1. traditional `kexec_load` 与 file-based `kexec_file_load` 都能选择 normal 或 crash purpose；
2. load path 构造并准备 `struct kimage`，最后通过 `xchg()` 安装到 `kexec_image` / `kexec_crash_image`；
3. crash image destination 受 `crashk_res` 约束；
4. `kimage_alloc_control_pages()` 使用 v5.10 的 type dispatch，让 crash image 使用 `kimage_alloc_crash_control_pages()`；
5. traditional/file 两条路径都只为 non-crash image 准备 `image->swap_page`；
6. `machine_kexec_prepare()` 位于 image installation 之前，属于仍可失败的 load phase；
7. x86-64 `machine_kexec_prepare()` 预先建立 transition page-table state，而 `machine_kexec()` 前的源码注释明确 point-of-no-return 边界。

自动检查：

```bash
python3 boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py /path/to/linux-v5.10
```

checker PASS 只说明源码契约与被检查 tree 匹配，不能证明发行版配置或运行时机器状态。

---

## 3. 准备 upstream Linux v5.10 源码

使用干净 checkout，并记录 ref：

```bash
git clone --depth 1 --branch v5.10 https://github.com/torvalds/linux.git linux-v5.10
cd linux-v5.10
git describe --tags --always
git rev-parse HEAD
```

B06 checker 当前读取：

```text
kernel/kexec.c
kernel/kexec_file.c
kernel/kexec_core.c
arch/x86/kernel/machine_kexec_64.c
```

人工上下文阅读还应结合：

```text
include/linux/kexec.h
arch/x86/kernel/kexec-bzimage64.c
```

配置至少区分：

```text
CONFIG_KEXEC_CORE
CONFIG_KEXEC
CONFIG_KEXEC_FILE
CONFIG_CRASH_DUMP
```

---

## 4. L1-A：加载 API 与 image purpose 是二维关系

定位：

```bash
grep -n "SYSCALL_DEFINE.*kexec_load" kernel/kexec.c
grep -n "SYSCALL_DEFINE.*kexec_file_load" kernel/kexec_file.c
grep -R -n "KEXEC_ON_CRASH\|KEXEC_FILE_ON_CRASH" kernel include arch/x86 | head -80
```

错误模型是：

```text
kexec_load      == normal Kexec
kexec_file_load == crash Kexec
```

traditional/file 是输入 API 维度，normal/crash 是 image purpose 维度。

---

## 5. L1-B：traditional load path 的 ownership handoff

沿 `kernel/kexec.c`：

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

upstream v5.10 的 `kimage_alloc_init()` 返回 `int`，image 经 `struct kimage **rimage` 输出。成功安装后，image 由 persistent global slot 持有，因此：

```text
load success != CPU control transfer
```

---

## 6. L1-C：file load path 的生命周期汇合

`kimage_file_alloc_init()` 同样返回 `int` 并通过 out-parameter 返回 image。

v5.10 file path 先把 `dest_image` 初始化为 `&kexec_image`，在 `KEXEC_FILE_ON_CRASH` 时再覆盖为 `&kexec_crash_image`。不要要求 traditional/file 两条路径具有相同文本排列。

后半段同样经过 `machine_kexec_prepare()`、segment loading/termination/post-load 和 `xchg(dest_image, image)`。

---

## 7. L1-D：normal/crash 的不同资源假设

在 `kernel/kexec_core.c` 检查：

- `sanity_check_segment_list()` 中 crash destination 与 `crashk_res`；
- `kimage_alloc_control_pages()` 的 `switch (image->type)`；
- `case KEXEC_TYPE_CRASH:` → `kimage_alloc_crash_control_pages()`。

`sanity_check_segment_list()` 在 upstream v5.10 是全局 `int` 函数，不应错误要求 `static`。

再分别检查 traditional/file alloc path，确认只有 `!kexec_on_panic` 时才准备 `image->swap_page`。

---

## 8. L1-E：prepare 与 execute 的 point-of-no-return

`arch/x86/kernel/machine_kexec_64.c` 中，`machine_kexec_prepare()` 调用 `init_pgtable()` 等逻辑准备 transition mapping；此阶段仍允许失败。

upstream v5.10 的：

```text
Do not allocate memory (or fail in any way) in machine_kexec().
We are past the point of no return ...
```

注释位于 `machine_kexec()` 定义之前，而不是函数体内部。

具体 CR3/page-list/`relocate_kernel` 指令级过程留给 B08。

---

## 9. L2：匹配构建的 ELF / 机器码

如果已有匹配构建：

```bash
nm -n vmlinux | grep -E ' (machine_kexec|machine_kexec_prepare|kimage_alloc_control_pages|sanity_check_segment_list)$'
objdump -drS vmlinux | less
```

记录 `.config` 中 Kexec/Kdump 相关配置，并检查真实 call/control-flow。不要用函数地址排序代替调用关系。

---

## 10. L3-A：证明 load 后旧 kernel 继续运行

只在隔离 VM 中执行。`kexec -l` 成功后不要立即 `kexec -e`，先观察：

```bash
cat /proc/uptime
cat /proc/cmdline
ps -p 1 -o pid,comm,args
```

确认旧 kernel 继续运行；之后才显式 execute，并在新 kernel 中重新记录 release、uptime 和 command line。

---

## 11. L3-B：crash image 预加载观察

只有正确配置 `crashkernel=` 且 VM 可丢弃时才执行。B06 只验证 healthy production kernel 中预加载 crash image 与以后 fatal event 的时间分离。没有可靠隔离、串口日志和恢复手段时不要主动 panic。

完整 `crash_kexec()`、CPU stopping、`elfcorehdr` 与 capture kernel 留给后续章节。

---

## 12. 当前验收状态与下一步

```text
B06 source-path / tutorial / experiment model:          present
7-group L1 checker:                                     present
1 positive + 21 negative fixtures (22 cases):           present
current exact-pair fixture PASS:                        not established
historical superseded fixture PASS:                     9/9, exit 0
manual upstream-v5.10 source revalidation:              done
full upstream-v5.10 automated L1 checker PASS:          not established
matching-vmlinux L2:                                    not executed
isolated-VM L3:                                         not executed
```

下一独立验收单元已经从“继续扩 fixture”切换为实际执行：

```text
A. 原样执行当前 checker/fixture pair，要求 22 tests / OK / exit 0；
B. 在 upstream Linux v5.10 commit
   2c85ebc57b3e1817b6ce1a6b703928e113a90442 的 source tree 上执行同一
   checker，要求 7 组 contract 全部 PASS；
C. 记录 checker blob SHA、fixture blob SHA、upstream commit 和输出；
D. 任一失败都以 upstream v5.10 源码为准修正，不得放宽契约绕过。
```

A-C 成立后再进入 B06 completion review。
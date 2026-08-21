# B06 收章复核：Kexec 的问题模型与生命周期

本文复核 B06《Kexec 解决什么问题》是否达到独立收章标准。源码事实基线固定为 **upstream Linux v5.10，x86-64**。本文件必须与实验目录中的 `selftest-results.md` 保持同一证据状态；历史 fixture PASS 不得继承给后来修改过的 checker/fixture revision。

当前领域入口 `boot-crash/README.md` 已同步为 `B06【待自动验收】`：在当前 exact 22-case suite 与 upstream v5.10 自动 L1 7/7 两个硬门槛均建立可复核执行证据前，不进入 B07。领域 README、本文和 `labs/06-kexec-lifecycle/selftest-results.md` 应始终保持同一证据状态。

复核材料：

- [`06-kexec-why-and-lifecycle.md`](06-kexec-why-and-lifecycle.md)
- [`../source-paths/06-kexec-model-linux-5.10.md`](../source-paths/06-kexec-model-linux-5.10.md)
- [`../labs/06-kexec-lifecycle/README.md`](../labs/06-kexec-lifecycle/README.md)
- [`../labs/06-kexec-lifecycle/expected-analysis.md`](../labs/06-kexec-lifecycle/expected-analysis.md)
- [`../labs/06-kexec-lifecycle/verify_source_contract.py`](../labs/06-kexec-lifecycle/verify_source_contract.py)
- [`../labs/06-kexec-lifecycle/test_verify_source_contract.py`](../labs/06-kexec-lifecycle/test_verify_source_contract.py)
- [`../labs/06-kexec-lifecycle/selftest-results.md`](../labs/06-kexec-lifecycle/selftest-results.md)

## 1. 内容边界

B06 回答的问题是：为什么 Kexec 要把“准备下一映像”和“真正切换机器状态”拆成两个生命周期，以及 normal/crash image 为什么从准备阶段就具有不同资源假设。

```text
B06  生命周期、ownership、normal/crash 前置假设
B07  segment / page-list / file loader 的具体装载机制
B08  machine_kexec() / relocate_kernel 的机器切换
B09  purgatory
B10+ crashkernel、panic/crash execute、capture kernel 与 vmcore
```

正文引用 segment、transition page table、`relocate_kernel` 与 `crashk_res` 时，只把它们作为生命周期边界证据，没有提前完整展开后续章节机制。章节职责仍然清晰。

## 2. load / execute 生命周期

正文、source-path 与实验采用同一个两阶段模型：

```text
healthy old kernel
  → load / validate / allocate / prepare
  → install struct kimage
  → syscall returns; old kernel continues running

later independent event
  → quiesce / crash handoff
  → machine_kexec()
  → architecture transition
  → new kernel
```

`machine_kexec_prepare()` 属于 load phase，仍允许准备资源并返回失败；`machine_kexec()` 位于 architecture transition 的 point-of-no-return 一侧。upstream v5.10 x86-64 源码中“不再分配内存/不要失败”的约束注释位于 `machine_kexec()` 定义之前，而不是函数体内。

## 3. `struct kimage` ownership

成功加载后，prepared image 通过 persistent global slot 跨越 syscall 生命周期：

```text
normal image → kexec_image
crash image  → kexec_crash_image
```

traditional/file 两条路径都通过 `xchg()` 安装新的 image；被替换的旧 image 才进入释放路径。因此 load syscall 返回不等于 execute，也不等于 CPU 已进入新内核。

## 4. load API 与 image purpose 是两个维度

B06 保持以下二维模型：

```text
加载 API：kexec_load / kexec_file_load
image purpose：KEXEC_TYPE_DEFAULT / KEXEC_TYPE_CRASH
```

traditional path 用 `KEXEC_ON_CRASH` 表达 crash purpose，file path 用 `KEXEC_FILE_ON_CRASH` 表达 crash purpose。因此不能把 `kexec_load` 等同 normal Kexec，也不能把 `kexec_file_load` 等同 crash Kexec。实际环境是否允许某种组合还受配置、签名、lockdown、LSM/IMA 和 userspace 工具限制。

## 5. normal / crash 的资源边界

B06 只选取足以证明 crash image 在 healthy-time load phase 已经特殊的三组事实：

1. crash segment destination 受 `crashk_res` 范围约束；
2. control-page allocation 对 crash image 使用 crash-specific policy；
3. traditional/file 两条路径都只为 non-crash image 准备 `image->swap_page`。

`crashkernel=` 的解析和 reserved-memory 生命周期留给 B10；`swap_page` 的 relocation/copy 具体用途留给 B07/B08。

## 6. upstream Linux v5.10 事实基线

当前 checker 的实现事实已重新回到 upstream `v5.10` tag 核验。该 tag 对应 commit：

```text
2c85ebc57b3e1817b6ce1a6b703928e113a90442
```

B06 人工复核使用的四个源码 blob 为：

```text
kernel/kexec.c
  c82c6c06f0518f3591de33431904d60175e69bc2
kernel/kexec_file.c
  e21f6b9234f7a2dbcfe17df61d1611b5d3bbb9d7
kernel/kexec_core.c
  8798a8183974e3b3d52ac53dc4b981f4055f0b52
arch/x86/kernel/machine_kexec_64.c
  a29a44a98e5bef10751af769bd198d783e23b9fd
```

复核确认：

- `kimage_alloc_init()` / `kimage_file_alloc_init()` 返回 `int`，通过 `struct kimage **` 输出 image；
- file loader 先选择 normal slot，再在 crash flag 存在时覆盖为 crash slot，不能强制套用 traditional loader 的文本排列；
- `sanity_check_segment_list()` 在 upstream v5.10 中不是 `static`；
- `kimage_alloc_control_pages()` 使用 `switch (image->type)`，`KEXEC_TYPE_CRASH` case 调用 crash-specific allocator；
- 两条 loader 都在 persistent install 之前调用 `machine_kexec_prepare(image)`；
- x86-64 `machine_kexec_prepare()` 调用 `init_pgtable()`，point-of-no-return 约束位于 `machine_kexec()` 定义之前。

这些属于 **人工 upstream-v5.10 L1 源码复核**，不能冒充自动 checker PASS。

## 7. 当前自动验收状态

B06 checker 固定 7 组 source-contract。synthetic fixture 已扩展并收口为：

```text
1 个完整正例
21 个针对性负例
共 22 cases
```

当前 exact blobs：

```text
verify_source_contract.py
  5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py
  f18918cfbe0b01ffba59be3ac083a9971295a2f8
```

历史上较早 revision 曾实际得到 `Ran 9 tests / OK / exit code 0`，但 checker/fixture 后续因 upstream-v5.10 事实纠偏和负例覆盖扩展而发生变化。因此该历史结果 **不能继承** 给当前 22-case exact pair。

当前证据状态是：

```text
当前 22-case exact-pair self-test：          未执行
当前 22-case PASS：                          未建立
upstream v5.10 人工 L1 事实复核：            已完成
完整 upstream v5.10 自动 L1 7/7：            未建立
匹配 vmlinux L2：                            未执行
隔离 Kexec/Kdump VM L3：                     未执行
```

fixture coverage 已经覆盖 7 组 checker contract 的独立 assertion；不再为了增加 case 数继续扩 synthetic fixture。下一步必须转向真实执行证据。

## 8. 执行环境、self-hosted 验收路径与成本边界

当前可用执行环境在 materialize GitHub / raw GitHub 文件时遇到 DNS 解析失败，因此不能把“connector 能读取源码”误写成“本地 Python 已执行 exact committed files”。这是执行环境 blocker，不是 checker failure，也不是 upstream v5.10 source failure。

2026-08-20 在当前零新增费用执行环境中实际尝试：

```text
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/kernelrepo
```

命令在 clone 内容落盘前失败，实际错误为：

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

因此当前环境仍不能执行当前 exact 22-case suite，也不能 materialize upstream `v5.10` tree 后运行 7/7 L1 checker。该结果只证明当前本地执行环境的 DNS/network blocker；GitHub connector 的仓库读取/写入能力不能替代本地 Python、Git checkout 或 source-tree CLI 的执行证据。

仓库已经提供 `.github/workflows/boot-crash-b06-selftest.yml` 作为零新增 runner 费用优先的验收入口。当前 workflow 的执行契约已经比最初版本严格得多，收章复核以实际 workflow 为准：

```text
触发方式：workflow_dispatch（仅手工触发）
并发：固定 boot-crash-b06-selftest group，cancel-in-progress=false
runner labels：[self-hosted, linux, x64, kernel-course]
GitHub-hosted runner：不使用
timeout：30 分钟
runner platform：实际 uname 必须为 Linux + x86-64（x86_64/amd64）
runner commands：git、python3、uname、grep、tee、mktemp、rm 必须存在
runner prerequisite：Git >= 2.18，Python >= 3.9；前置条件失败必须发生在 checkout/test 证据产生之前
third-party action：actions/checkout 固定到完整 commit
                    11d5960a326750d5838078e36cf38b85af677262
course revision：checkout 显式 ref=${{ github.sha }}，随后要求 HEAD == GITHUB_SHA
course tree：测试前必须 clean
checker blob：5c89b67628cf55560089656d5b65e80ff74c556f
fixture blob：f18918cfbe0b01ffba59be3ac083a9971295a2f8
blob gate：HEAD committed blob == expected blob == worktree blob
fixture gate：unittest exit 0，且日志必须明确 Ran 22 tests + OK
upstream source：checkout 到 workspace 内隔离目录 .b06-upstream-linux-v5.10
upstream commit：2c85ebc57b3e1817b6ce1a6b703928e113a90442
upstream identity：HEAD 必须严格等于上述 commit，且 upstream tree clean
upstream L1：同一 verify_source_contract.py 执行真实源码检查
7/7 gate：恰好 7 条 PASS group，编号 1..7 完整，最终 summary 为 7 groups PASS
credentials / Git global state：不持久化 checkout credentials，不写 safe.directory
cleanup：无论成功失败都删除临时 upstream checkout；最终 course tree 必须 clean
```

这里的 machine gates 定义的是**什么样的未来 run 才能成为 B06 收章证据**，并不意味着当前已经 PASS。一次成功的 workflow run 必须同时留下可复核的 `GITHUB_SHA → course HEAD → checker/fixture exact blobs → 22/22 → exact upstream v5.10 commit → 7/7` 证据链。

当前没有额外 runner 预算。若尚未注册满足 `[self-hosted, linux, x64, kernel-course]` 的 runner，workflow 等待/无法调度属于基础设施 blocker；不得为了取得表面 PASS 静默改用可能产生费用的 GitHub-hosted runner。

## 9. 收章判定

**B06 当前不能维持“已完成/已收章”的判定。** 内容主体、source-path、实验模型、7 组 checker 和 22-case synthetic coverage 已建立，但独立验收仍缺两个硬门槛：

```text
A. 对当前 exact checker/fixture pair 执行：
   python3 -m unittest -v test_verify_source_contract.py
   要求：22 tests / OK / exit code 0

B. 用同一个 verify_source_contract.py 对 upstream Linux v5.10
   commit 2c85ebc57b3e1817b6ce1a6b703928e113a90442 执行：
   要求：7 组 source-contract 全部 PASS
```

只有 A、B 都建立可复核执行证据，并且领域 README 同步到这一证据状态后，才能恢复 B06 的【已完成】状态并进入 B07。任一执行失败时，具体 failure 本身就是下一最小修正单元，必须回到 upstream v5.10 源码判断是 checker、fixture 还是课程结论需要修正，不能通过放宽 matcher 获得表面 PASS。

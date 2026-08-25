# B06 收章复核：Kexec 的问题模型与生命周期

本文复核 B06《Kexec 解决什么问题》是否达到独立收章标准。源码事实基线固定为 **upstream Linux v5.10，x86-64**。本文件必须与实验目录中的 `selftest-results.md` 保持同一证据状态；历史 fixture PASS 不得继承给后来修改过的 checker/fixture revision。

当前领域入口 `boot-crash/README.md` 已同步为 `B06【待自动验收】`：在当前 exact 22-case suite 与 upstream v5.10 自动 L1 7/7 两个硬门槛均建立可复核执行证据前，不进入 B07。

## 当前收章状态

B06 内容主体、source-path、实验模型、7 组 checker 与 22-case synthetic coverage 已建立。当前 exact blobs 为：

```text
verify_source_contract.py
  5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py
  f18918cfbe0b01ffba59be3ac083a9971295a2f8
```

当前仍必须实际取得：

```text
A. exact 22-case fixture：22 tests / OK / exit 0
B. upstream Linux v5.10 commit
   2c85ebc57b3e1817b6ce1a6b703928e113a90442：7/7 source-contract PASS
```

人工 upstream-v5.10 L1 事实复核已经完成，但不能冒充自动 checker PASS。

## 历史真实 workflow 证据与边界

GitHub Actions 历史 run `32230874907`（2026-08-19）已经重新复核。该 run：

```text
workflow:   boot-crash B06 checker self-test
course SHA: 4cb6c9b6c9d870ab037e75fb2c9c9d80a25e4284
runner:     GitHub-hosted Ubuntu 24.04
result:     success
fixture:    Ran 9 tests / OK
```

该 course revision 中：

```text
verify_source_contract.py
  5c89b67628cf55560089656d5b65e80ff74c556f   # 与当前 checker 相同

test_verify_source_contract.py
  5a3b4d41f0a0b9c46575904431136f26cc46ab5d   # 历史 9-case fixture
```

因此这条 run 可以证明：**当前 checker blob 确实曾在真实 GitHub Actions 环境中与历史 9-case fixture 一起执行并得到 PASS**。它不能证明当前 22-case fixture `f18918cf...` 已执行，也没有运行当前 upstream-v5.10 7-group checker，所以不能继承为当前 22/22 或 7/7 收章证据。

该历史 run 使用的是 GitHub-hosted runner。这里只读取既有历史证据；当前课程验收不会因此切回可能产生额外费用的 GitHub-hosted runner。

## pinned checkout Action 的 runtime 证据边界

当前 workflow 固定使用：

```text
actions/checkout@11d5960a326750d5838078e36cf38b85af677262
```

该 revision 对应 checkout v4.4.0；其 `action.yml` 声明 `runs.using: node20`。但是历史 run `32230874907` 的真实 runner 日志同时明确显示：GitHub runner 当时因 Node 20 deprecation policy **强制以 Node 24 执行该 Action**，checkout 仍成功完成。

因此正确的 prerequisite 不是“self-hosted runner 必须提供 Node 20”，而是：

> **选定的 self-hosted GitHub Actions runner 必须能够按照其实际 Actions runtime policy 成功执行这个 pinned checkout Action revision。**

`node20` 是该 Action revision 的 metadata/provenance 事实，不等于未来 runner 一定按 Node 20 启动它。若 self-hosted runner 在启动 pinned Action 时因 runtime policy、runner 版本或 runtime compatibility 失败，应分类为 **runner / Action-runtime prerequisite failure**，不能误记为 fixture failure 或 Linux v5.10 source-contract failure。

## self-hosted workflow 路径状态

当前 `.github/workflows/boot-crash-b06-selftest.yml` 使用固定 revision 的 `actions/checkout` 取得 course repository；upstream Linux v5.10 则在 `$RUNNER_TEMP` 中使用原生 Git materialize。workflow 继续机器验证 Linux/x86-64、Git/Python 版本、course HEAD/worktree、checker/fixture blob、22-case 输出、upstream exact commit/worktree 与 7-group checker 输出。

runner 的部署与路径前提包括：`$RUNNER_TEMP` 必须是 non-root、existing、absolute、non-symlink、CR/LF-free 且等于 `pwd -P` 得到的 canonical physical path；`GITHUB_RUN_ID` / `GITHUB_RUN_ATTEMPT` 必须是正整数。真实 B06 runner 还必须是 dedicated 或等价隔离的可信 runner，其 `RUNNER_TEMP` namespace 在 job 生命周期内不能被不可信本地 principal 修改。

### scratch path 的 identity、ownership、本机权限与部署信任边界

`RUNNER_TEMP + GITHUB_RUN_ID + GITHUB_RUN_ATTEMPT` 只能确定本次 run 期望使用的路径，不能证明预存对象属于本次 run。scratch child 的 `0700` 也不能单独证明任意 hostile multi-user host 安全。

prepare 阶段当前遵循：

```text
计算本次唯一 expected scratch path
→ 若路径已存在（包括 dangling symlink），立即失败且不删除
→ umask 077
→ mkdir 创建本次 run 的 exact scratch directory
→ 安装同一 prepare shell 的局部 EXIT trap
→ 验证对象为 non-symlink directory
→ 用 Python os.stat(..., follow_symlinks=False) + stat.S_IMODE() 验证 mode == 0700
→ 通过 GITHUB_ENV 发布 B06_UPSTREAM_DIR
→ 标记 published 并解除局部 EXIT trap
```

这里区分两类对象：

- **pre-existing / unowned object**：在本次 `mkdir` 之前已经存在，本次 run 从未取得 ownership，因此 prepare fail-closed，绝不自动删除；
- **run-created but not-yet-published object**：本次 `mkdir` 已成功，但 type/mode validation 或 publish 之前失败；同一 shell 的局部 `EXIT` trap 可回收这个刚创建的 exact object。

局部 trap 的删除授权来自本次 shell 的直接创建事实，不来自可预测路径名。publish 成功后，跨-step 生命周期由最终 `always()` cleanup 接管。

最终 cleanup 会独立重新验证 `$RUNNER_TEMP` 与 run identity，重建 expected path。若 `B06_UPSTREAM_DIR` 未 publish，后续 step 不得仅凭路径可重建性推断 ownership；若已 publish，则必须与 independently reconstructed path 字节级相等后才允许删除。

当前删除边界可概括为：**可信且隔离的 runner temp namespace + 明确的对象 ownership 来源 + private mode contract + exact-path identity**。

这些 machine gates 只定义“什么样的 run 才是有效证据”，并不等于当前已经实际运行成功。

本地 `run_acceptance.sh` 仍是独立的零新增费用验收路径；它要求调用者先提供已经 materialize 的 exact upstream v5.10 Git worktree。

## Linux v5.10 事实边界

B06 的实现结论继续以 upstream commit `2c85ebc57b3e1817b6ce1a6b703928e113a90442` 为最终事实基线。人工复核确认的主事实包括：

- traditional/file 两条 loader 都区分 normal/crash purpose，并把成功准备的 image 安装到 persistent slot；
- `sanity_check_segment_list()` 对 crash image 检查 `crashk_res` 边界；
- `kimage_alloc_control_pages()` 按 `image->type` 分派 crash-specific control-page allocation；
- traditional/file 两条路径都只为 non-crash image 准备 `image->swap_page`；
- 两条 loader 都在 persistent install 前执行 `machine_kexec_prepare(image)`；
- x86-64 `machine_kexec_prepare()` 调用 `init_pgtable()`；`machine_kexec()` 前存在 point-of-no-return 约束。

这些事实没有因 workflow 执行路径或 Action runtime policy 的变化而改变。

## 收章判定

**B06 当前仍为【待自动验收】，不能进入 B07。** 下一最小单元优先级如下：

1. 在满足 trusted/isolated runner deployment assumption 且匹配 `[self-hosted, linux, x64, kernel-course]` 的零新增费用 runner 上实际运行当前 workflow，取得 22/22 与 upstream 7/7 的完整日志；
2. 若零新增费用本地环境先具备 exact upstream v5.10 worktree，则直接执行 `boot-crash/labs/06-kexec-lifecycle/run_acceptance.sh`；
3. 任一路径出现具体 checkout/runtime、fixture 或 source-contract failure，立即把该真实 failure 作为下一修正单元；
4. 只有 22/22 与 7/7 都建立可复核执行证据后，才恢复 B06【已完成】并进入 B07。

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

历史较早 revision 的 `9 tests / OK` 不能继承。当前仍必须实际取得：

```text
A. exact 22-case fixture：22 tests / OK / exit 0
B. upstream Linux v5.10 commit
   2c85ebc57b3e1817b6ce1a6b703928e113a90442：7/7 source-contract PASS
```

人工 upstream-v5.10 L1 事实复核已经完成，但不能冒充自动 checker PASS。

## self-hosted workflow 路径状态（2026-08-25）

当前 `.github/workflows/boot-crash-b06-selftest.yml` 使用固定 revision 的 `actions/checkout` 取得 course repository；upstream Linux v5.10 则在 `$RUNNER_TEMP` 中使用原生 Git materialize。workflow 继续机器验证 Linux/x86-64、Git/Python 版本、course HEAD/worktree、checker/fixture blob、22-case 输出、upstream exact commit/worktree 与 7-group checker 输出。

runner 的部署与路径前提包括：`$RUNNER_TEMP` 必须是 non-root、existing、absolute、non-symlink、CR/LF-free 且等于 `pwd -P` 得到的 canonical physical path；`GITHUB_RUN_ID` / `GITHUB_RUN_ATTEMPT` 必须是正整数。checkout Action 固定为 `actions/checkout@11d5960a326750d5838078e36cf38b85af677262`，其 Node 20 runtime compatibility 仍只能由真实 self-hosted workflow run 证明。

### scratch path 的 identity、ownership、本机权限与部署信任边界必须分开

`RUNNER_TEMP + GITHUB_RUN_ID + GITHUB_RUN_ATTEMPT` 只能确定本次 run 期望使用的路径，不能证明预存对象属于本次 run。scratch child 的 `0700` 也不能单独证明任意 hostile multi-user host 安全；真实 B06 验收要求 dedicated 或等价隔离的可信 runner，并要求 job 生命周期内不可信本地 principal 不能修改其 `RUNNER_TEMP` namespace。

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

这里必须区分两类对象：

- **pre-existing / unowned object**：在本次 `mkdir` 之前已经存在，本次 run 从未取得 ownership，因此 prepare fail-closed，绝不自动删除；
- **run-created but not-yet-published object**：本次 `mkdir` 已成功，ownership 已由同一 prepare shell 建立，但 type/mode validation 或 `GITHUB_ENV` publish 之前失败。此时局部 `EXIT` trap 可以安全回收该 shell 刚创建的 exact object，避免 persistent runner 留下 stale scratch blocker。

局部 trap 的删除授权来自“本次 shell 已成功创建该对象”，不是来自可预测路径名。它安装在 pre-existing-object gate 和成功 `mkdir` 之后，因此不会重新引入“能够重建路径即可删除”的旧语义。publish 成功后立即解除局部 trap，跨-step 生命周期随后由最终 `always()` cleanup 接管。

最终 `always()` cleanup 仍采用独立授权规则：重新验证 `$RUNNER_TEMP` 和 run identity，重建 expected path；若 `B06_UPSTREAM_DIR` 未发布，则它本身不取得跨-step 删除授权；若已发布，则要求其与 expected path 字节级相等后才允许 `rm -rf`。因此未发布对象的安全回收只发生在**仍持有直接创建事实的同一个 prepare shell**中，而不是由后续 cleanup 根据路径推断 ownership。

当前删除边界可概括为：**可信且隔离的 runner temp namespace + 明确的对象 ownership 来源 + private mode contract + exact-path identity**。prepare-local trap 与 final cleanup 是两个不同生命周期的删除授权点，不能混为一谈。

这些 machine gates 只定义“什么样的 run 才是有效证据”，并不等于已经实际运行成功。当前尚未取得匹配 `kernel-course` self-hosted runner 上的 22/22 + 7/7 执行记录，因此 B06 状态不变。

本地 `run_acceptance.sh` 仍是独立的零新增费用验收路径；它要求调用者先提供已经 materialize 的 exact upstream v5.10 Git worktree。

## 事实边界

B06 的 Linux v5.10 结论仍以 upstream commit `2c85ebc57b3e1817b6ce1a6b703928e113a90442` 为最终事实基线。人工复核确认的主事实包括：

- traditional/file 两条 loader 都区分 normal/crash purpose，并把成功准备的 image 安装到 persistent slot；
- `sanity_check_segment_list()` 对 crash image 检查 `crashk_res` 边界；
- `kimage_alloc_control_pages()` 按 `image->type` 分派 crash-specific control-page allocation；
- traditional/file 两条路径都只为 non-crash image 准备 `image->swap_page`；
- 两条 loader 都在 persistent install 前执行 `machine_kexec_prepare(image)`；
- x86-64 `machine_kexec_prepare()` 调用 `init_pgtable()`；`machine_kexec()` 前存在 point-of-no-return 约束。

这些事实没有因 workflow 执行路径的修正而改变。

## 收章判定

**B06 当前仍为【待自动验收】，不能进入 B07。** 下一最小单元优先级如下：

1. 在满足 trusted/isolated runner deployment assumption 且匹配 `[self-hosted, linux, x64, kernel-course]` 的零新增费用 runner 上实际运行当前 workflow，取得 22/22 与 upstream 7/7 的完整日志；
2. 若零新增费用本地环境先具备 exact upstream v5.10 worktree，则直接执行 `boot-crash/labs/06-kexec-lifecycle/run_acceptance.sh`；
3. 任一路径出现具体 fixture/source-contract failure，立即回到 upstream v5.10 源码判断 checker、fixture 或课程结论哪一项需要修正；
4. 只有 22/22 与 7/7 都建立可复核执行证据后，才恢复 B06【已完成】并进入 B07。

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

## self-hosted workflow 路径状态（2026-08-22）

此前发现的 `$RUNNER_TEMP` + `actions/checkout path` blocker 已经修正。当前 `.github/workflows/boot-crash-b06-selftest.yml` 不再尝试让 `actions/checkout` 在 `$GITHUB_WORKSPACE` 外建立 upstream checkout：course repository 仍由固定 revision 的 `actions/checkout` 取得；upstream Linux v5.10 则在 `$RUNNER_TEMP` 中使用原生 Git materialize：

```text
git init "$B06_UPSTREAM_DIR"
git -C "$B06_UPSTREAM_DIR" remote add origin https://github.com/torvalds/linux.git
git -C "$B06_UPSTREAM_DIR" fetch --depth=1 origin \
  2c85ebc57b3e1817b6ce1a6b703928e113a90442
git -C "$B06_UPSTREAM_DIR" checkout --detach FETCH_HEAD
```

因此，上一 revision 中“当前 workflow 不能作为已经可执行的 B06 验收入口”的判断已经失效，不能继续作为 blocker。当前 workflow 的设计路径已经恢复为可执行状态，并继续机器验证：

- runner 实际为 Linux/x86-64，Git >= 2.18、Python >= 3.9，且所需外部命令存在；
- course `HEAD == GITHUB_SHA`，course worktree clean；
- checker/fixture 的 committed blob 与 worktree blob 均严格匹配当前 exact baseline；
- fixture 必须报告 `Ran 22 tests` 与 `OK`；
- upstream `HEAD` 必须精确等于 Linux v5.10 commit `2c85ebc57b3e1817b6ce1a6b703928e113a90442`，执行前后 worktree 均 clean；
- checker 必须恰好得到 `PASS 1..7` 和最终 7-group summary；
- `$RUNNER_TEMP` 中的 upstream tree 在 `always()` cleanup 中删除；cleanup 不依赖 prepare step 已成功发布 `B06_UPSTREAM_DIR`：若环境变量尚不存在，会由 `$RUNNER_TEMP`、`GITHUB_RUN_ID` 和 `GITHUB_RUN_ATTEMPT` 重建本次 run 的确定路径后删除，因此 prepare 阶段提前失败也不能把本次临时 upstream tree 留在持久 runner 上；cleanup 同时以 `-e` 与 `-L` 判断目标，删除后同时断言目标既不存在也不是 symbolic link，因此 dangling symlink 也不能绕过清理并跨 run 残留；
- course checkout 在执行后再次验证 HEAD 与 clean 状态。

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

1. 在匹配 `[self-hosted, linux, x64, kernel-course]` 的零新增费用 runner 上实际运行当前 workflow，取得 22/22 与 upstream 7/7 的完整日志；
2. 若零新增费用本地环境先具备 exact upstream v5.10 worktree，则直接执行 `boot-crash/labs/06-kexec-lifecycle/run_acceptance.sh`；
3. 任一路径出现具体 fixture/source-contract failure，立即回到 upstream v5.10 源码判断 checker、fixture 或课程结论哪一项需要修正；
4. 只有 22/22 与 7/7 都建立可复核执行证据后，才恢复 B06【已完成】并进入 B07。

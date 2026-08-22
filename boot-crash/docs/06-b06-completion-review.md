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

## self-hosted workflow 路径 blocker（2026-08-22）

对 `.github/workflows/boot-crash-b06-selftest.yml` 再次做执行语义复核后，发现当前 revision 存在一个会阻止真实执行的具体问题：workflow 把 upstream checkout 目标设置为 `$RUNNER_TEMP/...` 的绝对路径，然后把该值传给 `actions/checkout` 的 `path` 输入。

`actions/checkout` 的 `path` 是相对于 `$GITHUB_WORKSPACE` 的 repository path；不能把 `$RUNNER_TEMP` 的绝对目录作为一种“workspace 外 checkout”机制。因此当前 workflow 虽然意图把大型 upstream tree 与 course worktree 做物理隔离，但该实现不能作为已经可执行的 B06 验收入口。

本轮尝试直接修正 workflow：保留 course repository 使用固定 revision 的 `actions/checkout`，upstream Linux 则改为在 `$RUNNER_TEMP` 中使用原生 Git：

```text
git init "$B06_UPSTREAM_DIR"
git -C "$B06_UPSTREAM_DIR" remote add origin https://github.com/torvalds/linux.git
git -C "$B06_UPSTREAM_DIR" fetch --depth=1 origin \
  2c85ebc57b3e1817b6ce1a6b703928e113a90442
git -C "$B06_UPSTREAM_DIR" checkout --detach FETCH_HEAD
```

这样可以同时满足两个要求：upstream tree 真正位于 `$GITHUB_WORKSPACE` 外；精确 commit、clean-tree、7/7 checker 与 `always()` cleanup 仍可继续验证。

但当前 GitHub 写入接口阻止了对 `.github/workflows/boot-crash-b06-selftest.yml` 的修改，因此本轮无法把上述修正写入 workflow。本文件记录该 blocker，防止后续把当前 workflow 误认为有效的自动验收入口。**在 workflow 修正落地并实际运行前，不得用它建立 B06 PASS。**

这不是 Linux v5.10 源码事实 blocker，也不是 checker failure；它是 self-hosted Actions 执行入口的路径语义 blocker。当前本地 `run_acceptance.sh` 仍是独立的零新增费用验收路径，但需要一个已经 materialize 的 exact upstream v5.10 Git worktree。

## 事实边界

B06 的 Linux v5.10 结论仍以 upstream commit `2c85ebc57b3e1817b6ce1a6b703928e113a90442` 为最终事实基线。人工复核确认的主事实包括：

- traditional/file 两条 loader 都区分 normal/crash purpose，并把成功准备的 image 安装到 persistent slot；
- `sanity_check_segment_list()` 对 crash image 检查 `crashk_res` 边界；
- `kimage_alloc_control_pages()` 按 `image->type` 分派 crash-specific control-page allocation；
- traditional/file 两条路径都只为 non-crash image 准备 `image->swap_page`；
- 两条 loader 都在 persistent install 前执行 `machine_kexec_prepare(image)`；
- x86-64 `machine_kexec_prepare()` 调用 `init_pgtable()`；`machine_kexec()` 前存在 point-of-no-return 约束。

这些事实没有因 workflow blocker 改变。

## 收章判定

**B06 当前仍为【待自动验收】，不能进入 B07。** 下一最小单元优先级如下：

1. 若允许修改 workflow，修正 `$RUNNER_TEMP` + `actions/checkout path` 的不合法组合，并实际运行 self-hosted 验收；
2. 若零新增费用本地环境先具备 exact upstream v5.10 worktree，则直接执行 `boot-crash/labs/06-kexec-lifecycle/run_acceptance.sh`；
3. 任一路径出现具体 fixture/source-contract failure，立即回到 upstream v5.10 源码判断 checker、fixture 或课程结论哪一项需要修正；
4. 只有 22/22 与 7/7 都建立可复核执行证据后，才恢复 B06【已完成】并进入 B07。

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

## self-hosted workflow 路径状态（2026-08-24）

此前发现的 `$RUNNER_TEMP` + `actions/checkout path` blocker 已经修正。当前 `.github/workflows/boot-crash-b06-selftest.yml` 不再尝试让 `actions/checkout` 在 `$GITHUB_WORKSPACE` 外建立 upstream checkout：course repository 仍由固定 revision 的 `actions/checkout` 取得；upstream Linux v5.10 则在 `$RUNNER_TEMP` 中使用原生 Git materialize：

```text
git init "$B06_UPSTREAM_DIR"
git -C "$B06_UPSTREAM_DIR" remote add origin https://github.com/torvalds/linux.git
git -C "$B06_UPSTREAM_DIR" fetch --depth=1 origin \
  2c85ebc57b3e1817b6ce1a6b703928e113a90442
git -C "$B06_UPSTREAM_DIR" checkout --detach FETCH_HEAD
```

当前 workflow 的设计路径已经恢复为可执行状态，并继续机器验证：

- runner 实际为 Linux/x86-64，Git >= 2.18、Python >= 3.9，且所需外部命令存在；
- course checkout 固定使用 `actions/checkout@11d5960a326750d5838078e36cf38b85af677262`（官方 v4.4.0 release commit）。该固定 revision 的 `action.yml` 声明 `runs.using: node20`，因此匹配的 self-hosted runner 还必须能够承载 Node 20 Action runtime。固定 Action SHA 与 runtime metadata 已完成 provenance 核验，但真实 runner 的 runtime compatibility 只能由实际 workflow run 建立；若 checkout 因 Action runtime 不兼容失败，应分类为 self-hosted runner / Action runtime prerequisite failure，而不是 fixture 或 Linux v5.10 source-contract failure；
- `$RUNNER_TEMP` 必须非空、为绝对路径、已经存在为目录、不能是 symbolic link、不能是根目录 `/`，并且字符串中不得包含 CR/LF；此外 workflow 会执行 `cd -- "$RUNNER_TEMP" && pwd -P`，要求得到的 canonical physical path 与 `$RUNNER_TEMP` 字节级相等；
- `GITHUB_RUN_ID` 与 `GITHUB_RUN_ATTEMPT` 必须分别是正整数；
- course `HEAD == GITHUB_SHA`，course worktree clean；
- checker/fixture 的 committed blob 与 worktree blob 均严格匹配当前 exact baseline；
- fixture 必须报告 `Ran 22 tests` 与 `OK`；
- upstream `HEAD` 必须精确等于 Linux v5.10 commit `2c85ebc57b3e1817b6ce1a6b703928e113a90442`，执行前后 worktree 均 clean；
- checker 必须恰好得到 `PASS 1..7` 和最终 7-group summary；
- course checkout 在执行后再次验证 HEAD 与 clean 状态；该 post-execution gate 只有本次 `Checkout course repository` step 成功时才运行。

### scratch path 的 identity、ownership、本机权限与部署信任边界必须分开

当前 workflow 对 persistent self-hosted runner 的删除规则采用 fail-closed ownership contract。`RUNNER_TEMP + GITHUB_RUN_ID + GITHUB_RUN_ATTEMPT` 只能证明“本次 run 期望使用哪个路径”，不能证明该路径上预先存在的对象属于本次 run；同样，已经由本次 run 创建对象也不自动意味着其本机访问权限足够收敛。

此外，scratch child 的 mode `0700` 只限制对该 child 内容的普通访问，**不能单独证明任意 hostile multi-user host 是安全的**。目录项能否被其他本地 principal rename、unlink 或 replace，还受父目录 namespace 的 ownership、permission 与 sticky-bit 等规则约束。当前 workflow 没有试图建立 hostile-local-user threat model，因此真实 B06 验收还包含一个部署前提：`kernel-course` self-hosted runner 必须是 dedicated 或等价隔离的可信 runner，runner account 不与不可信交互式 workload 共用，并且在 job 生命周期内不可信本地 principal 不能修改其 `RUNNER_TEMP` namespace。workflow 的 exact-path、ownership 与 `0700` 检查是在这一部署信任边界内部提供 defense-in-depth，而不是替代该部署边界。

因此 prepare 阶段遵循以下顺序：

```text
计算本次唯一 expected scratch path
→ 若该路径已经存在（包括 dangling symlink），立即失败
→ 不删除任何预先存在的对象
→ 设置 umask 077
→ mkdir 创建本次 run 的 exact scratch directory
→ 验证新对象确为 directory 且不是 symbolic link
→ 使用 Python os.stat(..., follow_symlinks=False) + stat.S_IMODE()
  验证新目录 mode 精确为 0700
→ 只有创建、对象类型与 mode 验证均成功后，才通过 GITHUB_ENV 发布 B06_UPSTREAM_DIR
→ 后续 materialization 在这个已建立 ownership 且权限收敛的目录中初始化 upstream Git tree
```

这里的 ownership 不再由“路径名已发布”单独建立。prepare 必须先实际创建本次 run 的 scratch directory，并验证创建结果；`B06_UPSTREAM_DIR` 的发布只是把**已经建立的对象 ownership**传播给后续 step。`umask 077` 与随后对 `0700` 的显式验证则把本次 upstream scratch tree 的本机访问权限限制在 runner account；不能只依赖 self-hosted runner 宿主进程可能变化的 ambient umask。使用 Python 检查 mode 是为了直接核对 POSIX mode bits，而不依赖不同平台 `stat(1)` 命令行格式。persistent runner 上的 stale object 仍不会被 B06 自动“预清理”，而会作为 runner hygiene / ownership blocker 留给 runner 管理者确认来源后处理。

`always()` cleanup 采用对应的授权规则：

- cleanup 必须独立重新验证 `$RUNNER_TEMP` 的绝对、非根、non-symlink、CR/LF-free、canonical-physical-path 条件，以及 `GITHUB_RUN_ID` / `GITHUB_RUN_ATTEMPT` 的正整数条件；
- cleanup 独立重建 expected scratch path；
- **如果 `B06_UPSTREAM_DIR` 没有在 scratch directory 成功创建、类型验证和 mode `0700` 验证后发布，cleanup 不获得删除授权**。它只记录本次 scratch path 未发布，并退出，不会因为“能够重建路径名”就执行 `rm -rf`；
- 如果 `B06_UPSTREAM_DIR` 已发布，它必须与 independently reconstructed expected path 字节级相等，否则拒绝删除；
- 只有“prepare 已确认路径原先不存在、以 `umask 077` 创建并验证本次 `0700` scratch directory、随后发布 ownership”与“cleanup 再次确认 exact path identity”同时成立，才允许 `rm -rf`；
- 对已经授权的目标，cleanup 同时用 `-e` 与 `-L` 识别普通对象和 dangling symlink，删除后要求两者都不存在。

因此当前删除边界不是 glob/prefix namespace，也不是“可由 run identity 重建即可删除”，而是：**可信且隔离的 runner temp namespace + 本次 run 已实际建立 object ownership + private mode contract + exact-path identity**。这些条件缺一不可。`0700` 不得被解释为允许把该 job 部署到任意不可信共享 shell host。

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

1. 在满足上述 trusted/isolated runner deployment assumption 且匹配 `[self-hosted, linux, x64, kernel-course]` 的零新增费用 runner 上实际运行当前 workflow，取得 22/22 与 upstream 7/7 的完整日志；
2. 若零新增费用本地环境先具备 exact upstream v5.10 worktree，则直接执行 `boot-crash/labs/06-kexec-lifecycle/run_acceptance.sh`；
3. 任一路径出现具体 fixture/source-contract failure，立即回到 upstream v5.10 源码判断 checker、fixture 或课程结论哪一项需要修正；
4. 只有 22/22 与 7/7 都建立可复核执行证据后，才恢复 B06【已完成】并进入 B07。

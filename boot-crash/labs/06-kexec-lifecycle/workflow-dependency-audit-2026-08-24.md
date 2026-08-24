# B06 self-hosted workflow dependency audit — 2026-08-24

本记录核验 B06 self-hosted 验收 workflow 中唯一的外部 GitHub Action 依赖。它属于 workflow provenance / supply-chain 证据，不是 Linux v5.10 源码事实证据，也不能替代当前 22/22 fixture PASS 或 upstream 7/7 source-contract PASS。

## 核验对象

当前 `.github/workflows/boot-crash-b06-selftest.yml` 的 course checkout 使用：

```text
actions/checkout@11d5960a326750d5838078e36cf38b85af677262
```

workflow 没有使用可移动的 `@v4` / `@main` 引用，而是固定完整 commit SHA。

## 固定 revision 与 release identity

通过 `actions/checkout` 官方 GitHub 仓库核验 commit `11d5960a326750d5838078e36cf38b85af677262`：

```text
repository: actions/checkout
commit:     11d5960a326750d5838078e36cf38b85af677262
subject:    backport fixes to releases-v4 (#2524)
author date: 2026-07-16
GitHub commit verification: verified / valid
```

官方 releases 页面将 `v4.4.0` 指向短 SHA `11d5960`，与 workflow 固定的完整 SHA 一致。因此 workflow 中的 `# v4.4.0` 注释有官方 revision identity 支撑。

## Action metadata 与 runner 实际 runtime 必须分开

固定 commit 的 `action.yml` 声明：

```yaml
runs:
  using: node20
  main: dist/index.js
  post: dist/index.js
```

这只建立 **Action metadata contract**，不能直接推出“执行该 Action 的 runner 必须实际启动 Node 20”。2026-08-19 的历史 workflow run `32230874907` 提供了一个反例：GitHub-hosted runner 日志明确写出：

```text
Node 20 is being deprecated. This workflow is running with Node 24 by default.
...
Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4.
```

同一日志同时记录下载到的 checkout revision 为：

```text
actions/checkout@v4
SHA: 11d5960a326750d5838078e36cf38b85af677262
```

因此此前把 `using: node20` 直接表述为“self-hosted runner 必须能执行 Node 20 runtime”过强。正确边界是：

```text
Action metadata: pinned revision declares using: node20.
Runner execution: actual Actions runner may apply its own supported-runtime policy
                  (历史 hosted run 已观察到强制 Node 24)。
Acceptance prerequisite: selected kernel-course runner must be able to execute
                         this pinned Action successfully under its actual runner
                         runtime policy.
```

如果未来真实 self-hosted run 在 checkout Action 装载/启动阶段失败，应分类为 **self-hosted runner / Action-runtime compatibility failure**，而不是 B06 fixture 或 Linux v5.10 source-contract failure；但在取得真实 runner 日志前，不应预先把失败原因限定成“缺少 Node 20”。

### 历史 run 的证据边界

run `32230874907` 于 2026-08-19 在 GitHub-hosted Ubuntu 24.04 runner 上成功完成。它的 fixture step 输出：

```text
Ran 9 tests in 0.013s
OK
```

该 run 的 course HEAD 为 `4cb6c9b6c9d870ab037e75fb2c9c9d80a25e4284`。在该 commit 上：

```text
verify_source_contract.py blob:
  5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py blob:
  5a3b4d41f0a0b9c46575904431136f26cc46ab5d
```

也就是说，历史 run 已真实执行过**当前 checker blob**，但 fixture 当时只有 9 个测试，尚不是当前 22-case fixture blob `f18918cfbe0b01ffba59be3ac083a9971295a2f8`。因此该成功 run不能转移为当前 22/22 PASS，也没有执行当前 upstream 7/7 acceptance。

该历史 run 使用 GitHub-hosted runner，只作为已经发生的历史证据读取；当前课程维护仍不应为了 B06 验收主动切回可能产生费用的 GitHub-hosted runner。当前 workflow 保持 `workflow_dispatch` + `[self-hosted, linux, x64, kernel-course]`。

## Checkout 输入语义复核

同一固定 revision 的官方 README 对当前 B06 使用的 checkout inputs 给出如下语义：

```text
checkout 工作目录位于 $GITHUB_WORKSPACE；
ref 指定要 checkout 的 branch/tag/SHA；
fetch-depth: 1 表示只取单个 commit 深度；
clean: true 在 fetch 前执行 git clean -ffdx && git reset --hard HEAD；
persist-credentials: false 禁止把认证 token 持久化到本地 Git config；
set-safe-directory: false 禁止把 repository path 写入全局 Git safe.directory。
```

当前 B06 workflow 使用：

```yaml
with:
  ref: ${{ github.sha }}
  clean: true
  fetch-depth: 1
  persist-credentials: false
  set-safe-directory: false
```

`clean: true` 不能替代 B06 自己的 checkout 后 `git status --porcelain`、`HEAD == GITHUB_SHA`、checker/fixture blob identity 以及执行后的 HEAD/clean 检查；`fetch-depth: 1` 也不能解释成已经证明 revision identity。

官方 README 同时说明，当 PATH 中没有 Git 2.18+ 时 checkout action 可以回退到 REST API。B06 仍主动要求 Git >= 2.18，因为后续 provenance 与 upstream materialization 依赖真实 Git 命令和 object identity；该 gate 是 B06 验收设计的更强 prerequisite。

## 仓库内交叉核对

当前 `.github/workflows/boot-crash-b06-selftest.yml` 仍精确使用：

```text
actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
```

并使用上节列出的五项 checkout inputs。workflow 后续还会独立核验 course HEAD、clean worktree、checker/fixture blobs，因此 Action 自身的 checkout 成功不等价于课程 provenance gate 成功。

若 workflow blob、`uses:` revision 或 checkout inputs 改变，本审计必须重新核验，不能把旧依赖事实自动继承给新的执行输入。

## 证据边界

本审计建立：

```text
1. pinned actions/checkout SHA 对应官方 v4.4.0 release commit；
2. pinned action.yml metadata 声明 using: node20；
3. 历史 GitHub-hosted run 证明 runner 可将该 Node-20-targeting Action
   强制运行在 Node 24，因此 metadata target != 必然的实际 runtime；
4. 当前 checkout inputs 的语义已回到 pinned revision 官方 README 核验；
5. 历史 run 真实执行过当前 checker blob + 当时 9-case fixture，
   但没有执行当前 22-case fixture，也没有建立 upstream 7/7。
```

它不证明：

```text
当前 kernel-course self-hosted runner 与 pinned Action runtime policy 兼容；
当前 dispatch checkout 后 HEAD 已等于 GITHUB_SHA；
当前 exact fixture 已得到 22 tests / OK；
upstream Linux v5.10 checker 已得到 PASS 1..7；
B06 已满足收章条件。
```

B06 仍必须由真实 self-hosted/local exact acceptance 建立当前执行证据。

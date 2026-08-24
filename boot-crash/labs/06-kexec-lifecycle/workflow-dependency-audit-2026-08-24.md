# B06 self-hosted workflow dependency audit — 2026-08-24

本记录核验 B06 self-hosted 验收 workflow 中唯一的外部 GitHub Action 依赖。它属于 workflow provenance / supply-chain 证据，不是 Linux v5.10 源码事实证据，也不能替代 22/22 fixture PASS 或 upstream 7/7 source-contract PASS。

## 核验对象

当前 `.github/workflows/boot-crash-b06-selftest.yml` 的 course checkout 使用：

```text
actions/checkout@11d5960a326750d5838078e36cf38b85af677262
```

workflow 没有使用可移动的 `@v4` / `@main` 引用，而是固定完整 commit SHA。

## 2026-08-24 独立核验

通过 `actions/checkout` 官方 GitHub 仓库重新读取 commit `11d5960a326750d5838078e36cf38b85af677262`，确认：

```text
repository: actions/checkout
commit:     11d5960a326750d5838078e36cf38b85af677262
subject:    backport fixes to releases-v4 (#2524)
author date: 2026-07-16
GitHub commit verification: verified / valid
```

同时核对 `actions/checkout` 官方 releases 页面：`v4.4.0` release 指向短 SHA `11d5960`，与 workflow 固定的完整 SHA 一致。因此 workflow 中的 `# v4.4.0` 注释不是根据第三方示例推断出来的版本标签。

### Action runtime 契约

本次进一步直接读取同一固定 commit 下的 `action.yml`，确认该 revision 声明：

```yaml
runs:
  using: node20
  main: dist/index.js
  post: dist/index.js
```

因此 B06 workflow 的 course checkout 不只是“需要 Git/Python 的 shell step”；它还依赖 self-hosted GitHub Actions runner 能够执行 **Node 20 action runtime**。这里应区分两个层次：`node20` 是该固定 Action revision 的 metadata 契约；Node runtime 实际是否能在某台 `kernel-course` runner 上启动，仍必须由真实 workflow run 证明。不能因为 action SHA 已核验，就把 runner runtime compatibility 记作已通过。

这个事实也解释了为什么不能只用 workflow 中的 `git --version` / `python3 --version` prerequisite 来宣称所有执行依赖均已验证：`actions/checkout` 由 runner 的 Action runtime 执行，不是由后续 shell 中的 `python3` 驱动。若未来真实 run 在 `Checkout course repository` 之前/期间因 Node action runtime 不兼容失败，应把它分类为 **self-hosted runner / Action runtime prerequisite failure**，而不是 B06 fixture 或 Linux v5.10 source-contract failure。

### Checkout 输入语义复核

本轮继续直接读取同一固定 revision 的官方 `README.md`，核对 B06 实际使用的 checkout inputs，而不是根据 workflow 字段名称自行推断语义。官方文档确认：

```text
checkout 工作目录位于 $GITHUB_WORKSPACE；
ref 指定要 checkout 的 branch/tag/SHA；
fetch-depth: 1 表示只取单个 commit 深度；
clean: true 在 fetch 前执行 git clean -ffdx && git reset --hard HEAD；
persist-credentials: false 禁止把认证 token 持久化到本地 Git config；
set-safe-directory: false 禁止把 repository path 写入全局 Git safe.directory。
```

当前 B06 workflow 对应使用：

```yaml
with:
  ref: ${{ github.sha }}
  clean: true
  fetch-depth: 1
  persist-credentials: false
  set-safe-directory: false
```

因此，B06 对 course checkout 的几个关键假设现在有 pinned Action 自身文档作为依赖事实依据：course tree 位于 `$GITHUB_WORKSPACE`；checkout 目标由 dispatch 对应的 `github.sha` 指定；凭据不会因为 checkout 默认行为被持久化；workflow 也不会依赖全局 `safe.directory` 修改来使后续 Git 命令工作。

需要特别区分 `clean: true` 与 B06 自己的 provenance gates：前者只描述 checkout action 在 fetch 前的清理行为，**不能替代**后续 `git status --porcelain`、`HEAD == GITHUB_SHA`、checker/fixture blob identity 以及执行后的 HEAD/clean 检查。也不能把 `fetch-depth: 1` 解释成“已经证明 HEAD 就是 GITHUB_SHA”；真正的 revision identity 仍由 workflow checkout 后的 `git rev-parse HEAD` 比较建立。

官方 README 同时说明，当 PATH 中没有 Git 2.18+ 时 checkout action 可以回退到 REST API 下载文件。B06 workflow 仍主动要求 Git >= 2.18，因为后续 provenance 和 upstream materialization 本身依赖真实 Git 命令与 object identity；因此 B06 的 Git 版本 gate 是课程验收设计的更强 prerequisite，不是对 checkout action 最低运行能力的错误转述。

## 仓库内交叉核对

本次维护继续直接读取仓库中的 `.github/workflows/boot-crash-b06-selftest.yml`，确认当前 workflow blob 为：

```text
965be5c6a483fd5bff368d9cf7a836df5d31b19c
```

该 blob 中 `Checkout course repository` step 仍精确使用：

```text
actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
```

并且 checkout inputs 与上节列出的五项完全一致。因此，本审计核验的 action revision 与输入语义都绑定到当前仓库实际 workflow，而不是只对应审计创建时的一份旧 workflow。若后续 workflow blob、`uses:` revision 或上述 checkout inputs 发生变化，必须重新核验依赖契约；不能把本记录自动继承给新的执行输入。

## 证据边界

本次核验建立下面三类事实：

```text
1. B06 workflow 当前固定的 actions/checkout 完整 SHA
   确实对应 actions/checkout 官方 v4.4.0 release commit。
2. 该固定 revision 的 action.yml 声明 using: node20。
3. 当前 checkout inputs 的工作目录、ref、clean、fetch-depth、
   credential persistence 与 safe.directory 语义已回到同一 pinned
   revision 的官方 README 复核。
```

它不证明：

```text
self-hosted runner 已成功启动该 Node 20 Action runtime；
self-hosted runner 已成功执行该 action；
checkout 后的实际 HEAD 已等于某次 dispatch 的 GITHUB_SHA；
当前 exact fixture 已得到 22 tests / OK；
upstream Linux v5.10 checker 已得到 PASS 1..7；
B06 已满足收章条件。
```

B06 仍必须以真实 workflow/local acceptance 执行日志建立上述执行证据。

## 为什么保留这项核验

B06 的自动验收证据要求能够归因到确定的 course revision、checker/fixture blob 和 upstream Linux revision。course checkout 本身也是这条证据链的输入。固定完整 action SHA 可以避免 major tag 后续移动造成执行依赖漂移；独立确认该 SHA 与注释中的 release 身份一致，则避免把未经核验的版本注释误当成 provenance。进一步核对固定 revision 的 `action.yml` 和 README，可以在搭建或诊断 `kernel-course` self-hosted runner 时明确区分 Action runtime、checkout input 语义与 B06 自己的 post-checkout provenance gates，避免把 checkout 的默认行为误当成课程验收已经建立的执行证据。

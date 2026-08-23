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

## 证据边界

本次核验只建立下面这条事实：

```text
B06 workflow 当前固定的 actions/checkout 完整 SHA
确实对应 actions/checkout 官方 v4.4.0 release commit。
```

它不证明：

```text
self-hosted runner 已成功执行该 action；
当前 exact fixture 已得到 22 tests / OK；
upstream Linux v5.10 checker 已得到 PASS 1..7；
B06 已满足收章条件。
```

B06 仍必须以真实 workflow/local acceptance 执行日志建立上述执行证据。

## 为什么保留这项核验

B06 的自动验收证据要求能够归因到确定的 course revision、checker/fixture blob 和 upstream Linux revision。course checkout 本身也是这条证据链的输入。固定完整 action SHA 可以避免 major tag 后续移动造成执行依赖漂移；独立确认该 SHA 与注释中的 release 身份一致，则避免把未经核验的版本注释误当成 provenance。

# B06 自动验收执行尝试记录

本文件只记录 **B06 当前 exact 自动验收的实际执行尝试与基础设施 blocker**。它不是 Linux v5.10 源码事实证据，也不能替代 `selftest-results.md` 中定义的 22/22 与 upstream 7/7 PASS 条件。

## 2026-08-23：当前零新增费用执行环境

目标：materialize `netplus/kernel` 当前 course checkout，随后准备 exact upstream Linux v5.10 tree，并执行 `run_acceptance.sh`。

实际首先执行：

```text
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/kernel
```

结果：clone 在取得任何 repository object 前失败：

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

因此本次失败分类为 **执行环境 DNS/network blocker**，不是：

- 当前 22-case fixture failure；
- `verify_source_contract.py` failure；
- upstream Linux v5.10 source-contract failure。

本次没有产生以下证据，禁止把人工源码复核或 workflow machine gates 写成这些 PASS：

```text
current exact fixture: 22 tests / OK / exit 0
upstream Linux v5.10: PASS 1..7 / 7-group summary / exit 0
```

GitHub repository connector 仍可读取和维护仓库内容，但它不能把读取结果暴露成本地 Git worktree 供 `run_acceptance.sh` 执行，因此不能绕过上述 blocker 伪造自动验收。

下一次具备可执行环境时，应直接运行当前 exact 验收路径；如果得到具体 fixture/checker failure，再把该 failure 作为下一修正单元并回到 upstream Linux v5.10 源码核验。

# B06 自动验收执行尝试记录

本文件只记录 **B06 当前 exact 自动验收的实际执行尝试与基础设施 blocker**。它不是 Linux v5.10 源码事实证据，也不能替代 `selftest-results.md` 中定义的 22/22 与 upstream 7/7 PASS 条件。

## 2026-08-23：当前零新增费用执行环境

目标：materialize `netplus/kernel` 当前 course checkout，随后准备 exact upstream Linux v5.10 tree，并执行 `run_acceptance.sh`。

首次实际执行：

```text
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/kernel
```

结果：clone 在取得任何 repository object 前失败：

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

同日后续再次从独立临时目录执行同一 materialization 步骤：

```text
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/b06run/kernel
```

结果仍在取得任何 repository object 前失败，错误保持为：

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

第三次实际执行使用新的独立目标目录，避免复用前两次路径：

```text
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/kernel-course-run9
```

结果仍在 clone 取得任何 repository object 前失败：

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

第四次实际执行再次使用新的独立目标目录：

```text
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/kernel-course-run10
```

结果仍在取得任何 repository object 前失败：

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

因此该问题已由四次独立 clone 尝试复现；当前失败分类仍为 **执行环境 DNS/network blocker**，不是：

- 当前 22-case fixture failure；
- `verify_source_contract.py` failure；
- upstream Linux v5.10 source-contract failure。

## 2026-08-24：跨日重试

在新的独立目标目录再次执行 course materialization：

```text
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/b06-auto9
```

结果仍在取得任何 repository object 前失败：

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

这次跨日重试说明当前执行环境的 DNS/network 条件尚未恢复；它**不增加** fixture 或 upstream L1 验收证据，也不改变下面的重试边界。后续在环境条件没有变化时，不再通过重复 clone 累积同类记录。

本次没有产生以下证据，禁止把人工源码复核或 workflow machine gates 写成这些 PASS：

```text
current exact fixture: 22 tests / OK / exit 0
upstream Linux v5.10: PASS 1..7 / 7-group summary / exit 0
```

GitHub repository connector 仍可读取和维护仓库内容，并可核对当前 exact checker/fixture blob；当前基线仍为 checker blob `5c89b67628cf55560089656d5b65e80ff74c556f`、fixture blob `f18918cfbe0b01ffba59be3ac083a9971295a2f8`。但 connector 不能把这些读取结果暴露成本地 Git worktree 供 `run_acceptance.sh` 按其 Git provenance contract 执行，因此不能绕过上述 blocker 伪造自动验收。

## 2026-08-25：GitHub Actions 调度面复核

在本地 exact-Git materialization 条件没有变化的情况下，本次没有继续重复同一 DNS clone。改为直接读取仓库 GitHub Actions 的当前 run collection，核对是否已经出现可用于 B06 当前 exact acceptance 的 self-hosted 执行。

GitHub Actions API 当前返回的仓库 run 总数仍为 **5**。最新一条仍是：

```text
run id:       32230874907
run number:   5
run date:     2026-08-19
course SHA:   4cb6c9b6c9d870ab037e75fb2c9c9d80a25e4284
event:        push
runner model: historical GitHub-hosted execution
result:       success
fixture:      historical 9-case suite
```

因此，截至本次复核，GitHub Actions 侧**没有出现新的 workflow run**，也没有出现当前 `workflow_dispatch` + `[self-hosted, linux, x64, kernel-course]` 路径的执行证据。这个结论比单纯重复本地 DNS failure 多确认了一层：当前 blocker 不只是本地 materialization 不可用，同时仓库 Actions 历史中也尚未出现可替代它的当前 self-hosted exact run。

这项复核仍然不构成：

```text
current exact fixture: 22 tests / OK / exit 0
upstream Linux v5.10: 7/7 source-contract PASS
```

历史 run `32230874907` 的证据边界继续以 `selftest-results.md` 为准：它证明 current checker blob 与历史 9-case fixture 的真实 PASS，不能转移给当前 22-case fixture。

### 重试边界

连续复现同一个 DNS failure 不会增加 fixture 或 upstream L1 证据。后续仍应优先尝试真实验收，但只有以下任一条件变化时，materialization 或 Actions 执行才可能越过当前 blocker：

```text
当前执行环境恢复 github.com 的 DNS/Git 网络访问；或
匹配 [self-hosted, linux, x64, kernel-course] 的 runner 可以实际调度并产生新 run；或
出现另一套零新增费用、能够 materialize exact Git worktree 的执行环境。
```

在这些条件尚未变化时，不应把重复 DNS failure 或重复读取同一历史 Actions run 误记为新的 checker regression，也不应通过放宽 exact commit/blob/provenance gate 来规避基础设施问题。若维护运行仍需推进仓库工作，应只处理能够明确影响 B06 验收正确性、证据可信度或 self-hosted runner 隔离性的具体问题。

下一次具备可执行环境时，应直接运行当前 exact 验收路径；如果得到具体 fixture/checker failure，再把该 failure 作为下一修正单元并回到 upstream Linux v5.10 源码核验。

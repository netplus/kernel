# Network 专题维护规则

本文件补充根目录 `AGENTS.md`，只适用于 `network/` 目录。

## 1. 源码事实基线

Network 专题从当前阶段起统一以 **upstream Linux v6.12** 为内核实现事实基线。

固定基线：

```text
Linux tag: v6.12
commit: adc218676eef25575469234709c2d87185ca223a
主要架构：x86-64（架构相关内容）
```

根目录现有基础课程仍包含已经按 Linux v5.10 核验的历史材料。这些章节保留各自原有的事实基线，不做整章或整仓的版本迁移。

如果后续学习更新的 Linux 内核版本，只在对应主题或章节增加“内核版本变化”补充，并分别基于相关 upstream tag 核实差异。补充内容应明确：

- 原章节的事实基线版本；
- 新版本及对应 upstream tag/commit；
- 哪些源码路径、函数、数据结构、调用关系或语义发生了变化；
- 哪些核心机制保持不变；
- 变化产生的原因和对执行路径、实验或用户可观察行为的影响。

不得为了采用更新版本而机械替换原章节中的版本号、源码路径或调用链，也不得把新版本实现反向改写成旧版本原有实现。版本变化应作为增量知识保留在对应章节，使读者能够同时看到原机制和后续演进。

凡 `network/` 中涉及内核实现的结论，包括文件路径、函数、宏、结构体、字段、调用关系、hook 注册、priority、verdict、执行顺序、CONFIG 条件、对象生命周期和并发语义，都必须先在 upstream Linux v6.12 源码中确认。

网上文章、man page、Netfilter wiki、LWN、发行版文档可用于解释用户态语义和设计背景，但不能替代 v6.12 源码成为内核实现依据。无法在 v6.12 中确认的实现细节应标为“待核实”。

## 2. nftables 学习材料组织

```text
network/
├── README.md
├── docs/nftables/          教材正文
├── labs/nftables/          可复现实验
└── source-paths/           v6.12 源码入口与调用路径
```

nftables 教材按以下顺序推进：

```text
用户可观察行为
→ ruleset/packet 执行模型
→ Netfilter hook 与网络路径
→ nftables evaluator
→ conntrack/NAT/routing 等关联子系统
→ 实验验证
→ v6.12 源码闭环
```

不能只罗列 `nft` 命令，也不能只给内核调用链。每个主题都要明确回答“包现在在哪里、哪个状态被读取或修改、下一步为什么去那里”。

## 3. 实验要求

实验优先使用独立临时 table，例如 `inet nft_demo`，避免破坏主机现有 ruleset。实验说明必须包括：

- 前置条件；
- 完整创建命令；
- 如何产生测试流量；
- 如何观察 counter、log、trace 或 conntrack；
- 预期结果和解释；
- 明确清理命令；
- 对高频 `log`、drop、NAT、policy routing 等可能影响现网行为的操作给出风险说明。

需要证明控制流时，优先组合 `counter`、`nft monitor trace` 和有速率限制的 `log`，而不是依赖猜测。

## 4. 源码分析要求

每个 `source-paths/` 文档至少记录：

- upstream v6.12 tag/commit；
- 文件路径；
- 入口函数或 expression eval 函数；
- 关键 verdict/数据结构；
- 与教材结论一一对应的源码行为；
- 尚未展开的分支和配置条件。

当前 nftables 核心优先从这些文件进入：

```text
include/linux/netfilter.h
net/netfilter/core.c
include/net/netfilter/nf_tables.h
net/netfilter/nf_tables_core.c
net/netfilter/nf_tables_api.c
net/netfilter/nft_counter.c
net/netfilter/nft_log.c
```

# nftables 学习计划

本计划用于 `network/` 专题中的 Netfilter/nftables 学习。内核实现事实统一以 upstream Linux v6.12（commit `adc218676eef25575469234709c2d87185ca223a`）为准。

## 学习目标

最终应能够从三个层次解释一个 nftables 行为：

```text
用户态规则语义
→ Netfilter hook/packet path
→ Linux v6.12 nf_tables 内核执行过程
```

并能够使用 `counter`、`log`、`nft monitor trace`、`conntrack`、`tcpdump`、`ip rule`、`ip route` 等工具验证结论。

## 阶段 1：ruleset evaluator

### NF00：整体执行模型【已完成】

掌握：

- table 主要用于组织 ruleset，不决定 packet evaluation 顺序；
- base chain 通过 hook 接入网络栈；
- 同一 hook 的 base chain 按 priority 从小到大执行；
- 相同 priority 不应依赖固定先后顺序；
- regular chain 不能独立接收 hook 流量；
- `accept` 结束当前 base-chain evaluation，但后续 base chain 仍可 drop；
- `drop` 是 packet 的终局 verdict。

材料：[`01-ruleset-evaluation-and-control-flow.md`](01-ruleset-evaluation-and-control-flow.md)

### NF01：chain 控制流【已完成】

掌握：

- evaluator 状态：current chain、current rule、owning base chain、jump stack；
- `jump` 保存 continuation；
- `goto` 不保存当前 continuation；
- regular-chain end 是 implicit return；
- `return` 只根据 jump stack 决定恢复位置；
- stack 为空时落到 base-chain policy；
- `accept/drop` 不按 return stack 返回。

### NF02：counter、log 与 rule 运维【已完成】

掌握：

- counter 是 stateful expression，不参与匹配或 verdict；
- counter 统计“执行流到达 counter statement”的 packet/byte；
- statement 相对位置会改变 counter 的统计口径；
- `log` 用于逐包观测，生产环境应考虑 rate limit；
- 使用 `nft -a` 查看 handle；
- 使用 handle 删除单条 rule；
- 使用 `flush chain` 清空 chain 中的 rules。

材料：[`02-counter-log-and-rule-operations.md`](02-counter-log-and-rule-operations.md)

## 阶段 2：可观测的真实 packet path

### NF03：`nft monitor trace`【下一课】

实验目标：

1. 创建独立 `inet nft_demo` table；
2. 仅对目标 ICMP/TCP 流量设置 `meta nftrace set 1`；
3. 使用 `nft monitor trace` 观察 rule、verdict、policy 和 chain transition；
4. 用 `jump/goto/return` 人工构造控制流并与 trace 对照；
5. 将 trace 输出映射到 Linux v6.12 `nft_do_chain()`。

完成标准：能够仅根据 trace 输出画出一次 base-chain evaluation 的完整控制流。

### NF04：Netfilter hooks 与 packet path

重点：

```text
local input:    ingress → PREROUTING → route → INPUT → socket
forward:        ingress → PREROUTING → route → FORWARD → POSTROUTING → egress
local output:   socket → route → OUTPUT → POSTROUTING → egress
```

需要精确回答：

- 各 hook 前后已经具备哪些 skb/interface/routing 信息；
- route lookup 在哪一步发生；
- 为什么 DNAT/SNAT/route chain 与 hook 位置有关；
- nftables base chain 如何注册到 Netfilter hook。

## 阶段 3：stateful packet processing

### NF05：Conntrack

- original/reply tuple；
- NEW/ESTABLISHED/RELATED/INVALID/UNTRACKED；
- conntrack entry 生命周期；
- `meta mark` 与 `ct mark`；
- `conntrack -L` 与 nft trace 联合观察。

### NF06：NAT

- stateful NAT 与 conntrack 的关系；
- DNAT/SNAT/masquerade/redirect；
- first packet 建立 NAT binding；
- 后续 packet 如何复用连接状态；
- NAT 与 routing decision 的顺序关系。

## 阶段 4：高效分类与策略表达

### NF07：sets/maps/verdict maps/concatenation

目标是从“大量顺序规则”转向“key lookup”：

```text
set          key → membership
map          key → value
verdict map  key → verdict
concat       tuple key → lookup
```

同时分析 interval、timeout、dynamic set 等特性。

## 阶段 5：nftables 与 Linux routing

### NF08：packet mark、connection mark 与 RPDB

主线：

```text
nft meta mark
→ skb->mark
→ ip rule fwmark
→ routing table
→ route lookup result
```

并比较：

```text
meta mark
ct mark
SO_MARK
```

### NF09：route chain 与 OUTPUT reroute

重点分析：

- `type filter hook output` 与 `type route hook output` 的区别；
- 哪些字段修改可能要求重新路由；
- mark/daddr 修改与 policy routing 的关系；
- Linux v6.12 实际 reroute 路径。

## 阶段 6：families 与更深层 datapath

### NF10a：kbuild、Kconfig 与协议族注册

掌握：

- kbuild 复合模块机制：`nf_tables-objs` 与 `nf_tables.o` 的关系；
- `CONFIG_NF_TABLES` 核心选项与默认值；
- 协议族选项：`NF_TABLES_IPV4/IPV6/ARP/INET/BRIDGE/NETDEV`；
- bool 与 tristate 的区别，以及为什么只有 BRIDGE 是独立模块；
- 协议族编号：`NFPROTO_IPV4=2`, `NFPROTO_IPV6=10`, `NFPROTO_INET=1`；
- INET 的特殊性：独立协议族、专属 INGRESS hook、broker 模式；
- INET 独有模块：`nft_fib_inet`、`nft_reject_inet` 的运行时协议分发。

材料：[`03-kbuild-and-protocol-families.md`](03-kbuild-and-protocol-families.md)

### NF10b：address families 语义与 hook 位置

系统比较：

```text
ip
ip6
inet
arp
bridge
netdev
```

需要结合实际 hook 位置，而不是只背 family 名称。

- 各 family 可用的 hook 位置；
- 同一 hook 在不同 family 中的语义差异；
- `nft list tables` 输出与实际内核注册的关系；
- 为什么 INET 表能同时处理 IPv4 和 IPv6 流量。

### NF11：stateful objects

- limit；
- quota；
- meter；
- dynamic set；
- timeout；
- named counter；
- synproxy（单独说明使用条件）。

### NF12：flowtable

重点不是语法，而是 fast path 到底绕过了哪些常规网络栈步骤，以及 conntrack/NAT/统计如何参与。

## 阶段 7：Linux v6.12 源码闭环

### NF13：nf_tables evaluator

核心入口：

```text
include/linux/netfilter.h
net/netfilter/core.c
net/netfilter/nf_tables_core.c
net/netfilter/nf_tables_api.c
net/netfilter/nft_counter.c
net/netfilter/nft_log.c
```

最终需要能够从 packet 到达某个 hook 开始，解释：

```text
Netfilter hook list
→ nftables base-chain callback
→ nft_do_chain()
→ rule/expression evaluation
→ NFT_BREAK/NFT_CONTINUE
→ NFT_JUMP/NFT_GOTO/NFT_RETURN
→ NF_ACCEPT/NF_DROP
→ 返回 Netfilter core
```

## 学习过程中的统一验证方法

每个主题尽量同时使用三类证据：

```text
配置证据：nft list ruleset / nft -a
运行证据：counter / log / trace / tcpdump / conntrack
源码证据：upstream Linux v6.12
```

如果三者冲突，先检查实验环境、内核版本、family、hook、priority 和配置条件，不用经验性解释替代事实核验。

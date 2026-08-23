# nftables counter、log 与 rule 运维

本文整理已经完成的 `counter`、`log`、rule handle 与删除操作，并说明 Linux v6.12 中对应的内核实现入口。

## 1. `counter` 是什么

`counter` 不是 match，也不是 verdict。它是一个有运行时状态的 nftables expression。

最准确的语义是：

> evaluator 真正执行到 `counter` expression 时，把 packet 数加 1，并把当前 skb 长度累加到 byte 数。

因此：

```nft
ip protocol icmp counter
```

只统计已经通过前置 `ip protocol icmp` 匹配并执行到 counter 的 packet。

而：

```nft
counter ip protocol icmp
```

counter 先执行，因此即使后面的 ICMP 匹配失败，计数也已经发生。

不要笼统地把 counter 解释成“整条 rule 最终命中次数”；它统计的是**执行流到达该 statement 的次数**。

## 2. Linux v6.12 中的 counter

源码：

```text
net/netfilter/nft_counter.c
```

关键入口：

```text
nft_counter_eval()
→ nft_counter_do_eval()
```

v6.12 中 counter 使用 per-CPU 数据：

```text
struct nft_counter_percpu_priv
    → struct nft_counter __percpu *counter
```

`nft_counter_do_eval()` 对当前 CPU 的 counter 更新：

```text
bytes   += pkt->skb->len
packets += 1
```

读取时 `nft_counter_fetch()` 遍历 possible CPUs 汇总 packets/bytes。

这说明 counter 不是一个简单的全局共享整数；v6.12 使用 per-CPU 统计以降低并发更新开销。

## 3. 查看 counter

规则示例：

```nft
ip protocol icmp icmp type echo-request counter
```

查看：

```bash
nft list chain inet nft_demo input
```

可能看到：

```text
counter packets 3 bytes 252
```

如果还想同时看到 rule handle：

```bash
nft -a list chain inet nft_demo input
```

## 4. counter 适合回答什么问题

典型问题：

```text
这条路径有没有 packet 到达？
一个分支有多少 packet/byte？
某条规则是否长期为 dead rule？
jump/goto/return 后面的规则实际上还能不能到达？
mark/NAT/filter 前后分别有多少流量？
```

counter 特别适合作为低成本的 datapath probe point。

## 5. `log` 是什么

`log` 也是 statement/expression，不负责 accept/drop。它在 packet 执行到该位置时向 Netfilter logging infrastructure 提交日志。

Linux v6.12：

```text
net/netfilter/nft_log.c
nft_log_eval()
→ nf_log_packet(...)
```

可以通过 `prefix` 给日志添加便于检索的标记：

```nft
log prefix "NFT-DEMO: "
```

典型查看方式：

```bash
journalctl -k -f
```

或：

```bash
dmesg -w
```

具体输出格式取决于 logger、family、协议和系统日志配置。

## 6. `counter` 与 `log` 的定位不同

```text
counter
    累计 packets/bytes
    适合回答“多少”以及“有没有经过”

log
    生成 packet 级观测记录
    适合回答“经过的具体是什么 packet”
```

高流量路径不应无节制逐包 log。需要长期启用时通常结合 `limit` 控制日志速率。

例如：

```nft
counter limit rate 5/second log prefix "NFT-DEMO: "
```

这里的顺序很重要：

```text
counter
→ 所有到达 counter 的 packet 都统计
limit
→ 只允许部分 packet 继续到 log
log
→ 只为通过 limit 的 packet 产生日志
```

所以 counter 数量可以远大于日志条数。

## 7. 最小 counter/log 实验

创建独立实验表：

```bash
nft add table inet nft_demo

nft 'add chain inet nft_demo input {
    type filter hook input priority -200;
    policy accept;
}'

nft 'add rule inet nft_demo input \
    ip protocol icmp icmp type echo-request \
    counter \
    log prefix "NFT-DEMO: "'
```

产生流量：

```bash
ping -4 -c 3 127.0.0.1
```

查看 counter：

```bash
nft -a list chain inet nft_demo input
```

实时查看 log：

```bash
journalctl -k -f
```

完整实验见：[`../../labs/nftables/01-counter-log/README.md`](../../labs/nftables/01-counter-log/README.md)。

## 8. 查看 rule handle

使用：

```bash
nft -a list chain inet nft_demo input
```

输出中会出现：

```text
# handle 5
```

handle 是当前 ruleset 中用于定位该 rule 的标识之一。重新创建/重新加载规则后不要假设旧 handle 永久不变。

## 9. 删除单条 rule

先查看当前 handle：

```bash
nft -a list chain inet nft_demo input
```

假设目标为：

```text
# handle 5
```

删除：

```bash
nft delete rule inet nft_demo input handle 5
```

再验证：

```bash
nft -a list chain inet nft_demo input
```

## 10. 清空 chain 中所有 rules

如果要保留 chain 本身，只删除其中的 rules：

```bash
nft flush chain inet nft_demo input
```

对于 base chain，这会保留：

```text
hook
priority
policy
chain 本身
```

但清空其中规则。

## 11. 删除 chain 或 table

删除 chain：

```bash
nft delete chain inet nft_demo input
```

删除整个实验 table：

```bash
nft delete table inet nft_demo
```

实验环境通常直接删除独立 table 最干净。

## 12. 用 counter 验证控制流

例如：

```nft
chain base {
    type filter hook input priority 0;
    policy accept;

    counter
    jump A
    counter
}

chain A {
    counter
    tcp dport 22 accept
    counter
    return
}
```

对命中 TCP/22 的 packet：

```text
base 第一个 counter    增长
A 第一个 counter       增长
A accept 后 counter    不增长
base jump 后 counter   不增长
```

原因是 regular chain 中的 `accept` 直接结束整个当前 base-chain evaluation，而不是 return 到 jump continuation。

这使 counter 成为验证 nftables 控制流的实用工具；下一阶段将用 `nft monitor trace` 获得更完整的逐 rule 执行轨迹。

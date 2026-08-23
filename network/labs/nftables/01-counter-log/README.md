# Lab: nftables counter 与 log 最小实验

## 目标

验证以下结论：

1. `counter` 只在执行流到达该 statement 时增长；
2. `log` 可以把目标 packet 交给 Netfilter logging infrastructure；
3. `counter` 与 `log` 都不会自动产生 accept/drop；
4. `nft -a` 可以看到 rule handle，并可按 handle 删除单条 rule。

## 前置条件

- Linux 主机已安装 `nft`；
- 内核启用 nftables/Netfilter；
- 以 root 权限执行；
- 实验使用独立 `inet nft_demo` table；
- 如果主机正在承担生产流量，不要把无速率限制的 `log` 放到高频通配路径。

## 1. 创建独立实验 table

```bash
nft add table inet nft_demo

nft 'add chain inet nft_demo input {
    type filter hook input priority -200;
    policy accept;
}'
```

添加只观察 ICMP echo request 的规则：

```bash
nft 'add rule inet nft_demo input \
    ip protocol icmp icmp type echo-request \
    counter \
    log prefix "NFT-DEMO: "'
```

注意这里没有 `accept`。匹配 packet 执行完 counter/log 后继续到 chain end，最终使用 `policy accept`。

## 2. 查看初始 counter 与 handle

```bash
nft -a list chain inet nft_demo input
```

应能看到类似：

```text
ip protocol icmp icmp type echo-request counter packets 0 bytes 0 log prefix "NFT-DEMO: " # handle N
```

记录当前实际 handle；不要假设示例中的数字固定。

## 3. 产生 ICMP 流量

```bash
ping -4 -c 3 127.0.0.1
```

再次查看：

```bash
nft -a list chain inet nft_demo input
```

预期 `packets` 增加 3。`bytes` 的具体值取决于实际 skb 长度，不把固定字节数作为实验通过条件。

## 4. 查看日志

另开终端：

```bash
journalctl -k -f
```

如果系统不使用相同的 journald/kernel-log 路径，也可尝试：

```bash
dmesg -w
```

再次执行：

```bash
ping -4 -c 3 127.0.0.1
```

预期能检索到带有前缀：

```text
NFT-DEMO:
```

的 kernel/netfilter log。具体字段和格式依赖 logger 与协议环境。

## 5. 验证 counter statement 的位置语义

先清空 chain 中 rules：

```bash
nft flush chain inet nft_demo input
```

加入 counter 在前的规则：

```bash
nft 'add rule inet nft_demo input \
    counter \
    ip protocol icmp icmp type echo-request \
    log prefix "NFT-DEMO2: "'
```

此时执行顺序为：

```text
所有到达该 rule 的 packet
→ counter
→ 检查是否 ICMP echo request
→ 只有匹配者才 log
```

如果主机同时有其他 INPUT 流量，counter 可能增长得比 `NFT-DEMO2` 日志条目快。这证明 counter 统计的是“到达 statement 的执行流”，而不是整条 rule 最终匹配数。

## 6. 删除单条 rule

先获取当前 handle：

```bash
nft -a list chain inet nft_demo input
```

假设实际显示 `handle 7`，则：

```bash
nft delete rule inet nft_demo input handle 7
```

再次确认：

```bash
nft -a list chain inet nft_demo input
```

目标 rule 应消失。

## 7. 可选：限制日志速率

重新添加规则时可使用：

```bash
nft 'add rule inet nft_demo input \
    counter \
    limit rate 5/second \
    log prefix "NFT-DEMO-RL: "'
```

这里的语义是：

```text
counter 统计全部到达 packet
→ limit 进行速率判断
→ 只有通过 limit 的 packet 才 log
```

因此日志条数小于 counter 是预期现象。

## 8. 清理

实验完成后删除整个独立 table：

```bash
nft delete table inet nft_demo
```

检查：

```bash
nft list tables
```

不应再看到：

```text
table inet nft_demo
```

## 结果解释

本实验主要验证 nftables statement 的顺序执行模型：

```text
expression/statement 按规则中的执行顺序运行
→ counter 在到达时立即更新状态
→ log 在到达时提交日志
→ 二者都不是 terminal verdict
→ 如果没有其他 verdict，evaluation 继续
```

下一实验将引入 `meta nftrace set 1` 与 `nft monitor trace`，直接观察 jump/goto/return 和 base-chain policy 的逐 rule 路径。

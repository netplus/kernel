# Linux v6.12 nftables 源码入口与已核验控制流

## 固定基线

```text
upstream repository: torvalds/linux
tag: v6.12
commit: adc218676eef25575469234709c2d87185ca223a
```

本文件只记录已经在该基线中确认的实现事实；尚未展开的 conntrack/NAT/route-chain 等路径后续逐项补充。

## 1. Netfilter hook 基础入口

### `include/linux/netfilter.h`

已核验：

```text
struct nf_hook_ops
    hook
    dev
    priv
    pf
    hook_ops_type
    hooknum
    priority
```

源码注释明确说明 hooks 按 ascending priority 排序。

同文件中的 `nf_hook()`：

```text
根据 protocol family 找到 hook entries
→ 构造 struct nf_hook_state
→ 调用 nf_hook_slow(...)
```

如果没有 hook entry，则保持通过状态，由调用者继续执行后续网络栈函数。

### `net/netfilter/core.c`

已核验：

- hook 注册时 `nf_hook_entries_grow()` 按 `priority` 把新的 hook 插入已有 entries；
- `accept_all()` 的源码注释直接说明 `NF_ACCEPT` 会使 `nf_hook_slow` 调用/继续下一个 hook；
- `nf_hook_slow()` 是多个已注册 hook entry 的慢路径调度入口。

这为“同一 Netfilter hook 上多个 base chain/其他 hook handler 按 priority 依次执行”提供内核层入口。

## 2. nftables evaluator 核心

### `net/netfilter/nf_tables_core.c`

关键函数：

```text
nft_do_chain(struct nft_pktinfo *pkt, void *priv)
```

关键状态：

```text
chain       当前 chain
basechain   owning base chain
rule        当前 rule
regs        nft registers/verdict
stackptr    jump stack pointer
jumpstack[] 保存 continuation rule
```

### 每条 rule 的开始

在 `next_rule:` 处：

```text
regs.verdict.code = NFT_CONTINUE
```

随后逐 expression 执行。

每个 expression 返回后检查：

```text
if (regs.verdict.code != NFT_CONTINUE)
    break
```

因此 expression 一旦产生非-continue verdict，当前 rule 后续 expression 不再执行。

## 3. match failure 与 `NFT_BREAK`

快速 compare expression 在条件失败时设置：

```text
regs.verdict.code = NFT_BREAK
```

`nft_do_chain()` 对 `NFT_BREAK` 的处理：

```text
重置为 NFT_CONTINUE
→ continue 外层 rule loop
→ 下一条 rule
```

所以 `NFT_BREAK` 可以理解为“当前 rule 不再继续，但继续本 chain 下一 rule”。

## 4. `jump`

v6.12 中：

```text
case NFT_JUMP:
    jumpstack[stackptr].rule = nft_rule_next(rule)
    stackptr++
    fallthrough
```

随后与 `NFT_GOTO` 共用：

```text
chain = regs.verdict.chain
goto do_chain
```

因此 `jump` 的直接实现语义是：

```text
保存当前 rule 的下一条 rule
→ stackptr + 1
→ 切换 target chain
```

即保存 continuation，而不是保存抽象的“父 chain”。

## 5. `goto`

v6.12 中 `NFT_GOTO` 直接执行：

```text
chain = regs.verdict.chain
goto do_chain
```

不会保存 `nft_rule_next(rule)`，也不会增加 `stackptr`。

因此 goto target 之后执行 `return` 时，没有“回到 goto 后面”的专属 frame。

## 6. `return` 与 regular-chain end

在 rule loop 结束后，`nft_do_chain()` 对：

```text
NFT_CONTINUE
NFT_RETURN
```

都会进入后续 stack 检查。

如果：

```text
stackptr > 0
```

则：

```text
stackptr--
rule = jumpstack[stackptr].rule
goto next_rule
```

所以 return 的恢复位置来自 jumpstack。

如果 jumpstack 已空，则不再恢复某个 regular chain，而是继续到 base-chain policy。

这也解释了 regular chain 正常走到末尾时为什么等价于 implicit return：没有 terminal Netfilter verdict 时最终走相同的 stack/policy 路径。

## 7. base-chain policy

当 jump stack 为空且 evaluator 没有提前返回 Netfilter terminal verdict 时：

```text
nft_trace_packet(... NFT_TRACETYPE_POLICY)
→ 可选更新 base-chain stats
→ 检查 nft_base_chain(basechain)->policy
→ 返回 base-chain policy
```

因此 policy 属于 owning base chain，而不是当前最后一个 regular chain。

## 8. `accept` / `drop`

`nft_do_chain()` 首先按 Netfilter verdict mask 处理：

```text
NF_ACCEPT
NF_QUEUE
NF_STOLEN
NF_DROP
```

其中：

```text
NF_ACCEPT / NF_QUEUE / NF_STOLEN
→ 直接 return 当前 verdict

NF_DROP
→ 直接返回 drop reason
```

这些路径不会逐层 pop nft jumpstack。

因此 regular chain 深处的 `accept` 会直接结束当前 `nft_do_chain()` base-chain evaluation，而不是“return 到调用者继续”。

返回 Netfilter core 后，`NF_ACCEPT` 允许同一 hook 的后续 hook entry 继续运行；`NF_DROP` 终止当前 packet。

## 9. trace 的内核入口

`net/netfilter/nf_tables_core.c` 中已经存在：

```text
nft_trace_packet()
nft_trace_verdict()
nft_trace_init()
```

trace 是否实际输出与 nft trace 开关以及 `skb->nf_trace` 有关。

下一课使用：

```bash
nft monitor trace
```

并通过规则设置目标 packet 的 `nftrace`，把用户态 trace 输出与这里的 evaluator 分支逐项对照。

## 10. counter

### `net/netfilter/nft_counter.c`

关键结构：

```text
struct nft_counter {
    bytes
    packets
}

struct nft_counter_percpu_priv {
    struct nft_counter __percpu *counter
}
```

关键路径：

```text
nft_counter_eval()
→ nft_counter_do_eval()
```

v6.12 的 `nft_counter_do_eval()`：

```text
取 this_cpu_ptr(priv->counter)
→ bytes += pkt->skb->len
→ packets += 1
```

查询 counter 时：

```text
nft_counter_fetch()
→ for_each_possible_cpu
→ 汇总每 CPU 的 packets/bytes
```

因此 counter 的准确含义是“expression 被执行到时更新 packet/byte 状态”，且实现使用 per-CPU counter。

## 11. log

### `net/netfilter/nft_log.c`

关键路径：

```text
nft_log_eval()
→ nf_log_packet(...)
```

`struct nft_log` 保存：

```text
struct nf_loginfo loginfo
char *prefix
```

普通 logger 路径通过 `nf_log_packet()` 把 packet、hook、in/out device、loginfo 和 prefix 交给 Netfilter logging infrastructure。

因此 `log` 本身不是 accept/drop verdict，只是执行到该 expression 时产生观测副作用。

## 12. 当前已核验的最小调用关系

```text
Linux network path
→ NF_HOOK()/nf_hook()
→ nf_hook_slow()
→ 某个注册的 nftables base-chain hook callback
→ nft_do_chain()
    → rule expressions
    → NFT_BREAK / NFT_CONTINUE
    → NFT_JUMP / NFT_GOTO / NFT_RETURN
    → NF_ACCEPT / NF_DROP / base policy
→ 返回 Netfilter core
→ 后续 hook entry 或终止 packet
```

目前已经源码闭环的课程内容：

```text
ruleset priority 模型
accept/drop 的作用范围
jump/goto/return 的 jump-stack 语义
base-chain policy
counter
log
trace evaluator 入口
```

待后续课程继续核验：

```text
base chain 的 nf_hook_ops 创建/注册细节
nft monitor trace 的 netlink 输出完整路径
conntrack
NAT binding
meta mark / ct mark
route chain reroute
sets/maps backend
flowtable
```

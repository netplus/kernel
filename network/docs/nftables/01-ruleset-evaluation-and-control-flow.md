# nftables ruleset evaluation 与控制流

本文整理已经完成的 nftables ruleset 执行模型与 chain 控制流。用户态语义参考 `nft(8)`；涉及内核实现的部分以 upstream Linux v6.12 为事实基线。

## 1. 两层执行模型

首先把整个求值过程分成两层：

```text
第一层：Netfilter hook 调度 base chain
第二层：某个 base chain 内部的 nftables evaluator
```

外层模型：

```text
packet 沿 Linux 网络栈移动
→ 到达某个 Netfilter hook
→ 找到挂在该 hook 的 base chains
→ 按 priority 从小到大执行
```

因此 table 不是 packet-flow 的执行节点。table 主要用于组织 ruleset 和限定对象/chain 的作用域。

## 2. base chain 与 regular chain

base chain 具有 hook/priority/policy，是网络栈进入 nftables 的入口。

regular chain 不直接挂 hook，只能由同一 table 中的 chain 通过 `jump`/`goto` 到达。

```text
hook
  ↓
base chain
  ↓
jump/goto
  ↓
regular chain
```

regular chain 走到末尾时产生 implicit return；base chain 走到末尾时应用 base-chain policy。

## 3. 同一 hook 上多个 base chain

示例：

```text
INPUT hook
  ├─ priority -100 → A
  ├─ priority    0 → B
  └─ priority  100 → C
```

priority 数值越小越早执行。不要依赖相同 priority 的确定顺序。

### `accept` 的作用域

`accept` 结束的是**当前 base-chain evaluation**，不是整个 ruleset。

```text
A → accept
↓
B 仍然执行
↓
B 可以 drop
```

因此前面 base chain 的 accept 不能保证 packet 最终通过后续 nftables/Netfilter/Linux 网络栈处理。

### `drop` 的作用域

`drop` 是终局 packet verdict：当前 packet 不再进入后续 base chain。后面的 accept 没有机会“推翻”它。

从纯粹的最终 allow/drop 结果看，可以把多个 filtering base chain 粗略理解为：

```text
最终通过 = 所有相关 base chain 都没有产生 drop
```

这个简化只适用于最终 verdict；如果前面的 chain 修改 packet 或 metadata，priority 顺序仍可能改变后续匹配结果。

## 4. 单个 base-chain evaluation 的状态模型

严格分析控制流时维护四个状态：

```text
B   owning base chain
C   current chain
PC  current rule / expression position
S   jump return stack
```

无论进入多少 regular chain，`B` 始终不变；最终需要 base policy 时使用的也是 owning base chain 的 policy。

## 5. rule 的基本分支

### rule 不匹配

```text
match false
→ next rule
```

### rule 匹配但没有 terminal verdict

执行已经到达的 statements，然后继续下一条 rule。

### `continue`

```text
current chain 不变
jump stack 不变
→ next rule
```

## 6. `jump`

严格语义：

```text
push(current chain 中 jump 后的 continuation)
→ current chain = target chain
→ 从 target 第一条 rule 开始
```

例如：

```text
base
  jump A
  BASE_AFTER
```

执行 `jump A` 后：

```text
S = [base:BASE_AFTER]
C = A
```

A 执行 `return` 或走到 chain end 时，pop 后回到 `BASE_AFTER`。

## 7. `goto`

严格语义：

```text
不 push 当前 continuation
→ current chain = target
→ 从 target 第一条 rule 开始
```

关键点不是“goto target 不能 return”，而是：

> `goto` 没有为当前位置创建 return frame。之后 `return` 只会使用更早的 `jump` frame；如果一个也没有，则应用 owning base-chain policy。

## 8. `return`

`return` 必须分成两个分支：

```text
return
  ├─ S 非空 → pop 最近的 jump continuation 并恢复执行
  └─ S 为空 → 结束当前 base-chain evaluation，应用 base policy
```

因此 `return` 不是“回逻辑上的父 chain”，它只认 jump stack。

regular chain 到末尾等价于 implicit `return`，因此也遵循完全相同的两个分支。

## 9. 典型组合推演

### `base jump R1 jump R2`

```text
base jump R1 → S=[base+]
R1 jump R2   → S=[base+,R1+]
R2 return    → pop R1+
R1 return    → pop base+
```

### `base jump R1 goto R2`

```text
base jump R1 → S=[base+]
R1 goto R2   → S=[base+]
R2 return    → pop base+
```

R2 不回 R1，因为 `goto` 没保存 R1 continuation。

### `base jump R1 jump R2 goto R3`

```text
base jump R1 → S=[base+]
R1 jump R2   → S=[base+,R1+]
R2 goto R3   → S=[base+,R1+]
R3 return    → pop R1+
```

R3 直接回 R1，跳过 R2 的 goto 后续。

### `base goto R1 jump R2`

```text
base goto R1 → S=[]
R1 jump R2   → S=[R1+]
R2 return    → R1+
R1 return    → S=[] → base policy
```

这个例子说明：goto 不会关闭 jump/return 机制，它只是不给 goto 自身建立 continuation。

## 10. `accept` 与 jump stack

如果在深层 regular chain 中执行：

```text
base
  jump A
    jump B
      accept
```

并不会逐层 pop：

```text
B accept
→ 整个当前 base-chain evaluation 结束
→ jump stack 不再用于恢复
→ 返回外层 hook 调度
```

所以 regular chain 中的 `accept` 不是 `return accept`。

## 11. `drop`

`drop` 同样不沿 jump stack 返回：

```text
任意深度 drop
→ packet terminal
→ 后续 chain/base chain 不再执行
```

## 12. base-chain policy

policy 主要在两类路径使用：

```text
1. base chain 正常走到末尾
2. return/implicit return 时 jump stack 已为空
```

`policy accept` 与显式 accept 对当前 base-chain evaluation 的最终效果相同；`policy drop` 与显式 drop 对 packet 的最终效果相同。

## 13. Linux v6.12 源码闭环

`net/netfilter/nf_tables_core.c:nft_do_chain()` 可以直接验证上述模型：

- evaluator 每条 rule 前把 `regs.verdict.code` 初始化为 `NFT_CONTINUE`；
- expression 产生非 `NFT_CONTINUE` verdict 后结束该 rule 后续 expression evaluation；
- `NFT_BREAK` 表示当前 rule 不匹配并继续下一 rule；
- `NFT_JUMP` 把 `nft_rule_next(rule)` 保存到 `jumpstack`，随后与 `NFT_GOTO` 共用切换 target chain 的路径；
- `NFT_GOTO` 不增加 `stackptr`；
- `NFT_RETURN`/`NFT_CONTINUE` 离开当前 chain 后，如果 `stackptr > 0` 就恢复最近保存的 rule；
- jump stack 为空时进入 base-chain policy；
- `NF_ACCEPT`、`NF_QUEUE`、`NF_STOLEN` 直接从 `nft_do_chain()` 返回；
- `NF_DROP` 直接返回 drop reason。

这说明“jump=保存 continuation，goto=不保存，return=只认 jump stack”不是类比，而是 Linux v6.12 evaluator 的直接实现。

## 14. 统一状态机

可以用下面的伪代码推演规则：

```text
evaluate_base(B):
    C = B
    S = []

    rule not match  → next rule
    no verdict      → next rule
    continue        → next rule

    jump X:
        push(next rule)
        C = X

    goto X:
        C = X

    return / regular-chain-end:
        if S not empty:
            resume(pop(S))
        else:
            return B.policy

    accept:
        return ACCEPT_CURRENT_BASE_CHAIN

    drop:
        return DROP_PACKET

    base-chain-end:
        return B.policy
```

分析复杂 ruleset 时不要凭“父子 chain”直觉推演，只维护 `current chain + jump stack` 即可。

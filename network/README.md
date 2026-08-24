# Linux Kernel 6.12 网络专题

本专题系统学习 Linux 网络数据路径，并以 **upstream Linux v6.12** 为内核实现事实基线。当前先从 Netfilter/nftables 切入，再逐步向收发路径、路由、conntrack、NAT、socket、TCP、TC/XDP 等方向扩展。

> v6.12 固定源码基线：`adc218676eef25575469234709c2d87185ca223a`。

## 当前学习入口

当前主线是 nftables：

- [nftables 学习计划](docs/nftables/00-learning-plan.md)
- [ruleset evaluation 与控制流](docs/nftables/01-ruleset-evaluation-and-control-flow.md)
- [counter、log 与 rule 运维](docs/nftables/02-counter-log-and-rule-operations.md)
- [Linux v6.12 nftables 源码入口](source-paths/nftables-v6.12.md)
- [counter/log 最小实验](labs/nftables/01-counter-log/README.md)

## 网络专题总主线

接收方向：

```text
网卡接收报文
→ DMA
→ 中断
→ NAPI
→ NET_RX_SOFTIRQ
→ sk_buff
→ 二层处理
→ IP
→ 路由
→ Netfilter
→ TCP/UDP
→ socket 接收队列
→ 唤醒用户进程
```

发送方向：

```text
用户 send/write
→ socket
→ TCP/UDP
→ IP
→ 路由
→ Netfilter
→ 邻居子系统
→ qdisc
→ 驱动发送队列
→ DMA
→ 发送完成
```

## N08：Netfilter / nftables 当前课程路线

这一部分优先推进，并与 Linux 网络路径、路由和 conntrack 交叉学习。

```text
NF00  ruleset evaluation 与基本对象                 已完成
NF01  jump/goto/return/verdict 精确控制流            已完成
NF02  counter/log/handle 与最小观测实验              已完成
NF03  nft monitor trace                               下一课
NF04  Netfilter hooks 与完整 packet path
NF05  conntrack：tuple、state、ct mark
NF06  NAT 与 conntrack binding
NF07  sets/maps/verdict maps/concatenation
NF08  meta mark、ct mark、RPDB 与 policy routing
NF09  route chain 与 OUTPUT reroute
NF10a kbuild、Kconfig 与协议族注册                     已完成
NF10b address families：ip/ip6/inet/bridge/netdev
NF11  limit/quota/meter/dynamic set 等 stateful object
NF12  flowtable 与 fast path
NF13  Linux v6.12 nf_tables evaluator 源码深入
```

学习方法不是按语法表背命令，而是始终维护下面四个问题：

```text
1. packet 当前位于 Linux 网络路径的哪个位置？
2. 当前由哪个 Netfilter hook/base chain 接管？
3. nft evaluator 此刻正在执行哪个 rule/expression/verdict？
4. packet、skb metadata、conntrack 或 routing state 被怎样读取/修改？
```

## 完整网络课程大纲

### N00：网络协议栈总体结构

- 用户态 socket API；
- 协议族、socket 层、传输层和网络层；
- 接收路径与发送路径；
- 进程上下文、硬中断和软中断；
- 网络路径中的主要数据结构。

### N01：`sk_buff`

- head、data、tail、end；
- 线性区与分片；
- clone/copy/引用计数；
- 协议头偏移；
- checksum 状态；
- GSO/GRO 元数据；
- 分配、传递和释放。

### N02：`net_device` 与驱动接口

- `struct net_device`；
- `net_device_ops`；
- RX/TX queue；
- 描述符环、DMA、carrier；
- 多队列和 RSS。

### N03：中断、NAPI 与网络软中断

```text
网卡中断
→ 调度 NAPI
→ NET_RX_SOFTIRQ
→ napi_poll
→ 驱动取包
→ napi_gro_receive
```

### N04：二层接收和协议分发

- `netif_receive_skb()`；
- Ethernet/VLAN；
- packet type；
- bridge、bonding、AF_PACKET。

### N05：IPv4 接收路径

```text
ip_rcv
→ PRE_ROUTING
→ ip_rcv_finish
→ 路由判断
→ ip_local_deliver / ip_forward
```

### N06：路由与 FIB

- FIB；
- 输入/输出路由；
- nexthop；
- RPDB/policy routing；
- route cache/result 与网络路径。

### N07：邻居子系统

- ARP/IPv6 ND；
- neighbour table；
- NUD；
- 未解析报文队列；
- 定时器和垃圾回收。

### N08：Netfilter 与 nftables

见上面的 NF00～NF13 课程路线。

### N09：UDP

- bind/端口查找；
- 接收队列；
- checksum；
- 分片、多播、error queue。

### N10：TCP 状态机与连接建立

- listen socket；
- SYN queue/accept queue；
- request socket；
- SYN cookie；
- established hash。

### N11：TCP 接收路径

```text
tcp_v4_rcv
→ tcp_v4_do_rcv
→ tcp_rcv_established
→ ACK/数据处理
→ socket 接收队列
→ 任务唤醒
```

### N12：TCP 发送、拥塞控制与重传

- send queue；
- cwnd/pacing；
- RTO；
- 快速重传；
- 拥塞控制状态更新。

### N13：Socket 与用户进程

- `struct socket` / `struct sock` / `inet_sock` / `tcp_sock`；
- fd 与 socket；
- wait queue；
- poll/epoll；
- socket 唤醒与调度。

### N14：发送路径与 Qdisc

- `dev_queue_xmit()`；
- qdisc enqueue/dequeue；
- BQL；
- TX ring；
- completion 与 skb 释放。

### N15：XDP、TC 与 eBPF

- XDP native/generic/offload；
- TC ingress/egress；
- verifier/map/redirect；
- JIT。

### N16：网络隔离与资源控制概览

- network namespace；
- veth/bridge；
- cgroup BPF；
- 容器网络路径。

### N17：网络观测与故障分析

- tcpdump；
- ss；
- ethtool；
- nstat；
- dropwatch；
- `nft monitor trace`；
- ftrace/tracepoint/perf/eBPF；
- crash 中的 socket/skb/队列。

## 推荐源码入口

```text
net/core/dev.c
net/core/skbuff.c
net/core/sock.c
net/ipv4/ip_input.c
net/ipv4/ip_output.c
net/ipv4/route.c
net/ipv4/tcp_input.c
net/ipv4/tcp_output.c
net/ipv4/tcp_ipv4.c
net/netfilter/
net/sched/
include/linux/netdevice.h
include/linux/skbuff.h
include/net/sock.h
```

具体内核实现结论以 `network/AGENTS.md` 规定的 upstream Linux v6.12 基线逐项核验。

# Linux Kernel 5.10 网络协议栈课程

本目录是本仓库的核心应用维度，用于系统学习 Linux kernel 5.10 网络协议栈，并把汇编、调度、时钟和内存知识带入真实收发包路径。

## 课程主线

```text
网卡收到报文
→ IRQ / NAPI
→ softirq
→ sk_buff
→ 二层处理
→ IPv4/IPv6
→ 路由与 Netfilter
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
→ 邻居子系统
→ qdisc
→ 驱动 TX ring
→ DMA
```

## 课程大纲

### N00：网络栈总体架构

- 用户态 socket API；
- VFS、socket、协议族和传输层；
- ingress 与 egress；
- process、softirq、hardirq 上下文；
- 报文在不同层次的核心数据结构。

### N01：`sk_buff`

- 线性区与分片；
- head/data/tail/end；
- clone、copy、share；
- header offset；
- checksum 状态；
- GSO/GRO 元数据；
- 生命周期与引用计数；
- 与 [`memory/`](../memory/) 的联系。

### N02：`net_device` 与驱动接口

- `struct net_device`；
- netdev ops；
- feature flags；
- queue；
- RX/TX ring；
- DMA；
- carrier 与 link state；
- 多队列和 RSS。

### N03：中断、NAPI 与 Softirq

核心路径：

```text
NIC interrupt
→ schedule NAPI
→ NET_RX_SOFTIRQ
→ napi_poll
→ driver receive
→ napi_gro_receive
```

重点：

- 为什么不能在 hardirq 中完成全部收包；
- NAPI budget；
- interrupt mitigation；
- GRO；
- ksoftirqd；
- 与 [`scheduler/`](../scheduler/) 和 [`timekeeping/`](../timekeeping/) 的关系。

### N04：二层收包与协议分发

- `netif_receive_skb`；
- `__netif_receive_skb_core`；
- packet type；
- Ethernet；
- VLAN；
- bridge；
- bonding；
- taps、AF_PACKET。

### N05：IPv4 接收路径

```text
ip_rcv
→ NF_INET_PRE_ROUTING
→ ip_rcv_finish
→ routing decision
→ ip_local_deliver / ip_forward
```

重点：

- IP header validation；
- fragmentation/reassembly；
- local delivery；
- forwarding；
- protocol dispatch。

### N06：路由与 FIB

- routing table；
- policy routing；
- FIB trie；
- nexthop；
- route cache 的历史变化；
- input/output lookup；
- namespace 与 VRF。

### N07：邻居子系统

- ARP/ND；
- neighbour table；
- NUD state；
- unresolved queue；
- timer；
- garbage collection；
- 与时钟和内存回收的联系。

### N08：Netfilter 与 NAT

- hook；
- conntrack；
- tuple；
- state；
- DNAT/SNAT；
- local/forward 路径；
- nftables；
- bridge netfilter；
- 性能与内存开销。

### N09：UDP

- bind 与端口查找；
- receive queue；
- checksum；
- fragmentation；
- cork；
- error queue；
- 多播。

### N10：TCP 状态机与连接建立

- socket state；
- listen、SYN queue、accept queue；
- three-way handshake；
- request socket；
- SYN cookie；
- established hash。

### N11：TCP 接收路径

```text
tcp_v4_rcv
→ tcp_v4_do_rcv
→ tcp_rcv_established
→ ACK/data processing
→ receive queue
→ wakeup
```

重点：

- sequence space；
- out-of-order queue；
- ACK；
- receive window；
- delayed ACK；
- socket 唤醒与调度。

### N12：TCP 发送、拥塞控制与重传

- send queue；
- write queue；
- segmentation；
- congestion window；
- pacing；
- retransmission timer；
- fast retransmit；
- RTO；
- 与 timer/hrtimer 的关系。

### N13：Socket 层与用户进程

- `socket`、`sock`、`inet_sock`、`tcp_sock`；
- file descriptor；
- wait queue；
- blocking/nonblocking；
- epoll；
- wakeup；
- syscall 与调度链。

### N14：发送路径与 Qdisc

- `dev_queue_xmit`；
- qdisc；
- enqueue/dequeue；
- traffic control；
- watchdog；
- BQL；
- driver TX；
- completion。

### N15：XDP、TC 与 eBPF

- XDP hook；
- native/generic/offload；
- TC ingress/egress；
- verifier；
- map；
- redirect；
- socket map、SK_MSG；
- JIT 与汇编的联系。

### N16：Namespace、Cgroup 与容器网络

- network namespace；
- veth；
- bridge；
- route namespace；
- cgroup BPF；
- socket cgroup；
- conntrack zone；
- 容器网络执行链。

### N17：网络观测与故障分析

- tcpdump；
- ss；
- ethtool；
- nstat；
- dropwatch；
- ftrace；
- perf；
- tracepoint；
- eBPF tracing；
- `/proc/net`；
- crash 中分析 skb、socket 和队列。

## 推荐源码入口

```text
drivers/net/
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

## 推荐实验

```text
跟踪一次 NAPI 收包
打印 skb 关键字段
分析 IPv4 local delivery
完成 KVM host DNAT
比较软中断与 ksoftirqd 路径
跟踪 TCP 建连和重传 timer
使用 tc/eBPF 分类和限速
分析 socket 唤醒到用户线程运行
```

## 与其他维度的关系

- 汇编：系统调用、软中断入口、JIT 和结构体偏移；
- 调度：ksoftirqd、socket 唤醒、busy polling；
- 时钟：TCP timer、邻居超时、qdisc watchdog；
- 内存：skb、page frag、DMA、socket memory accounting。
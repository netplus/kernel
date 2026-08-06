# Linux Kernel 5.10 网络协议栈（后续专题）

网络协议栈不属于当前“内核基础机制”学习阶段。完成汇编、x86_64 启动、内存管理、时钟、调度、Kexec、Kdump 和 vmcore 分析后，再进入本专题。

## 学习主线

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
→ 驱动发送队列
→ DMA
→ 发送完成
```

## 课程大纲

### N00：网络协议栈总体结构

- 用户态 socket API；
- 协议族、socket 层、传输层和网络层；
- 接收路径与发送路径；
- 进程上下文、硬中断和软中断；
- 网络路径中的主要数据结构。

### N01：`sk_buff`

- head、data、tail 和 end；
- 线性区与分片；
- clone、copy 和引用计数；
- 协议头偏移；
- checksum 状态；
- GSO 和 GRO 元数据；
- 分配、传递和释放过程。

### N02：`net_device` 与网卡驱动接口

- `struct net_device`；
- `net_device_ops`；
- RX/TX queue；
- 描述符环；
- DMA；
- carrier 和链路状态；
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

重点理解：

- 为什么不能在硬中断中处理全部报文；
- NAPI budget；
- 中断抑制；
- GRO；
- softirq 与 `ksoftirqd`。

### N04：二层接收和协议分发

- `netif_receive_skb()`；
- `__netif_receive_skb_core()`；
- Ethernet；
- VLAN；
- packet type；
- bridge、bonding 和 AF_PACKET 的位置。

### N05：IPv4 接收路径

```text
ip_rcv
→ PRE_ROUTING
→ ip_rcv_finish
→ 路由判断
→ ip_local_deliver 或 ip_forward
```

重点包括：

- IP 头检查；
- 本机接收与转发；
- 分片和重组；
- 上层协议分发。

### N06：路由与 FIB

- 路由表；
- FIB trie；
- 输入路由和输出路由；
- nexthop；
- policy routing；
- 路由结果在收发路径中的作用。

### N07：邻居子系统

- ARP 和 IPv6 ND；
- neighbour table；
- NUD 状态；
- 未解析报文队列；
- 定时器和垃圾回收；
- 邻居解析与发送路径的关系。

### N08：Netfilter 与 NAT

- hook 点；
- conntrack；
- tuple 和连接状态；
- DNAT 与 SNAT；
- 本机、转发和输出路径；
- nftables 与内核 hook 的关系。

### N09：UDP

- bind 与端口查找；
- 接收队列；
- checksum；
- 分片；
- 多播；
- error queue。

### N10：TCP 状态机与连接建立

- socket 状态；
- listen socket；
- SYN queue 和 accept queue；
- 三次握手；
- request socket；
- SYN cookie；
- established hash。

### N11：TCP 接收路径

```text
tcp_v4_rcv
→ tcp_v4_do_rcv
→ tcp_rcv_established
→ ACK 或数据处理
→ socket 接收队列
→ 任务唤醒
```

重点包括：

- sequence space；
- 乱序队列；
- ACK；
- 接收窗口；
- delayed ACK；
- 用户进程唤醒。

### N12：TCP 发送、拥塞控制与重传

- 发送队列；
- 分段；
- congestion window；
- pacing；
- RTO；
- 快速重传；
- 重传定时器；
- 拥塞控制状态更新。

### N13：Socket 与用户进程

- `struct socket`、`struct sock`、`inet_sock` 和 `tcp_sock`；
- 文件描述符与 socket 的连接；
- 阻塞与非阻塞；
- wait queue；
- poll 和 epoll；
- socket 唤醒与调度。

### N14：发送路径与 Qdisc

- `dev_queue_xmit()`；
- qdisc enqueue 和 dequeue；
- 流量排队；
- watchdog；
- BQL；
- 驱动 TX ring；
- 发送完成与报文释放。

### N15：XDP、TC 与 eBPF

- XDP hook；
- native、generic 和 offload；
- TC ingress 与 egress；
- verifier；
- BPF map；
- redirect；
- socket map 和 SK_MSG；
- JIT 与机器指令。

### N16：网络隔离与资源控制概览

- network namespace；
- veth 和 bridge；
- 容器网络基本路径；
- cgroup BPF；
- 本章只说明这些机制如何接入网络栈，详细内容以后另行展开。

### N17：网络观测与故障分析

- tcpdump；
- ss；
- ethtool；
- nstat；
- dropwatch；
- ftrace 和 tracepoint；
- perf 与 eBPF tracing；
- crash 中查看 socket、skb 和队列。

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

本专题安排在基础机制课程之后学习。
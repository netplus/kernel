# nftables kbuild、Kconfig 与协议族注册

本文整理 nftables 内核模块的构建机制、配置选项和协议族注册过程。内容以 upstream Linux v6.12 为事实基线，对应学习计划的 NF10a 阶段。

## 1. 问题背景

学习 nftables 时，以下问题需要先理解构建和配置机制才能回答：

- 为什么 `modprobe nf_tables` 加载的是一个模块，而 `nft list tables` 能看到多个协议族？
- 为什么有的系统有 `nf_tables_bridge.ko`，有的没有？
- 为什么内核配置中 `NF_TABLES` 是 `m`，而 `NF_TABLES_IPV4` 是 `y`？
- 为什么 INET 表能同时处理 IPv4 和 IPv6 流量？

这些问题涉及 Linux kbuild 的复合模块机制、Kconfig 配置系统，以及 nftables 协议族的注册方式。

## 2. kbuild 复合模块机制

### 2.1 单文件模块与多文件模块

最简单的内核模块由一个 `.c` 文件编译成一个 `.o`，再链接成 `.ko`：

```text
foo.c → foo.o → foo.ko
```

但大型功能需要拆分为多个源文件。kbuild 使用复合模块（composite module）机制：

```text
foo-part1.c → foo-part1.o ─┐
foo-part2.c → foo-part2.o ─┼→ ld -r → foo.o → foo.ko
foo-part3.c → foo-part3.o ─┘
```

关键规则：**当 `obj-y` 或 `obj-m` 中出现 `foo.o`，且存在 `foo-objs`（或 `foo-y`）变量时，kbuild 将 `foo-objs` 中列出的所有 `.o` 文件链接成单一的 `foo.o`**，而不是去编译 `foo.c`。

### 2.2 nf_tables 的零件清单

`net/netfilter/Makefile` 中定义了 `nf_tables` 的组成：

```makefile
nf_tables-objs := nf_tables_core.o nf_tables_api.o nft_chain_filter.o \
		  nf_tables_trace.o nft_immediate.o nft_cmp.o nft_range.o \
		  nft_bitwise.o nft_byteorder.o nft_payload.o nft_lookup.o \
		  nft_dynset.o nft_meta.o nft_rt.o nft_exthdr.o nft_last.o \
		  nft_counter.o nft_objref.o nft_inner.o \
		  nft_chain_route.o nf_tables_offload.o \
		  nft_set_hash.o nft_set_bitmap.o nft_set_rbtree.o \
		  nft_set_pipapo.o
```

`:=` 定义基础对象列表。这些文件覆盖 nftables 的核心逻辑：规则引擎、表达式、集合后端、链类型等。

### 2.3 条件追加零件

同一 Makefile 中，通过条件语句追加平台或特性相关的对象：

```makefile
# x86_64 平台（且非 UML 模式）追加 AVX2 加速的集合实现
ifdef CONFIG_X86_64
ifndef CONFIG_UML
nf_tables-objs += nft_set_pipapo_avx2.o
endif
endif

# 启用 retpoline 缓解且启用 NFT_CT 时，追加快速路径 conntrack 表达式
ifdef CONFIG_NFT_CT
ifdef CONFIG_MITIGATION_RETPOLINE
nf_tables-objs += nft_ct_fast.o
endif
endif
```

`+=` 在条件满足时向零件清单追加优化对象。`nft_set_pipapo_avx2.o` 是 pipapo 集合的 AVX2 向量化查找实现；`nft_ct_fast.o` 在 retpoline 开销存在时提供 conntrack 表达式的快速路径。

### 2.4 触发构建

```makefile
obj-$(CONFIG_NF_TABLES) += nf_tables.o
```

`CONFIG_NF_TABLES` 的值决定构建行为：

| 值 | 结果 |
|---|---|
| `y` | `nf_tables.o` 链入 vmlinux（内核内建） |
| `m` | 生成 `nf_tables.ko` 可加载模块 |
| `n` | 整行无效，`nf_tables-objs` 列表即使被填充也不会被使用 |

## 3. Kconfig 选项解析

### 3.1 核心选项：CONFIG_NF_TABLES

`net/netfilter/Kconfig`：

```kconfig
config NF_TABLES
	select NETFILTER_NETLINK
	select LIBCRC32C
	tristate "Netfilter nf_tables support"
```

- 类型为 `tristate`，可取值 `y`/`m`/`n`
- `select` 语句自动启用依赖项：`NETFILTER_NETLINK` 和 `LIBCRC32C`
- 没有 `default y` 或 `default m`，因此默认值为 `n`

### 3.2 协议族选项

在 `if NF_TABLES` 块内，定义了各协议族选项：

```kconfig
config NF_TABLES_INET
	depends on IPV6
	select NF_TABLES_IPV4
	select NF_TABLES_IPV6
	bool "Netfilter nf_tables mixed IPv4/IPv6 tables support"

config NF_TABLES_NETDEV
	bool "Netfilter nf_tables netdev tables support"
```

以及在其他目录中：

```kconfig
# net/ipv4/netfilter/Kconfig
config NF_TABLES_IPV4
	bool "IPv4 nf_tables support"

config NF_TABLES_ARP
	bool "ARP nf_tables support"
	select NETFILTER_FAMILY_ARP

# net/ipv6/netfilter/Kconfig
config NF_TABLES_IPV6
	bool "IPv6 nf_tables support"

# net/bridge/netfilter/Kconfig
menuconfig NF_TABLES_BRIDGE
	depends on BRIDGE && NETFILTER && NF_TABLES
	select NETFILTER_FAMILY_BRIDGE
	tristate "Ethernet Bridge nf_tables support"
```

### 3.3 bool 与 tristate 的区别

| 类型 | 协议族 | 结果 |
|---|---|---|
| `bool` | `NF_TABLES_IPV4`, `NF_TABLES_IPV6`, `NF_TABLES_ARP`, `NF_TABLES_INET`, `NF_TABLES_NETDEV` | 编译进 `nf_tables.ko` 内部，不生成独立模块 |
| `tristate` | `NF_TABLES_BRIDGE` | 可独立编译为 `nf_tables_bridge.ko` |

`bool` 类型的协议族是"总是随核心模块加载"的；`tristate` 类型的协议族可以单独加载或卸载。

### 3.4 默认配置：x86_64_defconfig

`arch/x86/configs/x86_64_defconfig` 中：

```text
CONFIG_NETFILTER=y
# CONFIG_NETFILTER_ADVANCED is not set
```

没有出现任何 `CONFIG_NF_TABLES` 行。根据 Kconfig 规则，未显式设置的 `tristate` 默认值为 `n`。因此 **x86_64 平台默认不启用 nf_tables**。

发行版（如 Debian）会维护自己的配置，将 `NF_TABLES` 设为 `m` 以平衡功能与资源占用。

## 4. 从 Kconfig 到协议族注册

### 4.1 协议族编号

`include/uapi/linux/netfilter.h`：

```c
enum {
	NFPROTO_UNSPEC =  0,
	NFPROTO_INET   =  1,
	NFPROTO_IPV4   =  2,
	NFPROTO_ARP    =  3,
	NFPROTO_NETDEV =  5,
	NFPROTO_BRIDGE =  7,
	NFPROTO_IPV6   = 10,
};
```

每个协议族有独立的编号。`NFPROTO_INET` 是独立的协议族，不是 `NFPROTO_IPV4 + NFPROTO_IPV6` 的组合。

### 4.2 链类型注册

`net/netfilter/nft_chain_filter.c` 中，每个协议族注册自己的链类型：

```c
// IPv4
static const struct nft_chain_type nft_chain_filter_ipv4 = {
	.name		= "filter",
	.type		= NFT_CHAIN_T_DEFAULT,
	.family		= NFPROTO_IPV4,
	.hook_mask	= (1 << NF_INET_LOCAL_IN) |
			  (1 << NF_INET_LOCAL_OUT) |
			  (1 << NF_INET_FORWARD) |
			  (1 << NF_INET_PRE_ROUTING) |
			  (1 << NF_INET_POST_ROUTING),
	.hooks		= { ... },
};

// IPv6
static const struct nft_chain_type nft_chain_filter_ipv6 = {
	.name		= "filter",
	.type		= NFT_CHAIN_T_DEFAULT,
	.family		= NFPROTO_IPV6,
	.hook_mask	= ...,  // 与 IPv4 相同
	.hooks		= { ... },
};

// INET
static const struct nft_chain_type nft_chain_filter_inet = {
	.name		= "filter",
	.type		= NFT_CHAIN_T_DEFAULT,
	.family		= NFPROTO_INET,
	.hook_mask	= (1 << NF_INET_INGRESS) |      ← 比 IPv4/IPv6 多 INGRESS
			  (1 << NF_INET_LOCAL_IN) |
			  (1 << NF_INET_LOCAL_OUT) |
			  (1 << NF_INET_FORWARD) |
			  (1 << NF_INET_PRE_ROUTING) |
			  (1 << NF_INET_POST_ROUTING),
	.hooks		= {
		[NF_INET_INGRESS]	= nft_do_chain_inet_ingress,
		[NF_INET_LOCAL_IN]	= nft_do_chain_inet,
		...
	},
};
```

**关键区别**：INET 链注册了 `NF_INET_INGRESS` 钩子，而纯 IPv4/IPv6 链没有此钩子。INET 的入口函数 `nft_do_chain_inet()` 会在运行时根据数据包的实际协议动态选择 pktinfo 解析方式。

### 4.3 协议族与模块的对应关系

| Kconfig | 类型 | 协议族编号 | 链类型 | 独立模块 |
|---|---|---|---|---|
| `NF_TABLES_IPV4` | `bool` | `NFPROTO_IPV4 = 2` | `nft_chain_filter_ipv4` | 否（编入 nf_tables.ko） |
| `NF_TABLES_IPV6` | `bool` | `NFPROTO_IPV6 = 10` | `nft_chain_filter_ipv6` | 否（编入 nf_tables.ko） |
| `NF_TABLES_ARP` | `bool` | `NFPROTO_ARP = 3` | `nft_chain_filter_arp` | 否（编入 nf_tables.ko） |
| `NF_TABLES_INET` | `bool` | `NFPROTO_INET = 1` | `nft_chain_filter_inet` | 否（编入 nf_tables.ko） |
| `NF_TABLES_NETDEV` | `bool` | `NFPROTO_NETDEV = 5` | `nft_chain_filter_netdev` | 否（编入 nf_tables.ko） |
| `NF_TABLES_BRIDGE` | `tristate` | `NFPROTO_BRIDGE = 7` | `nft_chain_filter_bridge` | 是（nf_tables_bridge.ko） |

## 5. INET 的特殊性：独立协议族与 broker 模式

### 5.1 不是简单超集

`NF_TABLES_INET` 的 Kconfig 定义中：

```kconfig
select NF_TABLES_IPV4
select NF_TABLES_IPV6
```

这看起来像是"包含"关系。但 INET 是独立的 `NFPROTO_INET` 协议族，有自己的链类型和专属功能，不是 IPv4 和 IPv6 的简单叠加。

### 5.2 运行时协议分发

INET 的入口函数 `nft_do_chain_inet()`：

```c
static unsigned int nft_do_chain_inet(void *priv, struct sk_buff *skb,
				      const struct nf_hook_state *state)
{
	struct nft_pktinfo pkt;

	nft_set_pktinfo(&pkt, skb, state);

	switch (state->pf) {
	case NFPROTO_IPV4:
		nft_set_pktinfo_ipv4(&pkt);
		break;
	case NFPROTO_IPV6:
		nft_set_pktinfo_ipv6(&pkt);
		break;
	default:
		break;
	}

	return nft_do_chain(&pkt, priv);
}
```

运行时根据 `state->pf` 判断数据包实际属于 IPv4 还是 IPv6，然后调用对应的 pktinfo 设置函数。这使得**同一个 INET 链可以同时处理两种协议的流量**。

### 5.3 INET 独有模块：broker 模式

某些 nftables 表达式需要协议相关的实现，但 INET 表要求统一接口。内核通过 broker（分发器）模式解决：

#### `nft_fib_inet`：FIB 查询分发器

```c
static void nft_fib_inet_eval(const struct nft_expr *expr,
			      struct nft_regs *regs,
			      const struct nft_pktinfo *pkt)
{
	switch (nft_pf(pkt)) {
	case NFPROTO_IPV4:
		return nft_fib4_eval(expr, regs, pkt);
	case NFPROTO_IPV6:
		return nft_fib6_eval(expr, regs, pkt);
	}
	regs->verdict.code = NF_DROP;
}
```

注册为 `.family = NFPROTO_INET`，只在 INET 表中可用。运行时根据数据包协议分发到 `nft_fib4_eval` 或 `nft_fib6_eval`。

#### `nft_reject_inet`：Reject 动作分发器

```c
static void nft_reject_inet_eval(const struct nft_expr *expr,
				 struct nft_regs *regs,
				 const struct nft_pktinfo *pkt)
{
	switch (nft_pf(pkt)) {
	case NFPROTO_IPV4:
		nf_send_unreach(...);   // IPv4: ICMP unreachable
		nf_send_reset(...);     // IPv4: TCP RST
		break;
	case NFPROTO_IPV6:
		nf_send_unreach6(...);  // IPv6: ICMPv6 unreachable
		nf_send_reset6(...);    // IPv6: TCP RST
		break;
	}
	regs->verdict.code = NF_DROP;
}
```

同样注册为 `NFPROTO_INET`，运行时分发到 IPv4 或 IPv6 的 reject 实现。

### 5.4 broker 模式的价值

没有 broker 时，用户需要为每种协议写单独的规则：

```bash
nft add rule ip filter input fib daddr type local accept
nft add rule ip6 filter input fib daddr type local accept
```

有了 broker，一条规则覆盖双栈：

```bash
nft add rule inet filter input fib daddr type local accept
```

### 5.5 不需要 broker 的模块

并非所有 INET 功能都需要 broker。以下模块本身就能同时处理双栈，无需协议分发：

| 模块 | 原因 |
|---|---|
| `nft_meta` | 读取 `skb->protocol` 等通用元数据，与 L3 协议无关 |
| `nft_ct` | conntrack 本身就能同时跟踪 IPv4/IPv6 连接 |
| `nft_counter` | 计数器只是 `skb` 经过时 +1，不关心协议 |
| `nft_limit` | 限速基于时间/包数，不关心协议 |

只有**协议相关**的操作（FIB 查询、reject 发送、NAT 等）才需要 broker。

## 6. 源码闭环

本文涉及的源码路径：

```text
net/netfilter/Makefile                  # nf_tables-objs 定义与条件追加
net/netfilter/Kconfig                   # NF_TABLES 核心选项
net/ipv4/netfilter/Kconfig              # NF_TABLES_IPV4, NF_TABLES_ARP
net/ipv6/netfilter/Kconfig              # NF_TABLES_IPV6
net/bridge/netfilter/Kconfig            # NF_TABLES_BRIDGE
include/uapi/linux/netfilter.h          # NFPROTO_* 协议族编号
net/netfilter/nft_chain_filter.c        # 各协议族链类型注册
net/netfilter/nft_fib_inet.c            # INET FIB broker
net/netfilter/nft_reject_inet.c         # INET reject broker
```

## 7. 常见误区

### 误区一：INET 是 IPv4 + IPv6 的缩写

INET 是独立的 `NFPROTO_INET` 协议族，有自己的链类型、hook 和专属模块。它不是"先检查 IPv4 再检查 IPv6"的快捷方式。

### 误区二：bool 选项比 tristate 选项"更小"

`bool` 选项编译进核心模块，会增加 `nf_tables.ko` 的体积；`tristate` 选项作为独立模块，可以按需加载。选择取决于功能是否常用，而非体积考量。

### 误区三：所有协议族都有独立的 .ko 文件

只有 `NF_TABLES_BRIDGE` 是 `tristate` 并生成独立模块。IPv4、IPv6、ARP、INET、NETDEV 都是 `bool`，编译进 `nf_tables.ko`。

## 8. 总结

- kbuild 复合模块机制：`nf_tables-objs` 定义零件清单，`obj-$(CONFIG_NF_TABLES)` 触发构建
- Kconfig 配置：`NF_TABLES` 是核心开关，各协议族选项决定可用 family
- 协议族注册：每个 family 在 `nft_chain_filter.c` 中注册链类型
- INET 的特殊性：独立 `NFPROTO_INET`，专属 INGRESS hook，broker 模式分发协议相关操作

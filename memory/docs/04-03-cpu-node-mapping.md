# M04-03：CPU 到 NUMA Node 的映射

本节只沿 CPU 这条线深入，目标是解释 Linux 5.10 中 `cpu_to_node(cpu)` 为什么能够工作，以及 early boot 中的 CPU/node 信息如何演化为稳定的运行时映射。

## 1. 本章目标

最终能够回答：

```text
CPU ID
  ↓
APIC / firmware affinity
  ↓
Linux node ID
  ↓
cpu_to_node(cpu)
```

并明确 CPU mask、node mask 与 CPU topology 的关系。

## 2. 核心问题

1. logical CPU ID 与 APIC ID 为什么不能混为一谈？
2. SRAT processor affinity 给出的 proximity domain 如何转换成 Linux node ID？
3. CPU 尚未全部 online 时，early CPU/node mapping 存在哪里？
4. `cpu_to_node()` 最终查询的映射由谁维护？
5. node 如何反向获得自己的 CPU mask？
6. BSP、AP 启动与 NUMA node assignment 有什么时序关系？
7. CPU hotplug 相关接口与本章启动主线如何区分？

## 3. 关键数据结构与接口

正式展开时重点分析：

```c
cpu_to_node(cpu)
numa_node_id()
set_cpu_numa_node()
set_cpu_numa_mem()
cpumask
nodemask_t
node_to_cpumask_map
```

具体名称和 5.10 实现位置必须以本地源码核验为准。

## 4. 关键源码文件

重点候选：

```text
arch/x86/mm/numa.c
arch/x86/mm/numa_64.c
arch/x86/include/asm/numa.h
include/linux/numa.h
include/linux/topology.h
include/linux/cpumask.h
include/linux/nodemask.h
```

如果 CPU topology 的关键实现位于 `arch/x86/kernel/`，正文中按真实调用路径补充。

## 5. 两层映射模型

本章需要明确区分：

```text
Firmware identity layer
APIC ID / proximity domain

Linux runtime layer
logical CPU ID / node ID
```

中间不是简单把数字直接复制，而是需要建立 Linux 自己的编号和映射关系。

## 6. 概念执行路径

```text
parse processor affinity
        ↓
obtain APIC / CPU identity
        ↓
resolve proximity domain
        ↓
resolve Linux nid
        ↓
record early CPU → nid
        ↓
CPU setup / online path
        ↓
final CPU → nid mapping
```

正式教程需要指出哪些步骤发生在 NUMA discovery，哪些发生在 CPU bring-up。

## 7. 正向与反向查询

最终运行时需要同时支持：

```text
CPU0 → Node0
CPU1 → Node0
...
```

以及：

```text
Node0 → { CPU0, CPU1, CPU2, CPU3 }
```

因此本章要同时解释：

```text
cpu_to_node()
node → cpumask
```

两个方向的数据关系，而不是只记一个 helper。

## 8. 示例机器推演

目标结果：

```text
CPU0 → node0
CPU1 → node0
CPU2 → node0
CPU3 → node0

CPU4 → node1
CPU5 → node1
CPU6 → node1
CPU7 → node1
```

反向：

```text
node0 cpumask = CPU0-3
node1 cpumask = CPU4-7
```

正文中要结合实际数据结构展示这张表何时成立。

## 9. 当前启动状态

本章结束后：

| 对象 | 状态 |
|---|---|
| memblock | 可用 |
| NUMA node | 已发现 |
| CPU → node | 已建立并可解释 |
| node → cpumask | 已建立并可解释 |
| memory range → node | 已有基础，下一章深入 |
| pg_data_t | 下一章重点 |
| zone | 未初始化 |
| buddy | 不可用 |

## 10. 容易混淆的问题

正文至少澄清：

```text
APIC ID != logical CPU ID
proximity domain != Linux node ID（不能默认数字永远相同）
node cpumask != scheduler domain
socket ID != node ID
```

## 11. 与上一章的连接

M04-02 同时获得了 CPU affinity 和 memory affinity。

本节只取：

```text
Processor Affinity
```

把 CPU → node 这条支线追完整。

## 12. 与下一章的连接

下一节回到物理内存支线：

```text
physical address / PFN range
        ↓
nid
        ↓
node memory ranges
        ↓
pg_data_t
```

这是从固件 NUMA topology 进入 Linux MM node abstraction 的关键一步。
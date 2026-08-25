# M04-02：x86 NUMA 拓扑发现

本节进入 Linux 5.10 x86-64 启动路径，研究固件提供的 NUMA affinity 信息如何被内核解析，并形成后续 CPU/node 与 memory/node 映射的基础。

## 1. 本章目标

建立这条主线：

```text
Firmware / ACPI
      ↓
SRAT
      ↓
Processor Affinity + Memory Affinity
      ↓
Linux early NUMA data
      ↓
CPU/node mapping + node memory ranges
```

重点理解“输入是什么、转换成什么”，而不是把本章变成完整 ACPI 教程。

## 2. 核心问题

1. x86 Linux 的 NUMA 信息主要从哪里获得？
2. SRAT 中 CPU affinity 和 memory affinity 为什么要分开描述？
3. APIC ID、logical CPU ID、proximity domain、Linux node ID 分别是什么？
4. 物理内存范围的 node affinity 在什么时候记录下来？
5. ACPI NUMA 信息缺失或禁用时，Linux 有哪些 fallback 思路？
6. NUMA discovery 与 e820/memblock 的关系是什么？

## 3. 输入信息模型

本章重点只保留与 MM 主线直接相关的 ACPI 信息：

```text
SRAT Processor Affinity
    CPU / APIC identity
    proximity domain

SRAT Memory Affinity
    physical address range
    proximity domain
```

最终需要转换为：

```text
CPU/APIC → Linux node ID
physical memory range → Linux node ID
```

## 4. 关键源码文件

正式展开时重点核验 Linux 5.10：

```text
arch/x86/mm/numa.c
arch/x86/mm/numa_64.c
arch/x86/mm/srat.c
arch/x86/kernel/acpi/boot.c
arch/x86/include/asm/numa.h
include/linux/acpi.h
```

如果实际主路径涉及其他文件，应在正文中按源码补充，而不是凭调用链印象推断。

## 5. 关键函数候选

正式教程需要结合 Linux 5.10 源码确认以下函数在实际主路径中的职责与关系：

```text
x86_numa_init()
numa_init()
acpi_numa_init()
相关 SRAT callback / affinity parser
numa_add_memblk()
```

要求对每个函数区分：

- architecture-specific entry；
- generic ACPI helper；
- callback；
- NUMA memory range recording。

## 6. 概念调用链

```text
setup_arch()
    ↓
NUMA initialization path
    ↓
parse ACPI NUMA information
    ├── processor affinity
    └── memory affinity
    ↓
construct early NUMA node information
```

正式正文必须给出“简化概念链”和“Linux 5.10 实际关键路径”两份图。

## 7. 与 memblock 的交汇点

本章重点追踪：

```text
physical memory range
        ↓
NUMA affinity / nid
        ↓
memblock representation
```

需要明确回答：

- memblock 何时已经存在；
- region 的 `nid` 在何时可用；
- e820 表示“物理内存是什么”，NUMA affinity 表示“这段内存离谁近”，二者如何合并。

## 8. 示例机器推演

假设 SRAT 最终表达：

```text
CPU0-3 → proximity domain A
CPU4-7 → proximity domain B

0-16 GiB  → domain A
16-32 GiB → domain B
```

本章要追踪 Linux 如何把它们归一化为：

```text
Node 0: CPU0-3, memory 0-16 GiB
Node 1: CPU4-7, memory 16-32 GiB
```

## 9. 当前启动状态

在本章结束时，目标状态是：

| 对象 | 状态 |
|---|---|
| memblock | 已可用于 early memory 描述 |
| NUMA node IDs | 已形成主要拓扑 |
| CPU → node | 已有早期映射基础，下一章深入 |
| memory range → node | 已有记录基础 |
| pg_data_t | 尚未作为本章重点初始化 |
| zone | 尚未初始化 |
| buddy | 不可用 |

## 10. 边界与 fallback

只建立必要认识：

```text
ACPI NUMA
NUMA disabled
fallback / dummy node
fake NUMA（如确实与 5.10 主线相关）
```

正文重点始终放在正常 ACPI NUMA server 路径。

## 11. 与上一章的连接

上一章建立硬件问题：

```text
哪些 CPU 与哪些内存更接近？
```

本章回答：

```text
固件如何把这种 affinity 告诉 Linux？
```

## 12. 与下一章的连接

下一节只沿 CPU 这条支线深入：

```text
APIC / CPU identity
    ↓
node ID
    ↓
cpu_to_node(cpu)
```

把 CPU → NUMA node 的软件映射完整追到底。
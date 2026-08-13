# A15 实验预期分析：TSS、IST 与特殊异常栈

本文是 `README.md` 中 TSS/IST 实验的验收基线。它不提供固定虚拟地址，也不把尚未执行的 kernel-GDB 结果写成实测值；目标是固定 Linux 5.10 x86-64 下各观察点之间应满足的关系。

## 1. 验收时必须区分的三个对象

实验中最容易混淆的是下面三个对象：

1. IDT gate 的 IST field：硬件 descriptor 中的 3-bit 编码，0 表示不使用 IST，1..7 选择 IST1..IST7。
2. Linux C 代码中的 `x86_hw_tss.ist[]`：零基数组，`IST_INDEX_*` 用来索引它。
3. 异常真正进入 Linux 汇编入口时的 `%rsp`：CPU 已经选择入口栈并在其上建立 hardware frame，因此它通常低于 TSS 中记录的 stack top。

因此不能直接比较 `IST_INDEX_DB` 与 gate.IST 的数值，也不能要求入口 `%rsp == tss.ist[IST_INDEX_DB]`。

## 2. 静态 descriptor/TSS 的预期关系

Linux 5.10 正常运行期应得到如下关系：

| Vector | IDT gate | Linux TSS slot | 基本含义 |
| --- | --- | --- | --- |
| `#DE` | IST field 为 0 | none | 不使用 IST |
| `#DB` | 非零 IST field | `ist[IST_INDEX_DB]` | debug exception stack |
| NMI | 非零 IST field | `ist[IST_INDEX_NMI]` | NMI exception stack |
| `#DF` | 非零 IST field | `ist[IST_INDEX_DF]` | double-fault exception stack |
| `#MC` | 非零 IST field（`CONFIG_X86_MCE`） | `ist[IST_INDEX_MCE]` | machine-check exception stack |

这里“非零”是架构层面的必要关系。实际 descriptor 数值必须从当前 Linux 5.10 guest 的 IDT 读取，并与该源码树的 descriptor 构造宏交叉核验。

若某个 `IST_INDEX_*` 的 C 数组值为 `n`，IDT descriptor 表示对应硬件 IST entry 时使用的是 1-based 编码；不要把零基数组索引直接抄成 gate field。

## 3. `#DE`：普通 privilege-level stack switch 的验收模型

用户态执行除零指令产生 `#DE` 时，vector 0 的正常 gate 不使用 IST。因为异常从 CPL3 进入 CPL0，CPU 仍然需要获得 ring-0 入口栈；这个换栈来自 privilege transition，而不是 IST。

因此早期入口观察应满足：

```text
IDT gate.IST == 0
current RSP belongs to the normal kernel/entry path
saved old RSP corresponds to the interrupted user RSP
```

这一 case 的意义是提供负对照：看到“异常时 `%rsp` 发生变化”并不足以证明使用了 IST。

## 4. `#DB`：IST stack switch 的验收模型

用户态设置 Trap Flag 后，在合适的指令边界产生 `#DB`。Linux 5.10 正常运行期的 debug gate 使用 debug IST。

CPU 进入第一条 Linux `#DB` entry 指令之前已经完成：

```text
read IDT gate
 -> select IST
 -> obtain stack top from current CPU TSS
 -> load new RSP
 -> build hardware return frame on that stack
 -> transfer control to Linux entry
```

因此在足够早的安全断点观察时，应满足：

```text
IDT gate.IST != 0
TSS selected slot points at debug exception-stack top
current RSP is inside the current CPU debug exception-stack range
current RSP < selected TSS stack top
hardware frame preserves the interrupted old RSP
```

`current RSP < stack top` 表达 x86 栈向低地址增长以及 CPU 已经压入入口 frame；具体差值不能脱离实际入口条件硬编码。

## 5. `#DE` 与 `#DB` 的核心对照

两者都可能从 CPL3 进入 CPL0，也都需要保存可返回的用户现场，但入口栈选择原因不同：

```text
#DE:
CPL3 -> CPL0
 -> privilege-level stack mechanism
 -> ordinary kernel/entry stack

#DB:
IDT gate.IST != 0
 -> TSS IST mechanism takes precedence for entry stack selection
 -> debug exception stack
```

验收时应根据 **descriptor + TSS pointer + stack range + hardware frame** 四项证据共同判断，不能只根据“当前 `%rsp` 与用户 `%rsp` 不同”下结论。

## 6. old RSP 的验收边界

IST 切换不会丢失被打断现场的 stack pointer。对于发生 stack switch 的入口，CPU 必须在新栈上的返回 frame 中保留返回所需的旧栈状态。

因此动态 `#DB` case 应同时记录：

```text
TSS debug IST stack top
entry current RSP
frame saved old RSP
user-side RSP near the trapping instruction
```

预期是：前两者属于 debug exception stack，saved old RSP 与用户侧被打断现场对应。不要把 frame 中的 old RSP 误认为当前 exception-stack RSP。

## 7. NMI 的可选验收

若隔离 guest 支持安全注入 NMI，可采用与 `#DB` 相同的证据链：

```text
NMI gate IST field
 -> current CPU TSS NMI slot
 -> NMI exception-stack range
 -> early-entry RSP
 -> saved interrupted RSP
```

NMI 可以打断内核中的敏感入口阶段，因此它比用户态 `#DB` 更能体现 IST 减少对当前栈状态依赖的目的。不过 NMI 动态观测不是本实验的最低完成条件。

## 8. `#DF/#MC` 的验收边界

基础课程不主动制造 double fault 或 machine check。

对 `#DF`，验收到以下证据即可：

```text
IDT descriptor uses DF IST
current CPU TSS has initialized DF IST pointer
pointer belongs to the expected exception-stack region
entry disassembly/source agrees with Linux 5.10 special path
```

对 `#MC` 还必须先确认 `CONFIG_X86_MCE`。配置未启用时，不能把其他构建的 machine-check gate/IST 行为当作当前 guest 的事实。

不应为了补齐一张结果表而主动制造 `#DF`、`#MC` 或 triple fault。

## 9. 不能从实验推出的结论

即使 `#DB` 动态观测成功，也不能据此推出：

- 所有异常都使用 IST；
- 所有 CPL3 -> CPL0 入口都使用 IST；
- TSS 仍被 Linux 用于传统 hardware task switching；
- IST 能保证 NMI、`#DF` 或 `#MC` 一定可恢复；
- TSS stack top 就是 handler 执行期间始终不变的 `%rsp`；
- 不同内核版本具有相同的 IST vector 分配。

本实验只验证 Linux 5.10 x86-64 的入口栈选择机制和几个代表性 vector 的实现。

## 10. 最低通过标准

在具备匹配 Linux 5.10 guest、`vmlinux` 和 kernel-GDB 环境后，第二部分实验至少应完成：

1. 从当前 guest 读取 `#DE` 与 `#DB` IDT gate，确认前者不使用 IST、后者使用 IST；
2. 读取当前 CPU TSS 的 debug IST pointer，并确认其属于 debug exception-stack 范围；
3. 动态触发用户态 `#DE`，确认其入口栈属于普通 privilege-transition/kernel entry 路径；
4. 动态触发可控 `#DB`，确认早期入口 `%rsp` 属于 debug IST stack；
5. 对 `#DB` 同时确认 hardware frame 中保存的 old RSP 对应被打断用户现场；
6. 对 `#DF` 和启用 `CONFIG_X86_MCE` 时的 `#MC` 完成 descriptor/TSS/source 静态核验，不要求破坏性动态触发。

当前课程维护环境缺少上述 kernel-GDB 条件，因此这些动态值仍应标记为“待实测”。本文件描述的是验收关系，不是伪造的实验记录。

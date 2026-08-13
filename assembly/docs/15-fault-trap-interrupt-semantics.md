# fault、trap 与 interrupt：先按事件语义区分入口

A15 前面的内容已经分别分析普通同步异常、IST 特殊异常和普通外部中断。进入下一章之前，还需要把几个经常混用的词放回同一套语义模型中。这里关注的是**事件与被打断指令之间的关系**，而不是把某个 Linux 入口宏简单贴上“fault”或“trap”标签。

## 1. 为什么需要先区分语义

`#DE`、`#DB`、`#GP` 和 device IRQ 最终都可以通过 IDT 把控制权交给内核，但这并不意味着它们属于同一种事件。

阅读入口代码时至少要分开两个问题：

1. 事件是由当前指令同步产生，还是在指令流之外异步到达？
2. 保存的 RIP 指向哪里，处理完成后应从哪里继续执行？

这两个问题决定了 fault、trap 与普通 interrupt 的基本区别。

## 2. fault：异常在指令完成前被报告

fault 是同步异常的一类。它与当前正在执行的指令直接相关，处理完成后通常需要让该指令重新执行，或者把异常转化为进程可见的错误。

典型模型是：

```text
instruction N 开始执行
        |
        | 检测到 fault
        v
CPU 进入异常入口
saved RIP -> instruction N
        |
        | handler 修复条件（如果能够修复）
        v
IRET
        |
        v
重新执行 instruction N
```

`#PF` 是最重要的例子：如果缺页处理成功，返回后需要重新执行触发缺页的指令。A16 会沿 Linux 5.10 的 `#PF` 入口继续分析这一点。

`#GP` 也属于 fault 类异常，但并不意味着它总能被修复后继续执行。fault 描述的是架构报告异常的语义，不是“Linux 一定能够恢复”的承诺。

## 3. trap：异常在指令完成后被报告

trap 同样是同步异常，但观察点位于触发条件对应的指令执行之后。保存的 RIP 通常指向下一条将要执行的指令。

概念模型是：

```text
instruction N 完成
        |
        | 产生 trap
        v
CPU 进入异常入口
saved RIP -> instruction N+1
        |
        v
handler
        |
        v
IRET
        |
        v
从 instruction N+1 继续
```

调试相关异常最能体现这种区别。例如 single-step 使用的 `#DB` 可以表现为 trap 语义：被单步执行的指令已经完成，然后 CPU 进入调试异常入口。

需要注意，`#DB` 的具体成因不止 single-step；不能把“vector 1”机械等同于一种固定的 fault/trap 场景。判断时应结合异常产生原因。

## 4. interrupt：异步打断当前指令流

本节所说的普通 interrupt 指外部或本地中断控制逻辑递送的异步中断，例如普通 device IRQ。它不是当前指令执行本身产生的同步异常。

概念模型是：

```text
程序正常执行
        |
        | CPU 在可接受中断的边界接受 IRQ
        v
保存 interrupted execution state
        |
        v
IDT -> Linux IRQ entry -> handler
        |
        v
恢复现场
        |
        v
继续被打断的执行流
```

因此普通 IRQ 的 saved RIP 应理解为“恢复被打断执行流所需的 RIP”，而不是 syscall 的 return RIP，也不是 fault 固定意义上的“faulting instruction RIP”。

A15 第三部分已经进一步说明 Linux 5.10 如何把 vector 送入 `common_interrupt`、建立 hardirq context，并在需要时切换到 per-CPU IRQ stack。

## 5. fault/trap 与 interrupt gate/trap gate 不是同一个分类轴

这是最容易混淆的地方之一。

`fault`、`trap` 描述**异常的报告语义**；IDT 中的 interrupt gate / trap gate 描述**入口 gate 的硬件行为**。二者不是同一组概念，不能因为名称都含有 trap 或 interrupt 就直接建立一一对应关系。

尤其不能使用下面这种推理：

```text
trap 异常 -> 必须使用 trap gate
fault 异常 -> 必须使用 interrupt gate
```

这种对应关系不存在。

阅读 Linux 5.10 IDT 初始化代码时，应分别核对：

```text
异常属于什么架构语义
vector 对应哪个 IDT descriptor
该 descriptor 使用什么 gate type / DPL / IST
Linux 汇编入口随后如何规范化现场
```

## 6. error code 也不是 fault/trap 的判定依据

CPU 是否压入 exception error code 是另一条独立的架构规则。

例如 A15 第一部分已经验证：

```text
#DE   无 hardware error code
#GP   有 hardware error code
```

但不能由“有没有 error code”推出“是 fault 还是 trap”。同样，普通 device IRQ 没有 exception error code；Linux vector stub 主动压入 vector，只是为了复用统一的软件入口布局。

所以至少要把下面四个维度分开：

```text
同步异常 / 异步中断
fault / trap 等异常语义
IDT gate type / DPL / IST
hardware error code 是否存在
```

## 7. 与 A15 已完成三条入口主线的对应关系

现在可以把 A15 的三类入口放在同一张图中：

```text
同步异常
  |
  +-- fault 语义示例：#GP
  |      CPU exception frame
  |      -> hardware error code
  |      -> Linux error_entry
  |      -> pt_regs
  |
  +-- trap 语义示例：single-step #DB
         IDT.IST
         -> CPU 使用 TSS.ist[] 指定的特殊栈
         -> special/paranoid entry

异步中断
  |
  +-- ordinary device IRQ
         CPU interrupt frame
         -> Linux vector stub
         -> pt_regs
         -> hardirq context
         -> optional per-CPU IRQ stack
```

这张图的重点不是给每个 vector 永久贴一个标签，而是建立分析顺序：**先判断事件语义，再分析该 vector 在当前 Linux 5.10 配置下使用的具体入口实现。**

## 8. 阅读现场时如何判断

以后遇到一个 x86-64 内核入口，可以按下面顺序检查：

```text
1. 事件是同步还是异步？
2. 如果是同步异常，当前成因表现为 fault 还是 trap 语义？
3. saved RIP 对应 faulting instruction、next instruction，还是 interrupted execution state？
4. CPU 是否提供 hardware error code？
5. IDT descriptor 的 gate type、DPL 和 IST 是什么？
6. 是否发生 CPL privilege stack switch 或 IST stack switch？
7. Linux 软件入口额外压入了什么？
8. 最终如何形成 pt_regs，并从哪里恢复执行？
```

只要保持这几个维度独立，就不会把“异常类型”“IDT gate”“error-code slot”和“Linux 入口宏”混成一套概念。

## 9. 本节边界

本节只建立 A15 所需的架构语义框架，不重复展开各条 Linux 5.10 入口实现：

- 普通 `#DE/#GP` 的 error-code 与 `pt_regs` 见 A15 第一部分；
- TSS/IST 与 `#DB/NMI/#DF/#MC` 特殊栈见 A15 第二部分；
- 普通 device IRQ、hardirq context 与 IRQ stack 见 A15 第三部分；
- `#PF` 的具体入口、`CR2` 和 page-fault error code 留到 A16。

这样 A15 负责“CPU 如何进入内核并保存现场”，A16 再以 `#PF` 为实例把入口交给内存管理。
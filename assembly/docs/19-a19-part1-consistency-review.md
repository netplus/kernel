# A19 第一部分一致性复核：长模式切换

本文对 A19 第一部分已经存在的教程、Linux 5.10 source-path 和验证实验做一次独立收口检查。目标不是增加新的启动流程，而是确认三份材料使用同一套架构状态模型、Linux 5.10 实现事实和实验验收边界。

对应材料：

- 教程：[`19-long-mode-transition-basics.md`](19-long-mode-transition-basics.md)
- Linux 5.10 源码事实核验：[`../source-paths/19-long-mode-transition-linux-5.10.md`](../source-paths/19-long-mode-transition-linux-5.10.md)
- 实验：[`../labs/19-long-mode-transition/`](../labs/19-long-mode-transition/)
- 实验验收：[`../labs/19-long-mode-transition/expected-analysis.md`](../labs/19-long-mode-transition/expected-analysis.md)

## 1. 本单元解决的问题

A19 第一部分只回答：Linux 5.10 compressed kernel 的 32-bit entry 如何准备并进入可执行 64-bit code 的状态。

完整 boot protocol、解压、KASLR、最终内核页表、`start_kernel()` 和完整 5-level paging 转换不属于本单元。它们应留在 `boot-crash/` 或 `memory/` 主线。

因此本单元的最小闭环是：

```text
32-bit protected-mode execution
        |
        v
64-bit code descriptor available in GDT
        |
        v
CR4.PAE = 1
        |
        v
early paging structures ready -> CR3
        |
        v
IA32_EFER.LME = 1
        |
        v
CR0.PE | CR0.PG = 1
        |
        v
far control transfer reloads CS
        |
        v
CS.L = 1 -> .code64 startup_64
```

教程、source-path 与实验均围绕这条主线，没有把完整启动过程复制到 assembly 领域。

## 2. 架构规则与 Linux 5.10 实现的分层

三份材料已经一致地区分两层事实。

架构层要求的是：

- protected-mode 基础已经成立；
- IA-32e paging 所需的 PAE、paging structures、CR3、LME 和 PG 条件成立；
- 当前 instruction stream 要真正使用 64-bit execution semantics，还必须让 `CS` 指向 long-mode code descriptor；
- 因而 `EFER.LME=1`、`CR0.PG=1` 和“当前已经执行 64-bit code”不能互相替代。

Linux 5.10 compressed `startup_32` 的具体实现则是：

- 在 `arch/x86/boot/compressed/head_64.S` 中准备 GDT；
- 设置 `CR4.PAE`；
- 建立本路径需要的 early page tables 并加载 CR3；
- 通过 `rdmsr/wrmsr` 设置 `IA32_EFER.LME`；
- 预构造 far-return frame；
- 打开 `CR0.PE | CR0.PG`；
- 使用源码实际存在的 `lret`，而不是把它改写成教材常见的 `ljmp`；
- 进入 `.code64 startup_64`。

这一分层满足“架构规则不冒充 Linux 实现、Linux 实现不冒充架构唯一方案”的课程要求。

## 3. `lret` 栈模型复核

实验验收已经把本路径最容易写错的位宽问题固定下来。

`startup_32` 仍处于 32-bit code 语境时，源码以两个 `pushl` 构造 far-return frame：先压入 `__KERNEL_CS`，再压入 `startup_64` target。由于栈向低地址增长，`lret` 前 `%esp` 指向 target，较高地址的下一个 4-byte slot 保存 selector。

因此本路径的静态栈模型应写成：

```text
low address / %esp
+--------------------+
| 32-bit target      |
+--------------------+
| selector slot      |  <- 由 pushl 建立的 4-byte slot
+--------------------+
high address
```

这里必须区分：

```text
stack slot width != selector semantic width
```

selector 装入 `CS` 时仍是 selector 语义，但源码确实用 `pushl` 建立 4-byte stack slot。不能套用 `retq` 或 `iretq` 的 8-byte-per-slot 模型。

## 4. 三个动态时刻的状态边界

实验把动态验证分成三个时刻是合理且必要的。

### 4.1 打开 CR0.PG 之前

此时应已经有 PAE、CR3 和 LME 前提，但当前仍是 32-bit protected-mode instruction stream。不能因为 LME 已设置就宣称 CPU 已经执行 64-bit code。

### 4.2 CR0 write 之后、`lret` 之前

这是本单元最关键的中间状态。IA-32e 的 paging/mode 条件已经激活，但旧 `CS` 仍未被 far transfer 替换。因此“long-mode 条件已经 active”和“当前 instruction stream 已进入 64-bit code segment”仍然是两个不同判断。

### 4.3 `lret` 之后

只有在以下证据同时成立时，才把当前现场验收为 64-bit execution：

```text
CS selector == __KERNEL_CS
该 selector 对应的 descriptor 是 64-bit code descriptor
instruction pointer 已进入 startup_64
CR0.PG、CR4.PAE、EFER.LME 仍满足
```

如果 GDB 不能直接显示 descriptor cache 中的 `CS.L`，应通过 selector、GDT descriptor 和当前 instruction pointer 交叉验证，不应虚构调试器没有提供的字段。

## 5. early page table 的课程边界

A19 第一部分只需要证明在 PG 生效前存在足以维持 transition 连续执行的 mapping，并且 CR3 已经指向相应 paging root。

本单元不应由此推出：

- 已经建立 Linux 最终 kernel page tables；
- 已经建立完整 direct map；
- 已经完成最终 KASLR address layout；
- 已经完成所有 LA57/5-level paging 状态转换。

这些结论超出 assembly 基础单元的验收范围。

## 6. `.code32` / `.code64` 与运行时 mode

教程和实验均正确区分 assembler encoding context 与 CPU runtime state。

`.code32` / `.code64` 告诉 GNU assembler 如何编码后续指令；它们不是 CPU 在运行时读取的 mode switch 指令。因此静态 `objdump` 只能证明构建产物在切换点两侧包含什么机器码，动态 mode 仍需结合 CR0/CR4/EFER、CS/GDT 和 instruction pointer 判断。

## 7. 多入口边界

`startup_32 -> startup_64` 是 Linux 5.10 compressed kernel 自己完成 32-to-64 transition 的具体路径，但 `startup_64` 也允许满足入口约束的 64-bit bootloader 直接进入。

因此本单元不能使用“所有 x86-64 Linux 启动都必经 `startup_32`”这样的表述。现有教程、source-path 和实验都保留了这一边界。

## 8. 实验执行状态

实验已经给出静态源码/反汇编检查和 QEMU/GDB 动态观察方法，但当前维护环境没有可执行 Linux 5.10 checkout、对应构建产物和早期启动 QEMU/GDB 会话。因此：

- 源码关系和预期状态可作为验收基线；
- 具体 CR3、GDT、`startup_32/startup_64` runtime address、`%esp/%rsp` 等数值仍是待实测项；
- 不把 expected analysis 中的状态关系写成已经取得的动态数据。

这不阻塞第一部分教材模型收口，但 README 中应继续保留动态验证尚未执行的说明。

## 9. 第一部分完成判定

经过本次一致性复核，A19 第一部分已经具备：

```text
问题背景与基本原理
Linux 5.10 具体 source-path
CR0/CR3/CR4/EFER/GDT/CS 的状态依赖
startup_32 -> startup_64 的真实实现映射
lret 与 far-return frame 的位宽/栈语义
静态反汇编与动态 QEMU/GDB 实验方案
expected-analysis 验收基线
架构规则、Linux 实现和课程边界说明
```

未发现需要阻止该单元收口的事实冲突。动态 QEMU/GDB 数据仍待具备环境后补充，但不能用虚构结果填充。

下一最小课程单元应依据 `assembly/README.md` 的 A19 剩余大纲继续推进，而不是重复扩展本节：在长模式切换模型已经建立后，下一步应补足阅读 `head_64.S` 所需的“早期页表汇编基础”，重点放在汇编层如何构造 page-table entries、地址/物理地址关系和临时映射用途；完整启动流程与页表子系统机制仍分别留给 `boot-crash/` 和 `memory/`。
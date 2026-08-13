# A15/A16 README 接入状态核验

本页记录一次针对 `assembly/README.md` 与 A15/A16 已有课程材料的一致性核验。它不是新的机制教程，也不替代领域 README；目的是把当前可独立验收的接入缺口固定下来，避免后续继续向 A17 推进时把“内容已完成”误判成“章节已收口”。

## 1. 核验范围

本次按仓库维护规则重新检查：

- 根目录 `AGENTS.md`；
- 根 `README.md`；
- `assembly/README.md`；
- A15 第三部分普通外部中断教程与实验材料；
- A15 fault/trap/interrupt 语义说明与整章复核；
- A16 `#PF` 入口、demand-fault 实验、返回/重试教程与整章复核。

## 2. A15 的实际状态

A15 第一、第二部分已经出现在领域 README 中，但 README 仍保留“第一、第二部分已完成，A15 尚未完成”的旧状态。

仓库实际内容已经超过该状态：

- 第三部分普通外部中断入口正文：`docs/15-external-interrupt-entry-and-irq-stack.md`；
- 第三部分实验：`labs/15-external-interrupt-entry/`，包含 expected analysis；
- 第三部分 Linux 5.10 源码核验：`source-paths/15-external-interrupt-entry-linux-5.10.md`；
- fault/trap/interrupt 独立语义说明：`docs/15-fault-trap-interrupt-semantics.md`；
- 整章一致性复核：`docs/15-a15-completion-review.md`。

因此 A15 的机制内容已经满足当前 assembly 基础课程边界。剩余工作不是继续增加机制内容，而是把这些入口接入 `assembly/README.md`，删除旧的“尚未完成”状态，并明确 kernel-GDB 动态结果仍受环境限制。

## 3. A16 的实际状态

领域 README 当前只有 A16 的章节纲要，没有接入已经完成的材料。仓库实际已经存在：

- 第一部分正文：`docs/16-page-fault-entry-cr2-and-error-code.md`；
- 第一部分 Linux 5.10 源码核验：`source-paths/16-page-fault-entry-linux-5.10.md`；
- 可运行 demand-fault 实验：`labs/16-page-fault-demand/`，包含 expected analysis；
- 第二部分正文：`docs/16-page-fault-retry-and-instruction-restart.md`；
- 第二部分 Linux 5.10 源码核验：`source-paths/16-page-fault-retry-return-linux-5.10.md`；
- 整章一致性复核：`docs/16-a16-completion-review.md`。

A16 的 assembly-side 主线已经完整：

```text
faulting instruction
-> #PF architecture state
-> saved RIP / CR2 / PF error code
-> Linux 5.10 exception entry / pt_regs
-> exc_page_fault()
-> memory-subsystem handoff
-> optional VM_FAULT_RETRY inside handler
-> successful exception return
-> restore faulting RIP
-> execute original instruction again
```

这里必须继续保持两个边界：

1. `VM_FAULT_RETRY` 是 fault handler 内部重试，不等于 CPU 对 faulting instruction 的重新执行；
2. VMA、页表建立、匿名页分配、COW 等主体属于 `memory/`，A16 只讲汇编入口、现场交接与返回。

因此 A16 同样已经达到内容完成标准，剩余工作是领域 README 接入和链接复核。

## 4. 下一次 README 修改的精确目标

下一次对 `assembly/README.md` 的修改应作为一个独立最小课程维护单元完成，不再新增 A15/A16 机制正文。修改应至少做到：

1. 在 A15 中加入第三部分教程、实验、source-path；
2. 加入 fault/trap/interrupt 语义说明和 A15 completion review；
3. 将 A15 状态改为已完成，并说明 kernel-GDB 动态验证的环境限制；
4. 在 A16 中接入两部分正文、两个 source-path、demand-fault 实验和 completion review；
5. 将 A16 标记为已完成；
6. 检查所有相对链接、章节编号和文件名；
7. 只有完成上述接入后，才进入 A17。

## 5. 验收结论

本次核验发现的是一个真实的课程状态一致性问题：**领域 README 落后于仓库实际完成内容**。因此不能把当前进度描述成“A15/A16 尚缺机制内容”，也不能直接开始 A17。

下一最小单元已经唯一化为：更新 `assembly/README.md`，正式收口 A15 与 A16。
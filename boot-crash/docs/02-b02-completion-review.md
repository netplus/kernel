# B02 收章复核：compressed kernel 与早期 64 位环境

本文件对 B02 的正式教程、Linux 5.10 源码核验、实验和 expected analysis 做收章复核。复核目标不是增加新的启动分支，而是确认本章已经形成一致的工作模型，并把尚未取得的证据明确留在对应证据层。

对应材料：

- [正式教程：压缩内核与早期 64 位环境](02-compressed-kernel-and-early-64bit.md)
- [Linux 5.10 源码事实核验](../source-paths/02-compressed-kernel-linux-5.10.md)
- [实验：compressed kernel 的构建、解压与 handoff](../labs/02-compressed-kernel/)
- [实验 expected analysis](../labs/02-compressed-kernel/expected-analysis.md)

## 1. 本章解决的问题

B01 已经说明 boot loader 如何通过 Linux boot protocol 与 `boot_params` 把启动输入交给 kernel。B02 继续回答正式内核开始执行之前的中间阶段：

```text
boot loader / setup
        ↓
compressed kernel
        ↓
选择 formal-kernel output
        ↓
解压 payload
        ↓
按 ELF PT_LOAD 形成装载布局
        ↓
[必要时] relocation
        ↓
跨映像 handoff
        ↓
formal kernel
```

本章的核心结论是：compressed kernel 不是 formal kernel 已经运行后调用的一段普通解压代码，而是一个具有自身入口、栈、早期映射、构建约束和控制流的独立早期执行映像。

## 2. compressed ELF 与 formal ELF 的边界一致

正文、source-path 和实验均明确区分：

```text
arch/x86/boot/compressed/vmlinux   compressed/decompressor ELF
vmlinux                            formal kernel ELF
```

两个映像拥有不同链接上下文。即使二者都出现 `startup_64`，符号值也只能在各自 ELF 内解释，不能通过比较两个地址的数值大小推导启动顺序。

这一边界也是后续 B03 的入口条件：B02 负责解释 compressed stage 怎样产生并进入 formal kernel；B03 再从 formal `arch/x86/kernel/head_64.S` 开始分析正式内核早期入口。

## 3. compressed PIE 与 formal relocation 没有混写

本章统一采用下面的区分：

```text
compressed PIE
    使 decompressor 自身能够从不同合法位置执行

formal-kernel relocation
    在 formal kernel 的实际 placement 改变时修正需要调整的地址
```

Linux 5.10 compressed build 的 `-fPIE`、`-ffreestanding`、`-fno-stack-protector` 和 PIE link 属于 compressed execution environment 的构建属性。

`handle_relocations()` 与压缩输入中的 relocation payload 则受 `CONFIG_X86_NEED_RELOCS` 条件控制。二者服务对象和发生阶段不同，正文、实验和验收基线没有把它们统称为同一种“重定位”。

## 4. CONFIG 条件已经明确分层

B02 涉及的主要条件已经在教程和实验中保持一致：

```text
CONFIG_X86_64
CONFIG_RELOCATABLE
CONFIG_RANDOMIZE_BASE
CONFIG_X86_NEED_RELOCS
```

其中：

- `CONFIG_X86_64` 决定本章采用的 x86-64 路径以及部分 64-bit 特有处理；
- `CONFIG_RELOCATABLE` 影响 formal kernel placement/ELF placement 的地址计算；
- `CONFIG_RANDOMIZE_BASE` 控制 compressed KASLR 代码是否进入相应构建与随机选址路径；
- `CONFIG_X86_NEED_RELOCS` 控制 relocation payload 与有效 relocation 处理。

源码中存在某个条件分支，只能证明该版本支持该路径，不能证明某个具体 `.config` 已启用它。实验已经要求实际构建时记录配置，而不是从源码存在性反推运行路径。

## 5. KASLR 模型保持为“约束内随机”

正文、source-path 与 expected analysis 对 KASLR 使用同一个模型：

```text
memory map / boot_params
→ 排除 compressed image、initrd、command line、boot_params 等占用区
→ 按 image size 与 alignment 形成合法候选
→ 从合法 slots 中随机选择
```

因此本章没有把 KASLR 描述为“生成任意随机物理地址”。`MEM_AVOID_*` 的意义也被放在位置所有权和覆盖风险中解释，而不是只罗列枚举名。

关闭 `CONFIG_RANDOMIZE_BASE` 时，compressed stage 的位置、解压、ELF placement 和 handoff 问题仍然存在，只是不执行随机位置选择。

## 6. `needed_size` 的语义一致

Linux 5.10 `extract_kernel()` 使用的核心关系在各材料中保持一致：

```text
kernel_total_size = VO__end - VO__text
needed_size = max(output_len, kernel_total_size)
```

x86-64 路径还要满足相应最小对齐要求。

本章据此说明：formal kernel 的目标区域不仅要容纳解压得到的文件字节，还必须覆盖完整运行时 footprint。因而 `needed_size` 不能简化成 compressed size，也不能简单等同于 `output_len`。

## 7. `extract_kernel()` 的阶段语义没有被压扁成“解压”

本章统一使用的主线是：

```text
接管 boot_params
→ sanitize_boot_params()
→ 建立 decompressor 所需的早期状态
→ 计算 needed_size
→ choose_random_location()
→ 检查 output / virt_addr
→ __decompress()
→ parse_elf()
→ handle_relocations()
→ return formal entry
```

其中三个后半阶段的职责已经明确区分：

- `__decompress()`：恢复 compressed payload 中的字节内容；
- `parse_elf()`：读取 ELF program headers，并按 `PT_LOAD` 形成 formal kernel 的装载布局；
- `handle_relocations()`：仅在配置要求时修正随实际 placement 变化的地址。

因此“解压算法返回”不能作为“formal kernel 最终布局完成”的同义事件。

## 8. `extract_kernel()` 返回与跨映像 handoff 的边界正确

B02 的硬边界是：

```text
compressed assembly
    call extract_kernel()
        ↓
C ABI return，携带 formal entry
        ↓
compressed assembly 继续执行
        ↓
跨映像 control transfer
        ↓
formal-kernel entry
```

`extract_kernel()` 的 C 返回仍返回 compressed image。真正进入 formal kernel 的动作发生在后续 assembly handoff。

这一点已经同时进入正文、实验和 expected analysis，并且实验明确要求未来使用真实 `objdump` 证明 `call extract_kernel` 返回后仍存在 compressed assembly 指令，再定位最终控制转移。

## 9. 与 assembly 和 memory 的职责边界正确

B02 只解释 compressed stage 为什么需要临时栈、早期页表和能够执行 64-bit decompressor 的 CPU 状态，以及这些状态如何服务于阶段交接。

以下机制没有在本章重新完整展开：

- GDT、CR0/CR3/CR4、EFER、long-mode transition：由 `assembly/` 负责；
- 页表项结构、通用地址翻译和完整页表管理：由 `memory/` 负责。

因此 B02 保持了 boot-crash 的职责：关注“上一阶段交付什么、当前阶段完成什么、下一阶段接收什么”，而不是复制机器执行机制课程。

## 10. 实验与证据等级一致

B02 实验已经形成四层清晰状态：

```text
工具证据
    checker fixture self-test

L1
    真实 Linux 5.10 source/build contract

L2
    实际 compressed/formal ELF、readelf/nm/objdump

L3
    QEMU/GDB 运行时 P0–P3
```

当前已经实际执行 checker fixture self-test：

```text
1 positive + 7 negative fixtures: PASS
complete positive fixture: 10 L1 contract checks
```

该结果只证明 checker 对已知完整/破坏 fixture 的接受与拒绝行为。

当前尚未执行：

```text
真实 Linux v5.10 checkout 上的 verify_source_contract.py
真实 compressed/formal ELF 的 readelf/nm/objdump
QEMU/GDB P0–P3 动态观察
```

这些分别属于真实 L1、L2 和 L3 增强证据。正文和实验均未把未执行项写成实测结果。

## 11. 自动 checker 的范围与限制

当前 `verify_source_contract.py` 自动检查 10 组 L1 source/build contract，包括：

- compressed PIE/freestanding/stack-protector 构建约束；
- compressed PIE link；
- KASLR 与 relocation 的 CONFIG 构建边界；
- compressed assembly 的入口与 `extract_kernel()` 关系；
- `boot_params` / `needed_size` 契约；
- `choose_random_location → __decompress → parse_elf → handle_relocations` 顺序；
- KASLR 对关键启动数据区域的 avoidance。

checker 是减少源码事实回归的辅助工具，不替代上下文阅读，也不证明具体 `.config`、ELF 或运行时地址。

## 12. 收章结论

按根目录 `AGENTS.md` 的章节完成标准，B02 现在能够回答：

- compressed kernel 为什么存在；
- 它为什么是独立执行映像；
- Linux 5.10 的构建和源码入口在哪里；
- `boot_params` 如何继续跨阶段传递；
- KASLR 如何在约束内选择位置；
- 解压、ELF placement 与 relocation 为什么是不同阶段；
- `extract_kernel()` 返回与真正 formal-kernel handoff 有何区别；
- 如何通过 source checker、ELF 工具和 QEMU/GDB 分层验证这些结论；
- 当前哪些结果已经实际执行，哪些仍受环境限制。

因此 B02 的**内容层面与实验设计层面达到收章标准**。真实 Linux 5.10 checkout、L2 构建产物和 L3 动态现场保留为增强证据，不阻止课程主线进入下一章，但未来一旦具备环境，应按实验 README 补齐并保存结果。

下一步应更新 `boot-crash/README.md`，把 B02 标记为已完成并接入本 completion review；完成 README 收口后，再进入 B03 formal `head_64.S` 与早期页表。
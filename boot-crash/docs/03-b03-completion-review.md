# B03 收章复核：formal `head_64.S` 与早期页表

本文用于确认 B03 的正文、Linux 5.10 源码事实核验和实验是否已经形成一致、可验收的课程单元。它不是新的页表教程；完整多级页表机制仍属于 `memory/`，long-mode、GDT 和控制寄存器指令语义仍属于 `assembly/`。

## 1. 收章结论

B03 当前已经能够回答本章的核心问题：**为什么进入 formal kernel 时 CPU 已经处于 64-bit mode、也已有可执行当前代码的页表，Linux 仍必须修正 early page tables、重载 CR3，并显式切换到 kernel virtual-address execution。**

正文、source-path 与实验现在使用同一条 Linux 5.10 主线：

```text
已有 64-bit mode + identity mapping
+ %rsi = boot_params / real_mode_data 物理指针
        ↓
arch/x86/kernel/head_64.S:startup_64
        ↓
verify_cpu
        ↓
arch/x86/kernel/head64.c:__startup_64()
        ↓
计算 load_delta
修正 high-half kernel mapping
建立 switchover identity mapping
更新 phys_base
返回 SME modifier
        ↓
assembly 形成 early_top_pgt 的 CR3 值
        ↓
mov %cr3
        ↓
indirect jump 到 kernel virtual-address execution
        ↓
GDT / initial_stack / early IDT / RFLAGS / ABI 参数
        ↓
lretq → initial_code == x86_64_start_kernel
```

没有把 formal `startup_64` 错写成第一次进入 long mode，也没有把 `__startup_64()` 的返回值错写成 CR3。

## 2. 地址模型一致性

三份材料都区分了以下三个量：

1. kernel 的 link-time high-half virtual address；
2. 由链接布局推导出的默认 physical position；
3. 本次启动实际执行的 formal-kernel physical position。

Linux 5.10 `__startup_64()` 使用：

```text
load_delta = physaddr - (_text - __START_KERNEL_map)
```

描述实际物理装载位置相对链接假定位置的差值。课程没有把 `load_delta` 写成一般虚实地址换算公式，也没有把它等同于 KASLR 随机数。

本章只解释这个差值为什么驱动 formal-entry 页表修正；页表索引、页表项格式和完整地址空间布局不在这里重复展开。

## 3. early page-table 对象的职责一致

正文、source-path 和 expected analysis 对三个关键对象的职责保持一致：

- `early_top_pgt`：BSP formal entry 切换使用的 top-level page table；
- `early_dynamic_pgts`：为 switchover identity mapping 提供临时页表页，Linux 5.10 中 `EARLY_DYNAMIC_PAGE_TABLES == 64`；
- `phys_base`：记录本次 kernel image 的实际物理基址状态。

`__startup_64()` 修正的是启动阶段需要的 kernel mapping，并构造过渡期 identity mapping；课程没有把它描述成“建立最终 Linux 地址空间”或“映射所有 RAM”。

switchover identity PMD 使用 `__PAGE_KERNEL_LARGE_EXEC & ~_PAGE_GLOBAL` 的事实也已经进入 source-path、教程和自动 checker，因此过渡映射与最终长期映射的职责没有混淆。

## 4. `__startup_64()` return 与 CR3 形成一致

这是 B03 最重要的易错边界之一，当前材料已经统一为：

```text
__startup_64() return = sme_get_me_mask()
        ↓
+ (early_top_pgt - __START_KERNEL_map)
        ↓
+ phys_base
        ↓
sev_verify_cbit(...)
        ↓
mov %rax,%cr3
```

因此，`call __startup_64` 刚返回时 `%rax` 的 C 语义是 SME modifier；只有经过后续 assembly 地址形成后，才得到写入 CR3 的值。

实验 P1 也要求断点精确位于 C return 后、相关 `addq` 之前。这样可以防止动态观察时把已经修改过的 `%rax` 仍标成纯 C 返回值。

## 5. CR3 switch 与 RIP address-context switch 一致

正文和实验都把下面两个动作分开：

```text
mov %rax,%cr3
    → 新 translation context 生效

mov $1f,%rax ; jmp *%rax
    → 后续 RIP 进入 formal kernel virtual-address execution
```

课程没有使用“加载 CR3 后 CPU 自动跳到高半区”这样的错误简化。`early_dynamic_pgts` 提供的 switchover identity mapping 正是为了保证这两个动作之间仍有可执行映射。

L3 P2 因而要求至少记录两个时刻：CR3 write 后，以及 indirect jump 后。

## 6. 进入 C 前的机器状态边界一致

B03 没有把“页表切换完成”当成“普通 C 环境已经成立”。virtual-address jump 后仍继续建立：

```text
kernel-space GDT
segment selector cleanup
MSR_GS_BASE
initial_stack → %rsp
early IDT
EFER.SCE / 条件性 NX
CR0 startup state
pushq $0 ; popfq
%rsi → %rdi
far-return frame
```

最终 `initial_code == x86_64_start_kernel`，通过 `lretq` 完成 formal assembly → early C 的交接。

其中 `%rsi` 在入口阶段保存 `boot_params` 的物理指针，直到最后才移动到 SysV AMD64 C ABI 的第一个参数寄存器 `%rdi`。这一点在正文、source-path 和实验中一致。

## 7. BSP/AP 与特殊条件复核

课程没有把 BSP 与 secondary CPU 混成同一入口：

```text
BSP:
startup_64 → __startup_64() → early_top_pgt

secondary CPU:
secondary_startup_64 → __startup_secondary_64() → init_top_pgt
```

两条路径复用后续部分 assembly，但入口前提和 early page-table ownership 不同。

`secondary_startup_64_no_verify` 仅按 Linux 5.10 的 SEV-ES secondary bring-up 特例解释，没有推广成普通 AP 默认路径。

LA57 也保持正确的阶段边界：在相关配置下，5-level paging 已由 decompression stage 检测/启用；formal kernel 的 `check_la57_support()` 是接管并同步该状态，不是第一次决定是否开启 LA57。

SME/SEV 只保留理解 early page-table address/modifier 所需的条件，不扩展成独立安全/虚拟化专题。

## 8. `ident_map.c` 的调用关系已经纠偏

领域 README 最初把 `arch/x86/mm/ident_map.c` 列为 B03 建议源码之一。实际核对 Linux 5.10 后，source-path 已明确：BSP formal entry 的 switchover identity mapping 是直接在 `head64.c::__startup_64()` 中构造的，`ident_map.c` 不属于 `startup_64 → __startup_64()` 的直接主调用链。

当前正文和实验没有为了匹配旧的建议列表而虚构调用关系。收章后更新领域 README 时，应以已经核验的 `head_64.S`、`head64.c` 和相关 page-table definitions 为 B03 主入口，并删除或降级这一误导性建议。

## 9. 实验与证据等级复核

B03 实验现在明确区分四类证据：

```text
工具证据
    checker fixture self-test

L1
    真实 Linux v5.10 checkout 的 source contract

L2
    匹配构建的 vmlinux / nm / readelf / objdump

L3
    QEMU/GDB 的实际 CR3/RIP/RSP/RFLAGS/GDTR/RSI/RDI 现场
```

自动 checker 固定 6 组 L1 source-contract；fixture self-test 已实际执行 8 个 unittest，包含 1 个完整正例和 7 个负例，exit code 0，完整正例返回 6 组 contract。

fixture 只验证 matcher 的 acceptance/rejection 行为，不能冒充真实 Linux checkout 的 L1，更不能替代 L2/L3。当前没有把未执行的 ELF 或动态数值写成实测结果。

## 10. 尚未执行但不阻塞收章的增强证据

当前仍未执行：

- 在真实 Linux v5.10 checkout 上运行 `verify_source_contract.py` 并保存 CLI 记录；
- 对匹配 `.config` 的 formal `vmlinux` 执行 `nm/readelf/objdump`；
- QEMU/GDB P0–P3 的 CR3、RIP、RSP、RFLAGS、GDTR、RSI/RDI 动态记录；
- LA57、SME/SEV 条件路径的实际运行观察。

这些项目会增强证据强度，但不改变已经通过 Linux 5.10 源码核验建立的章节工作模型。当前环境缺少相应 build/runtime，因此保持“未执行”比填入推测值更符合课程验收要求。

## 11. B03 完成判定

B03 当前已经满足基础课程的独立验收要求：

- 已解释 formal entry 为什么仍需要 early page-table fixup；
- 已区分架构/ABI 前提与 Linux 5.10 具体实现；
- 已固定入口寄存器、地址模型、CR3 数据流和控制流；
- 已区分 BSP/AP、LA57、SME/SEV 等条件路径；
- 已建立源码、机器码和运行现场的验证方法；
- 已有自动 source-contract checker 和实际执行通过的正/负 fixture；
- 未执行的增强证据均有明确边界；
- 没有越界重复 `memory/` 或 `assembly/` 的完整机制。

因此 B03 内容层面可以收章。下一最小单元是更新 `boot-crash/README.md`：将 B03 标记为已完成，接入正式教程、source-path、实验和本 completion review，并同步修正 `ident_map.c` 的旧建议入口。完成领域 README 收口后，再进入 B04 `x86_64_start_kernel() → start_kernel()` 的 Linux 5.10 源码事实核验。

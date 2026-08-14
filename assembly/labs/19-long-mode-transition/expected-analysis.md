# A19 实验预期分析：x86-64 长模式切换

本文是 [`README.md`](README.md) 的验收基线，服务于 [`../../docs/19-long-mode-transition-basics.md`](../../docs/19-long-mode-transition-basics.md) 和 [`../../source-paths/19-long-mode-transition-linux-5.10.md`](../../source-paths/19-long-mode-transition-linux-5.10.md)。这里记录的是依据 x86 架构规则与 Linux 5.10 源码得到的**预期关系**，不是本次维护环境中的 QEMU/GDB 实测数据。

## 1. 独立验收目标

本实验只有在下面这条证据链能够闭合时才算通过：

```text
GDT 中已有可用的 64-bit code descriptor
        |
        v
CR4.PAE = 1
        |
        v
有效 early page tables 已建立，CR3 指向 paging root
        |
        v
IA32_EFER.LME = 1
        |
        v
far-return frame 已准备 __KERNEL_CS:startup_64
        |
        v
CR0.PE | CR0.PG = 1
        |
        |  IA-32e 条件已经激活，但旧 CS 尚未被替换
        v
lret reloads CS and instruction pointer
        |
        v
.code64 startup_64
```

任何单个条件都不足以替代整条链。例如，只看到 `EFER.LME=1`、`CR0.PG=1` 或源码中的 `.code64` 都不能独立证明当前 CPU 已经在 64-bit code segment 中执行。

## 2. 三个关键观察时刻

### 2.1 CR0 write 之前

在最后一次打开 `CR0.PG` 的写操作之前，预期至少满足：

```text
CR4.PAE = 1
CR3     = 当前 compressed boot path 已准备的 early paging root
EFER.LME = 1
CR0.PG  = 0（就本次 transition 尚未打开 paging 的路径而言）
CS       = 当前 32-bit protected-mode code segment
```

此时不能把 `%eip` 所在代码称为 64-bit execution。`LME` 的含义是允许后续在 paging 条件满足时激活 long mode，而不是立即改变当前指令的解码模式。

### 2.2 CR0 write 之后、`lret` 之前

这是最重要的中间状态。预期：

```text
CR4.PAE  = 1
EFER.LME = 1
CR0.PG   = 1
CR0.PE   = 1
CR3      = 有效 early paging root
CS       = 旧的 32-bit code segment
```

因此应把这一时刻描述为：IA-32e mode 的必要 paging/mode 条件已经激活，但当前 `CS` 还没有通过 far control transfer 换成 `CS.L=1` 的 64-bit code segment。

这正是为什么“写 CR0”与“开始执行 `.code64 startup_64`”必须作为两个事件分析。

### 2.3 `lret` 之后

单步越过 far return 后，预期同时看到：

```text
instruction pointer = startup_64 的实际 runtime target
CS selector         = __KERNEL_CS
CR4.PAE             = 1
EFER.LME            = 1
CR0.PG              = 1
```

并且 `__KERNEL_CS` 对应的 GDT code descriptor 必须具有 long-mode code 属性。若调试器不能直接显示 descriptor cache 中的 `CS.L`，可以用下面三项交叉证明，而不能虚构一个调试器未提供的 `CS.L` 值：

1. 当前 selector 是 `__KERNEL_CS`；
2. GDT 中该 selector 对应 64-bit code descriptor；
3. instruction pointer 已进入构建产物中的 `.code64 startup_64`。

## 3. far-return frame 的栈语义

Linux 5.10 compressed `startup_32` 在仍按 32-bit code 执行时准备：

```asm
pushl $__KERNEL_CS
pushl %eax              # startup_64 target
...
lret
```

因此在 `lret` 执行前，从当前 `%esp` 向高地址观察，逻辑顺序应为：

```text
低地址 / %esp
+----------------------+  startup_64 target offset（32-bit operand）
| target               |
+----------------------+  __KERNEL_CS 由 pushl 建立的 32-bit stack slot
| __KERNEL_CS          |
+----------------------+
高地址
```

这里必须区分“栈槽宽度”和“selector 的有效语义宽度”：源码使用 `pushl` 建立两个 32-bit 槽；far return 从第二个槽取得 code-segment selector 时，真正作为 segment selector 使用的是其 selector 值，而不是把这个场景套成 64-bit `retq`/`iretq` 的 8-byte 栈布局。

验收时应以当前构建产物的 `lret` 编码、32-bit operand-size 语义和单步后的 `%esp` 变化共同确认消费宽度；不要仅根据十六进制内存显示猜测槽宽。

## 4. GDT 与 CS 的验收关系

`lgdt` 的验收结论只能是：CPU 的 GDTR 已经指向包含后续 code descriptor 的表。它本身不会替换当前 `CS`。

正确的因果关系是：

```text
prepare GDT
    -> lgdt
    -> prepare selector __KERNEL_CS
    -> activate IA-32e paging conditions
    -> far control transfer
    -> reload CS from descriptor
    -> 64-bit execution
```

因此若在 `lgdt` 后、`lret` 前观察到当前 `CS` 仍是旧 selector，这是预期现象，不是失败。

## 5. CR3 与 early page table 的验收边界

实验只需要证明：在 `CR0.PG` 被置位前，CR3 已经指向当前 transition 可用的 paging-structure root，并且映射足以让 CPU 在切换点和 `startup_64` 目标处继续取指。

不能从这个实验推出：

- 这就是 Linux 最终内核页表；
- 这里已经建立完整 direct map；
- 这里已经完成 KASLR 后最终虚拟地址布局；
- 这里已经完成 5-level paging 的最终配置。

这些属于后续 boot/memory 主线。

## 6. `.code32` / `.code64` 的正确解释

`.code32` 与 `.code64` 指示 GNU assembler 按相应编码上下文生成机器码。它们不是 CPU 运行时读取的 mode metadata。

所以静态反汇编能够回答：

```text
切换点两侧实际生成了哪些机器指令？
```

而动态 mode 判断必须回答：

```text
CR0/CR4/EFER 当前是什么状态？
当前 CS selector/descriptor 是什么？
当前 instruction pointer 落在哪一段代码？
```

只有两类证据一致时，才能把 `startup_64` 现场判定为 64-bit execution。

## 7. 不能作为硬编码验收值的内容

以下值依赖当前构建、装载和配置，expected analysis 不给固定常量：

```text
startup_32 runtime address
startup_64 runtime address
CR3 的具体物理地址
GDT runtime address
当前 %esp/%rsp 数值
compressed image relocation delta
```

执行实验时必须从当前 `vmlinux`、实际装载地址和 QEMU/GDB 现场取得这些值。

## 8. 失败判定

出现以下任一情况，都不能宣称完成模式切换验证：

1. 只检查源码，没有检查当前构建产物；
2. 只看到 `.code64` 就断言 CPU 已处于 64-bit mode；
3. 只看到 `EFER.LME=1` 或 `CR0.PG=1` 就结束验证；
4. 没有确认 CR3 对应的 early mapping 能覆盖切换后的取指地址；
5. 没有确认 far transfer 实际装载 `__KERNEL_CS`；
6. 把 Linux 5.10 此路径实际使用的 `lret` 写成源码中不存在的 `ljmp`；
7. 把 compressed `startup_32` 路径描述成所有 x86-64 bootloader 唯一允许的入口；
8. 把预期寄存器值或地址写成未实际取得的 QEMU/GDB 结果。

## 9. 本实验与 A19 第一部分的完成边界

A19 第一部分要求建立的是“进入 long-mode 64-bit code 所需状态之间的依赖关系”，而不是完整 Linux boot sequence。完成本实验后，读者应能够解释：

```text
为什么要先有 GDT 和 early page tables；
为什么 CR4.PAE、CR3、EFER.LME、CR0.PG 缺一不可；
为什么 LME=1 不等于当前已经执行 64-bit instructions；
为什么 Linux 5.10 这里还需要 lret reload CS；
为什么 startup_64 也可能由已经满足 64-bit 入口条件的 bootloader 直接进入。
```

本次维护环境没有可执行 Linux 5.10 checkout/QEMU guest，因此上述动态状态仍是待实测验收标准，不是运行记录。
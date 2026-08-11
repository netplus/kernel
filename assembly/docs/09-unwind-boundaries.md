# 第 9 课（第五部分）：多层调用链与 CFI 展开边界

前一部分已经建立了 CFA、CIE、FDE 和 `.cfi_*` 的基本模型，但只证明“元数据存在且与栈变化对应”。真正需要回答的下一步是：**当调用链里某一层的 unwind 规则正确、缺失或错误时，实际 backtrace 会发生什么？**

这也是理解后续内核栈展开之前必须建立的边界：函数能正常 `ret`，与调试器能否从当前 frame 恢复 caller，是两件不同的事。

## 1. 两条彼此独立的正确性

对一个普通函数，至少有两类状态：

```text
机器执行状态：RIP、RSP、寄存器、栈内存、返回地址
展开描述状态：当前 PC 对应的 CFA 与 caller 寄存器恢复规则
```

机器指令决定程序是否能继续运行：

```asm
subq $8, %rsp
call target
addq $8, %rsp
ret
```

而 `.cfi_*` 描述的是 unwinder 如何解释这一段执行状态。CPU 执行 `ret` 时不会读取 `.eh_frame`。

因此可能出现：

```text
机器状态正确 + CFI 正确    程序正常，标准 unwind 也可继续
机器状态正确 + CFI 缺失    程序正常，但元数据展开可能在此失去依据
机器状态正确 + CFI 错误    程序正常，但 unwinder 可能得到错误 caller 状态
```

本节实验专门把机器指令保持一致，只改变 CFI。

## 2. 最小调用链

实验建立：

```text
main
  -> c_top
      -> c_mid
          -> assembly frame
              -> capture_trace
```

其中 assembly frame 有三种版本：

```text
good_frame       正确 CFI
missing_frame    无该函数自己的 FDE
wrong_frame      有 FDE，但 CFA offset 故意写错
```

外围 C 函数使用：

```text
-fno-omit-frame-pointer
-fno-optimize-sibling-calls
```

目的是尽量保持外围调用层次稳定，把变量集中到手写汇编 frame。

## 3. 三个函数的真实机器栈完全相同

三个函数核心都是：

```asm
subq $8, %rsp
leaq label(%rip), %rdi
call capture_trace@PLT
addq $8, %rsp
ret
```

设函数入口时：

```text
RSP = S
caller CFA = S + 8
```

执行：

```asm
subq $8, %rsp
```

后：

```text
RSP = S - 8
caller CFA 仍应是 S + 8
因此 CFA = RSP + 16
```

同时这个 `subq $8` 使调用 `capture_trace` 之前的 `%rsp` 回到 16 字节对齐边界。

`subq` 会更新算术标志位；`call` 改变 `%rsp` 和 `%rip`；`addq` 也会更新算术标志位；`ret` 从真实栈顶取回返回地址。CFI 对这些 CPU 动作没有控制权。

## 4. 正确 CFI：unwinder 有连续的恢复规则

`good_frame` 写成：

```asm
.cfi_startproc
subq $8, %rsp
.cfi_def_cfa_offset 16
...
addq $8, %rsp
.cfi_def_cfa_offset 8
ret
.cfi_endproc
```

关键点是：执行 `subq $8,%rsp` 后，CFA offset 从入口默认的 8 更新为 16。

实验中 `readelf --debug-dump=frames` 确认该函数地址范围存在 FDE，并且规则变化与机器指令一致。运行 `backtrace()` 时，展开可以跨过 `good_frame`，继续恢复 `c_mid`、`c_top`、`main` 等 caller。

当前验证得到 8 层调用栈。

## 5. CFI 缺失：控制流正常，但元数据链在这里断开

`missing_frame` 不使用：

```asm
.cfi_startproc
.cfi_endproc
```

也没有为该函数生成单独 FDE。

机器执行仍完全正确，因此：

```text
capture_trace 返回
missing_frame 执行 addq
ret 回到 c_mid
程序最后 exit 0
```

但 `backtrace()` 从 `capture_trace` 向上展开到 `missing_frame` 后，在当前环境没有可继续使用的该 frame 恢复规则，实际只返回 2 层。

这里必须注意：**“当前 backtrace 在这里停止”不是 x86-64 ISA 规则。** 不同 unwinder 可以实现额外 fallback，例如利用 frame pointer 或启发式策略。因此本节结论应表述为：缺失 CFI 时，不能再假定基于该元数据的标准展开可以可靠跨过该 frame。

## 6. CFI 错误：有元数据不等于元数据可信

`wrong_frame` 故意写成：

```asm
subq $8, %rsp
.cfi_def_cfa_offset 8
```

这是错误的。因为真实 `%rsp` 已从 `S` 变为 `S-8`，若 caller CFA 要保持 `S+8`，此时必须是：

```text
CFA = RSP + 16
```

错误规则却声称：

```text
CFA = RSP + 8 = S
```

于是基于默认返回地址规则：

```text
return RIP = [CFA - 8]
```

unwinder 会从错误位置推导 caller 的返回状态。

当前实验里 `wrong_frame` 也只展开出 2 层，但这个具体帧数不是 ABI 保证。更重要的结论是：**错误 CFI 会主动向 unwinder 提供错误恢复信息，因此不能把“有 FDE”理解成“可正确展开”。**

## 7. 用 `nm` 与 FDE PC 范围做事实核对

判断某个函数究竟是“没有 FDE”还是“FDE 内容错误”，不能只看运行时 backtrace。

实验同时执行：

```bash
nm -n unwind-demo
readelf --debug-dump=frames unwind-demo
```

本次实际符号顺序包括：

```text
capture_trace
good_frame
missing_frame
wrong_frame
```

将符号地址范围和 FDE 的 `pc=start..end` 对照后确认：

```text
good_frame     有 FDE，CFA offset 变化正确
missing_frame  地址范围没有对应 FDE
wrong_frame    有 FDE，但 CFA offset 明确错误
```

这一步很重要，因为“backtrace 停止”本身不能告诉我们根因究竟是元数据缺失、错误，还是 unwinder 自身的策略。

## 8. 为什么不能把 glibc `backtrace()` 当成所有 unwinder 的统一行为

本实验用 glibc 环境的 `backtrace()` 做实际验证。它给出了一个非常直观的结果，但课程结论必须保持层次清晰：

```text
SysV AMD64 ABI / DWARF CFI    定义调用约定和恢复信息的语义基础
ELF .eh_frame                 保存编译/汇编产生的 unwind 元数据
具体 unwinder                决定怎样消费这些规则、是否实现 fallback
```

所以不能写成：

```text
没有 CFI 就绝对不可能 backtrace
```

也不能写成：

```text
有错误 CFI 一定只会丢一层栈
```

更准确的是：标准、可靠的栈展开需要有与真实机器状态一致的恢复规则；其他 fallback 是否存在，属于具体工具与运行环境行为。

## 9. 与 frame pointer 的关系

传统 `%rbp` 链可以提供另一条恢复线索：

```text
[RBP]   -> previous RBP
[RBP+8] -> return address
```

但本实验的三个手写 frame 都不建立 `%rbp` frame pointer，因此可以更清楚地观察 CFI 对展开连续性的作用。

外围 C 函数保留 `%rbp`，并不自动修复中间一个没有可用 unwind 规则的无 `%rbp` frame。要到达外围 frame，unwinder 首先必须知道怎样跨过当前这一层。

## 10. 这与 Linux 5.10 内核 unwind 还不是同一件事

本节仍是**用户态 x86-64 / ELF / DWARF CFI 基础课程**。

不能直接推出：

```text
Linux 5.10 内核栈展开 = glibc backtrace + .eh_frame
```

Linux 内核在不同配置和架构下有自己的 unwind 机制。后续进入内核入口与栈展开时，需要单独核对 Linux 5.10 x86-64 的 Kconfig、编译选项、ORC/frame-pointer 等实现，不能把本节用户态实验直接套用到内核。

## 11. 实验验证结果

实验入口：[`../labs/09-unwind-boundaries/`](../labs/09-unwind-boundaries/)

本次实际环境：

```text
GCC 14.2.0
GNU binutils 2.44
x86-64 glibc
```

实际执行结果：

```text
good_frame      backtrace 8 frames，exit 0
missing_frame   backtrace 2 frames，exit 0
wrong_frame     backtrace 2 frames，exit 0

AT&T objdump                  已检查
Intel objdump                 已检查
readelf -S                    已确认 .eh_frame/.eh_frame_hdr
readelf --debug-dump=frames   已核对三个函数的 FDE 边界
nm                            已核对函数地址顺序
GDB                           当前环境未安装，未执行 bt
```

## 12. 本节完成后应能回答

1. 为什么 CFI 错误不会妨碍 CPU 正常执行 `ret`？
2. `subq $8,%rsp` 后为什么正确 CFA 是 `%rsp+16`？
3. 怎样区分“函数没有 FDE”和“函数 FDE 内容错误”？
4. 为什么有 `.eh_frame` 不等于调用栈一定能正确展开？
5. 为什么外围函数有 `%rbp` frame 也不能自动跨过一个无法恢复的中间 frame？
6. 为什么不能把当前 glibc `backtrace()` 的具体行为扩大成所有 unwinder 的规则？
7. 为什么本节结论不能直接等同于 Linux 5.10 内核的栈展开机制？

下一步对 A09 做整章复核：检查 stack frame、spill/reload、leaf/frame-pointer omission、DWARF CFI 与本节 unwind boundary 的术语和链接是否一致；通过后再决定 A09 是否达到完成标准。

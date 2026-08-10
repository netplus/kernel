# 第 8 课（第二部分）：caller-saved 与 callee-saved 寄存器

A08 第一部分解决了“参数和返回值放在哪里”。本节继续回答另一个函数边界问题：**一次函数调用前后，哪些寄存器值可以被破坏，哪些值必须保持不变。**

这仍然属于 System V AMD64 ABI，而不是 `call`/`ret` 指令本身的语义。

## 1. 为什么必须区分两类寄存器

假设调用者正在计算：

```text
x 保存在某个寄存器
→ 调用 helper()
→ 返回后继续使用 x
```

如果 ABI 不规定寄存器保存责任，调用者就无法知道 `helper()` 返回后 `x` 是否还存在。

因此调用约定把责任分成两类：

```text
caller-saved：调用者若需要跨 call 保留值，必须自己先保存
callee-saved：被调函数若要修改，必须在返回前恢复原值
```

“saved”描述的是**跨函数调用边界的值保持责任**，不是说某类寄存器永远不能被修改。

## 2. System V AMD64 的通用寄存器保存规则

对本课程当前使用的经典 16 个 x86-64 通用寄存器，可以先建立下面的工作模型。

### callee-saved

```text
RBX
RBP
R12
R13
R14
R15
```

如果被调函数使用这些寄存器并改变其值，就必须在返回前恢复调用者原来的值。

`RSP` 也必须在正常函数返回边界恢复到调用者期望的位置，但它是栈指针，通常不把它和普通“保存一个业务值”的寄存器混为一谈。

### caller-saved

```text
RAX
RCX
RDX
RSI
RDI
R8
R9
R10
R11
```

被调函数可以覆盖这些寄存器而不恢复进入函数时的值。如果 caller 在 `call` 之后仍然需要其中某个旧值，就必须在调用前保存它，或者让编译器把该值放到别处。

其中 `%rax` 还承担普通整数返回值寄存器的角色，所以函数返回后它通常本来就会包含新值。

## 3. “caller-saved”不等于“每次调用前都要 push”

最容易产生的误解是：

```text
caller-saved = caller 每次都 push
```

这不正确。

真实编译器会根据活跃变量决定是否保存：

```text
如果 call 之后不再需要旧值
→ 不需要保存

如果旧值需要跨 call 存活
→ 可以放到 callee-saved 寄存器
→ 可以 spill 到栈
→ 可以重新计算
→ 也可以使用其他优化策略
```

因此 caller-saved 是**允许被 callee 破坏**，不是“必须机械保存”。

## 4. “callee-saved”也不等于“callee 一进入就全部 push”

同理，函数只需要保存自己实际修改的 callee-saved 寄存器。

例如一个函数只使用 `%rbx` 和 `%r12`：

```asm
pushq %rbx
pushq %r12

# 修改并使用 RBX、R12

popq %r12
popq %rbx
ret
```

没有使用 `%r13/%r14/%r15` 时，就没有理由为它们额外制造栈流量。

保存与恢复必须成对，并且恢复的是**进入当前函数时 caller 看到的值**。

## 5. 为什么要由不同一方承担保存责任

如果所有寄存器都由 callee 保存，每个很小的函数也可能保存大量实际根本没被 caller 使用的值。

如果所有寄存器都由 caller 保存，那么每个调用点又可能承担很重的保存成本。

ABI 选择混合策略：

```text
一组 scratch / volatile 寄存器
→ 适合短期计算和参数传递

一组 preserved / non-volatile 寄存器
→ 适合保存需要跨调用继续存活的值
```

编译器的寄存器分配器可以据此权衡变量生命周期和保存成本。

## 6. 本节实验为什么使用两层手写汇编

实验入口是：

```text
main()                 C
  ↓
run_preservation_probe 汇编 caller
  ↓
clobber_probe          汇编 callee
```

`run_preservation_probe` 先给：

```text
RBX/RBP/R12-R15
```

写入固定哨兵值，同时给 `%r10/%r11` 写入另一组哨兵值。

随后调用 `clobber_probe`。

`clobber_probe` 做两类不同操作：

1. 暂时修改 `%rbx/%r12`，但先保存、返回前恢复；
2. 直接改写 `%r10/%r11`，不恢复。

返回后外层汇编把所有观察值写入全局变量，由 C 程序检查。

这个实验直接验证真实 ABI 边界，而不是依赖“某次 GCC 恰好生成了什么”。

## 7. 一个容易遗漏的问题：外层汇编自己也是 callee

`run_preservation_probe` 是由 C 的 `main()` 调用的，因此它自己也必须遵守 ABI。

它不能为了实验方便直接破坏 `main()` 的 `%rbx/%rbp/%r12-%r15`。

所以入口第一件事是保存：

```asm
pushq %rbx
pushq %rbp
pushq %r12
pushq %r13
pushq %r14
pushq %r15
```

完成内部实验并记录观察结果后，再反向恢复：

```asm
popq %r15
popq %r14
popq %r13
popq %r12
popq %rbp
popq %rbx
ret
```

这正好体现了 callee-saved 的责任是逐层成立的。

## 8. 保存寄存器会立即影响 RSP

六次 `pushq` 共占用 48 字节。

在 System V AMD64 普通函数入口，`call` 已经压入 8 字节返回地址，因此函数入口通常满足：

```text
RSP mod 16 = 8
```

六次 push 后：

```text
48 mod 16 = 0
```

所以 `%rsp` 仍然是 `8 mod 16`，这时不能直接再发起一个满足 ABI 的普通 `call`。

实验因此额外：

```asm
subq $8, %rsp
call clobber_probe
addq $8, %rsp
```

使调用点执行 `call` 之前 `%rsp mod 16 = 0`，`call` 再压入返回地址后，被调函数入口恢复为 `%rsp mod 16 = 8`。

这说明**寄存器保存规则和栈对齐规则并不是彼此独立的**。A08 后续会专门展开 16 字节栈对齐。

## 9. 实验中 callee-saved 的实际变化

进入 `clobber_probe` 时，外层已经设置：

```text
RBX = 0x1111111111111111
R12 = 0x3333333333333333
```

内层先保存，然后故意改成：

```text
RBX = 0xdead000000000001
R12 = 0xdead000000000002
```

最后通过 `pop` 恢复。

所以回到 caller 后观察到的仍然是：

```text
RBX = 0x1111111111111111
R12 = 0x3333333333333333
```

这不是因为硬件自动保护了它们，而是因为**callee 按 ABI 主动恢复**。

## 10. caller-saved 的实际变化

外层调用前设置：

```text
R10 = 0xa0a0a0a0a0a0a0a0
R11 = 0xb0b0b0b0b0b0b0b0
```

内层直接改成：

```text
R10 = 0xaaaaaaaaaaaaaaaa
R11 = 0xbbbbbbbbbbbbbbbb
```

并直接 `ret`。

因此调用返回后，caller 看到的是新值。

这完全符合 ABI：callee 对 `%r10/%r11` 没有恢复义务。

如果 caller 真正需要旧值，就必须在 `call` 之前安排保存。

## 11. RBP 为什么是 callee-saved，但又经常叫 frame pointer

`%rbp` 的 ABI 保存属性和它是否被用作 frame pointer 是两件事。

在传统函数序言中常见：

```asm
pushq %rbp
movq %rsp, %rbp
```

这里保存旧 `%rbp` 同时建立新栈帧。

但优化编译时可以省略 frame pointer，把 `%rbp` 当普通 callee-saved 通用寄存器使用。

因此：

```text
callee-saved 属性：ABI 规则
是否作为 frame pointer：具体代码生成选择
```

A09 会继续分析 frame pointer omission 和栈展开。

## 12. RFLAGS 不属于这里的“通用寄存器保存表”

不要推导出“函数返回后条件码也必须保持”。

System V AMD64 psABI 要求方向标志 DF 在函数入口和返回时为 clear；其他普通用户态条件标志不承担类似通用 callee-saved 保证。

因此 caller 不能跨普通函数调用依赖先前 `cmp` 产生的 `ZF/CF/SF/OF` 状态仍然存在。

## 13. 与 Linux kernel 5.10 的关系

本节主体是用户态 System V AMD64 ABI，不是系统调用 ABI，也不是中断/异常入口保存现场的规则。

不过 Linux x86-64 内核的 C/汇编边界同样需要理解 C ABI 中的 callee-preserved 与 callee-clobbered 概念。后续 A17 分析 `__switch_to_asm` 时，会再次看到 callee-saved 寄存器为何与上下文切换汇编直接相关。

要特别区分：

```text
普通 C 函数调用的 ABI 保存责任
≠ syscall 入口保存 pt_regs
≠ 异常/中断入口保存现场
≠ 任务切换保存 CPU 上下文
```

这些机制可能保存相似寄存器，但目的、入口条件和恢复时机不同。

## 14. 本次实际验证

配套实验：

[`../labs/08-register-preservation/`](../labs/08-register-preservation/)

本次环境：

```text
GCC 14.2.0
GNU assembler 2.44
```

已经实际验证：

```text
-O0 构建和运行       通过
-O2 构建和运行       通过
RBX/RBP/R12-R15      调用后保持哨兵值
R10/R11              调用后被 callee 改写
objdump AT&T         已检查
objdump Intel        已检查
nm                   已检查
GDB                  当前环境未安装，未执行
```

规范依据：x86-64 psABI 的 Register Usage 表明确把 `%rbx/%rbp/%r12-%r15` 标为 callee-saved，并把 `%rax/%rcx/%rdx/%rsi/%rdi/%r8-%r11` 标为非 callee-saved。

## 15. 本节完成后应能回答

1. caller-saved 和 callee-saved 分别由谁承担保存责任？
2. 为什么 caller-saved 不意味着每次调用前都要 `push`？
3. 为什么 callee-saved 不意味着函数入口要保存全部六个寄存器？
4. `%rbx/%rbp/%r12-%r15` 为什么可以承载跨调用存活的值？
5. `%r10/%r11` 为什么允许被任意普通 callee 改写？
6. 为什么手写汇编函数自己也必须遵守同一 ABI？
7. 保存寄存器为什么会影响后续 `call` 的栈对齐？
8. 普通函数 ABI 保存规则为什么不能等同于 syscall、异常入口或上下文切换的现场保存？

下一部分继续学习**栈上传递的参数**，回答 INTEGER 参数寄存器耗尽以后参数如何出现在 caller/callee 的栈边界。
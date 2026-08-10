# 第 7 课（第四部分）：返回地址损坏的基本后果

前三部分已经建立了正常函数调用的模型：`call` 保存返回地址，`ret` 从当前栈顶取得返回目标。本节只研究一个边界问题：**如果栈顶保存的返回地址不再是原来的值，普通 near `ret` 会发生什么。**

本节的目标是理解控制流和栈状态，不讨论缓冲区溢出利用、ROP、绕过防护或任意代码执行技巧。配套实验不会接收外部输入，也不会构造越界写；它直接在一段可审计的手写汇编中替换自己的返回地址，用来观察 CPU 的基本行为。

## 1. 为什么返回地址是控制流状态

正常调用：

```asm
    call worker
after_call:
    ...

worker:
    ...
    ret
```

执行 `call worker` 时，处理器除了跳转到 `worker`，还会保存下一条指令 `after_call` 的地址。

在本课程的 x86-64 near call 模型中，可以简化为：

```text
RSP = RSP - 8
[RSP] = after_call
RIP = worker
```

随后 `ret` 的关键动作是从当前栈顶取得返回目标：

```text
new_RIP = [RSP]
RSP = RSP + 8
RIP = new_RIP
```

因此，栈顶的 8 字节不仅是普通数据，它还决定本次 `ret` 的下一条控制流目标。

这就是为什么分析调用栈时要同时跟踪：

```text
RSP
[RSP] 中保存的值
该值原本对应哪一个 continuation
ret 执行后 RIP 应落到哪里
```

## 2. `ret` 不会重新推导“正确调用者”

一个常见误解是：

> CPU 是否知道当前函数是谁调用的，所以即使栈里的返回地址坏了，也能自动回到正确调用者？

普通 near `ret` 并不会按函数符号、调试信息或 C 语言调用关系重新寻找调用者。

从程序员可见的执行模型看，`ret` 使用当前栈顶保存的返回信息作为控制流输入。Intel 对 near `RET` 的说明同样把它归类为返回控制转移；Intel 对返回预测的资料也明确说明，硬件 Return Stack Buffer 只是预测 `RET` 目标，架构执行仍必须按照真实控制流状态完成并最终校正。

因此需要区分：

```text
架构状态中的真实返回地址
≠
微架构用于预测的 RSB 条目
```

本节只讨论前者。

## 3. 如果返回地址被替换

假设 `call` 原本保存：

```text
[RSP] = after_call
```

随后某段代码把它改成：

```text
[RSP] = redirected_target
```

那么 `ret` 不会再回到 `after_call`，而会尝试把 `redirected_target` 作为新的控制流目标。

如果这个地址是当前进程中有效、允许取指的代码地址，CPU 可以从那里继续执行。

如果目标地址无效、没有映射、不可执行或违反其他架构检查，后续会产生相应异常。具体故障类型取决于目标值和当前页表、权限等条件。本节不把所有异常路径混在一起，重点只保留一个结论：

> `ret` 的行为依赖实际保存在返回栈槽中的值，而不是源代码中“本来应该返回到哪里”。

## 4. 受控实验为什么不使用非法地址

最直接的错误实验是把返回地址改成一个无效值，然后观察程序崩溃。

这种实验只能说明“程序出错了”，却不容易精确分离：

```text
ret 取返回地址
控制流改变
目标地址合法性检查
页表映射
NX/执行权限
信号处理
```

因此本课程采用更干净的验证方法：把返回地址替换为**当前静态程序中一个已知、合法的标签地址**。

这样可以直接验证：

```text
原返回地址被保存
→ 栈顶被替换
→ ret 消耗新的栈顶值
→ RIP 到达 redirected_target
→ redirected_target 设置观察标志
→ 再回到原 continuation
```

没有外部输入，也没有越界访问。

## 5. 实验代码的关键路径

实验核心函数：

```asm
corrupt_return_address:
    movq (%rsp), %r13
    leaq redirected_target(%rip), %rax
    movq %rax, (%rsp)

before_corrupted_ret:
    ret
```

进入函数时：

```text
[RSP] = after_corrupt_call
```

第一条指令：

```asm
movq (%rsp), %r13
```

只是把原返回地址保存到 `R13`，便于实验稍后回到正常 continuation。

接着：

```asm
leaq redirected_target(%rip), %rax
movq %rax, (%rsp)
```

把当前栈顶改为：

```text
[RSP] = redirected_target
```

此时 `RSP` 本身没有改变，改变的是 `RSP` 指向的 8 字节内容。

随后：

```asm
ret
```

处理器读取新的栈顶值，因此控制流到达：

```asm
redirected_target:
    movq $1, %r12
    jmp *%r13
```

这里把 `R12` 设为 1，证明替代路径确实执行过，然后使用普通间接 `jmp` 回到原来的 `after_corrupt_call`。

## 6. 为什么替代目标使用 `jmp` 返回原 continuation

`ret` 已经把被替换的栈顶项弹出，所以到达 `redirected_target` 时：

```text
RSP 已经恢复到调用前的值
```

原来的返回地址已经保存在 `R13`，但不再位于栈顶。

此时实验使用：

```asm
jmp *%r13
```

而不是再执行一个 `ret`。

原因是当前栈顶已经不是“这次函数调用的返回地址”。如果无条件再 `ret`，会把调用者栈中的下一项误当成新的返回地址，反而混淆实验。

因此这段 `jmp` 只用于把实验控制流安全地接回原 continuation，并清楚展示：

```text
ret 会消耗一个栈项
jmp 不会按 call/ret 规则修改 RSP
```

## 7. `RSP` 如何变化

设 `_start` 在执行 `call corrupt_return_address` 之前：

```text
RSP = S
```

执行 `call` 后：

```text
RSP = S - 8
[RSP] = after_corrupt_call
```

替换返回地址期间：

```text
RSP = S - 8
[RSP] = redirected_target
```

执行 `ret` 后：

```text
RSP = S
RIP = redirected_target
```

随后：

```asm
jmp *%r13
```

不会改变 `RSP`，所以进入 `after_corrupt_call` 时仍然有：

```text
RSP = S
```

实验会显式比较调用前保存的 `RSP` 与返回后的 `RSP`，两者必须相等。

## 8. `RFLAGS` 在这里不是返回目标来源

本节容易把控制流变化与条件跳转混淆。

`ret` 的返回目标不是根据 `ZF/CF/SF/OF` 选择的。实验中：

```text
mov/lea
```

用于搬运地址，随后 `ret` 根据栈中返回值改变控制流。

后面的 `cmp/jne` 只是测试实验结果：

```text
RSP 是否恢复
R12 是否证明 redirected_target 执行过
```

因此应分开分析：

```text
ret：由返回栈槽决定目标
jcc：由 RFLAGS 决定是否跳转
```

## 9. 与真实错误的关系

真实软件中，返回地址可能因为多种 bug 或状态破坏而变得不正确。例如错误的栈指针调整、错误地覆盖栈内存、错误的手写汇编等。

本课程在这里停留在最基础的故障模型：

```text
正确返回地址被改变
→ ret 使用改变后的值
→ 控制流与原设计不一致
```

后续课程在分析栈帧、异常入口和上下文切换时，会继续强调“谁拥有当前栈、RSP 指向什么、哪些栈槽必须保持完整”。

安全利用、攻击链和绕过机制不属于本基础课程范围。

## 10. 实验

配套实验：

[`../labs/07-damaged-return-address/`](../labs/07-damaged-return-address/)

固定实验预期：

```text
exit status=41
```

退出状态只用于自动校验。真正要确认的是：

```text
call 前 RSP
call 后 [RSP] 的原返回地址
overwrite 后 [RSP] 的新地址
ret 后到达 redirected_target
最终到 after_corrupt_call 时 RSP 恢复
```

## 11. 本节完成后应能回答

1. 为什么返回地址属于控制流状态，而不只是普通栈数据？
2. 普通 near `ret` 为什么不会自动推导源代码中的“正确调用者”？
3. 只修改 `[RSP]` 而不修改 `RSP`，为什么仍然能改变 `ret` 的目标？
4. 本实验执行 `ret` 后为什么 `RSP` 已恢复到调用前值？
5. 为什么替代目标使用 `jmp *%r13` 而不是再次 `ret`？
6. `ret` 的目标选择与 `RFLAGS` 有什么区别？
7. 为什么本实验使用合法固定标签比直接制造非法地址崩溃更适合学习基本机制？

至此，A07 大纲中的 direct call、indirect call、函数指针、递归和返回地址损坏基本后果均已覆盖。下一章进入 A08：System V AMD64 ABI。
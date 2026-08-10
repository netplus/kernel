# Lab 07-4：返回地址被替换后的 `ret`

## 1. 实验要回答什么

本实验只验证一个受控的机器级问题：

> 如果 ordinary near `ret` 使用的栈顶返回地址被替换，CPU 会不会仍然自动回到源代码中原本的调用者 continuation？

需要验证：

1. `call` 进入函数后，`[RSP]` 保存原 continuation `after_corrupt_call`；
2. 只修改 `[RSP]` 的 8 字节内容而不修改 `RSP`，就可以改变随后 `ret` 读取的目标；
3. `ret` 到达替代标签后，`RSP` 已经恢复 8 字节；
4. 普通 `jmp` 可以在不再修改栈深度的情况下回到原 continuation；
5. 最终 `RSP` 与调用前一致，说明本实验观察到的是返回目标变化，而不是未平衡的栈操作。

对应教程：

[`../../docs/07-damaged-return-address.md`](../../docs/07-damaged-return-address.md)

本实验不接受外部输入、不制造越界写、不使用非法目标，也不讨论利用链。它只是为了把 `ret`、`RSP` 和返回地址三者之间的关系观察清楚。

## 2. 文件说明

```text
return_address_corruption.s  受控纯汇编实验
Makefile                     构建、运行、反汇编和符号入口
gdb.cmd                      GDB 观察脚本
expected-analysis.md         逐步预期分析
```

## 3. 构建与运行

```bash
make clean all
make run
```

预期：

```text
exit status=41 (expected 41)
```

程序内部还保留两个失败状态：

```text
91  回到 continuation 后 RSP 与调用前不一致
92  redirected_target 没有执行
```

退出状态只是自动化检查；真正学习重点是 `[RSP]`、`RIP` 和 `RSP` 的变化。

## 4. 核心执行路径

调用者：

```asm
movq %rsp, %r15
xorq %r12, %r12
call corrupt_return_address
after_corrupt_call:
```

被调用函数：

```asm
movq (%rsp), %r13
leaq redirected_target(%rip), %rax
movq %rax, (%rsp)
ret
```

替代目标：

```asm
redirected_target:
    movq $1, %r12
    jmp *%r13
```

重点不是记代码，而是按时间顺序写出：

```text
call 前：RSP = S
call 后：RSP = S-8，[RSP] = after_corrupt_call
替换后：RSP = S-8，[RSP] = redirected_target
ret 后：RSP = S，RIP = redirected_target
jmp 后：RSP = S，RIP = after_corrupt_call
```

## 5. 反汇编

```bash
make disasm
```

会同时输出 AT&T 和 Intel 语法。

重点确认：

```text
mov (%rsp),...
RIP-relative lea
mov ...,(%rsp)
ret
jmp *register
```

并确认 `ret` 与 `jmp` 对 `RSP` 的作用不同。

## 6. 符号检查

```bash
make symbols
```

应能看到至少：

```text
_start
corrupt_return_address
before_corrupted_ret
redirected_target
after_corrupt_call
```

实际地址由链接器决定，不应在教程中依赖固定值。

## 7. GDB

环境具备 GDB 时：

```bash
make gdb
```

脚本会依次在以下位置停止：

```text
corrupt_return_address
before_corrupted_ret
redirected_target
after_corrupt_call
```

重点记录：

```text
RSP
[RSP]
R13
R12
PC/RIP
```

在 `before_corrupted_ret` 处执行 `x/i *(void **)$rsp`，应看到当前栈顶已经解析到 `redirected_target`。

## 8. 本次实际验证

课程维护环境已实际执行：

```text
GNU as 构建       通过
GNU ld 链接       通过
程序运行          通过，exit status=41
nm                 通过
objdump AT&T       通过
objdump Intel      通过
GDB                当前环境未安装，脚本已静态检查但未执行
```

## 9. 常见误区

### 误区一：`ret` 知道函数符号关系

处理器不读取 ELF 符号表来决定普通 near `ret` 的目标。符号名主要服务于链接、调试和分析，不是这里的返回目标来源。

### 误区二：只要 `RSP` 没变，返回控制流就没变

错误。`RSP` 指向的是一个内存位置；即使地址不变，只要该位置保存的返回值改变，`ret` 读到的目标就不同。

### 误区三：`ret` 到替代目标后 `RSP` 仍指向原返回地址

错误。`ret` 已经消费了该栈项，所以到达替代目标时 `RSP` 已加 8。

### 误区四：RSB 就是软件栈里的返回地址

不是。Return Stack Buffer 是微架构预测结构；本实验观察的是程序员可见的真实栈和架构控制流。

## 10. 验收标准

完成实验后，应能够不依赖源代码直觉，仅根据下面的状态：

```text
RSP = S-8
[RSP] = X
下一条指令 = ret
```

说明：

```text
ret 将把 X 作为返回控制流目标
ret 消费该栈项后 RSP 恢复到 S
X 是否能继续执行还要由地址合法性和执行权限等条件决定
```

完整逐步分析见：

[`expected-analysis.md`](expected-analysis.md)

# 预期分析：返回地址被替换后的 `ret`

## 1. 固定运行结果

执行：

```bash
make clean all
make run
```

预期：

```text
exit status=41 (expected 41)
```

退出状态 41 表示：

```text
redirected_target 确实执行过
并且
回到 after_corrupt_call 时 RSP 与调用前一致
```

91 表示栈深度检查失败；92 表示没有观察到替代目标执行。

## 2. 调用前

`_start` 先执行：

```asm
movq %rsp, %r15
xorq %r12, %r12
call corrupt_return_address
```

设调用前：

```text
RSP = S
R15 = S
R12 = 0
```

`call` 后进入 `corrupt_return_address`：

```text
RSP = S - 8
[RSP] = after_corrupt_call
```

## 3. 保存原返回地址

函数首先执行：

```asm
movq (%rsp), %r13
```

因此：

```text
R13 = after_corrupt_call
RSP = S - 8
[RSP] 仍然是 after_corrupt_call
```

`mov` 不改变 `RSP`。

## 4. 替换栈顶

执行：

```asm
leaq redirected_target(%rip), %rax
movq %rax, (%rsp)
```

以后：

```text
RAX = redirected_target
RSP = S - 8
[RSP] = redirected_target
R13 = after_corrupt_call
```

这里最重要的是：

```text
RSP 没变
但 [RSP] 的值变了
```

因此即使栈深度没有变化，返回控制流已经被修改。

## 5. 执行 `ret`

`before_corrupted_ret` 处执行：

```asm
ret
```

near `ret` 消耗当前栈顶返回值，所以：

```text
RIP = redirected_target
RSP = S
```

这一步证明：`ret` 使用实际的返回栈槽，而不会重新推导原来的 `after_corrupt_call`。

## 6. 替代路径

`redirected_target`：

```asm
movq $1, %r12
jmp *%r13
```

执行后：

```text
R12 = 1
RSP = S
RIP = after_corrupt_call
```

`jmp` 本身不按 `call/ret` 规则压入或弹出返回地址，所以 `RSP` 保持为 S。

## 7. 原 continuation 的检查

到达：

```asm
after_corrupt_call:
    cmpq %r15, %rsp
    jne fail_stack
    cmpq $1, %r12
    jne fail_redirect
```

预期：

```text
RSP == R15 == S
R12 == 1
```

两项都成立，程序以 41 退出。

## 8. 反汇编观察点

执行：

```bash
make disasm
```

AT&T 语法中应能找到等价于：

```asm
mov    (%rsp),%r13
lea    redirected_target(%rip),%rax
mov    %rax,(%rsp)
ret
...
jmp    *%r13
```

Intel 语法中对应：

```asm
mov    r13,QWORD PTR [rsp]
lea    rax,[rip+...]
mov    QWORD PTR [rsp],rax
ret
...
jmp    r13
```

具体地址和位移取决于链接结果，不应写死。

## 9. GDB 观察

如果环境安装了 GDB：

```bash
make gdb
```

重点比较四个断点：

```text
corrupt_return_address
before_corrupted_ret
redirected_target
after_corrupt_call
```

预期观察：

1. 函数入口 `[RSP]` 指向 `after_corrupt_call`；
2. `ret` 前 `[RSP]` 已改为 `redirected_target`；
3. 到达 `redirected_target` 后，`RSP` 已恢复 8 字节；
4. 回到 `after_corrupt_call` 时 `R12=1`，且 `RSP` 等于调用前值。

## 10. 实验边界

本实验是受控控制流教学实验：

```text
没有外部输入
没有越界写
没有非法地址
没有 ROP 链
没有利用或权限提升过程
```

它只验证一个机器级事实：

> 如果 near `ret` 所使用的返回栈槽被改变，返回目标也会随之改变。

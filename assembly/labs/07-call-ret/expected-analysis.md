# Lab 07 预期分析：direct `call` / `ret`

本文件记录实验需要验证的事实。地址值来自本次参考构建；如果链接布局变化，绝对地址可能改变，但相对关系必须保持。

## 1. 参考构建结果

参考环境中：

```text
before_direct_call = 0x40100a
after_direct_call  = 0x40100f
direct_target      = 0x40102a
before_ret         = 0x40103e
```

关键反汇编：

```asm
40100a: e8 1b 00 00 00    call 40102a <direct_target>
40100f: ...                # after_direct_call
...
40103e: c3                 ret
```

因此 direct `call` 使用 `E8 rel32`，并把紧随其后的 `0x40100f` 作为返回地址。

## 2. `RSP` 变化

设调用前：

```text
RSP = S
```

执行 `call direct_target` 后，在 `direct_target_entry`：

```text
RSP   = S - 8
[RSP] = after_direct_call
```

实验代码将：

```asm
movq (%rsp), %r13
leaq after_direct_call(%rip), %r14
cmpq %r14, %r13
```

所以正常情况下：

```text
R13 == R14 == after_direct_call
```

## 3. `ret` 变化

执行 `ret` 前，如果函数没有额外遗留栈内容：

```text
[RSP] = after_direct_call
```

执行 `ret` 后：

```text
RIP = after_direct_call
RSP = S
```

因此 `after_direct_call` 中：

```asm
cmpq %r12, %rsp
```

应该相等。`R12` 在 `_start` 一开始保存了调用前的 `RSP`。

## 4. 数据结果

调用前：

```text
RAX = 10
```

函数体：

```asm
addq $3, %rax
```

返回后：

```text
RAX = 13
```

成功路径最终使用退出状态 37，只作为“所有检查均通过”的自动化路径标记，不用于表达完整寄存器值。

## 5. 参考验证

实际执行：

```text
as --64 -g        通过
ld                通过
程序运行          exit status=37
objdump -dr        通过
objdump -Mintel    通过
nm -n             通过
```

参考反汇编确认：

```text
CALL: e8 1b 00 00 00
RET:  c3
```

当前自动化执行环境未安装 GDB，因此 `gdb.cmd` 已做静态检查，但未实际执行。使用具备 GDB 的 Linux x86-64 环境时，可执行：

```bash
make gdb
```

逐点观察 `RSP` 和栈顶返回地址。

## 6. 不应得出的错误结论

不要从本实验推出：

- 所有 `call` 指令都是 5 字节；
- 所有函数只在栈上保存一个返回地址；
- `call/ret` 已经定义了完整 System V AMD64 ABI；
- 函数内部一定不修改 `RSP`；
- 返回地址永远不可被其他机制保护或校验。

本实验只验证最基础的 near direct `call` + near `ret` 正常路径。
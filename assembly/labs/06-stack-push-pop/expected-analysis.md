# Lab 06（一）预期分析

设进入 `_start` 后保存的初始栈顶为：

```text
S = R12
```

## 第一次 `pushq`

```asm
movabsq $0x1122334455667788, %rax
pushq %rax
```

预期：

```text
RSP = S - 8
[RSP] = 0x1122334455667788
R13 = S - 8
RBX = 0x1122334455667788
```

## 第二次 `pushq`

```asm
movabsq $0x99aabbccddeeff00, %rcx
pushq %rcx
```

预期：

```text
RSP = S - 16
[RSP]     = 0x99aabbccddeeff00
[RSP + 8] = 0x1122334455667788
R14 = S - 16
RDX = 0x99aabbccddeeff00
R8  = 0x1122334455667788
```

这说明后压入的数据位于更低地址的当前栈顶。

## 两次 `popq`

第一次：

```asm
popq %r9
```

预期：

```text
R9  = 0x99aabbccddeeff00
RSP = S - 8
```

第二次：

```asm
popq %r10
```

预期：

```text
R10 = 0x1122334455667788
RSP = S
```

这验证 LIFO。

`popq` 后原内存字节不要求被清零；变化的是当前 `RSP` 所定义的栈顶位置。

## 手工栈空间

```asm
subq $16, %rsp
```

预期：

```text
RSP = S - 16
```

随后：

```asm
movq %rax, 8(%rsp)
```

只是在保留区域内做普通内存写入。

执行：

```asm
addq $16, %rsp
```

后：

```text
RSP = S
```

## `RFLAGS` 注意点

普通 `pushq/popq` 不像算术指令那样根据普通压栈数据更新 `ZF/CF/SF/OF`。

但：

```asm
subq $16, %rsp
addq $16, %rsp
```

属于算术操作，会按各自规则更新条件标志。

因此不能只根据最终 `RSP` 和内存效果，把二者视为所有语义完全等价。

## 本次实际验证

在当前 x86-64 Linux 环境中实际执行：

```text
as --64 -g
ld
程序运行
objdump -dr -Mintel
nm -n
```

结果：

```text
exit status = 42
```

反汇编确认存在预期的：

```text
push rax
push rcx
pop r9
pop r10
sub rsp,0x10
add rsp,0x10
```

`nm` 确认所有观察标签存在。

当前环境没有安装 GDB，因此 GDB 断点观察未执行。
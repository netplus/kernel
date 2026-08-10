# Lab 06（一）：栈模型与 `push/pop`

## 1. 实验目标

本实验只验证 A06 第一部分的架构语义，不展开 `_start` 初始用户栈内容和 ABI 对齐。

需要确认：

1. 64 位 `pushq` 使 `RSP` 减少 8 字节；
2. 新值写入新的 `[RSP]`；
3. 连续压栈形成 LIFO；
4. `popq` 先读取 `[RSP]`，再使 `RSP` 增加 8 字节；
5. 两次 `popq` 后 `RSP` 恢复到实验开始值；
6. `subq/addq %rsp` 可以手工保留和释放栈空间；
7. `sub/add` 与 `push/pop` 的 `RFLAGS` 语义不同。

对应教程：

[`../../docs/06-stack-model-and-push-pop.md`](../../docs/06-stack-model-and-push-pop.md)

## 2. 文件

```text
stack_push_pop.s     纯汇编实验
Makefile             构建、运行、反汇编和符号检查
gdb.cmd              RSP、内存和标志位观察脚本
expected-analysis.md 预期结果与解释
```

## 3. 构建和运行

```bash
make clean all
make run
```

预期：

```text
exit status=42 (expected 42)
```

退出码 42 表示程序内部的全部检查通过。

## 4. 反汇编和符号

```bash
make disasm
make symbols
```

应看到关键序列：

```asm
pushq %rax
pushq %rcx
popq  %r9
popq  %r10
subq  $16, %rsp
movq  %rax, 8(%rsp)
addq  $16, %rsp
```

并确认以下观察标签存在：

```text
stack_after_push1
stack_after_push2
stack_after_pop1
stack_after_pop2
manual_after_sub
manual_after_add
```

## 5. GDB

若环境已安装 GDB：

```bash
make gdb
```

重点比较每个断点处的：

```text
RSP
初始 RSP（R12）
栈顶附近内存
弹出目标寄存器
RFLAGS
```

当前自动验证环境未安装 GDB，因此 `gdb.cmd` 已做静态检查，但本次没有实际执行。

## 6. 验收标准

完成实验后，应能准确解释：

```text
初始 RSP = S
第一次 push 后 = S - 8
第二次 push 后 = S - 16
第一次 pop 后  = S - 8
第二次 pop 后  = S
```

并能说明为什么：

```asm
subq $8, %rsp
movq %rax, (%rsp)
```

与 `pushq %rax` 在普通数据效果上相似，但不能视为所有语义都完全等价。
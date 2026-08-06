# Lab 01：寄存器宽度与部分写入

## 1. 实验要回答什么

本实验不要求先记住所有寄存器名称，只验证一个核心问题：

> 当我们写 `AL`、`AX`、`EAX` 时，完整的 `RAX` 分别会发生什么变化？

实验还会顺带验证：

- `mov` 不重新计算算术条件标志；
- 零扩展和符号扩展产生不同的 64 位结果；
- Shell 退出状态不能展示完整 64 位寄存器；
- 汇编、链接、反汇编和动态调试分别解决什么问题。

对应教程：

[`../../docs/01-cpu-execution-model-and-register-width.md`](../../docs/01-cpu-execution-model-and-register-width.md)

---

## 2. 文件说明

```text
register_width.s      最小纯汇编实验
companion.c           零扩展、符号扩展和 64 位运算的 C 对照
Makefile              构建、运行和反汇编入口
gdb.cmd               GDB 自动观察脚本
expected-analysis.md  预期结果与逐条解释
```

---

## 3. 推荐学习顺序

### 基础路径

```bash
make clean all
make run
make gdb
```

目标是亲眼观察：

```text
0x1122334455667788
0x11223344556677ff
0x112233445566abcd
0x0000000012345678
```

### 进阶路径

```bash
make disasm
make disasm-intel
make companion
```

对照 AT&T、Intel 和 GCC 生成的汇编，关注位宽和扩展方式。

### 系统方向路径

额外执行：

```bash
readelf -h -S -s register_width
nm -n register_width
```

观察 ELF 入口、`.text` 节和 `_start` 符号之间的关系。

---

## 4. 构建

```bash
make clean all
```

核心构建过程等价于：

```bash
as --64 -g -o register_width.o register_width.s
ld -o register_width register_width.o
```

这里没有链接 libc，所以程序直接从 `_start` 开始执行。

---

## 5. 运行验证

```bash
make run
```

预期：

```text
exit status: 120 (expected 120 / 0x78)
```

最终完整值是：

```text
RAX = 0x0000000012345678
```

程序先把该值复制到 `RDI`，再执行 `exit` 系统调用。Shell 通常只显示低 8 位：

```text
0x78 = 120
```

因此不要用退出状态判断完整寄存器内容，应使用 GDB。

---

## 6. GDB 观察

```bash
make gdb
```

或者手工执行：

```bash
gdb -q ./register_width
```

```gdb
break _start
run
x/i $rip
info registers rax rip rsp eflags
si
```

每一步都记录：

```text
当前指令
写入目标
写入宽度
执行前 RAX
执行后 RAX
RFLAGS 是否变化
```

预期 `RAX`：

| 指令执行后 | `RAX` |
|---|---|
| `movabsq` | `0x1122334455667788` |
| 写 `AL` | `0x11223344556677ff` |
| 写 `AX` | `0x112233445566abcd` |
| 写 `EAX` | `0x0000000012345678` |

---

## 7. 反汇编对照

AT&T：

```bash
make disasm
```

Intel：

```bash
make disasm-intel
```

重点观察：

```text
AT&T：源在前、目标在后，寄存器带 %，立即数带 $
Intel：目标在前、源在后
```

不要只比较文本形式，还要确认两种输出对应相同的机器字节和语义。

---

## 8. 编译器输出对照

```bash
make companion
less companion-O0.s
less companion-Og.s
less companion-O2.s
```

重点函数：

```text
zero_extend_u32
sign_extend_i32
add_u64
```

观察：

- 无符号 32 位值返回 64 位时，高位如何变为 0；
- 有符号 32 位值返回 64 位时，如何复制符号位；
- 优化级别变化后，栈操作和临时搬运如何减少。

具体指令可能随 GCC 版本变化，但零扩展和符号扩展的语义不能变化。

---

## 9. 分层练习

### 基础练习

1. 解释为什么写 `AL` 后高 56 位保持不变；
2. 解释为什么写 `EAX` 后高 32 位归零；
3. 写出每条指令的目标位范围；
4. 说明 `mov` 是否改变 `ZF/CF/OF/SF`。

### 进阶练习

把源码中的：

```asm
movb $0xff, %al
```

改为：

```asm
movb $0xee, %ah
```

先预测完整 `RAX`，再用 GDB 验证。

对比：

```asm
movl $0, %eax
xorl %eax, %eax
```

两者都把 `RAX` 置零，但对 `RFLAGS` 的影响不同。

### 系统方向练习

1. 用 `readelf -h` 找到入口地址；
2. 用 `nm` 找到 `_start` 地址；
3. 用 GDB 查看运行时 `_start` 与 `RIP`；
4. 说明符号地址、运行时地址和寄存器位宽为什么是不同层次的问题。

---

## 10. 验收标准

实验完成后，应能够脱离文档准确写出：

```text
写 AL：只改低 8 位
写 AX：只改低 16 位
写 EAX：改低 32 位并清零高 32 位
写 RAX：改完整 64 位
```

完整逐条结果见：

[`expected-analysis.md`](expected-analysis.md)

# A08 实验：结构体参数与返回值

## 验证目标

本实验验证两个最小 ABI 边界：

1. 两个 `uint64_t` 组成的 16 字节结构体分类为两个 INTEGER eightbyte，可用两个通用寄存器传入并从 `%rax/%rdx` 返回；
2. 三个 `uint64_t` 组成的 24 字节普通结构体按 MEMORY 传参，并通过隐藏的 `%rdi` 返回对象指针完成结构体返回。

实验采用 C caller 和手写 AT&T 汇编 callee，使跨语言函数边界直接暴露 ABI 状态。

## 构建与运行

```bash
make clean
make verify
```

`make verify` 会构建 `-O0` 和 `-O2` 两个版本、运行二者，并生成 AT&T / Intel 反汇编、`nm` 和 `readelf` 结果。

## 预期结果

```text
pair=12,24
big=34,46,58
```

两个程序都应返回 0。

### `pair_bump`

进入函数时：

```text
RDI = p.a = 11
RSI = p.b = 22
```

返回时：

```text
RAX = result.a = 12
RDX = result.b = 24
```

关键汇编：

```asm
leaq 1(%rdi), %rax
leaq 2(%rsi), %rdx
ret
```

### `big_bump`

callee 入口没有调整 `%rsp`，因此：

```text
RDI        = caller 提供的返回对象地址
[RSP]      = 返回地址
[RSP + 8]  = p.a = 33
[RSP + 16] = p.b = 44
[RSP + 24] = p.c = 55
```

callee 将三个结果字段写入 `%rdi` 指向的对象，并在返回前执行：

```asm
movq %rdi, %rax
```

## 本次实际验证

当前环境：GCC 14.2、GNU binutils 2.44。

```text
-O0 构建：通过
-O0 运行：pair=12,24；big=34,46,58；exit 0
-O2 构建：通过
-O2 运行：pair=12,24；big=34,46,58；exit 0
objdump AT&T：已检查 pair_bump / big_bump
objdump Intel：已检查 pair_bump / big_bump
nm：已确认 main、pair_bump、big_bump 符号
readelf：已确认 pair_bump、big_bump 为 GLOBAL FUNC
GDB：当前环境未安装，未执行
```

实际 AT&T 反汇编中，`big_bump` 对参数的访问为：

```asm
mov 0x8(%rsp),%rax
mov 0x10(%rsp),%rax
mov 0x18(%rsp),%rax
```

Intel 语法对应为：

```asm
mov rax,QWORD PTR [rsp+0x8]
mov rax,QWORD PTR [rsp+0x10]
mov rax,QWORD PTR [rsp+0x18]
```

## 边界说明

这里没有试图覆盖所有聚合分类。本实验只验证 `INTEGER,INTEGER` 和普通 24 字节 `MEMORY` 两个最基础案例。包含 `double`、向量、未对齐字段以及 X87 类别的结构体留给后续小单元。

另外，“MEMORY 参数”仍是按值参数，不应误解为 C 源码层面的 `struct *` 参数。隐藏 `%rdi` 指针只属于 MEMORY 类返回值的 ABI 接口。

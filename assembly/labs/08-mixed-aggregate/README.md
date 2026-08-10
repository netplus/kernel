# A08 实验：混合 INTEGER/SSE 聚合

## 验证目标

验证自然对齐的：

```c
struct mixed {
    double d;
    uint64_t n;
};
```

在 SysV AMD64 ABI 下分类为 `(SSE, INTEGER)`，并直接观察跨函数边界：

```text
参数：XMM0 = d，RDI = n
返回：XMM0 = result.d，RAX = result.n
```

实验使用 C caller 和手写 AT&T 汇编 callee，避免把编译器内部临时栈槽误认为 ABI 接口。

## 构建与运行

```bash
make clean
make verify
```

`make verify` 构建并运行 `-O0`、`-O2` 两个版本，然后生成 AT&T / Intel 反汇编、`nm` 和 `readelf` 结果。

预期输出：

```text
mixed=2.5,42
mixed=2.5,42
```

两个程序都应返回 0。

## 关键观察点

输入：

```text
x.d = 1.5
x.n = 40
```

`mixed_bump` 不建立栈帧，直接执行：

```asm
addsd .LCONE(%rip), %xmm0
leaq 2(%rdi), %rax
ret
```

如果参数没有按 `(SSE, INTEGER)` 分别到达 `%xmm0` 和 `%rdi`，这个 callee 就不能得到预期结果；返回值同理直接从 `%xmm0` 和 `%rax` 被 C caller 接收。

## 本次实际验证

当前执行环境：GCC 14.2、GNU binutils 2.44。

```text
-O0 构建：通过
-O0 运行：mixed=2.5,42；exit 0
-O2 构建：通过
-O2 运行：mixed=2.5,42；exit 0
objdump AT&T：已检查 mixed_bump
objdump Intel：已检查 mixed_bump
nm：已确认 mixed_bump 为全局文本符号
readelf：已确认 mixed_bump 为 GLOBAL FUNC
GDB：当前环境未安装，未执行
```

AT&T 关键反汇编：

```asm
addsd  ...(%rip),%xmm0
lea    0x2(%rdi),%rax
ret
```

Intel 关键反汇编：

```asm
addsd  xmm0,QWORD PTR [rip+...]
lea    rax,[rdi+0x2]
ret
```

## 边界说明

本实验只验证一个最小的 `(SSE, INTEGER)` 聚合案例。它不覆盖 `SSEUP`、向量、X87、未对齐字段、寄存器资源不足时的回退以及可变参数规则。这里的规则属于用户态 System V AMD64 ABI，而不是 x86-64 ISA 对 C 结构体的规定。

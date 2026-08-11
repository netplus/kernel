# A09 实验：RBP 栈帧基本模型

这个实验验证经典 x86-64 函数栈帧的最小模型：函数入口先保存调用者的 `%rbp`，再用当前 `%rsp` 建立新的 frame base，并在 `%rbp` 以下分配局部变量空间。

实验函数使用手写汇编，避免编译器把关键序言、尾声和局部变量访问优化掉。C 程序负责调用、打印观测值和检查不变量。

## 构建与运行

```bash
make clean
make check
```

同时生成 `-O0` 和 `-O2` 两个 caller：

```text
frame-o0
frame-o2
```

关键 callee `frame_sum` 始终来自 `frame.S`，所以两个优化级别都必须满足相同的 ABI 边界和相同的 frame 结构。

## 要验证的问题

函数入口时：

```text
[RSP] = return address
RBP   = caller 当前的 RBP 值
```

执行：

```asm
pushq %rbp
movq  %rsp, %rbp
subq  $16, %rsp
```

后，期望得到：

```text
RBP + 8   return address
RBP + 0   saved caller RBP
RBP - 8   local a
RBP - 16  local b
RSP       RBP - 16
```

因此程序检查：

```text
entry_rsp - frame_rbp == 8
frame_rbp - frame_rsp == 16
*(uint64_t *)frame_rbp == entry_rbp
frame_sum(17, 25) == 42
```

## 反汇编检查

AT&T：

```bash
objdump -drwC frame-o0 | sed -n '/<frame_sum>:/,+25p'
```

Intel：

```bash
objdump -drwC -Mintel frame-o0 | sed -n '/<frame_sum>:/,+25p'
```

还可以检查符号：

```bash
nm -n frame-o0
readelf -sW frame-o0
```

应该能看到关键序列：

```asm
pushq %rbp
movq  %rsp, %rbp
subq  $16, %rsp
...
leave
ret
```

其中 `leave` 在这里等价于：

```asm
movq %rbp, %rsp
popq %rbp
```

随后 `ret` 从恢复后的栈顶取回返回地址。

## 本次实际结果

环境：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
```

`-O0`：

```text
result=42
entry_rsp-frame_rbp=8
frame_rbp-frame_rsp=16
saved_rbp_matches_entry=yes
```

`-O2`：

```text
result=42
entry_rsp-frame_rbp=8
frame_rbp-frame_rsp=16
saved_rbp_matches_entry=yes
```

两个程序退出码均为 0。

同时已检查 AT&T / Intel 两种反汇编；`0(%rbp)` 确实读取保存的旧 `%rbp`，`8(%rbp)` 确实读取返回地址，`-8(%rbp)` 和 `-16(%rbp)` 用作两个 64 位局部槽。

当前环境未安装 GDB，因此本次没有执行逐指令单步。实验本身通过运行时快照和反汇编完成验证。

## 注意事项

这个实验展示的是“显式使用 frame pointer 的经典栈帧”，不是所有优化后函数都必须采用的形式。编译器可以省略 frame pointer，也可以把局部变量全部保存在寄存器中；这些情况将在 A09 后续部分讨论。

不要把 `%rbp` 误解为 CPU 强制规定的“栈帧寄存器”。从 ISA 角度看它只是一个通用寄存器；在 SysV AMD64 ABI 中它属于 callee-saved 寄存器，是否把它用作 frame pointer 是函数实现和编译器策略问题。
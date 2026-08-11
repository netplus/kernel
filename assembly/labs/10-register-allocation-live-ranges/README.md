# A10 实验：寄存器分配与 live range

## 要验证的问题

本实验验证两件事：

1. 同一个物理寄存器可以在不同时间承载不同机器级 value；
2. 多个 value 必须跨越普通函数调用继续存活时，寄存器压力会迫使编译器在 callee-saved 寄存器和栈槽之间做选择，并可能出现真实的 spill/reload。

## 构建与运行

```bash
make clean
make all
make run
make inspect
```

## 本次实际验证环境

```text
GCC 14.2.0
GNU binutils 2.44
x86-64
```

三个优化级别均实际运行通过，输出：

```text
reuse_chain=39
pressure_across_call=110
```

并以 exit 0 结束。

## 观察一：同一个寄存器连续复用

`reuse_chain()` 在本次 `-O2` 下为：

```asm
add    %rsi,%rdi
imul   %rdx,%rdi
add    %rcx,%rdi
lea    (%rdi,%rdi,2),%rax
ret
```

因此 `%rdi` 依次承载：

```text
a
→ a+b
→ (a+b)*c
→ (a+b)*c+d
```

旧 value 最后一次使用后即可死亡，物理寄存器随后被新 value 覆盖。

## 观察二：跨 `call` 的寄存器压力

`pressure_across_call()` 的十个输入在调用 `opaque()` 后仍然参与最终结果。`opaque.c` 与 `main.c` 分开编译且没有 LTO，因此 caller 必须按普通 SysV AMD64 调用边界处理 caller-saved 状态。

本次 `-O2` 可以观察到：

```asm
mov    %rdx,%r15
mov    %rcx,%r14
mov    %r8,%r13
mov    %r9,%r12
mov    %rdi,%rbx
mov    %rsi,-0x38(%rbp)
call   opaque
mov    -0x38(%rbp),%rsi
```

其中 `%rbx/%r12-%r15` 是 callee-saved 寄存器；当前函数在使用它们前先保存原值，并在返回前恢复。

`%rsi` 则被写入 `-0x38(%rbp)`，跨过 `call` 后重新加载。这一 store/reload 对是本实验中实际观察到的 spill/reload。

## 为什么 `opaque.c` 必须独立编译

如果 `opaque()` 与 caller 在同一个 translation unit 中，编译器可能根据被调函数实际实现做 interprocedural 优化，从而弱化实验中的普通调用边界。

`regalloc-O2` 的 Makefile 因而先独立生成：

```text
main-O2.o
opaque-O2.o
```

最后再链接，并且不开启 LTO。

## 工具检查

本次实际执行：

```text
-O0 / -Og / -O2 构建与运行     通过
AT&T objdump                   已检查
Intel objdump                  已检查
nm                             已检查
readelf                        已检查
GDB                            当前环境未安装，未执行
```

`nm` 用于确认 `reuse_chain`、`pressure_across_call` 和 `opaque` 都保留为独立符号；`readelf -h` 用于确认 ELF64 / AMD x86-64。

## 观察结论的边界

本实验能证明的是当前 GCC、当前源码和当前选项产生了上述分配结果。具体寄存器、栈槽偏移以及 spill 数量都不是 ABI 固定规则。

ABI 只规定哪些寄存器属于 caller-saved / callee-saved，以及调用边界必须满足什么保存语义；编译器如何选择寄存器、缩短 live range、重新计算或者 spill，属于代码生成策略。

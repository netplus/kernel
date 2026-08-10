# 预期分析

## 1. 参数寄存器

调用：

```c
abi_probe6(11, 22, 33, 44, 55, 66)
```

进入 `abi_probe6` 时应满足：

```text
RDI = 11
RSI = 22
RDX = 33
RCX = 44
R8  = 55
R9  = 66
```

汇编函数入口立即把这些值保存到 `seen_*` 全局变量，因此程序运行结果可以直接验证 C caller 是否按照 System V AMD64 ABI 传递六个 INTEGER 参数。

## 2. 返回值

`abi_probe6` 把六个参数相加到 `%rax`：

```text
11 + 22 + 33 + 44 + 55 + 66 = 231
```

所以 `ret` 前应有：

```text
RAX = 231
```

C caller 应读取到 `231`。

## 3. 本次实际验证结果

环境：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
```

执行 `make clean all run disasm`：通过。

两个可执行文件均输出：

```text
args: 11 22 33 44 55 66
return: 231
```

`-O0` 的 `call_probe` 反汇编明确显示：

```asm
mov $66, %r9d
mov $55, %r8d
mov $44, %ecx
mov $33, %edx
mov $22, %esi
mov $11, %edi
call abi_probe6
```

`-O2` 下 GCC 将 `return abi_probe6(...)` 优化为 tail call，因此最后使用 `jmp abi_probe6`，但六个参数寄存器仍按完全相同的 ABI 顺序准备。

`abi_probe6` 的反汇编确认入口直接读取 `%rdi/%rsi/%rdx/%rcx/%r8/%r9`，并在返回前把结果保存在 `%rax`。

`nm` 已确认 `abi_probe6` 和六个 `seen_*` 符号存在。

GDB：当前验证环境未安装，因此 `gdb.cmd` 已检查但未实际执行。

## 4. 不应过度推广的结论

本实验使用六个 64 位 `long`，它们都属于简单 INTEGER 类，因此可以直接观察六个通用参数寄存器。

不能由本实验推出：

```text
所有类型的前六个参数都固定使用这六个寄存器
```

浮点、向量、聚合类型和需要 MEMORY 分类的对象遵循更完整的 psABI 分类规则；超过可用 INTEGER 参数寄存器后的传参也将在后续单元讨论。

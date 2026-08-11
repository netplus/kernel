# A10 实验：内联与函数边界消失

## 要验证的问题

同一段 C 代码在不同优化级别下，编译器是否会把一个小 helper 的函数体直接并入 caller，从而让真实机器代码中的 `call` 和独立 helper 符号消失？`noinline` 又能否作为对照保留函数边界？

## 构建与运行

```bash
make clean
make all
make run
make inspect
```

## 观察点

重点比较 `use_inline()`：

- `-O0` 是否仍调用 `inline_helper()`；
- `-Og/-O2` 是否不再出现该 `call`；
- `nm` 中 `inline_helper` 是否在 `-O2` 二进制中消失；
- `use_noinline()` 在 `-O2` 下是否仍调用 `noinline_helper()`。

同时用 AT&T/Intel 两种语法检查反汇编，避免把语法差异误当成代码生成差异。

## 本次实际结果

验证环境：

```text
GCC 14.2.0
GNU binutils 2.44
x86-64
```

三个版本都输出：

```text
use_inline=27
use_noinline=27
```

并以 exit 0 结束。

当前 `-O0` 的 `use_inline()` 中存在：

```asm
call   inline_helper
add    $0x5,%rax
```

当前 `-Og/-O2` 的 `use_inline()` 都被化简为：

```asm
lea    0x6(%rdi,%rdi,2),%rax
ret
```

这里已经没有 helper 调用。`nm -n demo-O0` 能看到局部符号 `inline_helper`，而 `nm -n demo-O2` 中该符号消失。

作为控制组，`-O2` 的 `use_noinline()` 仍然包含：

```asm
call   noinline_helper
add    $0x5,%rax
ret
```

因此本实验验证的是“当前 GCC 在当前选项下的实际内联决策”，而不是“写了 `inline` 就一定内联”这一错误规则。

## 边界

`inline` 在 C 语言和编译器中不是强制机器码内联指令。是否真正内联还受优化级别、函数体、属性、编译器版本和调用上下文影响。本实验只把 `static inline` 作为候选，把 `__attribute__((noinline))` 用作明确控制组。

GDB 当前环境未安装，因此本次没有用单步调试观察 `-O0` 与 `-O2` 的源码级调用差异；二进制执行、`objdump`、`nm` 和 `readelf` 已实际完成。

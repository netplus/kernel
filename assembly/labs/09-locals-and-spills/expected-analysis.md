# 预期分析：局部变量与 spill/reload

## `locals-o0`

预期看到 `%rbp` 栈帧，以及参数和中间结果的多次 store/load。当前 GCC 14.2.0 实际反汇编中出现：

```asm
mov    %rdi,-0x28(%rbp)
mov    %rsi,-0x30(%rbp)
...
mov    %rax,-0x8(%rbp)
mov    %rax,-0x10(%rbp)
mov    %rax,-0x18(%rbp)
```

## `locals-og` / `locals-o2`

预期源码局部变量不再一一对应内存槽。当前验证中两个版本都直接用寄存器完成计算，并在 `ret` 前没有为 `x/y/z` 建立固定栈槽。

## `spill-o2`

该目标使用 `-O2 -fno-omit-frame-pointer`。当前验证中：

```asm
mov    %r8,-0x40(%rbp)
mov    %r9,-0x38(%rbp)
call   opaque
...
mov    -0x38(%rbp),%r9
...
mov    -0x40(%rbp),%r8
```

这组 store/load 用于让原 `%r8/%r9` 参数跨 `opaque()` 调用保持可用，随后为 `consume12()` 恢复到参数寄存器。

同时第二次调用前会出现多个 `push`，它们用于传递第 7 个及以后的 INTEGER 参数，属于 outgoing stack arguments，而不是 spill slot。

具体偏移和寄存器分配不是 ABI 保证；不同 GCC/Clang 版本可能产生不同但等价的代码。

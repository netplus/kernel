# 预期分析

## `raw_getpid`

```asm
mov $39, %eax
syscall
ret
```

写 `%eax` 会把 `%rax` 高 32 位清零，因此执行 `syscall` 时 `%rax=39`。Linux 5.10 `arch/x86/entry/syscalls/syscall_64.tbl` 中 39 对应 `getpid`。

## `raw_mmap`

普通 System V AMD64 C ABI 给 `raw_mmap` 的六个参数为：

```text
RDI RSI RDX RCX R8 R9
```

Linux x86-64 syscall ABI 要求：

```text
RDI RSI RDX R10 R8 R9
```

因此：

```asm
mov %rcx, %r10
```

不是优化细节，而是两套 ABI 之间的必要转换。随后 `%rax=9` 选择 `mmap`。

## `%rcx` 与 `%r11`

Linux 5.10 `entry_SYSCALL_64` 前的源码注释与 x86-64 `syscall` 语义一致：

```text
RCX = return address
R11 = saved RFLAGS
```

实验中的 `raw_getpid_state` 在 `syscall` 返回后立即保存这两个寄存器，避免后续 C 代码覆盖观察值。

## 错误返回

不存在的 syscall number 在当前实验环境返回 `-ENOSYS`：

```text
raw = -38
```

相同请求经 libc `syscall()` 后变为：

```text
return = -1
errno = 38
```

这验证了 raw kernel ABI 与 libc API 的分层。

## 不应从实验推出的结论

- 不应把某次 `rcx_after` 地址写成固定地址；PIE/ASLR 会改变它。
- 不应把 `0x246` 等 RFLAGS 样例值写成 ABI 常量。
- 不应据此推导完整内核入口栈布局；那属于 A14。
- 不应说 `syscall` 自动切换到 Linux 内核栈；硬件指令自身不替软件完成普通的 RSP 栈切换，Linux 入口代码负责后续处理。

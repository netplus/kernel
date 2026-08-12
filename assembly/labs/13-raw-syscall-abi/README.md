# A13 实验：Linux x86-64 原始 syscall ABI

本实验验证 A13 第一部分的五个结论：

1. 系统调用号放在 `%rax`；
2. `getpid` 的 Linux x86-64 syscall number 为 39；
3. 六参数 syscall 的第四参数使用 `%r10`，而普通 C ABI 的第四参数最初位于 `%rcx`；
4. `syscall` 返回后 `%rcx`、`%r11` 已被硬件用于返回 RIP 和用户 RFLAGS；
5. 原始负 errno 与 libc 的 `-1 + errno` 是两个接口层次。

## 构建与运行

```bash
make clean
make
./syscall-demo
```

完整检查：

```bash
make check
```

## 关键观察

### `raw_getpid`

```bash
objdump -dr syscall_demo.o
```

应看到：

```asm
mov $0x27,%eax
syscall
ret
```

`0x27` 即十进制 39。

### 第四参数从 `%rcx` 移到 `%r10`

`raw_mmap` 应包含：

```asm
mov %rcx,%r10
mov $0x9,%eax
syscall
```

第一条 `mov` 是普通 System V AMD64 函数 ABI 到 Linux syscall ABI 的显式适配。

### 原始 errno 与 libc errno

示例程序故意调用不存在的 syscall number。当前 Linux 测试环境得到：

```text
invalid: raw=-38 libc=-1 errno=38
```

`38` 是 `ENOSYS`。

### `%rcx`、`%r11` 与 RFLAGS

程序会输出类似：

```text
state: rflags_before=0x246 rcx_after=0x... r11_after=0x246 rflags_after=0x246
```

地址和 flags 数值不是固定值。需要观察的是：

- `%rcx` 返回后保存与 syscall 返回位置相关的地址；
- `%r11` 承载用户 flags；
- `pushfq` 可以独立读取返回后的用户态 RFLAGS。

## 提交前实际验证

本实验已在 x86-64 Linux 环境实际构建并运行。一次结果为：

```text
getpid: libc=371 libc_syscall=371 raw=371 state=371
invalid: raw=-38 libc=-1 errno=38
raw_mmap: success
state: rflags_before=0x246 rcx_after=0x5585cbc7138b r11_after=0x246 rflags_after=0x246
```

PID、`rcx_after` 和 RFLAGS 的具体数值会随运行环境变化，不应作为固定预期值。

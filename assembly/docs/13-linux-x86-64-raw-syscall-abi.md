# Linux x86-64 原始系统调用 ABI：`syscall`、寄存器与返回值

## 1. 为什么需要单独学习系统调用 ABI

普通 C 函数调用和系统调用都使用寄存器传递参数，但它们不是同一套调用约定。

System V AMD64 普通函数调用中，前六个整数或指针参数通常依次放在 `%rdi`、`%rsi`、`%rdx`、`%rcx`、`%r8`、`%r9`。Linux x86-64 系统调用则通过 `syscall` 指令进入内核。该指令会占用 `%rcx` 和 `%r11` 保存返回所需的处理器状态，因此 Linux syscall ABI 把第四个参数放到 `%r10`。

```text
普通用户态函数 ABI
    arg1  arg2  arg3  arg4  arg5 arg6
    RDI   RSI   RDX   RCX   R8   R9

Linux x86-64 syscall ABI
    nr    arg1  arg2  arg3  arg4  arg5 arg6
    RAX   RDI   RSI   RDX   R10   R8   R9
```

本节只建立用户态在执行 `syscall` 前后应遵守的 ABI 模型。内核如何切换到内核栈、构造 `pt_regs`、调用 `do_syscall_64()`，以及如何选择 `sysretq` 或 `iretq` 返回，留到 A14。

## 2. `syscall` 指令本身做什么

### 2.1 架构层规则

在 64-bit mode 下执行 `syscall` 时，处理器不会像普通 `call` 那样把返回地址压入用户栈。与本节直接相关的硬件动作是：

- 下一条用户态指令地址保存到 `%rcx`；
- 用户态 `RFLAGS` 保存到 `%r11`，其中 RF 有专门处理规则；
- 从预先配置的 MSR 取得新的代码段相关状态和入口 RIP；
- 按 `IA32_FMASK` 对进入内核后的 RFLAGS 做屏蔽；
- `syscall` 指令自身不把完整寄存器现场压入当前栈，也不替软件完成普通的 `%rsp` 栈切换。

所以从软件 ABI 角度，`%rcx` 与 `%r11` 必须视为被 `syscall` clobber。

### 2.2 Linux 5.10 对入口寄存器的约定

Linux 5.10 的 `arch/x86/entry/entry_64.S` 在 `entry_SYSCALL_64` 前直接记录了 64-bit syscall 的入口寄存器：

```text
RAX = system call number
RDI = arg0
RSI = arg1
RDX = arg2
R10 = arg3
R8  = arg4
R9  = arg5
RCX = return address
R11 = saved user RFLAGS
```

源码注释从 `arg0` 开始编号；本文表格按“第 1 个参数”开始编号。两者描述的是同一组寄存器。

## 3. 为什么第四个参数必须从 `%rcx` 改到 `%r10`

普通六参数 C 函数进入时通常是：

```text
RDI=a1, RSI=a2, RDX=a3, RCX=a4, R8=a5, R9=a6
```

如果它是一个 syscall wrapper，不能原样执行 `syscall`，因为硬件会把返回 RIP 写入 `%rcx`。因此包装代码必须先完成：

```asm
mov %rcx, %r10
```

再把 syscall number 放入 `%rax` 并执行 `syscall`。

本节实验中的 `raw_mmap()` 正好验证这一转换。`mmap()` 有六个参数，第四参数 `flags` 在普通 C ABI 中进入 wrapper 时位于 `%rcx`，而 syscall ABI 要求它位于 `%r10`。

## 4. 系统调用号来自哪里

系统调用号不是 `syscall` 指令编码的一部分。用户态先把编号放入 `%rax`，Linux 再按编号分派。

Linux 5.10 x86-64 的编号表位于：

```text
arch/x86/entry/syscalls/syscall_64.tbl
```

本节实验使用：

```text
9   mmap
39  getpid
```

并故意使用 `0x7fffffff` 作为不存在的编号来观察错误返回。

系统调用号属于 Linux ABI，而不是 x86-64 ISA。其他操作系统即使也使用 `syscall` 指令，也不需要采用同一编号表。

## 5. `%rax`：输入编号，输出原始返回值

执行前：

```text
RAX = syscall number
```

返回用户态后，Linux 原始 syscall 接口把结果放回 `%rax`。成功时它可能是 PID、字节数、文件描述符或地址；失败时则返回负 errno。

实验中的不存在 syscall 实际得到：

```text
RAX = -38 = -ENOSYS
```

这与 libc 暴露给 C 程序的错误接口不同。

## 6. libc wrapper 与 `errno`

普通 C 程序通常调用 libc 的 `read()`、`mmap()`、`getpid()` 或通用 `syscall()` 包装，而不是手写 `syscall` 指令。wrapper 需要完成 ABI 适配，并把原始负 errno 转成常见的 C 接口形式：

```text
return = -1
errno  = positive error number
```

因此同一个不存在 syscall 在实验中表现为：

```text
raw syscall:       -38
libc syscall(...): -1, errno=38
```

不是内核返回了两种结果，而是 libc 在用户态做了转换。

## 7. `%rcx`、`%r11` 与 RFLAGS

`syscall` 把返回 RIP 保存到 `%rcx`，所以 syscall 前的 `%rcx` 不能被调用者视为保留值。它还把用户态 RFLAGS 保存到 `%r11`，因此 `%r11` 同样属于 clobber。

需要区分两种 flags 状态：

1. `%r11` 中保存用于返回的用户态 flags；
2. 内核入口实际运行时的 RFLAGS 会按 MSR mask 处理。

Linux 5.10 的 `entry_64.S` 注释明确记录了这两个动作。实验会在 `getpid` 前后用 `pushfq` 读取用户态 RFLAGS，并在 `syscall` 返回后立即保存 `%rcx/%r11`。一次实际运行得到：

```text
rflags_before = 0x246
r11_after     = 0x246
rflags_after  = 0x246
```

具体数值不是 ABI 常量；需要验证的是寄存器角色。

## 8. 最小汇编例子：`getpid`

```asm
.globl raw_getpid
.type raw_getpid,@function
raw_getpid:
    mov $39, %eax
    syscall
    ret
```

控制流可以写成：

```text
C caller
  |
  v
raw_getpid
  | RAX = 39
  v
syscall
  | RCX <- userspace return RIP
  | R11 <- userspace RFLAGS
  v
Linux kernel
  | RAX <- result
  v
instruction after syscall
  |
  v
ret -> C caller
```

最后的 `ret` 使用的是普通 `call raw_getpid` 进入函数时压入用户栈的返回地址；`syscall` 自己没有把 syscall 返回地址压入该栈。

## 9. 六参数例子：`mmap`

实验函数声明：

```c
void *raw_mmap(void *addr, size_t len, int prot,
               int flags, int fd, off_t off);
```

作为普通 C 函数刚进入时：

```text
RDI = addr
RSI = len
RDX = prot
RCX = flags
R8  = fd
R9  = off
```

执行 Linux syscall 前要变成：

```text
RAX = 9
RDI = addr
RSI = len
RDX = prot
R10 = flags
R8  = fd
R9  = off
```

所以关键汇编是：

```asm
mov %rcx, %r10
mov $9, %eax
syscall
```

这说明 wrapper 不只是“执行一条 syscall”，还承担普通函数 ABI 到 syscall ABI 的转换。

## 10. 常见误区

**System V AMD64 ABI 就是 Linux syscall ABI。** 不是。普通函数第四参数用 `%rcx`，Linux x86-64 syscall 第四参数用 `%r10`。

**`syscall` 会像 `call` 一样压入返回地址。** 不是。64-bit `syscall` 把返回 RIP 放入 `%rcx`。

**`RCX`、`R11` 只是内核随意破坏。** 不是。它们分别承担返回 RIP 与用户 RFLAGS 的硬件角色。

**系统调用失败时内核直接返回 `-1` 并设置 `errno`。** 不是。原始 syscall 返回负 errno，`errno` 属于 libc/user-space API 层。

**系统调用号属于 x86 指令集。** 不是。`syscall` 是处理器指令，编号表属于 Linux ABI。

## 11. 与 A14 的边界

完成本节后应掌握的是用户态入口条件和返回值：

```text
RAX + six argument registers
       |
       v
    syscall
       |
       v
Linux syscall entry
       |
       v
result in RAX
```

A14 再沿 Linux 5.10 源码分析：

```text
entry_SYSCALL_64
→ 用户 RSP 保存与内核栈切换
→ pt_regs
→ do_syscall_64
→ exit-to-user work
→ SYSRET / IRET
```

这样可以把架构规则、用户态 ABI 和 Linux 5.10 入口实现分层理解。

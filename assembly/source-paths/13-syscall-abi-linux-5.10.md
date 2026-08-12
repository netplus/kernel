# A13 Linux 5.10 syscall ABI 源码事实核验

本文件只记录 A13 第一部分需要依赖的 Linux kernel 5.10 源码事实。A13 的重点仍是用户态 syscall ABI；内核入口如何切栈、构造 `pt_regs` 和返回用户态在 A14 展开。

## 1. 核验范围

A13 正文需要确认四类事实：

1. x86-64 syscall 的寄存器约定；
2. syscall number 的来源；
3. Linux 原始错误返回与 `errno` 的边界；
4. 哪些内容属于 A14，而不应提前混入用户态 ABI。

## 2. 64-bit syscall 入口寄存器

Linux 5.10 x86-64 的入口汇编位于：

```text
arch/x86/entry/entry_64.S
```

`entry_SYSCALL_64` 前的源码注释给出的入口状态为：

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

因此 A13 使用的六参数模型是：

```text
nr   arg1 arg2 arg3 arg4 arg5 arg6
RAX  RDI  RSI  RDX  R10  R8   R9
```

这里正文从“第 1 个参数”编号，而内核注释从 `arg0` 编号，两者只是编号方式不同。

需要特别保留的边界是：普通 System V AMD64 C 函数的第四个 INTEGER 参数使用 `%rcx`，而 Linux x86-64 syscall 的第四参数使用 `%r10`。因此一个以普通 C ABI 被调用、随后直接执行 syscall 的六参数 wrapper 必须在进入 syscall 前完成 `%rcx -> %r10` 的适配。

## 3. `%rcx` 与 `%r11` 的角色

`entry_64.S` 的入口约定与 x86-64 `syscall` 指令的架构语义一致：进入内核时 `%rcx` 已承载用户返回 RIP，`%r11` 已承载用户 RFLAGS。

因此对用户态手写 syscall wrapper 来说：

```text
RCX: clobbered by syscall
R11: clobbered by syscall
```

这不是 Linux 任意选择两个 caller-saved 寄存器覆盖，而是 syscall/sysret 架构接口本身使用了这两个寄存器。

`syscall` 本身也不会像普通 near `call` 一样把返回地址压入当前用户栈。Linux 在入口后如何保存用户 `%rsp`、切换到内核栈并构造后续入口现场属于 A14。

## 4. syscall number

Linux 5.10 x86-64 系统调用编号表位于：

```text
arch/x86/entry/syscalls/syscall_64.tbl
```

A13 实验使用的两个编号为：

```text
9   mmap
39  getpid
```

因此系统调用号应理解为 Linux x86-64 ABI 的一部分，而不是 `syscall` 指令编码或 x86 ISA 固有编号。

## 5. 原始返回值与 libc `errno`

Linux x86-64 syscall 返回路径把系统调用结果通过 `%rax` 交还用户态。A13 实验故意使用不存在的 syscall number，并实际观察到原始返回：

```text
-38 == -ENOSYS
```

同一次语义测试通过 libc `syscall()` 观察到：

```text
return = -1
errno  = 38
```

这里必须区分两个接口层：负 errno 是 Linux 原始 syscall 接口的可观察结果；把错误转换成 `-1` 并设置线程局部 `errno` 是 libc 用户态接口行为。不能把“内核设置 errno”写入课程。

## 6. 与 A14 的源码边界

A13 到此只需要把用户态入口条件核实到 `entry_SYSCALL_64` 的入口约定。下面这些 Linux 5.10 实现细节属于 A14：

```text
entry_SYSCALL_64
  -> 保存用户 RSP
  -> 切换到内核栈
  -> 构造 pt_regs
  -> do_syscall_64
  -> exit-to-user 检查
  -> SYSRET 或 IRET 返回路径
```

A14 编写时应重新逐项核对 Linux 5.10 的实际汇编宏、C 函数、配置条件和快/慢返回路径，不能仅依据这份边界说明补全调用链。

## 7. 与 A13 实验的对应关系

正文：

```text
../docs/13-linux-x86-64-raw-syscall-abi.md
```

实验：

```text
../labs/13-raw-syscall-abi/
```

实验中的 `raw_mmap()` 用反汇编验证 `%rcx -> %r10`；`raw_getpid()` 验证 `%rax=39` 与 `syscall`；不存在 syscall 对照验证 raw negative errno 与 libc `errno` 的接口边界；状态采样验证 `%rcx/%r11` 的 syscall 特殊角色。

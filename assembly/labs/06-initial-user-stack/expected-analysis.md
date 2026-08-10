# Lab 06：初始用户栈预期分析

## 1. 运行条件

实验固定使用：

```bash
env -i DEMO=1 ./initial-stack alpha beta
```

因此期望：

```text
argc = 3
argv[0] -> ./initial-stack
argv[1] -> alpha
argv[2] -> beta
argv[3] = NULL
```

环境中至少存在：

```text
DEMO=1
```

`envp[]` 末尾还有一个 NULL 指针，随后进入 auxiliary vector。

## 2. 初始 RSP

实验首先保存：

```asm
movq %rsp, %rbx
```

在本课程的 Linux x86-64 ELF 环境中，入口栈应满足：

```text
initial_rsp % 16 == 0
```

因此 bit 0 应为 1。

## 3. argc 与 argv

```asm
movq (%rbx), %r12
leaq 8(%rbx), %r13
```

预期：

```text
R12 = 3
R13 = &argv[0]
```

并且：

```asm
(%r13,%r12,8)
```

对应 `argv[3]`，应为 0。

因此 bit 1 和 bit 2 应置位。

## 4. envp

程序使用：

```asm
leaq 8(%r13,%r12,8), %r14
```

定位 `envp[0]`。

随后每次增加 8 字节扫描，直到遇到 NULL。

使用 `env -i DEMO=1` 的目的是让环境内容尽量简单，同时仍能证明环境指针区真实存在。

因此 bit 3 应置位。

## 5. auxv

跳过 envp 末尾 NULL 后，每个 64 位辅助向量条目按：

```text
8 bytes a_type
8 bytes a_val
```

解析。

实验重点寻找：

```text
AT_PAGESZ = 6
```

并一直扫描到：

```text
AT_NULL = 0
```

若扫描能够正常结束，则 bit 4 置位；若 `AT_PAGESZ` 的 value 非零，则 bit 5 置位。

## 6. 最终退出码

六个检查分别编码为：

```text
bit 0 = 1   initial RSP 16-byte aligned
bit 1 = 2   argc == 3
bit 2 = 4   argv[argc] == NULL
bit 3 = 8   至少存在一个 envp 指针
bit 4 = 16  auxv 扫描到 AT_NULL
bit 5 = 32  找到非零 AT_PAGESZ
```

全部成立：

```text
1 + 2 + 4 + 8 + 16 + 32 = 63
```

因此：

```bash
make run
```

应输出：

```text
exit status=63 (expected 63)
```

## 7. 反汇编检查

`make disasm` 后应能确认：

- `_start` 第一阶段直接从 `%rsp` 读取数据，没有普通函数序言；
- `argc` 来自 `(%rbx)`；
- `argv` 基址来自 `8(%rbx)`；
- envp 扫描步长为 8 字节；
- auxv 扫描步长为 16 字节；
- `AT_NULL` 使用 `test %rax,%rax` 判断；
- `AT_PAGESZ` 与立即数 6 比较。

## 8. GDB 观察

如果本机安装 GDB：

```bash
make gdb
```

脚本会在 `_start` 第一条指令前停住。此时最重要的是先观察原始栈，而不是先单步执行很多指令：

```gdb
p/x $rsp
p *(long *)$rsp
x/12gx $rsp
```

然后按照 `argc` 计算 `argv` 和 `envp`。

注意 GDB 启动调试程序时会建立自己的被调试进程环境，因此 `make gdb` 与 `make run` 的环境变量数量可能不同；栈结构规则不因此改变。

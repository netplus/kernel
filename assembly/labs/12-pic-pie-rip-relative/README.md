# A12 实验：non-PIE、PIE 与 RIP-relative 寻址

本实验对应 [`../../docs/12-pic-pie-and-rip-relative.md`](../../docs/12-pic-pie-and-rip-relative.md)。

## 1. 要验证的问题

本实验验证四个结论：

1. 普通 non-PIE executable 与 PIE executable 的 ELF type 不同；
2. 取得同一映像内静态对象地址时，`-fno-pie` 与 `-fPIE` 可以生成不同的地址形成方式；
3. `.o` 中可以直接观察到 `R_X86_64_32` 与 `R_X86_64_PC32` relocation 的差异；
4. 在 ASLR 开启的当前 Linux 环境中，PIE 主映像可以在不同执行之间使用不同基址，而普通 non-PIE 通常保持固定链接地址。

本实验**不分析** `printf` 对应的 PLT/GOT 过程。程序使用 `printf` 只是为了打印运行时地址；相关 relocation 留到 A12 后续单元解释。

## 2. 构建

```bash
make clean
make
```

Makefile 分别生成：

```text
nonpie.o   -O2 -fno-pie
pie.o      -O2 -fPIE
nonpie     -O2 -fno-pie -no-pie
pie        -O2 -fPIE -pie
```

## 3. 运行

```bash
make run
```

每个程序连续运行三次。预期：

```text
value=12 address=...
```

退出码应为 0。

如果系统启用了 ASLR，通常会看到 non-PIE 地址保持一致，而 PIE 地址随运行变化。若地址没有变化，先检查：

```bash
cat /proc/sys/kernel/randomize_va_space
```

不要把“每次必须不同”写成 PIE 的 ABI 保证。

## 4. 检查 ELF 与 relocation

```bash
make inspect
```

重点观察：

### 4.1 ELF type

```bash
readelf -h nonpie
readelf -h pie
```

当前实验环境预期：

```text
nonpie -> EXEC
pie    -> DYN (Position-Independent Executable file)
```

### 4.2 `local_address()`

```bash
objdump -dr nonpie.o
objdump -dr pie.o
```

当前工具链下，non-PIE 对象可看到近似：

```asm
mov $0x0, %eax
```

并带：

```text
R_X86_64_32 .data
```

PIE 对象可看到近似：

```asm
lea 0x0(%rip), %rax
```

并带：

```text
R_X86_64_PC32 .data-0x4
```

### 4.3 `local_read()` 不应被误解

继续检查 `local_read()`。在当前 GCC 中，non-PIE 和 PIE 都可以使用 RIP-relative load 访问 `local_value`。

这正是实验的重要结论之一：

```text
RIP-relative addressing 是 x86-64 的寻址机制；
PIE 会系统性依赖位置无关关系，但 non-PIE 也可以使用 RIP-relative 指令。
```

## 5. 本次实际验证环境

```text
Architecture: x86_64
GCC: 14.2.0
GNU ld / binutils: 2.44
/proc/sys/kernel/randomize_va_space: 2
```

实际执行 `make clean all run inspect` 成功，无编译 warning。

本次三次 non-PIE 运行：

```text
value=12 address=0x404018
value=12 address=0x404018
value=12 address=0x404018
```

本次三次 PIE 运行：

```text
value=12 address=0x5623abf21018
value=12 address=0x564f081b4018
value=12 address=0x563924328018
```

这些具体地址只属于本次实验环境，不应作为课程固定值。

## 6. 清理

```bash
make clean
```

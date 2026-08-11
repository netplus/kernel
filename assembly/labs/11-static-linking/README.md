# A11 静态链接实验

## 要验证的问题

本实验把 A11 前四部分串起来，验证一次最小静态链接中发生的五件事：

1. 多个 `ET_REL` 各自拥有 input `.text/.data`；
2. GNU ld 把这些 input section 放入最终 output section；
3. 最终布局确定后，defined symbol 获得最终地址；
4. input `.rela.text` 中的 `R_X86_64_PC32/PLT32` 被链接器消费；
5. 最终 `ET_EXEC` 的相关机器字段已经是可执行位移，本实验不再保留 relocation。

最终程序不依赖 libc。`_start` 调用 `combine(7)`，计算结果 37 后直接执行 Linux x86-64 `exit(37)` 系统调用。

## 文件

```text
start.S             最小 _start 和 sys_exit
part1.c             left() 与 left_data
part2.c             combine()、right_data，以及对 left() 的未定义引用
Makefile            构建、运行和检查命令
expected-analysis.md 关键观察结果
```

## 构建与运行

```bash
make clean
make check
```

成功时应看到：

```text
exit_status=37
```

这里 shell exit status 只用于验证程序计算结果确实为 37；没有用它承载完整 64-bit 寄存器值。

## 完整检查

```bash
make inspect
```

主要使用：

```text
readelf -SW   section table
readelf -Ws   symbol table
readelf -Wr   relocation table
objdump -dr   ET_REL 指令与 relocation
objdump -d    最终机器指令
nm -n         最终 symbol address
ld -Map       input section 对 output section 的贡献
```

## 建议按顺序观察

### 1. 先看链接前

```bash
readelf -SW part1.o part2.o
readelf -Ws start.o part1.o part2.o
readelf -Wr start.o part1.o part2.o
objdump -dr part2.o
```

重点确认：

- 每个 `.o` 有自己的 `.text`；
- `combine` 在 `start.o` 中是 `UND`；
- `left` 在 `part2.o` 中是 `UND`；
- 函数调用使用 `R_X86_64_PLT32`；
- RIP-relative 数据访问使用 `R_X86_64_PC32`；
- 对应 `rel32/disp32` 在链接前仍是占位值。

### 2. 再看 linker map

```bash
less linked.map
```

当前工具链下关键布局应与下列关系一致：

```text
output .text
  start.o:.text
  part1.o:.text
  part2.o:.text

output .data
  part1.o:.data
  part2.o:.data
```

具体地址可能随 linker/binutils 版本和默认 linker script 改变，不应把本机绝对地址当作 ABI 规则。

### 3. 再看最终符号

```bash
nm -n linked.elf
```

验证 `_start`、`left`、`combine`、`left_data`、`right_data` 的地址与 `linked.map` 中对应 input section 的最终位置一致。

### 4. 最后看 relocation 是否已被消费

```bash
readelf -Wr linked.elf
objdump -d linked.elf
```

本实验应得到：

```text
There are no relocations in this file.
```

同时 `call left` 和对 `right_data` 的 RIP-relative 访问已经包含真实位移。

## 环境说明

本实验已在以下环境实际执行：

```text
GCC 14.2.0
GNU ld / binutils 2.44
x86-64 Linux
```

若其他版本的默认 linker script 导致绝对地址不同，应比较 section 相对关系、symbol 绑定和 relocation 是否被正确消费，而不是要求地址逐字一致。

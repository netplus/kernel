# Lab 08-2：caller-saved 与 callee-saved 寄存器

## 1. 实验目标

验证 System V AMD64 ABI 中两类通用寄存器的保存责任：

```text
callee-saved：RBX、RBP、R12、R13、R14、R15
caller-saved：RAX、RCX、RDX、RSI、RDI、R8、R9、R10、R11
```

实验重点使用 `RBX/RBP/R12-R15` 与 `R10/R11`，直接观察一次嵌套函数调用前后的值。

对应教程：

[`../../docs/08-caller-saved-and-callee-saved.md`](../../docs/08-caller-saved-and-callee-saved.md)

## 2. 文件

```text
main.c                 C 驱动和结果检查
preservation_probe.S   手写汇编 caller/callee
Makefile               -O0/-O2 构建、运行和反汇编
gdb.cmd                调用边界寄存器观察脚本
expected-analysis.md   预期和实际验证结果
```

## 3. 实验结构

```text
main()
  ↓
run_preservation_probe
  ├─ 保存 main 的 callee-saved 寄存器
  ├─ 写入固定哨兵值
  ├─ 对齐 RSP
  ↓
clobber_probe
  ├─ 保存 RBX/R12
  ├─ 临时修改 RBX/R12
  ├─ 直接覆盖 R10/R11
  ├─ 恢复 RBX/R12
  ↓
run_preservation_probe
  ├─ 记录返回后的寄存器
  ├─ 恢复 main 的 callee-saved 寄存器
  ↓
main() 检查结果
```

## 4. 构建与运行

```bash
make clean all
make run
```

预期两个版本都输出：

```text
callee-saved: rbx=0x1111111111111111 rbp=0x2222222222222222 r12=0x3333333333333333 r13=0x4444444444444444 r14=0x5555555555555555 r15=0x6666666666666666
caller-saved: r10=0xaaaaaaaaaaaaaaaa r11=0xbbbbbbbbbbbbbbbb
```

程序只有在 callee-saved 值全部保持、并且 `R10/R11` 确实被内层函数覆盖时才返回 0。

## 5. 为什么实验额外调整 8 字节 RSP

`run_preservation_probe` 保存六个寄存器，共使 `%rsp` 减少 48 字节。普通 SysV AMD64 函数入口 `%rsp mod 16 = 8`，减 48 后仍为 8，所以不能直接发起下一个符合 ABI 的 `call`。

因此实验使用：

```asm
subq $8, %rsp
call clobber_probe
addq $8, %rsp
```

使 `call` 前 `%rsp mod 16 = 0`。

这一点非常重要：手写汇编不能只检查寄存器保存，还必须同步检查栈对齐。

## 6. 反汇编

```bash
make disasm
```

重点检查：

- `run_preservation_probe` 的六组 push/pop；
- `subq/addq $8, %rsp`；
- `clobber_probe` 只保存自己实际改动的 `RBX/R12`；
- `R10/R11` 被直接覆盖而没有恢复。

## 7. 符号

```bash
make symbols
```

检查函数和 `seen_*` 全局观察变量。

## 8. GDB

如果系统安装了 GDB：

```bash
gdb -q -x gdb.cmd ./preservation_O0
```

脚本在 `clobber_probe` 入口和返回后打印 `RBX/R12/R10/R11/RSP`。

本次验证环境没有安装 GDB，因此脚本未实际执行。

## 9. 本次实际验证

```text
GCC 14.2.0
GNU assembler 2.44

-O0 构建和运行       通过
-O2 构建和运行       通过
callee-saved 哨兵值   全部保持
R10/R11               被内层函数覆盖
AT&T 反汇编          已检查
Intel 反汇编         已检查
nm                    已检查
GDB                   未安装，未执行
```

详细分析见 [`expected-analysis.md`](expected-analysis.md)。
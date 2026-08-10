# Lab 08-2 预期分析与本次验证结果

## 1. 预期行为

`run_preservation_probe` 在调用 `clobber_probe` 前设置：

```text
RBX = 0x1111111111111111
RBP = 0x2222222222222222
R12 = 0x3333333333333333
R13 = 0x4444444444444444
R14 = 0x5555555555555555
R15 = 0x6666666666666666
R10 = 0xa0a0a0a0a0a0a0a0
R11 = 0xb0b0b0b0b0b0b0b0
```

`clobber_probe` 暂时修改 `RBX/R12`，但在返回前恢复；它直接覆盖 `R10/R11`，不恢复。

所以调用返回后预期：

```text
RBX/RBP/R12-R15 保持原哨兵值
R10 = 0xaaaaaaaaaaaaaaaa
R11 = 0xbbbbbbbbbbbbbbbb
```

## 2. 栈对齐检查

`run_preservation_probe` 作为普通 SysV AMD64 函数，在入口处 `%rsp mod 16 = 8`。

保存六个 callee-saved 通用寄存器共执行六次 `pushq`：

```text
6 * 8 = 48 bytes
48 mod 16 = 0
```

因此六次 push 后 `%rsp mod 16` 仍然是 8。为了使下一次 `call` 之前 `%rsp mod 16 = 0`，实验显式执行：

```asm
subq $8, %rsp
call clobber_probe
addq $8, %rsp
```

这样 `call` 再压入 8 字节返回地址后，`clobber_probe` 入口重新满足 `%rsp mod 16 = 8`。

## 3. 本次实际环境

```text
GCC 14.2.0
GNU assembler 2.44
```

## 4. 实际运行结果

`-O0` 与 `-O2` 两个版本均构建并运行成功，程序返回 0。

观察输出：

```text
callee-saved: rbx=0x1111111111111111 rbp=0x2222222222222222 r12=0x3333333333333333 r13=0x4444444444444444 r14=0x5555555555555555 r15=0x6666666666666666
caller-saved: r10=0xaaaaaaaaaaaaaaaa r11=0xbbbbbbbbbbbbbbbb
```

这与预期一致。

## 5. AT&T 反汇编检查

已确认 `run_preservation_probe` 中存在：

```text
push %rbx/%rbp/%r12/%r13/%r14/%r15
sub $0x8,%rsp
call clobber_probe
add $0x8,%rsp
...
pop %r15/%r14/%r13/%r12/%rbp/%rbx
ret
```

同时确认 `clobber_probe`：

```text
push %rbx
push %r12
修改 RBX/R12
修改 R10/R11
pop %r12
pop %rbx
ret
```

## 6. Intel 反汇编检查

使用：

```bash
objdump -drwC -Mintel preservation_O0
```

已确认与 AT&T 反汇编表达同一寄存器保存、恢复、对齐和调用过程。

## 7. nm 检查

已确认以下符号存在：

```text
run_preservation_probe
clobber_probe
seen_rbx
seen_rbp
seen_r12
seen_r13
seen_r14
seen_r15
seen_r10
seen_r11
```

## 8. GDB 状态

当前执行环境未安装 GDB，所以 `gdb.cmd` 只做了静态检查，没有实际执行。

不要把脚本中预期打印的寄存器值描述成 GDB 已验证结果。

## 9. 结论

实验直接说明：

```text
callee-saved 不是“硬件不会改”
而是 callee 修改后必须恢复

caller-saved 不是“callee 必须改”
而是 callee 可以改，caller 若需要旧值必须自己负责保存
```

同时说明寄存器保存操作会改变 `%rsp`，因此在包含嵌套 `call` 的手写汇编中必须同时核对栈对齐。
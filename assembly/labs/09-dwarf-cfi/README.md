# A09 实验：DWARF CFI、CFA 与 `.eh_frame`

## 1. 验证目标

本实验验证四件事：

1. `.cfi_*` 是 unwind 元数据描述，不是运行时 CPU 指令；
2. 保留 `%rbp` 的函数可以把 CFA 基准寄存器切换到 `%rbp`；
3. 不使用 `%rbp` frame pointer 的函数仍可只围绕 `%rsp` 维护完整 CFA 规则；
4. `readelf --debug-dump=frames` 能把 `.eh_frame` 中的 CIE/FDE 规则展示出来，并与真实 `push/sub/add/pop/leave/ret` 指令对应。

## 2. 文件

```text
driver.c   C caller 与结果检查
funcs.S    两个带手写 .cfi_* 的汇编函数
Makefile   构建、运行与静态检查
```

两个函数分别是：

```text
cfi_rbp_sum   经典 RBP frame
cfi_rsp_sum   不建立 RBP frame，保存 RBX 并调整 RSP
```

## 3. 构建与运行

```bash
make
make run
```

预期输出：

```text
cfi_rbp_sum=42
cfi_rsp_sum=43
```

程序正常返回 `0`。

## 4. 检查机器指令

AT&T：

```bash
objdump -drwC cfi-demo
```

Intel：

```bash
objdump -drwC -Mintel cfi-demo
```

`cfi_rbp_sum` 应观察到：

```asm
push %rbp
mov  %rsp,%rbp
sub  $0x10,%rsp
...
leave
ret
```

`cfi_rsp_sum` 应观察到：

```asm
push %rbx
sub  $0x10,%rsp
...
add  $0x10,%rsp
pop  %rbx
ret
```

注意反汇编中不会出现 `.cfi_*`，因为它们不是机器指令。

## 5. 检查 `.eh_frame`

```bash
readelf -S cfi-demo | grep -E '\.(eh_frame|debug_frame)'
readelf --debug-dump=frames cfi-demo
```

普通 x86-64 函数入口的共享规则应能看到类似：

```text
DW_CFA_def_cfa: r7 (rsp) ofs 8
DW_CFA_offset: r16 (rip) at cfa-8
```

对 `cfi_rbp_sum`，应观察到：

```text
CFA offset 变为 16
caller RBP 位于 CFA-16
CFA register 从 RSP 改为 RBP
函数尾部重新变为 RSP+8
```

对 `cfi_rsp_sum`，应观察到：

```text
push RBX 后       CFA = RSP + 16
                  caller RBX 在 CFA - 16
sub 16 后         CFA = RSP + 32
add 16 后         CFA = RSP + 16
pop RBX 后        CFA = RSP + 8
```

函数实际地址会因链接结果变化，不要把某次 FDE 的 PC 地址写成固定规则。

## 6. 符号检查

```bash
nm -n cfi-demo | grep cfi_
```

应能找到：

```text
cfi_rbp_sum
cfi_rsp_sum
```

## 7. 本次实际验证结果

验证环境：

```text
GCC 14.2.0
GNU binutils 2.44
```

本次实际执行：

```text
构建                         通过
运行                         通过，exit 0
cfi_rbp_sum                  42
cfi_rsp_sum                  43
AT&T objdump                 已检查
Intel objdump                已检查
readelf -S                   已确认 .eh_frame/.eh_frame_hdr
readelf --debug-dump=frames  已核对 CIE/FDE 与 CFA 变化
nm                           已检查函数符号
GDB                          当前环境未安装，未执行动态 backtrace
```

## 8. 观察重点

不要只记 `.cfi_def_cfa_offset` 的数字。每看到一条规则，都重新回答：

```text
当前真实 RSP 是多少？
当前 CFA 希望保持在哪里？
因此 CFA = 哪个寄存器 + 多少？
caller 的旧寄存器值保存在 CFA 的什么偏移？
返回地址相对 CFA 在哪里？
```

这样才能把 unwind 元数据与真实栈变化对应起来。

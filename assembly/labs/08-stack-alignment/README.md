# Lab 08-4：普通函数调用边界的 16 字节栈对齐

## 1. 实验目标

验证普通 System V AMD64 函数调用中：

```text
call 前：              RSP mod 16 = 0
callee 入口：          (RSP + 8) mod 16 = 0
```

并观察一个 callee 如果还要继续调用其他函数，如何通过调整 `%rsp` 重新满足下一个调用点的对齐要求。

对应教程：[`../../docs/08-stack-alignment.md`](../../docs/08-stack-alignment.md)

## 2. 实验结构

```text
main
  ↓
probe_alignment
  ├─ 记录函数入口 RSP
  ├─ sub $8, RSP
  ├─ 记录 nested call 前 RSP
  ├─ call nested_probe
  ├─ add $8, RSP
  └─ 返回 73
        ↓
     nested_probe
       ├─ 记录入口 RSP
       └─ 返回 42
```

## 3. 构建与运行

```bash
make clean all
make run
```

预期两种优化级别均输出：

```text
outer entry: rsp%16=8 (rsp+8)%16=0
before nested call: rsp%16=0
nested entry: rsp%16=8 (rsp+8)%16=0
return: 73
```

程序只有在所有对齐检查和返回值检查都通过时才返回 0。

## 4. 反汇编与符号检查

```bash
make disasm
make symbols
```

重点观察 `probe_alignment`：

```asm
movq %rsp, seen_outer_entry_rsp(%rip)
subq $8, %rsp
movq %rsp, seen_pre_nested_call_rsp(%rip)
call nested_probe
addq $8, %rsp
```

同时生成 AT&T 和 Intel 两种反汇编。

## 5. GDB

当前验证环境没有安装 GDB，因此未实际执行 GDB。若环境具备 GDB，可运行：

```bash
gdb -q -x gdb.cmd ./align_O0
```

脚本用于观察 `probe_alignment` 与 `nested_probe` 入口的 `%rsp`。

## 6. 本次实际验证

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44

-O0 构建与运行             通过
-O2 构建与运行             通过
outer entry RSP mod 16     8
outer (RSP+8) mod 16       0
nested call 前 RSP mod 16  0
nested entry RSP mod 16    8
nested (RSP+8) mod 16      0
返回值                     73
AT&T 反汇编               已检查
Intel 反汇编              已检查
nm                        已检查
readelf                   已检查
GDB                       未安装，未执行
```

详细解释见 [`expected-analysis.md`](expected-analysis.md)。

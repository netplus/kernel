# Lab 07（第二部分）：indirect `call` 与函数指针

## 1. 实验目标

本实验验证 A07 的第二最小单元：x86-64 ordinary near indirect `call` 的目标解析和返回地址行为。

需要确认：

1. `call *%r12` 从寄存器读取运行时目标地址；
2. `call *memory_target_ptr(%rip)` 先从内存读取目标地址，再跳转到该地址；
3. 两种 indirect call 都把各自的下一条指令地址压入栈顶；
4. callee 入口的 `RSP` 比调用前小 8；
5. `ret` 返回后调用者的 `RSP` 恢复；
6. C 函数指针在当前 GCC `-O2` 参考输出中可以形成 `call *%rax`；
7. call 指令长度依具体编码而变化，不能把 direct `E8 rel32` 的 5 字节规则套到 indirect call。

对应教程：

[`../../docs/07-indirect-call-and-function-pointers.md`](../../docs/07-indirect-call-and-function-pointers.md)

## 2. 文件

```text
indirect_call.s       纯汇编实验：寄存器和内存两种间接调用
companion.c           C 函数指针对照代码
Makefile              构建、运行、反汇编和 C 汇编输出
 gdb.cmd               分阶段观察目标地址、RSP 和返回地址
expected-analysis.md  已验证结果和参考反汇编
```

## 3. 构建和运行

```bash
make clean all
make run
```

预期：

```text
exit status=46 (expected 46)
```

校验值来自：

```text
register-indirect target = 17
memory-indirect target   = 29
checksum                 = 46
```

程序内部还会检查两次调用返回以后 `RSP` 是否恢复，以及两个 callee 入口的 `[RSP]` 是否等于各自的 `after_*_call` 标签地址。

## 4. 反汇编

```bash
make disasm
```

重点寻找：

```asm
call *%r12
call *memory_target_ptr(%rip)
ret
```

当前参考构建的关键字节：

```text
41 FF D4             call *%r12
FF 15 disp32         RIP-relative memory-indirect call
C3                   near ret
```

对应当前实例：

```text
call *%r12                       长 3 字节
call *memory_target_ptr(%rip)    长 6 字节
```

因此两个调用保存的返回地址都仍然是“下一条指令地址”，但不能用统一的 `call_address + 5` 计算。

## 5. 符号检查

```bash
make symbols
```

重点比较：

```text
before_register_call
after_register_call
register_target
before_memory_call
after_memory_call
memory_target
memory_target_ptr
```

注意：

```text
memory_target_ptr
```

是保存函数地址的内存对象，不是 callee 本身。

## 6. C 函数指针对照

```bash
make c-asm
```

重点函数：

```text
call_function_pointer
choose_and_call
```

`companion.c` 故意在 `fn(value)` 返回以后再执行 `+1`。原因是如果直接：

```c
return fn(value);
```

优化器可能把它变成 tail call：

```asm
jmp *%reg
```

当前参考 GCC `-O2` 输出中，可以观察到真正的：

```asm
call *%rax
```

这能把“函数指针”与“indirect call”直接对应起来。

## 7. GDB 观察

如果环境安装了 GDB：

```bash
make gdb
```

脚本分别在以下位置停止：

```text
before_register_call
register_target_entry
after_register_call
before_memory_call
memory_target_entry
after_memory_call
```

应观察：

```text
调用前的目标地址
调用前 RSP
callee 入口 RSP
callee 入口 [RSP]
返回后 RSP
```

当前自动化执行环境中未安装 `gdb`，因此本次没有把 GDB 输出记作已验证结果。

## 8. 已实际验证

本实验已在 Linux x86-64 环境实际执行：

```text
as --64 -g             通过
ld                     通过
程序运行               exit status=46
nm -n                  通过
objdump AT&T           通过
GCC -O0 生成汇编       通过
GCC -O2 生成汇编       通过
GCC -O2 的 call *%rax  通过
GDB                    未安装，未执行
```

详细地址和解释见：

[`expected-analysis.md`](expected-analysis.md)

## 9. 本实验暂不覆盖

A07 还剩：

- 递归产生的多层返回地址；
- 返回地址损坏后的基本后果。

这些内容完成并复核后，才把 A07 标记为整章完成。

# Lab 07 第二部分预期分析：indirect `call`

## 1. 参考构建结果

在当前 Linux x86-64 环境中实际执行：

```text
as --64 -g -o indirect_call.o indirect_call.s
ld -o indirect-call indirect_call.o
./indirect-call
```

程序退出状态：

```text
46
```

校验值：

```text
register-indirect target result = 17
memory-indirect target result   = 29
------------------------------------
checksum                        = 46
```

失败路径固定退出 `99`。

## 2. 参考符号地址

当前参考链接结果：

```text
before_register_call    0x401010
after_register_call     0x401013
before_memory_call      0x401024
after_memory_call       0x40102a
register_target         0x401049
memory_target           0x401061
memory_target_ptr       0x402000
```

地址会因源码和工具链变化而改变，分析时应依赖符号关系，而不是死记具体地址。

## 3. 寄存器间接调用

关键反汇编：

```asm
401006: 4c 8d 25 3c 00 00 00    lea    0x3c(%rip),%r12
401010: 41 ff d4                   call   *%r12
401013: ...                        # after_register_call
```

因此当前实例中：

```text
R12 = 0x401049 = register_target
```

`call *%r12` 长度为 3 字节，因此保存的返回地址是：

```text
0x401013 = after_register_call
```

进入 `register_target_entry` 时，实验验证：

```text
[RSP] == after_register_call
```

并在 `ret` 后验证调用者的 `RSP` 恢复。

## 4. 内存间接调用

关键反汇编：

```asm
401024: ff 15 d6 0f 00 00    call *0xfd6(%rip)
                                # 0x402000 <memory_target_ptr>
40102a: ...                     # after_memory_call
```

`.rodata` 中：

```asm
memory_target_ptr:
    .quad memory_target
```

因此需要区分：

```text
memory_target_ptr 的地址 = 0x402000
[memory_target_ptr]      = memory_target 的代码地址
```

CPU 从内存读取后者作为调用目标。

当前调用指令长度为 6 字节，因此返回地址是：

```text
0x40102a = after_memory_call
```

进入 `memory_target_entry` 后实验再次验证：

```text
[RSP] == after_memory_call
```

## 5. direct/indirect 不改变返回机制

两条路径的共同结构是：

```text
调用前 RSP = S
→ call 解析目标
→ RSP = S - 8
→ [RSP] = next_RIP
→ RIP = target
→ callee
→ ret
→ RIP = [RSP]
→ RSP = S
```

差异仅在：

```text
direct call:   target 来自指令的相对位移
register call: target 来自寄存器值
memory call:   target 来自内存读取值
```

## 6. C 函数指针对照

`companion.c` 中：

```c
long result = fn(value);
return result + 1;
```

当前 GCC `-O2` 参考输出在 `call_function_pointer` 中包含：

```asm
movq %rdi, %rax
movq %rsi, %rdi
...
call *%rax
...
addq $1, %rax
ret
```

这里：

```text
RAX = fn 函数地址
call *%rax = 运行时选择目标
```

`choose_and_call` 当前参考输出会先用两个 RIP-relative `lea` 得到 `times_five` 和 `add_three` 的地址，再根据条件选择地址，最后同样执行：

```asm
call *%rax
```

## 7. 为什么示例故意在调用后 `+1`

若源代码写成：

```c
return fn(value);
```

优化器可能使用尾调用：

```asm
jmp *%rax
```

这样不会产生新的返回地址层级，因为当前函数直接把控制权交给最终 callee。

为保证本实验专门观察 indirect `call`，示例让函数调用返回后还必须执行 `+1`。这使当前 GCC `-O2` 参考构建保留 `call *%rax`。

## 8. 已验证与未验证

已实际验证：

```text
GNU as 构建                 通过
GNU ld 链接                 通过
纯汇编程序运行              exit status=46
nm -n                       通过
objdump AT&T                通过
GCC -O0/-O2 生成汇编        通过
GCC -O2 出现 call *%rax     通过
```

GDB：当前自动化环境未确认安装，因此只有在 `make gdb` 实际成功执行后，才能把 GDB 结果标记为已验证。

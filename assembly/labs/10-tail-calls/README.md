# A10 实验：尾调用与 sibling-call 优化

## 要验证的问题

当一个函数的最后动作只是把另一个函数的返回值原样返回时，优化器能否把普通的 `call target; ret` 改成直接 `jmp target`？这种变化对返回地址、`RSP` 和真实调用栈意味着什么？

实验同时设置两个控制条件：

- `non_tail_wrapper()` 在 target 返回后还要执行 `+1`，因此不能直接跳转后丢掉自己的后续工作；
- `-fno-optimize-sibling-calls` 显式关闭 GCC 的 sibling-call 优化，用于观察同一个 `tail_wrapper()` 恢复为 `call + ret`。

## 构建与运行

```bash
make clean
make all
make run
make inspect
```

## 本次实际验证环境

```text
GCC 14.2.0
GNU binutils 2.44
x86-64
```

四个二进制都实际运行通过：

```text
tail_wrapper=38
non_tail_wrapper=39
```

并以 exit 0 结束。

## 关键反汇编

`-O0` 的 `tail_wrapper()` 仍是普通调用：

```asm
call   tail_target
leave
ret
```

当前 GCC 14.2.0、`-O2` 下，`tail_wrapper()` 变成：

```asm
jmp    tail_target
```

这里没有新的 `call`，因此也不会为 `tail_target()` 再压入一层返回地址。`tail_target()` 最终执行 `ret` 时，直接消费原本属于 `tail_wrapper()` caller 的返回地址。

控制组 `non_tail_wrapper()` 在 `-O2` 下仍然是：

```asm
call   tail_target
add    $0x1,%rax
ret
```

因为 target 返回后 wrapper 还有真实工作要执行。

关闭 sibling-call 优化后：

```bash
gcc -O2 -fno-optimize-sibling-calls ...
```

同一个 `tail_wrapper()` 恢复为：

```asm
call   tail_target
ret
```

所以这里观察到的是 GCC 当前优化选项下的代码生成决策，不是 x86-64 ISA 或 SysV AMD64 ABI 强制规定“尾位置调用必须使用 jmp”。

## 栈与控制流观察点

设 caller 执行：

```asm
call tail_wrapper
```

进入 `tail_wrapper()` 时，栈顶保存的是返回 caller 的地址 `RA`。

未优化形式：

```text
caller --call--> tail_wrapper --call--> tail_target
```

第二个 `call` 会再压入一层返回地址，所以 `tail_target()` 返回到 `tail_wrapper()`，随后 wrapper 再 `ret` 回 caller。

优化形式：

```text
caller --call--> tail_wrapper --jmp--> tail_target
```

`jmp` 不压入返回地址，也不会因为跳转本身改变 `RSP`。因此 `tail_target()` 继续使用栈上的 `RA`，其 `ret` 直接返回 caller。

这也是为什么优化后的真实机器调用链中不存在一个需要再次返回到 `tail_wrapper()` 的动态 frame。

## 工具检查

本次实际执行：

```text
-O0 / -Og / -O2 构建与运行                 通过
-O2 -fno-optimize-sibling-calls            通过
AT&T objdump                               已检查
Intel objdump                              已检查
nm                                         已检查
readelf                                    已检查
GDB                                        当前环境未安装，未执行
```

`nm` 仍可看到 `tail_wrapper` 符号。符号存在只说明 ELF 中有该代码入口，不代表运行时一定会形成一个独立、可返回到的动态栈帧。

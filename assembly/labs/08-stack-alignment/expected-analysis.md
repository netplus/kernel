# Lab 08-4 结果分析

## 1. `probe_alignment` 入口

实际输出：

```text
outer entry: rsp%16=8 (rsp+8)%16=0
```

这说明 C caller 在执行 `call probe_alignment` 前满足普通 SysV AMD64 调用点的 16 字节对齐；`call` 再压入 8 字节返回地址，所以函数刚进入时 `%rsp` 指向返回地址并表现为 `8 mod 16`。

## 2. 为嵌套调用重新对齐

`probe_alignment` 执行：

```asm
subq $8, %rsp
```

实际记录：

```text
before nested call: rsp%16=0
```

因此 `call nested_probe` 执行前调用点重新达到 16 字节对齐。

这里的 `sub $8` 只是本实验的最小布局。真实函数应根据完整 frame size、保存寄存器、局部对象和 outgoing arguments 共同决定调整量。

## 3. `nested_probe` 入口

实际输出：

```text
nested entry: rsp%16=8 (rsp+8)%16=0
```

这再次显示 `call` 压入 8 字节返回地址后的入口状态，与 outer callee 完全一致。

## 4. 返回路径

`nested_probe` 返回 42。`probe_alignment` 在 `call` 返回后：

```asm
addq $8, %rsp
addq $31, %rax
ret
```

最终返回 73。程序能正常回到 C caller 且所有检查通过，也验证了本实验对 `%rsp` 的减法和加法严格配对，没有破坏原返回地址位置。

## 5. 反汇编检查

AT&T 反汇编中关键序列为：

```asm
mov    %rsp,seen_outer_entry_rsp(%rip)
sub    $0x8,%rsp
mov    %rsp,seen_pre_nested_call_rsp(%rip)
call   nested_probe
add    $0x8,%rsp
add    $0x1f,%rax
ret
```

Intel 语法显示相同机器语义，只改变操作数和内存表达形式。

## 6. `-O0` 与 `-O2`

手写汇编 callee 的关键序列不随 C 编译优化级别变化。实际 `-O0` 与 `-O2` 两个程序均通过相同对齐检查，说明 caller 无论如何优化，都必须在跨 ABI 函数边界时满足同一调用约定。

## 7. 边界

本实验不验证：

```text
Red Zone
需要 32/64 字节对齐的栈上传递向量参数
可变参数函数
动态栈分配 alloca/VLA
系统调用、异常或中断入口
```

这些机制不能从本实验简单外推。

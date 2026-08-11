# A09 实验：leaf function、frame pointer omission 与 Red Zone

本实验用同一段 C 代码构造三个版本，分别观察：

1. 默认 `-O2` 下省略 frame pointer 且使用 Red Zone；
2. `-fno-omit-frame-pointer` 下保留 `%rbp` frame；
3. `-mno-red-zone` 下省略 `%rbp`，但通过显式调整 `%rsp` 建立局部栈空间。

这样可以避免把“没有 `%rbp`”“没有修改 `%rsp`”和“没有使用栈”混成同一件事。

## 1. 构建与运行

```bash
make clean
make
make check
```

本次维护时实际使用：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
GNU objdump 2.44
```

实际结果：

```text
leaf_slots(7,11)=26
leaf_slots(7,11)=26
leaf_slots(7,11)=26
```

三个程序均以退出码 0 结束。

## 2. 为什么使用 `volatile long slots[2]`

如果只写普通局部整数，`-O2` 很可能把它们完全保留在寄存器中，无法观察局部内存布局。

这里使用：

```c
volatile long slots[2];
```

强制保留对两个槽的实际内存访问。实验关注的是这些访问相对于 `%rsp/%rbp` 的位置，不是推荐业务代码使用 `volatile`。

## 3. 默认 `-O2`

查看：

```bash
objdump -dr leaf-default
objdump -dr -Mintel leaf-default
```

本次 GCC 14.2.0 的 `leaf_slots` 关键反汇编：

```asm
add    $0x3,%rdi
add    $0x5,%rsi
mov    %rdi,-0x18(%rsp)
mov    %rsi,-0x10(%rsp)
mov    -0x18(%rsp),%rax
mov    -0x10(%rsp),%rdx
add    %rdx,%rax
ret
```

观察点：

- 没有 `push %rbp`；
- 没有 `mov %rsp,%rbp`；
- 没有 `sub/add %rsp`；
- 仍然访问 `%rsp` 以下的内存。

这是省略 frame pointer 并使用 SysV AMD64 Red Zone 的 leaf function。

## 4. 强制保留 frame pointer

查看：

```bash
objdump -dr leaf-frame-pointer
objdump -dr -Mintel leaf-frame-pointer
```

关键序列：

```asm
push   %rbp
...
mov    %rsp,%rbp
mov    %rdi,-0x10(%rbp)
mov    %rsi,-0x8(%rbp)
...
pop    %rbp
ret
```

这里 `%rbp` 恢复为稳定 frame base，但仍没有额外 `sub %rsp`。leaf function 仍可以利用 Red Zone，因此“保留 frame pointer”不等于“必须显式分配局部栈空间”。

## 5. 禁用 Red Zone

查看：

```bash
objdump -dr leaf-no-red-zone
objdump -dr -Mintel leaf-no-red-zone
```

关键序列：

```asm
sub    $0x18,%rsp
...
mov    %rdi,(%rsp)
mov    %rsi,0x8(%rsp)
...
add    $0x18,%rsp
...
ret
```

这里仍然没有 `%rbp` frame，但因为不能使用 Red Zone，编译器必须先移动 `%rsp`，为局部对象建立实际可用空间。

本次编译结果选择 24 字节。这个具体数字是当前 GCC 和当前函数布局的代码生成结果，不是 ABI 固定常量。

## 6. 对比表

```text
版本                        RBP frame   Red Zone   显式 RSP 分配
-O2                         否          是         否
-O2 -fno-omit-frame-pointer 是          是         仅 push/pop RBP
-O2 -mno-red-zone           否          否         sub/add 24
```

判断一个函数栈布局时，应分别检查这三件事，而不是只搜索 `push %rbp`。

## 7. 额外验证

本次还实际执行：

```bash
nm -n leaf-default | grep ' leaf_slots$'
readelf -h leaf-default
```

确认：

```text
leaf_slots 为文本符号
ELF Class: ELF64
Machine: Advanced Micro Devices X86-64
```

AT&T 与 Intel 两种反汇编都已检查。

## 8. GDB 观察建议

当前验证环境没有安装 GDB，因此未执行单步。

在具备 GDB 的环境中，可以：

```gdb
break leaf_slots
run
info registers rsp rbp rip eflags
x/8gx $rsp-0x40
si
```

重点比较三个二进制中：

- 函数入口 `%rsp`；
- `%rbp` 是否改变；
- 局部内存写入前后 `%rsp` 是否改变；
- `ret` 前 `%rsp` 是否恢复到入口状态。

## 9. 本实验验证的结论

```text
frame pointer omission 不等于不使用栈
Red Zone 与 frame pointer omission 是独立机制
省略 RBP 后仍可以用 RSP 相对地址描述当前 frame
禁用 Red Zone 后 leaf function 仍可省略 RBP，只需显式调整 RSP
```

下一步将进入 DWARF CFI，解释没有传统 `%rbp` 链时，调试器和 unwind 工具怎样描述 caller 状态。

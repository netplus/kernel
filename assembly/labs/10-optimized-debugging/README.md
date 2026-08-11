# A10 实验：优化代码的调试限制

## 要验证的问题

本实验使用同一段带局部变量的 C 代码，对比 `-O0`、`-Og` 和 `-O2`，验证三件事：

1. 源码行与机器指令地址之间不是固定的一行一指令关系；
2. 优化后源码变量可能位于寄存器中，也可能由 DWARF expression 计算得到，而不是拥有固定栈槽；
3. 调试信息可以描述某些已经优化变形后的值，但不能把机器执行重新变成源码逐语句执行。

## 构建与运行

```bash
make clean
make all
make run
make inspect
```

本次实际验证环境：

```text
GCC 14.2.0
GNU binutils 2.44
x86-64
```

三个版本均实际运行通过：

```text
debug_limits=120
```

并以 exit 0 结束。

## `-O0`：源码对象大多有直接存储位置

`debug_limits()` 在本次 `-O0` 中建立 `%rbp` frame，并为参数与局部变量分配明确栈槽。例如：

```asm
mov    %rdi,-0x28(%rbp)
mov    %rsi,-0x30(%rbp)
...
mov    %rax,-0x8(%rbp)    # x
...
mov    %rax,-0x10(%rbp)   # y
...
mov    %rax,-0x18(%rbp)   # z
...
mov    %rax,-0x20(%rbp)   # w
```

这种布局容易把源码变量与内存位置对应起来，但它是当前无优化代码生成结果，不是 C 语言或 ABI 要求。

## `-Og/-O2`：同一源码收敛为寄存器数据流

本次 `-Og` 与 `-O2` 的 `debug_limits()` 都只有五条算术指令加 `ret`：

```asm
add    $0x3,%rdi
lea    (%rsi,%rsi,4),%rax
add    %rdi,%rax
add    %rax,%rax
sub    %rdi,%rax
ret
```

因此 `x/y/z/w` 不再各自拥有一个固定栈槽。真实执行只维护满足最终语义所需的寄存器 value。

## 行号表不是“一行源码对应一条机器指令”

`readelf --debug-dump=decodedline debug-O2` 的实际结果中，同一个地址 `0x401174` 同时出现了多条源码行 view：

```text
line 6   0x401174
line 7   0x401174
line 8   0x401174
line 9   0x401174
```

随后真正执行的地址又依次映射到第 7、8、9 行。

这说明 DWARF line table 描述的是“某地址范围与源码位置之间的调试映射”，而不是源语言逐语句执行日志。优化器可以重排、合并或提前计算表达式，因此多个源码位置可以共享同一个机器地址/view。

## 变量 location 也不一定是物理存储位置

`debug-O2` 的 DWARF 中，`x/y/z/w` 都仍有 `DW_TAG_variable`，但 location 不全是简单寄存器或栈地址。

例如实际 `readelf --debug-dump=loc` 中：

```text
x: DW_OP_reg5 (rdi)

y: DW_OP_breg4 (rsi): 0; DW_OP_lit5; DW_OP_mul; DW_OP_stack_value

z: DW_OP_breg4 (rsi): 0; DW_OP_lit5; DW_OP_mul;
   DW_OP_breg5 (rdi): 0; DW_OP_plus; DW_OP_stack_value

w: ... ; DW_OP_lit1; DW_OP_shl; DW_OP_stack_value
```

其中 `DW_OP_stack_value` 这里表示前面的 DWARF expression 产生的是变量的值，而不是一个需要再次解引用的内存地址。也就是说，调试器有时可以根据当前寄存器和表达式重建源码变量，而不是从某个固定变量槽读取它。

## 为什么仍然会出现“optimized out”或无法稳定单步

即使调试信息很丰富，也有硬边界：

- 某个值如果已经死亡，并且编译器没有留下可重建它的 location expression，调试器就无法恢复；
- 多条源码语句可能合并为一条或几条机器指令，源码级 `step` 因而不能保证每条语句都停一次；
- 一条机器指令可能同时服务于多个源码表达式；
- 指令可能被提前、延后、合并或完全删除；
- 调试器显示的“变量值”可能来自 DWARF 计算，而非当前存在一个同名机器存储对象。

因此优化代码调试的正确模型是：**机器指令是真实执行过程，DWARF 提供源码到机器状态的有限映射。**

## 工具检查

本次实际执行：

```text
-O0 / -Og / -O2 构建与运行        通过
AT&T objdump                     已检查
Intel objdump                    已检查
readelf decoded line             已检查
readelf debug info               已检查
readelf location lists           已检查
nm / readelf -h                  已检查
GDB                              当前环境未安装，未执行
```

GDB 未安装，因此本次没有把某个具体 GDB 版本的 `step`、`print` 或 `optimized out` 输出写成既定结果；实验保留了足够的 DWARF 与反汇编检查入口，可在有 GDB 的环境继续观察。

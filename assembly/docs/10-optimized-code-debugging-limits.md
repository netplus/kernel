# 第 10 课（第五部分）：优化代码的调试限制

前四部分已经说明，优化器会内联函数、消除重复计算、缩短或合并 live range，并重新安排机器级 value 的存放位置。这样做不会改变程序可观察语义，但会改变一个重要事实：**源码中的“变量、语句和函数边界”不再能一一对应到机器指令。**

本节讨论这种偏离对调试意味着什么，并通过 DWARF 行号表和变量 location list 做实际验证。

## 1. 问题背景：调试器看到的是两层世界

调试优化后的程序时，要区分两层：

```text
真实执行层
    RIP、寄存器、内存、RFLAGS、真实机器指令

调试映射层
    DWARF 行号、变量 location、调用帧、源码名称
```

CPU 只执行第一层。第二层由编译器生成，用来帮助调试器把机器状态解释回源码概念。

因此，“源码第 8 行正在执行”更准确的含义通常是：当前 RIP 落在 DWARF line table 映射到第 8 行的地址范围，而不是 CPU 内部存在一个“第 8 行”状态。

## 2. `-O0` 为什么通常容易调试

在本节实验中：

```c
long x = a + 3;
long y = b * 5;
long z = x + y;
long w = z * 2;
return w - x;
```

GCC 14.2.0、`-O0 -g -fno-omit-frame-pointer` 生成的代码为参数和局部变量保留了多个 `%rbp` 相对栈槽。

例如可以实际观察到：

```asm
mov %rdi,-0x28(%rbp)
mov %rsi,-0x30(%rbp)
...
mov %rax,-0x8(%rbp)
mov %rax,-0x10(%rbp)
mov %rax,-0x18(%rbp)
mov %rax,-0x20(%rbp)
```

在这种代码里，源码对象、机器存储位置和语句顺序比较接近，所以断点、单步和变量查看通常更直观。

但这仍然只是当前代码生成策略，不是 C 语言或 SysV AMD64 ABI 要求“每个局部变量都必须有栈槽”。

## 3. `-Og/-O2`：源码对象可以完全没有独立栈槽

同一函数在本次 `-Og` 与 `-O2` 下都收敛为：

```asm
add    $0x3,%rdi
lea    (%rsi,%rsi,4),%rax
add    %rdi,%rax
add    %rax,%rax
sub    %rdi,%rax
ret
```

这里没有 `x/y/z/w` 四个独立机器对象。

真实数据流是：

```text
RDI: a -> x
RSI: b 持续保留，必要时用于重建 y
RAX: y -> z -> w -> return value
```

所以如果调试器还能显示 `y/z/w`，并不意味着这些变量一定真的存放在某个寄存器或栈槽中。

## 4. DWARF line table 描述的是映射，不是执行日志

本次 `readelf --debug-dump=decodedline debug-O2` 中，同一个地址 `0x401174` 可以同时对应第 6、7、8、9 行的不同 view。

随后的地址又分别对应后续源码行。

这是优化后很重要的现象：

```text
源码语句 A
源码语句 B
源码语句 C
       ↓
可能部分合并、提前计算或共享机器指令
       ↓
同一机器地址可能对应多个源码位置
```

因此源码级单步不能被理解为“每执行一条 C 语句就一定停一次”。真正可精确定义的是机器级单步：RIP 执行一条真实指令后前进到下一条指令。

## 5. DWARF location 可以描述“如何求值”，而不是“变量在哪里”

`debug-O2` 的 `.debug_info` 中仍然存在 `x/y/z/w` 的 `DW_TAG_variable`。

但 `readelf --debug-dump=loc` 显示，变量 location 不只是简单地址。例如 `y` 可以被描述为：

```text
DW_OP_breg4 (rsi): 0
DW_OP_lit5
DW_OP_mul
DW_OP_stack_value
```

它表达的是：使用当前 `%rsi` 的值乘以 5，并把结果当作变量值。

类似地，`z` 和 `w` 也可以由当前寄存器通过 DWARF expression 重建。

这说明调试信息中的“location”不一定意味着物理存储地址；它也可以是一段求值规则。

## 6. `DW_OP_stack_value` 不等于程序运行栈

这里尤其容易误解。

`DW_OP_stack_value` 中的 “stack” 指 DWARF expression evaluator 的求值栈，不是 `%rsp` 指向的 x86 运行时栈。

它表示：表达式栈顶现在是变量的值本身，而不是变量所在地址。

因此不能把：

```text
DW_OP_stack_value
```

解释成“变量被 spill 到进程栈上”。这是两个完全不同的概念。

## 7. 为什么有些变量仍会 `optimized out`

调试器能显示一个变量，必须有足够信息把当前机器状态映射回该源码值。

如果某个 value 已经死亡，并且 DWARF 没有留下有效 location 或可重建表达式，那么调试器就不能凭空恢复原值。

优化越激进，越可能出现：

- 变量从未拥有独立存储；
- 多个变量共享同一寄存器的不同时间段；
- 某些值在最后一次使用后立即死亡；
- 某段地址范围内没有有效变量 location；
- 表达式被常量传播、合并或彻底删除。

此时 `optimized out` 的本质不是调试器“找不到变量名”，而是当前机器状态和调试元数据不足以恢复那个源码 value。

## 8. 调试优化代码时什么最可信

优先级可以这样理解：

```text
第一层：真实机器状态
RIP / 寄存器 / 内存 / RFLAGS / 指令

第二层：ABI 和控制流事实
call、ret、jmp、栈布局、保存规则

第三层：DWARF 映射
源码行、变量 location、inline frame 等

第四层：源码级直觉
“这一行应该先执行”“这个变量应该一直存在”
```

越靠前越接近 CPU 的真实执行。

调试复杂优化代码时，应经常同时使用：

```text
objdump -dr --source --line-numbers
readelf --debug-dump=decodedline
readelf --debug-dump=info
readelf --debug-dump=loc
GDB disassemble / stepi / info registers
```

而不是只依赖源码窗口中的高亮行。

## 9. `RSP`、`RFLAGS` 与控制流仍按机器指令理解

优化不会改变 x86 指令的架构语义。

本实验 `-O2` 的 `debug_limits()` 是 leaf function，没有建立自己的 stack frame，也没有改变 `%rsp`。函数入口到 `ret` 之间，`%rsp` 保持指向 caller 的返回地址。

算术方面：

- `add` 和 `sub` 会更新算术 `RFLAGS`；
- `lea` 不更新 `RFLAGS`；
- 本函数没有后续条件分支消费这些 flags，所以中间 flags 不构成需要保留的程序语义。

源码行号或变量 location 的变化不会改变这些架构事实。

## 10. GDB 能做什么，不能保证什么

在有 GDB 的环境中，可以继续检查：

```gdb
break debug_limits
run
info registers
info locals
disassemble /m debug_limits
step
stepi
```

但需要明确：

- `stepi` 以真实机器指令为单位；
- `step` 依赖源码映射，优化后可能跨过、重复落在或看似跳回某些源码行；
- `print x` 成功并不意味着 `x` 有固定存储槽；
- `print x` 失败也不代表程序语义错误，只可能说明当前没有可恢复的调试 location。

本次执行环境未安装 GDB，因此没有把某个具体 GDB 版本的交互输出记录为课程事实。

## 11. 本节实验

实验入口：[`../labs/10-optimized-debugging/`](../labs/10-optimized-debugging/)

本次实际验证环境：

```text
GCC 14.2.0
GNU binutils 2.44
x86-64
```

实际完成：

```text
-O0 / -Og / -O2 构建运行        通过
三个版本输出                     debug_limits=120
AT&T / Intel objdump             已检查
DWARF decoded line               已检查
DWARF debug info                 已检查
DWARF location lists             已检查
nm / readelf -h                  已检查
GDB                              当前环境未安装，未执行
```

## 12. 本节完成后应能回答

1. 为什么优化后源码行和机器指令不再一一对应？
2. 为什么一个源码变量可能没有独立物理存储？
3. DWARF location expression 与真实寄存器/栈槽是什么关系？
4. `DW_OP_stack_value` 为什么不是“变量在 x86 栈上”？
5. 为什么调试器有时能重建一个并不存在独立存储的变量？
6. 为什么某些变量会显示为 `optimized out`？
7. 调试优化代码时，为什么应优先回到真实机器指令、寄存器和内存状态？

# 第 7 课（第二部分）：间接 `call` 与函数指针

第一部分已经确认：near `call` 会把下一条指令地址压入当前栈，然后把控制流转移到目标；near `ret` 再从当前栈顶恢复返回地址。本节继续研究另一个问题：**如果调用目标不是写死在指令中的符号，而是运行时才确定，CPU 如何完成函数调用？**

这就是 indirect call（间接调用）。函数指针、回调表、虚函数分派和很多内核操作表最终都会涉及类似控制流。

本节仍然只讨论 x86-64 用户态实验中的普通 near call，不展开完整 System V AMD64 ABI，也不提前进入内核函数指针安全机制。

## 1. direct call 与 indirect call 的区别

第一部分的 direct call：

```asm
    call worker
```

目标由指令中的 PC-relative 位移确定。当前实验里对应典型的：

```text
E8 rel32
```

而 indirect call 的目标来自寄存器或内存，例如：

```asm
    call *%r12
```

或者：

```asm
    call *function_ptr(%rip)
```

两者真正不同的是 **目标地址从哪里来**。

它们保存返回地址的基本机制没有改变：

```text
return_address = next_RIP
RSP = RSP - 8
[RSP] = return_address
RIP = runtime_target
```

因此，不能把“间接调用”理解成另一套返回机制。变化的是目标解析，返回仍然依赖栈中的返回地址。

## 2. 寄存器间接调用

考虑：

```asm
    leaq worker(%rip), %r12
    call *%r12
```

第一条指令先把 `worker` 的地址放入 `R12`。

执行 `call *%r12` 时，可以把关键过程理解为：

```text
target = R12
return_address = call 后的下一条指令地址
RSP -= 8
[RSP] = return_address
RIP = target
```

这里的 `R12` 保存的是 **代码地址**，而不是函数执行结果。

如果运行时把另一个合法函数地址放进 `R12`，同一条 `call *%r12` 就会调用另一个目标。

这正是函数指针能够进行运行时分派的机器层基础。

## 3. 内存间接调用

另一种形式是：

```asm
    call *memory_target_ptr(%rip)
```

假设：

```asm
memory_target_ptr:
    .quad memory_target
```

这里需要特别注意“地址”和“地址处的数据”的区别。

CPU 不是跳到 `memory_target_ptr` 本身，而是：

```text
1. 根据 RIP-relative 寻址得到 memory_target_ptr 的内存地址；
2. 从该内存位置读取 8 字节目标地址；
3. 把这个读取出来的值作为新的 RIP；
4. 同时照常保存 call 后的返回地址。
```

可以简化为：

```text
target = [memory_target_ptr]
call target
```

这与 A02 中“地址”和“解引用”的区别完全一致。

## 4. 为什么函数指针自然对应 indirect call

C 代码：

```c
typedef long (*operation_fn)(long);

long call_function_pointer(operation_fn fn, long value)
{
    long result = fn(value);
    return result + 1;
}
```

`fn` 的值是一个运行时函数地址。

编译器无法把调用固定编码为：

```asm
call add_three
```

因为调用者传入的可能是 `add_three`，也可能是 `times_five`。

在本实验当前 GCC `-O2` 输出中，函数指针被放入 `RAX`，随后出现：

```asm
    call *%rax
```

因此可以建立对应关系：

```text
C 函数指针的值
→ 某个可执行代码地址
→ 放入寄存器或内存
→ indirect call 读取该地址
→ CPU 跳到运行时选中的目标
```

## 5. 运行时选择函数

考虑：

```c
operation_fn fn = choose_times_five ? times_five : add_three;
long result = fn(value);
```

当前 GCC `-O2` 参考输出会先形成两个候选地址：

```asm
leaq times_five(%rip), %rdx
leaq add_three(%rip), %rax
```

然后根据条件选择最终地址，最后：

```asm
call *%rax
```

这里需要区分两个阶段：

```text
选择目标地址
≠
执行调用
```

前一阶段只是在数据层面决定“哪个地址”；真正改变 `RIP` 并压入返回地址的是后面的 `call`。

## 6. indirect call 仍然保存下一条指令地址

本节纯汇编实验分别使用：

```asm
before_register_call:
    call *%r12
after_register_call:
```

和：

```asm
before_memory_call:
    call *memory_target_ptr(%rip)
after_memory_call:
```

两个 callee 入口都会检查：

```text
[RSP] == 对应 call 后面的标签地址
```

也就是说，无论目标来自：

```text
rel32
寄存器
内存
```

普通 near `call` 都需要保存返回位置。

这是后续 `ret` 能够回到正确调用点的基础。

## 7. 编码长度不能从 direct call 套用过来

第一部分实验中的：

```asm
call direct_target
```

使用 `E8 rel32`，当前实例长度为 5 字节。

本节实际反汇编中：

```asm
call *%r12
```

编码为：

```text
41 FF D4
```

长度为 3 字节。

而 RIP-relative 内存间接调用：

```asm
call *memory_target_ptr(%rip)
```

当前实例编码为：

```text
FF 15 disp32
```

长度为 6 字节。

所以：

```text
返回地址 = 下一条指令地址
```

是稳定的架构语义；

```text
返回地址 = call 地址 + 5
```

只是某一种具体编码下的结果，不能推广到所有 `call`。

## 8. `RSP` 与栈内存变化

假设寄存器间接调用前：

```text
RSP = S
R12 = target
```

执行：

```asm
call *%r12
```

进入目标后：

```text
RSP = S - 8
[RSP] = return_address
RIP = target
R12 = target（call 本身不会因为“使用它作为目标”而自动改写它）
```

如果 callee 不额外改变栈，执行：

```asm
ret
```

则：

```text
RIP = return_address
RSP = S
```

因此 direct/indirect 的差异不改变这一基本栈模型。

## 9. `RFLAGS` 与目标寄存器

普通 near indirect `call` 的主要可见作用仍然集中在：

```text
RIP
RSP
[RSP] 返回地址
```

它不会像 `cmp/add/test` 那样为了算术或比较语义产生新的 `ZF/CF/SF/OF` 结果。

同时，目标寄存器只是提供地址。例如：

```asm
call *%r12
```

不意味着 `R12` 自动变成返回值寄存器，也不意味着 `call` 自动清空 `R12`。

函数参数和返回值由 ABI 规定，属于 A08 的内容。

## 10. 一个重要的编译器优化：尾调用

如果 C 代码只有：

```c
return fn(value);
```

优化器可能发现当前函数在调用 `fn` 后没有任何工作，于是把：

```text
call fn
ret
```

优化成：

```asm
jmp *%reg
```

这叫 tail call / sibling call optimization。

因此，本节 `companion.c` 故意写成：

```c
long result = fn(value);
return result + 1;
```

这样调用返回后仍然必须执行 `+1`，当前 GCC `-O2` 参考构建才能稳定展示真正的：

```asm
call *%rax
```

这也说明：**阅读优化后的汇编时，不能假设源代码中的“函数调用”一定表现为机器指令 `call`。**

A10 会系统学习这种优化现象。

## 11. 与后续内核阅读的关系

Linux 内核中大量使用函数指针，例如各种操作表和回调。

本节只需要建立机器层认识：

```text
结构体/表中保存函数地址
→ 代码读取函数地址
→ indirect call
→ callee 执行
→ ret 回到原调用点
```

具体某个内核子系统为什么设计这些回调、对象生命周期如何管理、是否受并发保护，应在对应领域再分析，不在本节展开。

## 12. 实验观察路径

配套实验：

[`../labs/07-indirect-call/`](../labs/07-indirect-call/)

重点验证两条路径：

```text
register_target 地址 → R12 → call *%r12
```

以及：

```text
memory_target 地址 → memory_target_ptr → call *memory_target_ptr(%rip)
```

两个 callee 都会验证自己的栈顶返回地址，然后 `ret` 回到对应调用点。

C 对照代码则用于观察函数指针在 GCC `-O0/-O2` 下的具体实现。

## 13. 本节完成后应能回答

1. direct call 和 indirect call 真正的差异是什么？
2. `call *%r12` 中 `R12` 保存的是什么？
3. `call *memory_target_ptr(%rip)` 为什么包含一次内存解引用？
4. indirect call 保存返回地址的机制是否与 direct call 不同？
5. 为什么不能把“call 固定 5 字节”当成通用规则？
6. C 函数指针为什么通常会落到 indirect branch/call？
7. 为什么优化器有时会把函数指针调用变成 `jmp *%reg`？

下一最小单元继续学习递归产生的多层返回地址和栈深度变化。
# 第 8 课（第五部分）：128-byte Red Zone

A08 前四部分已经建立了参数寄存器、寄存器保存责任、栈上传参和 16 字节调用边界。本节继续处理一个只在特定调用约定和执行环境中成立的优化：**System V AMD64 ABI 的 Red Zone**。

理解 Red Zone 时要特别区分三层规则：

```text
x86-64 指令集本身        不定义 Red Zone
System V AMD64 ABI       定义用户态普通函数的 128-byte Red Zone
Linux kernel 5.10 x86-64 明确用 -mno-red-zone 编译内核 C 代码
```

因此，Red Zone 不是 CPU 自动保护的一块内存，也不是“x86-64 的固定栈结构”。它首先是一条 ABI 约定。

## 1. 问题背景：为什么 leaf function 还要调整 `%rsp`

假设一个很小的 leaf function 需要几个临时的 8 字节槽，但它不调用其他函数、不需要把这些临时值保存到函数返回之后，而且所需空间很小。如果没有额外约定，它通常需要先调整 `%rsp`，再在返回前恢复 `%rsp`。SysV AMD64 ABI 因此允许函数利用当前 `%rsp` 以下的一小段保留区域，减少这种开销。

## 2. ABI 规则：当前 `%rsp` 以下 128 字节

SysV AMD64 psABI 规定，当前 `%rsp` 以下的 128 字节区域保留给当前函数临时使用；signal 或 interrupt handler 不应修改这一区域。这个区域称为 Red Zone。

如果函数刚进入时 `%rsp = S`，那么它的 Red Zone 是：

```text
[S - 128, S - 1]
```

`[S]` 是返回地址，不属于 Red Zone。

## 3. Red Zone 不会改变 `%rsp`

函数可以在不改变 `%rsp` 的情况下访问这些临时槽，例如：

```asm
movq $11, -8(%rsp)
movq $22, -16(%rsp)
movq -8(%rsp), %rax
addq -16(%rsp), %rax
ret
```

这里没有 `subq $N,%rsp` / `addq $N,%rsp`。这也是为什么 Red Zone 最常与 leaf function 联系在一起：leaf function 不再执行嵌套 `call`，更容易保证这些临时槽只在当前调用实例内部使用。

## 4. 为什么不能跨函数调用依赖 Red Zone

psABI 的关键限制是：Red Zone 适合保存 **not needed across function calls** 的临时数据。调用动作本身就会改变栈边界。

假设当前函数入口 `%rsp = S`，它在 `S-16` 保存一个临时值。callee 入口通常是 `RSP mod 16 = 8`，为了发起一个正常的嵌套调用，可以先执行：

```asm
subq $8, %rsp
call target
```

`subq $8,%rsp` 后调用点为 `S-8`；near `call` 再压入 8 字节返回地址，于是：

```text
RSP = S - 16
[RSP] = return address
```

原来位于 `S-16` 的 Red Zone 临时值已经被返回地址覆盖。因此“Red Zone 数据不应跨函数调用继续依赖”是一条真实的生命周期约束，而不是编译器习惯。

## 5. leaf function 并不是形式上的唯一条件

常见说法是“Red Zone 只给 leaf function 用”，这有助于入门，但不够精确。ABI 的真正约束是：**放在 Red Zone 中的数据不能是跨函数调用仍然需要的值。**

理论上，一个会调用其他函数的函数也可以只在两个调用之间短暂使用当前 Red Zone；但一旦数据要存活到调用之后，就应放入正式栈帧、callee-saved 寄存器或其他具有明确生命周期的位置。基础课程中，把 Red Zone 首先理解为 leaf function 的小型临时栈空间最稳妥。

## 6. Red Zone 与 16 字节栈对齐不是一回事

上一部分讨论的是函数调用边界：

```text
call 前              RSP mod 16 = 0
callee 入口          (RSP + 8) mod 16 = 0
```

Red Zone 讨论的是当前 `%rsp` 以下 128 字节能否作为临时空间。二者有关联，但解决不同问题。Red Zone 不会取消调用前的栈对齐要求。

## 7. 编译器如何使用 Red Zone

在允许 Red Zone 的用户态 SysV 环境中，编译器经常把 leaf function 的小型局部对象或 spill 槽放在 `%rsp` 的负偏移处，而不建立传统栈帧。

本节实验中的 C leaf function 在当前 GCC 14.2、`-O2` 下生成了 `-0x28(%rsp)`、`-0x20(%rsp)`、`-0x18(%rsp)`、`-0x10(%rsp)` 等访问，没有 `sub %rsp`。

这里必须区分：

```text
“允许使用 Red Zone”       是 ABI 规则
“具体用了哪些负偏移”       是当前编译器和优化结果
```

不能把某次反汇编中的具体槽位置写成 ABI 固定布局。

## 8. Linux kernel 5.10 为什么不能使用用户态 Red Zone

Linux v5.10 的 x86-64 构建规则位于：

```text
arch/x86/Makefile
```

64 位分支中明确加入：

```make
KBUILD_CFLAGS += -mno-red-zone
```

也就是说，x86-64 内核 C 代码由构建系统明确禁止使用 Red Zone。普通用户态 SysV 函数依赖 ABI 对 signal/interrupt handler 的约束，而 Linux 内核代码运行在自己的异常、中断、NMI、调度等执行环境中，不能套用用户态 Red Zone 假设。

因此，看到用户态 leaf function 的 `-8(%rsp)`、`-32(%rsp)`，不能推导出内核函数也能无条件使用 `%rsp` 以下空间。

## 9. 这不是 CPU 的硬件保护区

CPU 不知道“Red Zone”这个 ABI 名称，也不会给 `[RSP-128,RSP-1]` 增加特殊保护属性。CPU 只执行普通内存访问、`push`、`call`、中断/异常入口等动作。哪一段栈空间由谁保持不变，是软件 ABI 和具体运行环境共同约定的。

因此 Red Zone 应归类为：

```text
不是：x86-64 ISA 固定规则
不是：页表权限机制
不是：Linux 内核自动保存区
而是：System V AMD64 用户态函数 ABI 约定
```

## 10. 本节实验

实验入口：[`../labs/08-red-zone/`](../labs/08-red-zone/)

实验包含三个观察面：

```text
red_zone_leaf
    手写汇编直接使用 -8/-16/-120(%rsp)
    整个函数保持 RSP 不变

red_zone_call_boundary
    在入口 RSP-16 保存哨兵
    准备嵌套 call 对齐
    call 的返回地址覆盖该槽

compiler_leaf
    观察 GCC -O2 是否直接使用 RSP 负偏移
```

实际结果：

```text
asm leaf result=66
red-zone value survived nested call=0
compiler leaf result=50
```

并已检查 AT&T/Intel 两种反汇编、`nm` 和 `readelf`。当前环境没有 GDB，因此 GDB 脚本未执行。

## 11. 常见误区

- Red Zone 不是 128 字节“额外栈帧”；它不会自动修改 `%rsp`。
- Red Zone 中的数据不是无条件不会被覆盖；尤其不能依赖其跨普通函数调用存活。
- Red Zone 不属于所有 x86-64 软件；它属于 SysV AMD64 ABI。
- Linux v5.10 x86-64 内核代码明确用 `-mno-red-zone` 禁用这种编译器行为。
- 看到 `%rsp` 负偏移不一定就是 Red Zone；必须确认函数是否调整过 `%rsp`、目标 ABI 和编译选项。

## 12. 本节完成后应能回答

1. Red Zone 位于哪个地址范围？
2. 为什么它是 ABI 规则而不是 x86-64 ISA 规则？
3. leaf function 为什么可能不需要 `sub/add %rsp`？
4. 为什么 Red Zone 中的数据不能跨普通函数调用依赖？
5. Red Zone 与 16 字节调用边界分别解决什么问题？
6. 为什么一次具体编译产生的负偏移不能当成 ABI 固定布局？
7. Linux kernel 5.10 x86-64 在哪里明确禁用了 Red Zone？
8. 为什么不能把用户态 Red Zone 模型直接套到内核异常、中断和系统调用入口？

下一部分进入 A08 的小结构体与大结构体参数/返回规则。

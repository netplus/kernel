# 第 8 课（第六部分）：聚合类型的参数与返回规则

前五部分已经建立了标量 INTEGER 参数、返回寄存器、寄存器保存责任、栈上传参、16 字节对齐和 Red Zone。本节处理下一层问题：**C 结构体按值传递时，ABI 如何决定它进入寄存器还是内存，以及结构体返回值从哪里返回。**

本节先只建立基础课程需要的核心模型，不一次展开所有 SSE/X87/vector 细节。

## 1. 问题背景：结构体不能只看“大小”

对于标量整数，参数寄存器规则比较直接。但结构体可能同时包含多个字段，ABI 不能简单规定“结构体都放栈上”。SysV AMD64 ABI 会先对聚合类型做 classification，再根据分类结果分配寄存器或内存位置。

因此分析一个结构体参数时，应按下面顺序思考：

```text
字段布局与对齐
→ 按 eightbyte 分类
→ 得到 INTEGER / SSE / MEMORY 等类别
→ 再分配参数或返回位置
```

这里的 **eightbyte** 是 ABI 分类算法使用的 8 字节单元，不等同于“每 8 字节一定占一个通用寄存器”。

## 2. 基础分类模型

SysV AMD64 psABI 将整数、指针等标量归入 INTEGER 类；浮点标量主要进入 SSE 类。聚合类型会递归分类其字段，并对各 eightbyte 的类别进行合并。

基础课程先记住三个最重要结论：

1. 只包含普通整数/指针字段、布局自然对齐的小结构体，常可被拆成一个或两个 INTEGER eightbyte；
2. 如果聚合最终得到 MEMORY 类，则参数在栈上传递；
3. MEMORY 类返回值不是从 `%rax/%rdx` 直接装下整个对象，而由 caller 提供返回对象地址。

不能把“`sizeof(struct) <= 16` 就一定走寄存器”写成规则。字段类别、对齐和 post-merge cleanup 都会影响结果。

## 3. 两个 64 位整数：`INTEGER, INTEGER`

本节实验定义：

```c
struct pair_u64 {
    uint64_t a;
    uint64_t b;
};
```

对象大小为 16 字节，两段 eightbyte 都只包含 `uint64_t`，因此分类为：

```text
第 1 个 eightbyte：INTEGER
第 2 个 eightbyte：INTEGER
```

当寄存器资源可用时，按值参数使用两个 INTEGER 参数寄存器。对于本实验只有这一个参数，因此：

```text
p.a -> %rdi
p.b -> %rsi
```

如果函数返回同样的 `struct pair_u64`，两个 INTEGER eightbyte 分别从：

```text
result.a <- %rax
result.b <- %rdx
```

返回。

这不是 C 语言本身规定的布局，而是当前目标平台的 SysV AMD64 ABI 规则。

## 4. 三个 64 位整数：为什么转为 MEMORY

实验同时定义：

```c
struct big3_u64 {
    uint64_t a;
    uint64_t b;
    uint64_t c;
};
```

这是三个普通 INTEGER eightbyte，总大小 24 字节。按照聚合分类后的 cleanup 规则，这种普通三-eightbyte 聚合不能作为 `INTEGER, INTEGER, INTEGER` 直接占用三个通用寄存器，而是整体按 MEMORY 传递。

于是 `big_bump(struct big3_u64 p)` 的参数位于 caller 构造的 outgoing argument area。callee 刚进入、尚未调整 `%rsp` 时，本实验观察到：

```text
[RSP]      返回地址
[RSP + 8]  p.a
[RSP + 16] p.b
[RSP + 24] p.c
```

这几个偏移是“当前函数入口没有再修改 `%rsp`”这个实验实现下的直接结果；建立栈帧后必须重新按新的基准计算。

## 5. MEMORY 类结构体如何返回

对于 MEMORY 类返回值，caller 先分配结果对象，再把结果地址作为一个隐藏参数传给 callee。SysV AMD64 ABI 对这种返回约定的关键点是：

```text
%rdi = caller 提供的结果对象地址
callee 把各字段写到 [%rdi + offset]
%rax = 同一个结果对象地址
```

因此，对：

```c
struct big3_u64 big_bump(struct big3_u64 p);
```

callee 同时面对两种位置：

```text
%rdi              隐藏的返回对象指针
8(%rsp)..24(%rsp) 按 MEMORY 传入的显式结构体参数
```

隐藏返回指针会占用一个 INTEGER 参数寄存器，但它和“结构体参数在栈上”是两个独立规则。

## 6. 本节实验

实验入口：[`../labs/08-aggregate-abi/`](../labs/08-aggregate-abi/)

实验使用 **C caller + 手写汇编 callee**，避免只根据编译器反汇编猜测 ABI：

```text
pair_bump
    输入：RDI=11, RSI=22
    输出：RAX=12, RDX=24

big_bump
    输入：RDI=隐藏返回对象地址
          [RSP+8]=33, [RSP+16]=44, [RSP+24]=55
    输出：写回 34,46,58
          RAX=原隐藏返回对象地址
```

实际在当前环境使用 GCC 14.2 / binutils 2.44 验证：

```text
-O0：通过，程序退出码 0
-O2：通过，程序退出码 0
输出：
pair=12,24
big=34,46,58

objdump AT&T：已检查
objdump Intel：已检查
nm：已检查
readelf：已检查
GDB：当前环境未安装，未执行
```

## 7. 架构、ABI 与编译器实现要分开

本节规则属于 **System V AMD64 ABI**，不是 x86-64 指令集本身。CPU 并不知道 C 的 `struct`，只看到寄存器、内存和指令。

同样，某次 GCC 生成的临时栈槽、寄存器搬运顺序或优化形态也不是 ABI 固定规则。ABI 只约束跨函数边界必须观察到的接口状态。

## 8. 常见误区

- `sizeof(struct) <= 16` 不意味着结构体无条件使用寄存器；必须经过 ABI 分类。
- 大结构体参数“在内存中传递”不等于传入一个 C 指针；按值参数仍然是对象值，只是 caller 把值放到参数栈区。
- MEMORY 类返回的隐藏指针是 ABI 添加的调用接口细节，不是 C 源码里显式声明的第一个参数。
- `%rax/%rdx` 返回两个 INTEGER eightbyte 只适用于对应分类结果，不能推广到任意 16 字节对象。
- 本节的 `8(%rsp)`、`16(%rsp)`、`24(%rsp)` 只针对 callee 入口尚未调整 `%rsp` 的观察点。

## 9. 本节完成后应能回答

1. 为什么结构体参数不能只按 `sizeof` 判断寄存器或栈？
2. eightbyte classification 在调用约定中解决什么问题？
3. `struct { uint64_t a, b; }` 为什么可以用 `%rdi/%rsi` 传入、`%rax/%rdx` 返回？
4. 三个 `uint64_t` 的 24 字节普通结构体为什么转为 MEMORY？
5. MEMORY 类按值参数与“传指针”有什么区别？
6. 大结构体返回时隐藏 `%rdi` 指针是谁提供、callee 如何使用、为什么 `%rax` 还要返回该地址？

下一最小单元应继续补充 **混合 INTEGER/SSE 聚合**，验证结构体中整数与 `double` 同时存在时如何跨通用寄存器和 XMM 寄存器传递；完成这一点后再判断 A08 是否达到整章验收标准。

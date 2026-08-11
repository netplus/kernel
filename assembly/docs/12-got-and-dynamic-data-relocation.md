# A12 第二部分：GOT、GOTPCREL 与动态数据符号解析

A12 第一部分已经说明：如果指令和目标对象属于同一 ELF 映像，并且二者一起移动，那么 x86-64 可以把地址关系编码成 RIP-relative 位移，使代码不依赖固定装载基址。

但动态链接又增加了一个问题：**编译 `consumer.o` 时，`shared_value` 的最终运行时地址可能根本不属于当前映像，也可能由动态链接器根据符号解析规则选择。** 这时，代码不能简单假定“目标对象和本映像一起平移”。Global Offset Table（GOT）就是解决这一类间接地址绑定问题的核心机制之一。

本节只讨论数据符号和 GOT。函数调用的 PLT、`JUMP_SLOT` 与 lazy binding 放到 A12 后续单元。

## 1. 问题背景：RIP-relative 只能直接表达已知相对关系

假设 `consumer.c` 中有：

```c
extern int shared_value;

int read_shared(void)
{
    return shared_value + 1;
}
```

而真正的定义在另一个共享对象中：

```c
int shared_value = 41;
```

编译 `consumer.o` 时，编译器只知道 `shared_value` 是一个外部对象，并不知道它最终会被装载到哪个虚拟地址。

如果直接生成：

```asm
mov shared_value(%rip), %eax
```

那么这条指令要求 `shared_value` 与当前指令之间存在一个可在最终链接时确定、并且运行时保持不变的 `disp32` 关系。对于由动态链接器解析的外部或可抢占符号，这个前提并不成立。

因此需要把问题拆成两步：

```text
当前代码 -> 本映像中的一个固定位置
这个固定位置 -> 运行时真正的 shared_value 地址
```

第一步可以继续使用 RIP-relative；第二步由动态链接器在装载时填写。这个中间位置就是 GOT slot。

## 2. GOT 的基本模型

可以把 GOT 简化理解成一个“运行时地址表”。每个需要通过 GOT 间接访问的动态符号，可以对应一个表项：

```text
           RIP-relative
代码 ----------------------> GOT slot
                               |
                               | 64-bit address
                               v
                         shared_value
```

在 x86-64 上，典型访问过程是：

```asm
mov shared_value@GOTPCREL(%rip), %rax
mov (%rax), %eax
```

第一条指令不是读取 `shared_value` 的值，而是从 GOT slot 取出 `shared_value` 的运行时地址；第二条指令才真正读取整数对象。

因此必须区分三个量：

1. 当前指令地址；
2. GOT slot 的地址；
3. `shared_value` 对象本身的地址。

GOT 的意义不是“消除 relocation”，而是把必须在运行时确定的绝对地址写入可写数据表，而不是反复修改只读代码页。

## 3. `GOTPCREL` 的含义

x86-64 ELF ABI 定义了 GOT-relative relocation。概念上，`R_X86_64_GOTPCREL` 让链接器计算：

```text
G + GOT + A - P
```

其中：

- `P`：relocation field 的地址；
- `A`：addend；
- `G`：目标符号对应 GOT entry 在 GOT 中的偏移；
- `GOT`：GOT 基址。

结果仍然是一个 PC-relative 位移，所以机器指令可以通过 `%rip + disp32` 找到本映像中的 GOT slot。

当前 GNU binutils 2.44 实验中没有直接显示 `R_X86_64_GOTPCREL`，而是显示：

```text
R_X86_64_REX_GOTPCRELX shared_value - 4
```

这是允许 linker 在条件满足时进一步放松（relax）的 GOTPCREL 变体。对于本节要建立的基本模型，关键点不变：**relocation 指向的是“如何通过 PC-relative 方式找到 GOT entry”，而不是直接把外部对象地址编码进指令。**

不要把某一版 GCC/binutils 恰好选择 `GOTPCREL`、`GOTPCRELX` 或 `REX_GOTPCRELX` 写成架构恒定规则。应以实际 `.o` 的 `readelf -Wr` / `objdump -dr` 为准。

## 4. 本节实验中的对象文件

实验使用：

```c
extern int shared_value;

__attribute__((noinline)) int read_shared(void)
{
    return shared_value + 1;
}
```

并使用：

```bash
gcc -O0 -fPIC -c consumer.c -o consumer.o
```

当前 GCC 14.2.0 / binutils 2.44 生成的 `read_shared()` 关键指令是：

```asm
mov 0x0(%rip), %rax
mov (%rax), %eax
add $0x1, %eax
```

`objdump -dr consumer.o` 在第一条 `mov` 的位移字段旁显示：

```text
R_X86_64_REX_GOTPCRELX shared_value-0x4
```

这里存在两次内存语义：

- 第一次 `mov` 读取 GOT slot，得到 `shared_value` 的地址；
- 第二次 `mov` 解引用该地址，读取 `shared_value` 的 32 位值。

这也是为什么 GOT 数据访问通常比同一映像内可直接 RIP-relative 的本地对象多一层间接。

## 5. 从 `.o` relocation 到最终 PIE

实验把 `shared_value` 放进 `libprovider.so`，再把 `consumer.o` 链接进 PIE `got_demo`。

最终 `readelf -Wr got_demo` 中可以看到：

```text
R_X86_64_GLOB_DAT shared_value + 0
```

当前实验对应的 relocation offset 是 `0x3fc8`。`readelf -S` 同时显示该地址落在 `.got` 区域。

这两类 relocation 的职责不同：

```text
consumer.o 中的 GOTPCRELX
    ↓
告诉静态链接器：指令怎样找到 GOT slot

最终 PIE 中的 GLOB_DAT
    ↓
告诉动态链接器：运行时把 shared_value 的解析结果写入这个 GOT slot
```

所以从编译到运行需要连接两次“绑定”：

```text
机器指令 --静态链接--> GOT slot
GOT slot  --动态链接--> 符号最终地址
```

这是理解 GOT 最重要的工作模型。

## 6. 最终反汇编怎样验证 GOT 间接访问

当前实验的最终 PIE 中，`read_shared()` 为：

```asm
mov 0x2e5e(%rip), %rax   # 3fc8 <shared_value@Base>
mov (%rax), %eax
add $0x1, %eax
```

第一条指令中的 `disp32` 已由静态链接器确定，因为 GOT slot 属于当前 PIE，它和代码一起移动，二者距离固定。

但 `0x3fc8` 这个 GOT slot 里的 8 字节内容需要在运行时根据 `shared_value` 的动态符号解析结果填写。于是：

- 代码页中的 RIP-relative 位移不需要因装载基址变化而重新改写；
- GOT 中保存的指针可以由动态加载器写入真实运行时地址。

## 7. `R_X86_64_GLOB_DAT` 在本模型中的作用

对于本实验，最终 ELF 的 `.rela.dyn` 中包含：

```text
R_X86_64_GLOB_DAT shared_value + 0
```

本节只需要掌握它的直接作用：动态链接器解析 `shared_value` 后，把解析得到的地址写到 relocation 指定的位置，即相应 GOT slot。

这里不展开完整的 ELF loader/dynamic linker 内部算法，也不把 glibc loader 的实现路径写成 Linux kernel 5.10 内核路径。动态链接器主要运行在用户态；Linux 内核负责建立进程映像并把控制交给 ELF interpreter，后续如果进入 Linux 5.10 ELF 装载源码章节，再按 5.10 源码单独核验。

## 8. 可抢占符号为什么需要这种间接层

ELF 动态链接允许某些 global/default-visibility 符号在运行时根据查找范围解析到另一个定义。编译当前共享对象时，不能总是假定一个外部全局符号最终就是“本文件附近那个地址”。

GOT 把这种不确定性集中到数据表：

```text
代码只知道 GOT slot 在哪里
动态链接器决定 slot 最后指向谁
```

因此需要把“位置无关”和“符号可抢占/动态解析”区分开：

- RIP-relative 解决的是当前位置到本映像某地址之间的相对寻址；
- GOT 解决的是目标真实地址需要在运行时绑定的问题；
- dynamic relocation 负责把运行时解析结果写入 GOT 等需要修正的位置。

## 9. 寄存器、RFLAGS 和控制流

以实验中的核心序列为例：

```asm
mov shared_value@GOTPCREL(%rip), %rax
mov (%rax), %eax
add $1, %eax
```

执行状态可以逐步描述为：

1. 第一条 `mov` 计算 GOT slot 地址并读取其中 64 位指针，写入 `%rax`；`mov` 不修改算术状态标志；
2. 第二条 `mov` 把 `%rax` 当作地址，读取 32 位整数到 `%eax`；写 `%eax` 会清零 `%rax` 高 32 位，这发生在地址已经完成使用之后；`mov` 仍不修改算术状态标志；
3. `add $1, %eax` 计算返回值，并按加法结果更新 `CF/ZF/SF/OF` 等算术标志；
4. 函数随后通过 `ret` 返回调用者，控制流机制与普通函数相同。

GOT 不引入新的 CPU 执行模式，它只是改变了“地址如何得到”。

## 10. 实验验证路径

实验目录：[`../labs/12-got-data-access/`](../labs/12-got-data-access/)

按下面顺序观察：

```bash
make
make run
make inspect
```

重点核对：

1. `consumer.o` 中 `shared_value` 是 undefined symbol；
2. `consumer.o` 的数据引用使用 `GOTPCREL` 家族 relocation；
3. 最终 PIE 有 `.got` 和 `.rela.dyn`；
4. `.rela.dyn` 中存在针对 `shared_value` 的 `R_X86_64_GLOB_DAT`；
5. 最终 `read_shared()` 先从 GOT 取地址，再解引用该地址；
6. 程序实际输出 `got_result=42`。

## 11. 常见误区

### 误区一：GOT 里保存的是变量值

通常不是。本实验的 GOT slot 保存的是 `shared_value` 的**地址**；变量值 `41` 位于 `libprovider.so` 的数据对象中。

### 误区二：用了 GOT 就没有 relocation

错误。`.o` 中需要 GOTPCREL 家族 relocation，最终动态 ELF 中还需要 `GLOB_DAT` 等 dynamic relocation 来初始化 GOT slot。

### 误区三：`@GOTPCREL` 是一次直接变量访问

错误。它定位 GOT slot。真正的数据读取还要通过 GOT slot 中的指针再次解引用。

### 误区四：所有全局变量都一定经 GOT

错误。是否能被 linker relax、符号是否本地绑定、visibility、链接方式和编译选项都会影响最终代码。课程中应观察实际 relocation 和最终反汇编，而不是用“global 就一定 GOT”代替分析。

### 误区五：GOT 和 PLT 是一回事

不是。GOT 是地址表这一基本机制；PLT 主要服务函数调用和动态符号跳转。二者会配合，但本节只完成数据 GOT 模型。

## 12. 本节形成的工作模型

完成本节后，应能够把下面的过程串起来：

```text
consumer.c 引用外部数据符号
        ↓
-fPIC 编译
        ↓
指令以 RIP-relative 方式定位 GOT slot
        ↓
.o 记录 GOTPCREL 家族 relocation
        ↓
静态链接器确定代码 -> GOT slot 的位移
        ↓
最终 ELF 保留 GLOB_DAT dynamic relocation
        ↓
动态链接器解析 shared_value
        ↓
真实地址写入 GOT slot
        ↓
运行时先取 GOT 指针，再读取 shared_value
```

下一最小单元进入 PLT：解释外部函数调用为什么通常不按数据符号的两次 `mov` 方式处理，以及 `PLT32`、`.plt`、`.got.plt` 和 `JUMP_SLOT` 如何协作。
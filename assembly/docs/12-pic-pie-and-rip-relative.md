# A12 第一部分：位置无关代码、PIE 与 RIP-relative 寻址

A11 已经说明了 ELF section、符号解析和 relocation。接下来要解决一个更直接的问题：**如果同一个可执行映像每次被装载到不同虚拟地址，代码中的地址引用怎样仍然保持正确？**

这就是 position-independent code（PIC）和 position-independent executable（PIE）要处理的基本问题。本节先只建立“代码为什么需要位置无关”以及“x86-64 如何利用 RIP-relative 寻址访问同一映像内的对象”这两个模型。GOT、PLT、动态符号解析和 lazy binding 放在 A12 后续部分，不在这里提前展开。

## 1. 问题背景：绝对地址把代码绑在一个装载位置上

假设一条指令需要取得某个静态对象 `local_value` 的地址。如果机器码中直接保存最终绝对地址，那么链接器必须先决定这个地址。例如：

```text
local_value -> 0x00404018
```

如果运行时整个映像仍装载在链接时假定的位置，这个常量可以工作；但如果映像整体平移到另一个基址，机器码里的绝对地址不会自动跟着平移。

因此需要区分两个概念：

- **绝对引用**：机器码中的值直接依赖目标的最终虚拟地址；
- **相对引用**：机器码保存“目标与当前位置之间的距离”。如果源和目标属于同一映像并一起平移，这个距离通常保持不变。

PIC/PIE 的核心不是“完全没有 relocation”，而是尽量避免必须因为装载基址变化而修改只读代码页的绝对地址引用。

## 2. x86-64 的 RIP-relative 基本模型

x86-64 支持 RIP-relative memory addressing。概念上可以写成：

```text
有效地址 = 下一条指令的 RIP + sign_extend(disp32)
```

AT&T 语法常见形式为：

```asm
mov local_value(%rip), %eax
lea local_value(%rip), %rax
```

这里要区分 `mov` 和 `lea`：

- `mov local_value(%rip), %eax` 读取目标地址处的数据；
- `lea local_value(%rip), %rax` 计算目标地址本身，不解引用。

`disp32` 是 32 位有符号位移。因此 RIP-relative 并不是“可以引用任意 64 位远地址”的魔法机制；目标必须落在该指令可表达的相对范围内。对同一 ELF 映像中的相邻代码和数据，这通常正是编译器和链接器希望利用的形式。

## 3. 为什么相对距离允许整个映像一起移动

假设链接完成后：

```text
指令下一条 RIP = B + 0x1100
local_value      = B + 0x4018
```

则位移为：

```text
disp = (B + 0x4018) - (B + 0x1100)
     = 0x2f18
```

如果装载基址从 `B` 改成 `B'`：

```text
(B' + 0x4018) - (B' + 0x1100) = 0x2f18
```

基址被抵消了。这是理解 PIE 的关键：**位置无关并不意味着没有地址，而是代码尽量使用不随映像整体平移而变化的关系。**

## 4. non-PIE 与 PIE 不是“是否出现 `%rip`”的简单二分

一个常见误区是：

```text
看见 %rip -> 一定是 PIE/PIC
没看见 %rip -> 一定不是 PIE/PIC
```

这个判断不成立。x86-64 编译器即使生成普通 non-PIE，也经常对数据读取使用 RIP-relative addressing，因为它本身就是高效的寻址方式。

本节实验故意同时观察两个函数：

```c
static volatile int local_value = 7;

int local_read(void)
{
    return local_value + 5;
}

uintptr_t local_address(void)
{
    return (uintptr_t)&local_value;
}
```

在当前 GCC 构建结果中，`local_read()` 在 non-PIE 和 PIE 对象里都可以使用 RIP-relative load。真正更有区分度的是“取得对象地址”这一动作：

- `-fno-pie` 对象中的 `local_address()` 使用绝对地址 relocation；
- `-fPIE` 对象中的 `local_address()` 使用 `lea disp32(%rip), %rax` 和 PC-relative relocation。

因此判断位置无关属性时，要结合编译选项、ELF 类型、relocation 和最终反汇编，而不是只搜索 `%rip`。

## 5. 实验中看到的两种 relocation

当前实验环境中，non-PIE 对象的 `local_address()` 为：

```asm
mov $0x0, %eax
```

`objdump -dr` 在立即数字段旁显示：

```text
R_X86_64_32 .data
```

这表示链接器需要把 `.data` 的最终地址写入这个 32 位字段。这里写 `%eax` 还会按 x86-64 规则把 `%rax` 高 32 位清零。

PIE 对象的同一函数为：

```asm
lea 0x0(%rip), %rax
```

对应：

```text
R_X86_64_PC32 .data-0x4
```

它与 A11 的 `S + A - P` 模型一致。链接器最终填入的是相对位移，而不是把运行时绝对虚拟地址写进这条指令。

这里的 `-4` 仍然来自 x86-64 PC-relative relocation 字段位置与“下一条指令 RIP”之间的关系；A11 已经详细推导，本节不重复展开。

## 6. PIE 的 ELF 类型与 ASLR 的关系

使用：

```bash
gcc -fno-pie -no-pie ... -o nonpie
gcc -fPIE -pie ... -o pie
```

在当前 GNU toolchain 环境中，`readelf -h` 显示：

```text
nonpie -> Type: EXEC
pie    -> Type: DYN (Position-Independent Executable file)
```

`ET_DYN` 不只用于共享库；PIE executable 也使用这种 ELF 类型，使整个主程序映像可以按可重定位基址装载。

必须把 PIE 和 ASLR 区分开：

- PIE 是程序代码/链接布局允许映像移动的性质；
- ASLR 是操作系统运行时选择随机化地址布局的策略；
- PIE 为主可执行映像的基址随机化提供前提，但“本次地址是否变化”仍取决于运行环境的 ASLR 设置。

本节实验在当前 Linux 环境连续运行三次，non-PIE 中 `local_value` 地址保持 `0x404018`，PIE 中地址分别落在不同基址；这是一项**环境观测结果**，不是 ELF ABI 保证每次执行地址必然不同。

## 7. 架构规则、工具链选择和操作系统策略要分开

### x86-64 架构规则

架构定义 RIP-relative addressing 的编码和执行语义，包括以“下一条指令 RIP”加有符号 `disp32` 得到有效地址。

### ELF / ABI 与链接规则

ELF 定义文件类型、section、symbol 和 relocation 的表示方式；x86-64 ELF relocation 定义 `R_X86_64_PC32` 等 relocation 的计算语义。

### 编译器和链接器策略

GCC 是否选择某种寻址形式、`-fPIE`/`-fno-pie` 如何影响代码生成，以及 linker 怎样消费 relocation，属于工具链实现和选项选择。

### Linux 运行时策略

Linux 的 ELF 装载和 ASLR 决定映像实际映射到哪里。A12 当前只观测用户态结果；涉及 Linux kernel 5.10 的具体 ELF 装载源码时，必须在后续相应章节按 5.10 源码重新核验，不能用这里的工具链现象反推内核调用路径。

## 8. 寄存器、RFLAGS 和控制流观察

以 PIE 中：

```asm
lea local_value(%rip), %rax
ret
```

为例：

- `lea` 读取当前指令编码中的相对位移并计算有效地址；
- 结果写入 `%rax`；
- `lea` 不读取 `local_value` 的内容；
- `lea` 不修改算术状态标志，因此这里不产生供后续条件分支使用的新 `CF/ZF/SF/OF`；
- `ret` 从当前栈顶取得返回地址并恢复到调用者控制流。

对于 `local_read()` 的 RIP-relative `mov`：

- CPU 先计算目标有效地址；
- 再从该地址读取 32 位 `local_value`；
- 写入 32 位目的寄存器时按 x86-64 规则清零对应 64 位寄存器高 32 位；
- 单纯的 `mov` 不修改算术状态标志。

这说明“位置无关”改变的是地址形成方式，不会额外引入一种特殊的 CPU 执行模式。

## 9. 本节实验验证什么

实验目录：[`../labs/12-pic-pie-rip-relative/`](../labs/12-pic-pie-rip-relative/)

需要完成四组观察：

1. `readelf -h`：比较 `ET_EXEC` 与 PIE 的 `ET_DYN`；
2. `objdump -dr`：比较 `local_address()` 的绝对立即数和 RIP-relative `lea`；
3. `readelf -Wr`：比较 `R_X86_64_32` 与 `R_X86_64_PC32`；
4. 连续运行程序：观察当前环境中 non-PIE 与 PIE 地址是否随执行改变。

## 10. 常见误区

### 误区一：PIC 就是“没有 relocation”

错误。编译阶段产生的 `.o` 仍然需要 relocation。关键在于 relocation 最终能否在链接阶段解决，以及运行时是否需要修改代码中的绝对地址字段。

### 误区二：RIP-relative 访问的是 `%rip` 寄存器当前保存的指令地址

需要更精确。x86-64 RIP-relative effective address 使用的是**下一条指令地址**作为基准，因此 A11 中 PC-relative relocation 的 addend 和字段位置必须配合这个规则。

### 误区三：non-PIE 不会出现 RIP-relative 指令

错误。non-PIE 也可以大量使用 RIP-relative data access。

### 误区四：PIE 等于 ASLR

错误。PIE 是可重定位执行映像的代码/链接属性；ASLR 是运行时地址布局随机化策略。

### 误区五：本节已经解释了所有外部符号访问

没有。本节只处理同一映像内可直接 PC-relative 表达的对象。跨共享对象的全局数据、外部函数、symbol interposition、GOT、PLT 和 lazy binding 是 A12 后续单元。

## 11. 本节形成的工作模型

完成这一节后，应能够把下面的过程连起来：

```text
源代码取得本地对象地址
        ↓
non-PIE 可以生成依赖最终绝对地址的字段
PIE 倾向生成不依赖映像基址的 PC-relative 关系
        ↓
.o 中记录 relocation
        ↓
linker 根据最终布局填写字段
        ↓
运行时整个 PIE 映像可以换基址
        ↓
同一映像内部的相对距离仍保持不变
```

下一最小单元将进入 GOT：解释为什么“同一映像内部 PC-relative”还不足以处理可被动态链接器解析或替换的外部/可抢占符号。
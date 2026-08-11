# x86-64 PC-relative relocation：从 `UND` 符号到最终位移

前一部分解决了 symbol resolution：多个输入文件出现同名符号时，链接器如何确定最终使用哪个 definition。确定目标是谁之后，还剩一个不同的问题：输入 `.o` 中的机器指令在编译时并不知道目标的最终地址，链接器必须把指令中的某个字段改写成最终值。这一步就是 relocation。

本节只讨论 x86-64 静态链接中最基础、最容易直接观察的 PC-relative relocation，并通过 `R_X86_64_PC32` 与 `R_X86_64_PLT32` 建立完整工作模型。GOT、PLT 的动态链接用途留到 A12。

## 1. 问题背景：机器指令已经生成，但地址还没有确定

考虑：

```c
extern long target(long);
extern long ext_data;

long call_target(long x)
{
    return target(x + ext_data) + 1;
}
```

单独编译 `caller.c` 时，汇编器可以确定：

- `mov`、`add`、`call` 等 opcode；
- 指令在当前 `.text` section 内的相对位置；
- 哪个指令字段需要一个 32-bit displacement。

但它不能确定：

- `ext_data` 最终位于哪个虚拟地址；
- `target()` 最终位于哪个虚拟地址；
- 因而也不能计算从当前指令到目标的最终相对位移。

所以 `.o` 同时保存两类信息：

```text
机器指令中的占位字段
+
relocation entry
```

relocation entry 告诉链接器：哪个字段需要修补、使用哪个 symbol、采用哪种 relocation 公式、addend 是多少。

## 2. 先区分 symbol resolution 与 relocation

这两个阶段容易混在一起：

```text
symbol resolution
    target 这个名字最终对应哪个 definition？

relocation
    已知 definition 后，caller.o 中哪几个字节应写成什么值？
```

在实验的 `caller.o` 中，`readelf -Ws` 可以看到：

```text
ext_data  GLOBAL UND
target    GLOBAL UND
```

而 `readelf -Wr caller.o` 同时能看到针对这两个 symbol 的 relocation record。`UND` 说明当前 object 没有 definition；relocation 则说明当前 object 的某处代码引用了该 symbol，并且该机器字段需要稍后修补。

## 3. 实际的 `.rela.text`

当前实验使用 GCC 14.2.0 / GNU binutils 2.44，执行：

```bash
readelf -Wr caller.o
```

关键结果：

```text
Relocation section '.rela.text' contains 2 entries:
Offset 0x0f  R_X86_64_PC32   ext_data - 4
Offset 0x1e  R_X86_64_PLT32  target   - 4
```

这里需要逐项解释。

### 3.1 `Offset`

`Offset` 不是“整条指令的地址”，而是 relocation 要修改的字段在目标 section 中的位置。

`objdump -dr caller.o` 显示：

```asm
c:  48 8b 15 00 00 00 00    mov 0x0(%rip),%rdx
    f: R_X86_64_PC32 ext_data-0x4
```

指令从 `0x0c` 开始，前 3 字节是 opcode/ModRM，后面的 4 字节 displacement 从 `0x0f` 开始，所以 relocation offset 是 `0x0f`。

同理：

```asm
1d: e8 00 00 00 00          call 22
    1e: R_X86_64_PLT32 target-0x4
```

`call rel32` 的 opcode `e8` 位于 `0x1d`，真正需要写入的 4-byte relative displacement 从 `0x1e` 开始。

## 4. RELA 与显式 addend

x86-64 ELF 通常使用 `SHT_RELA` relocation section。本实验对应的是 `.rela.text`。

RELA entry 中 addend 独立保存在 relocation record 中，因此可以使用经典记号：

```text
S = symbol value/address
A = addend
P = address of the relocation field
```

对于本节的 `R_X86_64_PC32` 与 `R_X86_64_PLT32`，理解当前实验最重要的公式是：

```text
S + A - P
```

结果最终写入 relocation field 所占的 32-bit signed 值。

这里讨论的是 ELF x86-64 relocation 语义；CPU 本身并不读取 ELF relocation table。链接完成以后，CPU 只看到已经被写好的机器指令字节。

## 5. 为什么 addend 是 `-4`

这是 PC-relative relocation 中最值得真正算明白的一点。

x86-64 的 RIP-relative memory operand 和 `call rel32` 在执行时都以“下一条指令地址”为基准：

```text
目标地址 = next_RIP + sign_extend(rel32)
```

但 ELF relocation 公式中的 `P` 指向的是 **relocation field 自身的起始地址**。

本实验的 relocation field 恰好都是 4 字节，因此：

```text
next_RIP = P + 4
```

我们希望 CPU 最终得到：

```text
S = (P + 4) + displacement
```

整理：

```text
displacement = S - P - 4
             = S + (-4) - P
```

因此 assembler 为这两个 relocation 记录 `A = -4`。

需要注意，这里的 `-4` 不是“PC-relative relocation 永远减 4”的抽象规则。它来自当前机器编码中 relocation field 与 next RIP 之间的具体几何关系。

## 6. `R_X86_64_PC32`：RIP-relative 数据访问

实验中的：

```asm
mov 0x0(%rip),%rdx
```

对应：

```text
R_X86_64_PC32 ext_data - 4
```

链接后变成：

```asm
401159: 48 8b 15 b8 2e 00 00  mov 0x2eb8(%rip),%rdx
                                      # 404018 <ext_data>
```

此时 CPU 不知道也不关心 `ext_data` 这个 ELF symbol 名称。它只执行：

```text
next RIP + sign-extended 0x2eb8
```

并得到最终地址 `0x404018`。

因此要区分：

```text
ELF symbol / relocation
    链接工具用来生成最终机器字节的元数据

RIP-relative addressing
    CPU 执行最终机器指令时采用的寻址方式
```

## 7. `R_X86_64_PLT32`：函数调用的相对位移

`caller.o` 中：

```asm
1d: e8 00 00 00 00          call 22
    1e: R_X86_64_PLT32 target-0x4
```

链接后的当前实验结果：

```asm
40116a: e8 06 00 00 00      call 401175 <target>
```

因为 `provider.o` 在同一个最终 executable 内提供 `target` definition，链接器能够把这个调用直接解析成对 `target` 的相对调用。

一个很常见的误解是：

> 看到 `R_X86_64_PLT32` 就说明 CPU 最终一定会先跳到 PLT。

这不成立。relocatable object 中使用 `PLT32` 表示该调用具有允许经 PLT 解析的链接语义；最终链接器若能绑定到本地可直接到达的 definition，可以把 displacement 直接写成目标函数地址。本实验正是这种情况。

动态链接场景中的 PLT/GOT 行为在 A12 单独展开。

## 8. 32-bit signed displacement 的范围

`PC32`/`PLT32` 最终写入的是 32-bit 字段，CPU 将其按有符号相对位移使用。因此目标必须能由该编码表达。

这里要区分两个位宽：

```text
目标虚拟地址
    x86-64 下通常是 64-bit 地址语义

指令中的 rel32/disp32
    只有 32 bit，并按有符号数扩展
```

所以“运行在 x86-64”并不意味着每条直接相对调用都携带一个 64-bit absolute target address。

## 9. relocation 被谁消费

完整主线是：

```text
compiler / assembler
    生成 caller.o
    留下 instruction placeholder + symbol + relocation entry

linker
    解析 symbol
    决定 section/output layout
    计算 S、A、P
    把 S + A - P 写入 relocation field

CPU
    只执行最终机器指令
    不读取 .rela.text
```

因此 relocation 是构建期机制，不是每次函数调用时都执行一次的运行时地址计算流程。

## 10. 本节实验

实验目录：

```text
assembly/labs/11-pc-relative-relocations/
```

已实际执行：

```bash
make clean
make check
make inspect
```

当前环境结果：

```text
result=37
```

并确认：

```text
caller.o:
  ext_data -> R_X86_64_PC32, addend -4
  target   -> R_X86_64_PLT32, addend -4

linked executable:
  ext_data access 已具有实际 RIP-relative disp32
  target call 已具有实际 rel32
```

实验同时使用 `readelf -Wr`、`readelf -Ws`、`objdump -dr` 与最终 executable 的 `objdump -d` 交叉核对。

## 11. 常见误区

### 11.1 relocation offset 就是指令地址

不是。它指向需要重写的 relocation field；对 `call rel32`，通常是 opcode 后面的 4-byte 位移字段。

### 11.2 `UND` 意味着链接器不知道怎样处理这个引用

不是。`UND` 只表示当前 object 没有 definition。只要其他链接输入提供可接受 definition，symbol resolution 后 relocation 就可以继续完成。

### 11.3 CPU 在运行时计算 `S + A - P`

不是。这个公式是链接器理解 ELF relocation 的模型。CPU 运行时只处理最终编码里的相对位移。

### 11.4 `PLT32` 必然产生一次 PLT 跳转

不是。是否最终经过 PLT 取决于最终链接结果和符号绑定条件。本实验最终是直接调用本 executable 内的 `target`。

### 11.5 64-bit 体系结构意味着这里写入 64-bit 位移

不是。本实验的两类 relocation 都写入 32-bit signed PC-relative field。

## 12. 到这里建立的 A11 工作模型

现在 A11 已经可以把前三层连接成第四层：

```text
section
    保存机器代码与数据

symbol table
    给实体命名并描述 binding / definition 状态

symbol resolution
    在多个输入 object 中确定名字最终绑定到谁

relocation
    根据最终布局，把引用位置的机器字段修补为可执行的值
```

下一部分应继续沿这个模型进入静态链接的整体过程：输入 section 如何合并到 output section，symbol value 如何随布局确定，以及 relocation 如何在最终链接中被消费。
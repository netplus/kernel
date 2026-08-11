# 静态链接的基本过程：从多个 `.o` 到最终 ELF

前四部分已经分别建立了 section、symbol table、symbol resolution 和 relocation 的模型。本节把它们连成一次完整的静态链接过程：链接器如何读取多个 relocatable object，安排 output section，确定最终 symbol value，再消费 relocation，生成 CPU 可以直接执行的 ELF。

这里的“静态链接”指链接器在构建期把本实验所需的目标文件和符号全部解析进最终 `ET_EXEC`。实验不依赖 libc，也不引入动态解释器，因此可以直接观察最小的链接主线。静态库 archive 的成员提取规则、链接脚本细节以及 GOT/PLT 留到后续章节。

## 1. 问题背景：单个 `.o` 只有局部布局

编译一个 C 文件得到 `ET_REL` 时，编译器和汇编器只能确定本 object 内部的布局。例如两个目标文件都可以拥有自己的：

```text
.text
.data
.bss
.symtab
.rela.text
```

它们各自的 `.text` 都可以从 section offset 0 开始。此时并不存在“`part1.o` 的 `.text` 一定在 `part2.o` 前面”这样的全局地址关系。

因此链接前只能确定：

- 某个定义属于哪个 input section；
- 某个 symbol 在该 input section 内的位置；
- 哪个机器字段引用了尚未得到最终地址的 symbol；
- 对这个字段应采用哪种 relocation 公式。

链接器随后把这些局部信息组合成全局布局。

## 2. 本节实验结构

实验由三个输入 object 组成：

```text
start.o
    _start
    调用 combine()

part1.o
    left()
    left_data = 10

part2.o
    combine()
    right_data = 20
    调用 left()
```

执行路径为：

```text
_start
  -> combine(7)
       -> left(7)
            -> 7 + left_data(10) = 17
       -> 17 + right_data(20) = 37
  -> sys_exit(37)
```

`_start` 直接使用 Linux x86-64 `exit` 系统调用退出，因此最终 ELF 不需要 libc，也不需要动态加载器。

## 3. 第一阶段：读取 input section

分别执行：

```bash
readelf -SW start.o
readelf -SW part1.o
readelf -SW part2.o
```

可以看到三个 object 都有自己的 section table。对本实验最重要的是：

```text
start.o   -> .text
part1.o   -> .text + .data
part2.o   -> .text + .data
```

这里的 `.text`、`.data` 是 **input section**。它们仍属于各自的 `ET_REL` 文件。

链接器并不是把三个 ELF 文件简单首尾拼接，而是按照输出布局规则把兼容的 input section 放入相应的 **output section**。

## 4. 第二阶段：建立 output section 布局

本实验使用：

```bash
ld -o linked.elf -e _start -Map=linked.map start.o part1.o part2.o
```

GNU ld 2.44 生成的 map 中，关键内容为：

```text
.text          0x401000  0x18 start.o
.text          0x401018  0x18 part1.o
.text          0x401030  0x24 part2.o

.data          0x402000  0x08 part1.o
.data          0x402008  0x08 part2.o
```

这几行非常重要。它们说明最终 output `.text` 内部依次容纳三个 input `.text`，最终 output `.data` 内部容纳两个 input `.data`。

因此可以建立下面的模型：

```text
input sections

start.o:.text   part1.o:.text   part2.o:.text
       \              |              /
        \             |             /
         +------ output .text ------+

part1.o:.data   part2.o:.data
       \             /
        +-- output .data --+
```

这不是说同名 section 在所有链接场景中都必然按输入顺序简单连接。实际规则由 linker script、section attributes、COMDAT/group、GC 等条件影响。本节只描述当前最小实验实际观察到的默认 GNU ld 布局。

## 5. 第三阶段：symbol value 随最终布局确定

在 `ET_REL` 中，defined symbol 的 `st_value` 通常表示它在所属 section 内的位置，而不是最终进程虚拟地址。

例如链接前：

```bash
readelf -Ws part1.o
readelf -Ws part2.o
```

`left`、`combine`、`left_data`、`right_data` 都只与各自 input section 建立关系。

链接完成后：

```bash
nm -n linked.elf
```

当前实验得到：

```text
0000000000401000 T _start
0000000000401018 T left
0000000000401030 T combine
0000000000402000 D left_data
0000000000402008 D right_data
```

这些值已经与最终 output section 布局绑定。

例如：

```text
output .text starts at 0x401000
start.o:.text size = 0x18

所以 part1.o:.text starts at 0x401018
left 位于 part1.o:.text offset 0

最终 left = 0x401018
```

同理，`part2.o:.text` 从 `0x401030` 开始，所以其中 offset 0 的 `combine` 最终值为 `0x401030`。

因此不要把 symbol value 看成独立于 section layout 的固定属性。对普通 defined symbol，最终地址来自：

```text
output section placement
+ input section placement within output section
+ symbol offset within input section
```

## 6. 第四阶段：symbol resolution 为 relocation 提供目标

链接前：

```bash
readelf -Ws start.o part2.o
```

可以看到：

```text
start.o:
    combine  -> UND

part2.o:
    left     -> UND
```

而其他 input object 提供：

```text
part2.o defines combine
part1.o defines left
```

symbol resolution 先回答：

```text
start.o 中的 combine 引用最终绑定到谁？
part2.o 中的 left 引用最终绑定到谁？
```

只有目标 definition 确定后，链接器才有条件计算引用处最终应写入的值。

这再次说明：

```text
symbol resolution != relocation
```

前者决定“名字指向谁”，后者决定“机器字段写什么”。

## 7. 第五阶段：消费 input relocation

链接前：

```bash
readelf -Wr start.o part1.o part2.o
```

当前实验得到三类关键引用：

```text
start.o:
  R_X86_64_PLT32 combine - 4

part1.o:
  R_X86_64_PC32 left_data - 4

part2.o:
  R_X86_64_PLT32 left - 4
  R_X86_64_PC32 right_data - 4
```

`objdump -dr part2.o` 中可以直接看到尚待链接器修补的字段：

```asm
13: e8 00 00 00 00       call 18 <combine+0x18>
    14: R_X86_64_PLT32 left-0x4

18: 48 8b 15 00 00 00 00 mov 0x0(%rip),%rdx
    1b: R_X86_64_PC32 right_data-0x4
```

这些全零并不表示最终调用地址或数据地址为 0。它们只是当前 `ET_REL` 中等待 relocation 的机器字段。

链接器已经知道最终：

```text
left       = 0x401018
right_data = 0x402008
```

于是可以根据 relocation type 和 addend 计算最终字段并写回 output `.text`。

## 8. 最终反汇编：占位字段已经成为真实位移

最终：

```bash
objdump -d linked.elf
```

当前实验中 `combine` 的关键部分为：

```asm
401043: e8 d0 ff ff ff        call 401018 <left>
401048: 48 8b 15 b9 0f 00 00 mov 0xfb9(%rip),%rdx
                                 # 402008 <right_data>
```

与链接前相比：

```text
call rel32:  00 00 00 00 -> d0 ff ff ff
RIP disp32:  00 00 00 00 -> b9 0f 00 00
```

从 CPU 视角看，此时已经没有“待解析的 C 符号引用”。CPU 只读取 opcode 和最终位移字段。

## 9. 为什么最终 ELF 中没有这些 relocation

执行：

```bash
readelf -Wr linked.elf
```

当前最小静态链接实验得到：

```text
There are no relocations in this file.
```

原因是本实验所有链接时引用都已由 GNU ld 完全解析并写入最终地址相关字段。input `.rela.text` 的任务已经完成，所以不需要把这些记录保留给运行时处理。

这里不能推广成“所有 executable 都没有 relocation”。动态链接、PIE、GOT/PLT、动态数据对象等场景可能在最终 ELF 中保留 dynamic relocation；这些属于 A12 的内容。

## 10. section header 与 program header 的角色再次分开

链接完成后：

```bash
readelf -SW linked.elf
readelf -lW linked.elf
```

可以从两个层次观察同一个文件：

```text
section view
    .text / .data / ...
    主要服务于链接、符号和文件组织

segment view
    PT_LOAD / flags / file and memory ranges
    描述程序装载到进程地址空间的方式
```

静态链接首先需要处理 input/output section 的布局；最终生成 executable 时，还必须形成 loader 可以使用的 program headers。A11 第一部分已经说明 section 与 segment 不应混为一谈。

## 11. 完整静态链接主线

现在可以把 A11 的知识压缩为一条执行顺序：

```text
1. 编译/汇编生成多个 ET_REL
       |
       v
2. 链接器读取 input sections
       |
       v
3. 建立全局 symbol 表并执行 symbol resolution
       |
       v
4. 决定 output sections 和各 input section 的最终位置
       |
       v
5. 因布局确定而得到最终 symbol value
       |
       v
6. 对每个 relocation 计算最终值并改写目标字段
       |
       v
7. 生成最终 ELF section/program header
       |
       v
8. CPU 运行时只执行已经完成重定位的机器指令
```

实际 linker 实现内部可能交错执行若干步骤，也会有 relaxation、section GC、linker script evaluation 等额外过程。本节描述的是理解静态链接所需的逻辑依赖关系，不把它冒充 GNU ld 内部函数级实现顺序。

## 12. 本节实验与验证结果

实验目录：

```text
assembly/labs/11-static-linking/
```

已实际执行：

```bash
make clean
make check
make inspect
```

环境：

```text
GCC 14.2.0
GNU ld / binutils 2.44
x86-64 Linux
```

运行结果：

```text
exit_status=37
```

并实际确认：

- `linked.map` 显示三个 input `.text` 进入一个 output `.text`；
- 两个 input `.data` 进入一个 output `.data`；
- `nm -n` 显示最终 symbol value 与 map 布局一致；
- `start.o`、`part1.o`、`part2.o` 含 `PC32/PLT32` relocation；
- 最终反汇编中的占位字段已被写成真实 `rel32/disp32`；
- `readelf -Wr linked.elf` 确认本实验最终文件不再含 relocation。

## 13. 常见误区

### 13.1 链接就是把 `.o` 文件简单拼接

不是。链接器处理的是 section、symbol、relocation 和最终 ELF 布局。input section 会被放入 output section，符号值和引用字段都可能因此改变。

### 13.2 `.o` 中 symbol 的 `st_value` 已经是最终运行地址

对普通 `ET_REL` defined symbol 不能这样理解。最终地址要等 output layout 确定。

### 13.3 symbol resolution 完成后 relocation 就没有意义

不对。知道 `left` 绑定到 `part1.o` 的 definition 之后，链接器仍必须计算调用位置到 `left` 的最终 `rel32` 并写入机器指令。

### 13.4 最终 ELF 没有 relocation 是 ELF 格式的普遍规则

不对。这只是当前完全解析的最小静态链接实验结果。动态链接和 PIE 会引入另一类运行时 relocation。

### 13.5 linker map 是 CPU 运行时读取的数据

不是。map 文件是链接器生成的诊断材料，用于展示链接布局。CPU 不读取它。

## 14. A11 到这里形成的完整模型

A11 可以收束为：

```text
section
    组织代码和数据

symbol table
    给 section 中的实体命名并记录绑定/定义状态

symbol resolution
    在多个链接输入之间决定符号最终绑定

relocation
    描述哪些机器字段依赖最终 symbol/layout

static link
    决定 output layout -> 确定 symbol value -> 消费 relocation -> 生成最终 ELF
```

掌握这条主线以后，A12 才适合引入位置无关代码、PIE、GOT、PLT 和动态链接：它们本质上是在“最终地址何时能够确定、由谁完成最后一次地址绑定”这个问题上继续扩展。
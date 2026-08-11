# A12 第三部分：PLT、JUMP_SLOT 与动态函数调用

A12 第二部分已经建立了数据符号的 GOT 模型：代码用 RIP-relative 指令找到本映像中的 GOT slot，动态链接器再把外部数据符号的运行时地址写进该 slot。

函数调用面临相似的不确定性，但 CPU 执行的是 `call`，而不是“先取地址、再读取变量值”。ELF/x86-64 工具链通常用 Procedure Linkage Table（PLT）给调用点提供一个**本映像内可直接到达的跳板**，再由跳板通过 GOT/`.got.plt` 中的函数地址把控制流转到真实实现。

本节建立下面这条主线：

```text
caller.o: call external_add
        ↓  R_X86_64_PLT32
最终 PIE: call external_add@plt
        ↓
.plt entry
        ↓  indirect jmp through .got.plt slot
external_add 的运行时地址
```

并进一步区分 lazy binding 与 eager binding。这里讨论的是 ELF 用户态动态链接机制，不把 glibc dynamic loader 的内部实现写成 Linux kernel 5.10 的内核调用路径。

## 1. 问题背景：外部函数地址在编译时未知

假设调用方只有声明：

```c
extern int external_add(int);

int call_external(int x)
{
    return external_add(x) + 1;
}
```

真正定义位于共享对象：

```c
int external_add(int x)
{
    return x + 5;
}
```

编译 `caller.o` 时，编译器不知道 `libprovider.so` 最终装载在哪，也不知道动态符号解析最终选中哪个定义。

但 x86-64 的普通 direct near `call rel32` 只编码一个相对位移：

```text
next RIP + sign_extend(rel32)
```

因此需要一个在最终 PIE 内部地址已知、又能把控制流转给运行时目标的位置。PLT entry 就承担这个角色。

## 2. `.o` 中为什么出现 `R_X86_64_PLT32`

本节实验使用：

```bash
gcc -O0 -fPIE -c caller.c -o caller.o
```

当前 GCC 14.2.0 / GNU binutils 2.44 的 `objdump -dr caller.o` 显示：

```asm
10: e8 00 00 00 00        call 15 <call_external+0x15>
        11: R_X86_64_PLT32 external_add-0x4
```

这里机器码中的 `rel32` 还没有最终值，relocation 告诉静态链接器：这个调用针对 `external_add`，可按 PLT 语义解析。

`R_X86_64_PLT32` 仍然属于 PC-relative relocation。概念上仍是：

```text
L + A - P
```

其中 `L` 表示目标符号的 PLT entry 地址，`A` 是 addend，`P` 是 relocation field 地址。

当前对象中 addend 为 `-4`，原因与 A11 的 `call rel32` relocation 相同：relocation field 从 4 字节位移字段起算，而 CPU 的相对调用基准是该指令之后的 next RIP。

注意：`PLT32` 表示链接器拥有按 PLT 方式处理这个调用的语义空间，并不意味着所有最终链接结果都一定保留一个 PLT 跳板。若符号可在链接时确定为本地目标，链接器可能进行优化。应以最终 ELF 的 relocation 与反汇编为准。

## 3. 最终调用点：先调用本映像内的 PLT entry

本实验把 `external_add` 放进 `libprovider.so`，把 `caller.o` 链接进 PIE。

最终 `call_external()` 的关键指令为：

```asm
1159: e8 e2 fe ff ff        call 1040 <external_add@plt>
```

这一步的重要性质是：

- `call_external` 与 `external_add@plt` 都属于当前 PIE；
- PIE 整体因 ASLR 平移时，两者距离不变；
- 因此 call site 可以保存一个最终确定的 `rel32`，不需要动态链接器在运行时改写这条代码指令。

调用进入 `external_add@plt` 时，`call` 已经正常把返回地址压入用户栈；PLT 不改变 x86-64 `call` 的基本语义。

## 4. PLT entry 如何通过 GOT slot 转移控制流

当前实验的 `.plt` 中：

```asm
0000000000001040 <external_add@plt>:
    1040: ff 25 c2 2f 00 00    jmp *0x2fc2(%rip)  # 4008 <external_add@Base>
    1046: 68 01 00 00 00       push $0x1
    104b: e9 d0 ff ff ff       jmp 1020
```

第一条是 RIP-relative **间接跳转**：

```text
PLT entry
   ↓
RIP-relative 找到 .got.plt slot
   ↓
读取 slot 中的 64-bit target address
   ↓
jmp 到该地址
```

这里要区分两类地址关系：

1. `.plt` entry 到 `.got.plt` slot 的位置关系属于同一 ELF，可静态确定；
2. slot 中最终保存哪个函数地址，需要动态符号解析。

这与第二部分的数据 GOT 模型有共同点：都把运行时地址绑定集中到数据槽中，而不必因装载位置变化去修改调用者代码页。

## 5. `R_X86_64_JUMP_SLOT` 负责什么

最终 PIE 的 `.rela.plt` 中，本实验观察到：

```text
0000000000004008  R_X86_64_JUMP_SLOT  external_add + 0
```

`0x4008` 正好是 `external_add@plt` 第一条间接 `jmp` 所访问的 slot。

因此可以把静态链接与动态链接职责分成两步：

```text
caller.o 中 R_X86_64_PLT32
        ↓
静态链接器建立 call site -> external_add@plt

最终 ELF 中 R_X86_64_JUMP_SLOT
        ↓
动态链接器建立 .got.plt slot -> external_add runtime address
```

不要把 `PLT32` 与 `JUMP_SLOT` 当成同一个 relocation：前者出现在可重定位输入对象中，解决调用点如何到 PLT；后者保留在最终动态 ELF 中，解决 PLT 使用的函数地址槽如何绑定。

## 6. lazy binding 的基本模型

默认链接的实验 ELF 没有 `BIND_NOW` dynamic flag。当前工具链生成的传统 `.plt` entry 除了第一条间接 `jmp`，后面还包含：

```asm
push $reloc_index
jmp  PLT0
```

这为 lazy binding 提供了路径。简化模型是：

```text
第一次 call external_add@plt
        ↓
slot 尚未指向最终 external_add
        ↓
进入 PLT 的解析路径
        ↓
dynamic linker 根据对应 JUMP_SLOT 做符号解析
        ↓
更新 slot
        ↓
调用真实 external_add

后续调用
        ↓
external_add@plt 第一条 jmp
        ↓
slot 已含真实地址
        ↓
直接跳到 external_add
```

实验用 `LD_DEBUG=bindings` 观察到默认构建中：

```text
transferring control: ./plt_demo
binding file ./plt_demo ... symbol `external_add'
```

即 `external_add` 的 binding 发生在控制已经交给程序之后，与 lazy binding 模型一致。

这里必须把“ELF/PLT 提供的机制”和“某个 dynamic loader 的具体解析实现”分开。不同平台、链接选项、编译器安全特性以及新型 PLT 布局可能改变具体指令布局；本课程只把当前 GNU 工具链实测布局作为实验事实。

## 7. eager binding：`-z now`

实验同时链接：

```bash
gcc -pie ... -Wl,-z,now ... -o plt_demo_now
```

`readelf -d plt_demo_now` 显示：

```text
FLAGS    BIND_NOW
FLAGS_1  Flags: NOW PIE
```

`LD_DEBUG=bindings` 的顺序则变成：

```text
binding file ./plt_demo_now ... symbol `external_add'
transferring control: ./plt_demo_now
```

这说明对应函数符号在进入用户程序主体前已经解析。

所以 eager binding 不是“没有 PLT”或“没有 JUMP_SLOT”。本实验的核心变化是**解析时机**：动态加载阶段先处理相关 `JUMP_SLOT`，而不是把首次解析推迟到函数第一次经过 lazy PLT path 时。

## 8. `.plt`、`.got.plt` 与 `.rela.plt` 的分工

在当前 GNU ld 2.44 输出中可以观察到：

```text
.plt       可执行的跳板代码
.got.plt   PLT 间接跳转使用的地址槽
.rela.plt  针对这些槽的动态 relocation（JUMP_SLOT）
```

这是非常有用的学习模型，但不要把 section 名称、拆分方式或每个 PLT entry 的精确字节序列视为 x86-64 CPU 架构规定。

应区分四层规则：

- **x86-64 架构**：定义 direct `call rel32`、indirect `jmp`、RIP-relative addressing 等机器指令语义；
- **ELF ABI**：定义 `R_X86_64_PLT32`、`R_X86_64_JUMP_SLOT` 等 relocation 语义；
- **linker/dynamic loader 设计**：决定 PLT/GOT 的具体布局、绑定策略与优化；
- **本实验工具链事实**：GCC 14.2.0 + GNU binutils 2.44 生成了本文展示的传统 `.plt/.got.plt/.rela.plt` 布局。

## 9. 寄存器、栈、RFLAGS 与控制流

以最终路径为例：

```asm
call external_add@plt
...
external_add@plt:
    jmp *slot(%rip)
```

状态变化如下：

1. `call` 先令 `%rsp -= 8`，把 next RIP 作为 64-bit 返回地址写入 `(%rsp)`，再把 RIP 改为 `external_add@plt`；`call` 不改变算术状态标志；
2. PLT entry 的 `jmp *slot(%rip)` 读取 slot 中的 64-bit 地址并把 RIP 改成该值；`jmp` 不额外压栈，也不修改算术状态标志；
3. 如果已经完成 binding，真实 `external_add` 执行时看到的返回地址仍然是最初 `call` 压入的调用者返回地址；
4. `external_add` 最终 `ret` 从 `(%rsp)` 弹出这个地址并恢复到调用者；
5. lazy resolver 路径会额外使用 PLT entry 中的 `push` 等机制，但这些额外栈内容属于动态解析协议的一部分，不能与源级函数的正常返回地址混为一谈。

因此 PLT 是**控制流中间层**，但不会把普通函数调用的 ABI 返回关系改成另一套模型。

## 10. 实验验证路径

实验目录：[`../labs/12-plt-dynamic-calls/`](../labs/12-plt-dynamic-calls/)

按顺序执行：

```bash
make
make run
make inspect
make trace
```

重点核对：

1. `caller.o` 中 `external_add` 为 undefined symbol；
2. call site 使用 `R_X86_64_PLT32 external_add - 4`；
3. 最终 `call_external()` 调用 `external_add@plt`；
4. `.plt` 中第一条跳转间接读取 `0x4008` 对应的 slot（具体地址仅是当前构建结果）；
5. `.rela.plt` 对同一 slot 存在 `R_X86_64_JUMP_SLOT external_add`；
6. 默认构建无 `BIND_NOW`，`-z now` 构建带 `BIND_NOW/NOW`；
7. 两个程序都输出 `plt_result=42`；
8. `LD_DEBUG=bindings` 中默认构建的目标绑定位于 `transferring control` 之后，而 `-z now` 构建位于其之前。

## 11. 常见误区

### 误区一：PLT 保存函数实现

错误。PLT 是跳板代码。真实函数实现位于最终解析出的共享对象或其他 ELF 映像中。

### 误区二：`.got.plt` 保存函数机器码

错误。它保存的是供 PLT 间接跳转使用的地址/解析状态相关槽，而不是函数指令正文。

### 误区三：`PLT32` 就是 `JUMP_SLOT`

错误。`PLT32` 解决输入对象中的 PC-relative 调用目标；`JUMP_SLOT` 解决最终动态 ELF 中函数地址槽的运行时绑定。

### 误区四：用了 PLT 就一定 lazy binding

错误。`-z now`、`LD_BIND_NOW` 等可以要求 eager binding；此外不同链接器和编译选项还可能采用不同的 PLT/GOT 调用形式。

### 误区五：`-fno-plt` 只是删除 `.plt`

过度简化。`-fno-plt` 会改变外部调用生成方式，例如让调用点经 GOT 做间接调用；最终 section 和 relocation 还取决于链接器、符号属性与其他选项。本节先掌握传统 PLT 路径，后续如需要再作为对照实验展开。

## 12. 本节形成的工作模型

完成本节后，应能够串起：

```text
C 调用外部函数
    ↓
.o 中 direct call 占位 + R_X86_64_PLT32
    ↓
static linker 建立 call -> foo@plt
    ↓
foo@plt 经 RIP-relative indirect jmp 读取 .got.plt slot
    ↓
最终 ELF 用 R_X86_64_JUMP_SLOT 描述该 slot 的动态绑定
    ↓
dynamic linker 解析 foo
    ↓
slot 指向真实函数地址
    ↓
控制流进入真实 foo
```

lazy 与 eager 的核心区别是这个函数地址解析发生在首次调用附近，还是在程序主体开始执行前完成。

下一最小单元应把本节正式接入 `assembly/README.md` 并做 A12 当前三部分的一致性复核；之后再决定 A12 是否还需要单独补充 `-fno-plt` / symbol interposition 对照，还是已经满足本章大纲要求。
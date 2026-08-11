# ELF section 与 segment：从文件组织到运行时映射

A10 之后，我们已经能够读懂编译器生成的大部分局部机器代码，但如果只盯着反汇编，仍然很难回答几个更基础的问题：一段机器指令为什么出现在某个地址？只读字符串、已初始化全局变量和零初始化全局变量分别放在哪里？链接器和加载器看到的是不是同一种文件结构？

A11 从 ELF 开始回答这些问题。本节先只建立 section 与 segment 的基本模型，不进入符号绑定和重定位细节。

## 1. 两个不同的问题

ELF 同时要服务两个阶段：

1. 构建和链接阶段需要知道“文件里有哪些逻辑区域，它们各自保存什么”；
2. 程序加载运行时需要知道“哪些文件范围应映射到哪些虚拟地址，并使用什么权限”。

这两个阶段关注点不同，因此 ELF 同时存在 section header table 和 program header table。

可以先把二者理解为：

```text
section：面向链接和文件组织的逻辑单元
segment：面向装载和运行时映射的区域
```

这只是第一层模型。不是所有 ELF 文件都同时依赖两者：例如 relocatable object 主要依赖 section；可执行文件在装载时，内核和动态加载器主要依据 program header，而不是逐个 section 建立映射。

## 2. 四个最常见的 section

### 2.1 `.text`

`.text` 通常保存可执行机器指令。典型 section flags 包含：

```text
A  ALLOC
X  EXECINSTR
```

也就是运行时需要占据内存，并且允许执行。

### 2.2 `.rodata`

`.rodata` 通常保存只读常量，例如字符串字面量和只读全局对象。它通常需要装入内存，但不需要写权限。

需要注意，“C 语言里的 const”与“最终一定落入 `.rodata`”不是完全等价的语言规则。这里讨论的是常见 ELF/GCC 链接结果，而不是 C 标准对 section 名称的规定。

### 2.3 `.data`

`.data` 通常保存具有非零静态初始化值、运行时可写的全局或静态对象。因为初始值不是全零，ELF 文件中需要实际保存这些初始化字节。

例如：

```c
int initialized_counter = 7;
```

在本节实验中，`nm` 将其标记为 `D`，并且 `objdump -s -j .data` 可以直接看到小端表示的 `07 00 00 00`。

### 2.4 `.bss`

`.bss` 通常保存零初始化或未显式初始化的静态存储期对象，例如：

```c
int zero_counter;
```

它最关键的特征不是“里面保存了一串零字节”，而是通常使用 `SHT_NOBITS`：section 在内存中有大小，但 ELF 文件不需要为全部零初始化数据保存等量内容。

加载后，这部分内存必须呈现为零值。

## 3. section header 记录什么

`readelf -S` 展示 section header table。每个 section header 记录的信息包括：

```text
名称
类型
flags
虚拟地址（对已分配 section）
文件偏移
大小
对齐要求
链接到其他 section 的关系
```

例如实验中观察到：

```text
.text    PROGBITS  AX
.rodata  PROGBITS  A
.data    PROGBITS  WA
.bss     NOBITS    WA
```

这里的 `PROGBITS` 表示对应 section 在文件中有实际字节内容；`NOBITS` 则表示它描述内存空间，但文件本身不需要保存同等大小的数据。

## 4. segment 解决的是运行时映射问题

可执行文件真正被装载时，加载逻辑不能简单地说“把每个 section 单独 mmap 一次”。运行时更关心的是：

```text
文件偏移范围
→ 映射到哪个虚拟地址
→ 文件中有多少字节
→ 内存中需要多少字节
→ 具有什么 R/W/X 权限
```

这些信息来自 program header。

`readelf -l` 中最关键的是 `PT_LOAD`。本实验构建的非 PIE 可执行文件中实际出现了多个 `LOAD` segment，大致分为：

```text
R
R E
R
RW
```

其中：

- `.text` 被归入可执行的 `R E` segment；
- `.rodata` 被归入只读的 `R` segment；
- `.data` 和 `.bss` 被归入可写的 `RW` segment。

这说明 section 与 segment 并不是一一对应关系。

## 5. 为什么多个 section 可以进入同一个 segment

链接器可以把运行时权限、地址连续性和对齐要求相近的 section 合并到一个 `PT_LOAD` 中。

例如实验中可写 `PT_LOAD` 不只包含 `.data/.bss`，还包含 `.dynamic`、`.got` 等其他 section。对加载器来说，它们共同构成一个需要映射到内存、初始具有类似权限属性的区域。

因此应区分两种视角：

```text
链接器/分析工具视角：
  我想知道某个符号、重定位或数据属于哪个 section。

加载器视角：
  我想知道某段文件内容应如何映射为运行时虚拟内存区域。
```

## 6. `.bss` 为什么能让 `p_memsz > p_filesz`

包含 `.bss` 的可写 `PT_LOAD` 经常出现：

```text
p_memsz > p_filesz
```

原因是 `.bss` 需要运行时内存，但对应的零值内容不需要全部存进 ELF 文件。

因此加载器需要保证：

```text
文件提供的部分     -> 从 ELF 映射/复制初始字节
额外的内存尾部     -> 运行时按零初始化语义提供
```

这也是 `.bss` 能减小可执行文件磁盘体积的核心原因。

## 7. 用 `nm` 把 C 对象与 section 对起来

实验程序定义：

```c
const char course_name[] = "kernel-5.10";
int initialized_counter = 7;
int zero_counter;
```

当前验证环境的 `nm -n` 结果为：

```text
0000000000402008 R course_name
0000000000404018 D initialized_counter
0000000000404020 B zero_counter
```

其中常见符号类型字母可以先理解为：

```text
R -> read-only data
D -> initialized writable data
B -> BSS / zero-initialized data
T -> text/code
```

这些字母是 `nm` 的符号分类输出，不是 CPU 或 ABI 自身的寄存器/权限规则。

## 8. 本节实验的实际验证

实验目录：

```text
assembly/labs/11-elf-sections/
```

构建：

```bash
make
./elf_sections
```

实际输出：

```text
value=115
```

随后执行：

```bash
readelf -W -S elf_sections
readelf -W -l elf_sections
objdump -h elf_sections
objdump -s -j .rodata -j .data elf_sections
nm -n elf_sections
```

当前验证环境为 GCC 14.2.0 / GNU binutils 2.44。已经实际确认：

```text
.text    -> AX PROGBITS
.rodata  -> A  PROGBITS
.data    -> WA PROGBITS
.bss     -> WA NOBITS
```

并确认 program header 的 section-to-segment mapping 中：

```text
.text   -> R E PT_LOAD
.rodata -> R   PT_LOAD
.data   -> RW  PT_LOAD
.bss    -> RW  PT_LOAD
```

具体地址、section 编号、segment 数量以及是否还出现其他工具链生成 section，不属于稳定 ABI 结论。

## 9. 常见误区

### 9.1 section 就是内存映射区域

不是。section 是 ELF 文件的逻辑组织单位；真正描述运行时 load mapping 的是 program header 中的 segment。

### 9.2 `.bss` 在 ELF 文件里保存大量零

通常不是。`.bss` 常用 `SHT_NOBITS`，只记录需要的内存大小，不为全部零值保存同等文件内容。

### 9.3 `.text/.data/.bss` 是 x86-64 ISA 规定

不是。这些是 ELF/toolchain 层面的组织方式。x86-64 ISA 只执行机器指令并访问虚拟地址；它并不知道某个地址在链接文件中曾属于 `.text` 还是 `.data`。

### 9.4 section 权限就是页表权限

不能直接等同。section flags 会影响链接布局，而运行时最终页权限由 segment 映射、加载器策略以及后续保护调整共同决定。应从 program header 和实际映射角度理解运行时权限。

## 10. 本节建立的工作模型

到这里可以形成下面这条主线：

```text
C/汇编中的代码与对象
        ↓
编译器/汇编器放入不同 section
        ↓
链接器组合 section 并生成 program header
        ↓
加载器按 PT_LOAD 把文件区域映射到虚拟地址
        ↓
CPU 最终只看到可执行地址、可读写地址和其中的字节
```

下一步再进入符号表，解释“名字如何绑定到 section 内的某个地址”，然后才能继续讨论强/弱/未定义符号与重定位。

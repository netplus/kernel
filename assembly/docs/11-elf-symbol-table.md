# ELF 符号表：名字如何绑定到 section 中的位置

上一节已经建立了 section 与 segment 的基本模型。现在还缺少一个关键问题：编译器生成的函数和对象，在 ELF 中怎样保留“名字”，链接器又怎样知道 `exported_add`、`global_counter` 或一个尚未定义的 `external_add` 指向什么？

答案是 ELF symbol table。本节先聚焦符号表本身，不讨论强/弱符号冲突规则，也不展开 relocation 的编码细节；这些内容放到 A11 后续小节。

## 1. 符号表解决什么问题

机器代码最终只使用地址和立即数，CPU 并不认识 C 语言名字。但在编译、汇编和链接阶段，工具链仍需要保留名字与实体之间的关系，例如：

```text
exported_add
    ↓
这是一个全局函数
    ↓
定义在当前 .o 的 .text 中
    ↓
从 .text 起始位置偏移 0x14
    ↓
大小 52 bytes
```

或者：

```text
external_add
    ↓
这是当前目标文件引用的全局名字
    ↓
当前 .o 没有定义
    ↓
Ndx = UND
    ↓
链接时必须从其他输入文件或库中寻找定义
```

因此，symbol table 是“名字 → 符号属性 → 所属 section/定义状态 → value”的索引结构。

## 2. `.symtab` 与 `.strtab`

典型 relocatable object 中：

```text
.symtab  保存 Elf64_Sym 数组
.strtab  保存符号名字符串
```

符号记录本身不会直接嵌入可变长度名字，而是通过 `st_name` 保存一个字符串表偏移。

因此：

```text
Elf64_Sym.st_name
        ↓
作为 offset 进入关联的 string table
        ↓
得到 "exported_add"
```

这也是为什么 section header 中 `.symtab` 的 `sh_link` 会指向它使用的 string table。

## 3. `Elf64_Sym` 的核心字段

64 位 ELF 的符号项可以抽象成：

```c
Elf64_Word      st_name;
unsigned char   st_info;
unsigned char   st_other;
Elf64_Half      st_shndx;
Elf64_Addr      st_value;
Elf64_Xword     st_size;
```

本节重点关注五个字段。

### 3.1 `st_name`

`st_name` 不是地址，而是符号字符串表中的字节偏移。`readelf -s` 已经替我们把它解析成人类可读的 `Name`。

### 3.2 `st_info`

`st_info` 同时编码 symbol binding 与 symbol type。工具通常拆开显示：

```text
Bind: LOCAL / GLOBAL / WEAK ...
Type: FUNC / OBJECT / NOTYPE ...
```

本节实验主要观察：

```text
LOCAL   只在当前链接单元内部参与名字绑定
GLOBAL  可被其他链接输入引用
FUNC    函数符号
OBJECT  数据对象符号
```

这里的 LOCAL/GLOBAL 是 ELF 符号绑定属性，不是 C 语言 storage class 的逐字同义词；但常见 C 编译结果中，文件作用域 `static` 实体通常生成 LOCAL symbol，非 `static` 外部链接实体通常生成 GLOBAL symbol。

### 3.3 `st_shndx`

`st_shndx` 是理解“符号在哪里”的关键字段。

普通已定义符号通常记录 section index。例如本实验 `symbol_demo.o` 中：

```text
local_add       Ndx = 1  -> .text
local_counter   Ndx = 3  -> .data
```

而未定义符号显示：

```text
external_add       Ndx = UND
external_counter   Ndx = UND
```

因此，判断一个 relocatable object 中的名字是否已经有定义，不能只看 `st_value` 是否为 0；应首先看 `st_shndx` 是否为 `SHN_UNDEF`（工具显示为 `UND`）。

### 3.4 `st_value`

`st_value` 的语义取决于 ELF 文件类型和符号种类。

在本节重点观察的 relocatable object (`ET_REL`) 中，对普通已定义 section symbol，`st_value` 通常表示相对于该 section 起点的偏移。例如实验结果：

```text
local_add      Value = 0x0   Ndx = .text
exported_add   Value = 0x14  Ndx = .text
main           Value = 0x48  Ndx = .text
```

这时不能把 `0x14` 理解为进程运行时虚拟地址。它表示 `exported_add` 在输入 `.text` 内的位置。

链接为 executable 后，符号值通常已经变成链接布局中的虚拟地址，例如当前实验里的 `exported_add` 位于 `0x40113a`。具体地址依赖链接器和构建环境，不是 ABI 常量。

### 3.5 `st_size`

`st_size` 描述与符号关联对象的大小（如果该符号有可用大小信息）。本实验中：

```text
local_counter  Size = 4
local_add      Size = 20
exported_add   Size = 52
```

函数大小是当前编译结果，不应理解为源代码函数具有固定机器字节数。

## 4. 为什么要优先观察 `.o`

最终 executable 已经过链接，很多“等待解析”的状态消失了。为了理解符号表，relocatable object 更直接：

```text
symbol_demo.c
      ↓ gcc -c
symbol_demo.o
      ↓
当前文件定义的名字：有 section index
当前文件只引用的名字：UND
      ↓ 与 provider.o 链接
symbol_demo
      ↓
external_add / external_counter 得到实际定义和地址
```

所以本实验同时检查 `.o` 和最终 executable，但概念分析以 `.o` 为主。

## 5. 实验中的 LOCAL 与 GLOBAL

实验定义：

```c
static int local_counter = 3;
int global_counter = 7;

static int local_add(int value) { ... }
int exported_add(int value) { ... }
```

`readelf -W -s symbol_demo.o` 的关键结果：

```text
local_counter   OBJECT  LOCAL   Ndx 3
local_add       FUNC    LOCAL   Ndx 1
global_counter  OBJECT  GLOBAL  Ndx 3
exported_add    FUNC    GLOBAL  Ndx 1
main            FUNC    GLOBAL  Ndx 1
```

结合 section table：

```text
[1] .text
[3] .data
```

就可以建立完整关系：

```text
local_add      -> LOCAL/FUNC   -> .text + 0x0
exported_add   -> GLOBAL/FUNC  -> .text + 0x14
global_counter -> GLOBAL/OBJECT-> .data + 0x4
```

`nm` 用大小写做了简化表达：

```text
t  local_add       local text symbol
T  exported_add    global text symbol
d  local_counter   local data symbol
D  global_counter  global data symbol
```

注意：`nm` 的字母是工具的摘要显示方式；完整属性仍应以 ELF symbol table 为准。

## 6. 未定义符号不是“地址为零的定义”

`symbol_demo.c` 只声明：

```c
extern int external_counter;
extern int external_add(int value);
```

但真正定义放在 `provider.c`。

因此 `symbol_demo.o` 中可以观察到：

```text
external_counter  GLOBAL DEFAULT UND
external_add      GLOBAL DEFAULT UND
printf            GLOBAL DEFAULT UND
```

这些记录表示当前 `.o` 存在名字引用，但没有提供定义。其 `Value` 显示为 0 并不意味着“变量或函数定义在地址 0”；决定未定义状态的是 `Ndx = UND`。

同样，symbol table 的第 0 项按 ELF 约定也是未定义保留项，因此不能仅凭 `UND` 推断“链接一定失败”。只有链接过程确实需要某个未定义引用、又找不到满足条件的定义时，才形成 unresolved-symbol 错误。

## 7. 链接后发生什么

`provider.o` 提供：

```c
int external_counter = 11;
int external_add(int value) { return value + 13; }
```

把两个 `.o` 链接后，最终 executable 的普通符号表中可以观察到：

```text
external_counter  GLOBAL OBJECT  -> section 24
external_add      GLOBAL FUNC    -> section 13
```

也就是说，这两个名字已经从 `symbol_demo.o` 里的 `UND` 引用，绑定到了另一个输入 object 提供的定义。

对于 `printf`，本实验使用正常 glibc 动态链接，因此它仍涉及动态符号和运行时动态链接。本节不借此展开 `.dynsym`/PLT/GOT；A12 再系统说明。

## 8. `st_value` 与 section 的联合解释

读符号时，不要孤立地看 Value。推荐固定采用：

```text
Name
 + Type/Bind
 + Ndx
 + 对应 section header
 + Value
 + Size
```

例如：

```text
exported_add
  Type  = FUNC
  Bind  = GLOBAL
  Ndx   = 1
  [1]   = .text
  Value = 0x14
  Size  = 52
```

才能得到准确含义：

> 这是当前 relocatable object 中定义的一个 GLOBAL function symbol，其代码位于 `.text` section 起点之后 0x14 字节处，当前机器代码范围大小为 52 字节。

这比只说“`exported_add` 地址是 0x14”准确得多。

## 9. 本节实际验证

实验目录：

```text
assembly/labs/11-elf-symbol-table/
```

当前环境实际使用 GCC 14.2.0 / GNU binutils 2.44 构建：

```bash
make
./symbol_demo
```

输出：

```text
symbol_result=39
```

计算过程为：

```text
5 + local_counter(3)
  + global_counter(7)
  + external_counter(11)
  + external_add 中增加的 13
= 39
```

随后实际执行：

```bash
readelf -W -S symbol_demo.o
readelf -W -s symbol_demo.o
nm -a symbol_demo.o
readelf -W -s symbol_demo
nm -n symbol_demo
```

已确认：

- `local_counter/local_add` 是 LOCAL defined symbols；
- `global_counter/exported_add/main` 是 GLOBAL defined symbols；
- `external_counter/external_add/printf` 在 `symbol_demo.o` 中是 GLOBAL `UND`；
- `provider.o` 链接进来后，`external_counter/external_add` 在最终 executable 中拥有实际 section index 和链接地址；
- `.symtab` 与 `.strtab` 都实际存在于当前 `.o` 中。

具体 symbol number、section number、地址和函数大小由工具链与源码布局决定，不属于稳定 ABI 常量。

## 10. 常见误区

### 10.1 `st_value` 永远就是运行时虚拟地址

不是。对 `ET_REL` 中普通 section-defined symbol，常见语义是 section-relative offset；完成链接后才可能成为最终链接地址。

### 10.2 `Value = 0` 就说明符号未定义

不是。`local_add` 在本实验 `.o` 中 `Value = 0`，但 `Ndx = 1 (.text)`，它是确定定义；未定义状态看 `st_shndx = SHN_UNDEF`。

### 10.3 `static`、LOCAL、文件内可见性完全是同一个概念

不能简单等同。C 语言定义 linkage/storage-duration 规则，ELF 定义 symbol binding。工具链通常会把文件作用域 `static` 实体表示为 LOCAL symbol，但这是从语言语义到目标文件格式的映射关系。

### 10.4 `nm` 的一个字母就是完整 ELF 语义

不是。`nm` 很适合快速定位，但 `readelf -s` 才能同时看到 Type、Bind、Vis、Ndx、Value、Size 等字段。

## 11. 本节工作模型

现在可以把 A11 前两部分连接起来：

```text
源码中的函数/对象名字
        ↓
编译器/汇编器生成 section 内容
        ↓
.symtab 中建立 Elf64_Sym
        ↓
st_shndx 指向 section 或 UND
        ↓
st_value 给出该 ELF 阶段下的位置语义
        ↓
链接器根据名字和 binding 解析跨 object 引用
```

下一步需要在这个模型上加入强符号、弱符号和同名定义选择规则，再进入 relocation：当一个输入 `.o` 尚不知道另一个符号最终地址时，机器指令里的待修补位置如何被记录和修正。

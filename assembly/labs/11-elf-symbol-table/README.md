# A11 实验：ELF 符号表

本实验验证 relocatable object 中 ELF symbol table 的核心字段，以及 local/global、defined/undefined 符号在链接前后的变化。

## 构建与运行

```bash
make
./symbol_demo
```

当前验证环境实际输出：

```text
symbol_result=39
```

计算过程：

```text
5 + local_counter(3)
  + global_counter(7)
  + external_counter(11)
  + external_add 中增加的 13
= 39
```

## 先观察 relocatable object

```bash
readelf -W -S symbol_demo.o
readelf -W -s symbol_demo.o
nm -a symbol_demo.o
```

当前环境中关键 section 为：

```text
[1]  .text
[3]  .data
[19] .symtab
[20] .strtab
```

section 编号取决于工具链和调试信息配置，不是固定值。

关键 symbol table 结果：

```text
local_counter   OBJECT  LOCAL   Ndx 3   Value 0x0  Size 4
local_add       FUNC    LOCAL   Ndx 1   Value 0x0  Size 20
global_counter  OBJECT  GLOBAL  Ndx 3   Value 0x4  Size 4
exported_add    FUNC    GLOBAL  Ndx 1   Value 0x14 Size 52
external_counter NOTYPE GLOBAL  UND
external_add     NOTYPE GLOBAL  UND
main             FUNC   GLOBAL  Ndx 1
printf           NOTYPE GLOBAL  UND
```

这里最重要的观察不是具体地址，而是：

```text
Ndx = 普通 section index -> 当前 .o 已经提供定义
Ndx = UND                -> 当前 .o 只有引用，没有定义
```

`Value = 0` 不能单独用来判断未定义。例如 `local_add` 的 Value 也是 0，但它的 `Ndx = 1 (.text)`，所以是一个确定定义。

## 用 `nm` 做快速对照

```bash
nm -a symbol_demo.o | grep -E \
  'local_counter|global_counter|external_counter|local_add|exported_add|external_add| main$'
```

当前结果：

```text
0000000000000014 T exported_add
                 U external_add
                 U external_counter
0000000000000004 D global_counter
0000000000000000 t local_add
0000000000000000 d local_counter
0000000000000048 T main
```

可快速读成：

```text
T/D -> global defined text/data symbol
t/d -> local defined text/data symbol
U   -> undefined symbol
```

`nm` 适合快速定位；需要完整 Type/Bind/Vis/Ndx/Value/Size 时仍应使用 `readelf -s`。

## 对照最终可执行文件

`provider.c` 提供：

```c
int external_counter = 11;
int external_add(int value) { return value + 13; }
```

链接：

```bash
cc symbol_demo.o provider.o -no-pie -o symbol_demo
```

再观察：

```bash
readelf -W -s symbol_demo
nm -n symbol_demo | grep -E \
  'local_counter|global_counter|external_counter|local_add|exported_add|external_add|main'
```

当前环境确认：

- `external_counter` 从 `symbol_demo.o` 中的 `UND` 引用变成最终 executable 中的 GLOBAL OBJECT definition；
- `external_add` 从 `UND` 引用变成 GLOBAL FUNC definition；
- `local_counter/local_add` 仍是 LOCAL symbols；
- executable 中符号的 Value 已表现为最终链接布局中的虚拟地址，而 `.o` 中普通已定义符号的 Value 主要是所属 section 内偏移。

具体最终地址依赖链接器和构建环境，不应写死为 ABI 结论。

## 完整检查

```bash
make inspect
```

当前验证环境：GCC 14.2.0 / GNU binutils 2.44。构建、运行、`readelf -S/-s`、`nm` 均已实际执行通过。

本实验没有展开 `WEAK`、同名强符号选择、relocation 和动态链接；这些属于 A11 后续单元及 A12。

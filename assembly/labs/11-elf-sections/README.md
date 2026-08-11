# A11 实验：ELF section 与 segment

本实验验证一个最小 ELF 可执行文件中 `.text`、`.rodata`、`.data`、`.bss` 的基本角色，并用 program header 观察多个 section 如何被装入少量 `PT_LOAD` segment。

## 构建与运行

```bash
make
./elf_sections
```

当前验证环境实际输出：

```text
value=115
```

`115 = 1 + 7 + 0 + 'k'(107)`。

## 检查 section

```bash
readelf -W -S elf_sections
objdump -h elf_sections
```

当前验证结果中可观察到：

```text
.text    PROGBITS  AX
.rodata  PROGBITS  A
.data    PROGBITS  WA
.bss     NOBITS    WA
```

`course_name` 位于 `.rodata`，`initialized_counter` 位于 `.data`，`zero_counter` 位于 `.bss`：

```bash
nm -n elf_sections | grep -E 'course_name|initialized_counter|zero_counter|add_course_value|main'
```

当前环境的关键结果为：

```text
0000000000401126 T add_course_value
000000000040114c T main
0000000000402008 R course_name
0000000000404018 D initialized_counter
0000000000404020 B zero_counter
```

地址取决于工具链和链接结果，不能把这些数值当成 ABI 常量。

## 检查 section 内容

```bash
objdump -s -j .rodata -j .data elf_sections
```

可以直接在 `.rodata` 中看到 `kernel-5.10` 字符串，在 `.data` 中看到初始化值 `7` 的小端字节 `07 00 00 00`。`.bss` 为 `SHT_NOBITS`，不需要在文件中为全部零值对象保存同样大小的初始化字节。

## 检查 segment

```bash
readelf -W -l elf_sections
```

当前验证结果中，主要映射关系是：

```text
R   PT_LOAD  -> ELF/动态链接相关只读元数据
R E PT_LOAD  -> .init .plt .text .fini
R   PT_LOAD  -> .rodata .eh_frame_hdr .eh_frame ...
RW  PT_LOAD  -> .init_array ... .got .data .bss
```

这说明 section 与 segment 不是一一对应关系。section 主要服务于链接、符号和文件组织；program header 描述加载器运行时需要映射的区域。多个具有相近运行时权限和布局要求的 section 可以归入同一个 `PT_LOAD` segment。

## 完整检查

```bash
make inspect
```

当前环境已实际执行：GCC 14.2.0 / GNU binutils 2.44，构建、运行、`readelf -S/-l`、`objdump -h/-s` 和 `nm` 均通过。不同发行版、编译器默认选项和链接器可能产生不同的 section 数量、地址和 program header 布局，因此实验只把稳定语义作为结论。

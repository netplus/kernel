# 预期分析

本文件记录本实验已经实际核验过的关键结果。绝对地址来自当前 GNU ld 2.44 默认 linker script，仅作为本次实验事实，不作为 ABI 保证。

## 1. 运行结果

```text
exit_status=37
```

调用关系：

```text
left(7) = 7 + 10 = 17
combine(7) = 17 + 20 = 37
```

## 2. input relocation

`readelf -Wr start.o part1.o part2.o`：

```text
start.o:
  offset 0x08  R_X86_64_PLT32  combine - 4

part1.o:
  offset 0x0b  R_X86_64_PC32   left_data - 4

part2.o:
  offset 0x14  R_X86_64_PLT32  left - 4
  offset 0x1b  R_X86_64_PC32   right_data - 4
```

因此链接前仍然需要同时解决函数调用和 RIP-relative 数据访问。

## 3. output section 布局

`linked.map` 的关键贡献：

```text
.text  0x401000 0x18 start.o
.text  0x401018 0x18 part1.o
.text  0x401030 0x24 part2.o

.data  0x402000 0x08 part1.o
.data  0x402008 0x08 part2.o
```

这验证了多个 input `.text` 被放入最终 output `.text`，多个 input `.data` 被放入最终 output `.data`。

## 4. 最终 symbol value

`nm -n linked.elf`：

```text
0000000000401000 T _start
0000000000401018 T left
0000000000401030 T combine
0000000000402000 D left_data
0000000000402008 D right_data
```

这些值与 map 中 input section 的最终 placement 一致。

## 5. relocation 前后对照

`part2.o`：

```asm
13: e8 00 00 00 00        call 18 <combine+0x18>
    14: R_X86_64_PLT32 left-0x4
18: 48 8b 15 00 00 00 00  mov 0x0(%rip),%rdx
    1b: R_X86_64_PC32 right_data-0x4
```

最终 `linked.elf`：

```asm
401043: e8 d0 ff ff ff        call 401018 <left>
401048: 48 8b 15 b9 0f 00 00 mov 0xfb9(%rip),%rdx
                                 # 402008 <right_data>
```

链接器已经把占位字段替换为最终相对位移。

## 6. 最终 relocation table

```bash
readelf -Wr linked.elf
```

结果：

```text
There are no relocations in this file.
```

这只说明本实验中的引用均已在最终静态链接时解析完成；不能推广到 PIE 或动态链接 executable。

# PC-relative relocation 实验

本实验验证一个可重定位目标文件中的 x86-64 PC-relative relocation，重点观察 `R_X86_64_PC32` 与 `R_X86_64_PLT32`。

## 验证问题

`caller.o` 在编译完成时还不知道 `ext_data` 和 `target()` 的最终地址。实验检查：

1. `caller.o` 中这两个名字仍为 `UND`；
2. `.rela.text` 中分别留下针对数据访问和函数调用的 relocation entry；
3. `objdump -dr` 能把 relocation entry 对应回具体机器指令字段；
4. 最终链接后，原先为 0 的 32-bit displacement 被链接器写成实际位移；
5. 这些位移满足 ELF x86-64 relocation 的 `S + A - P` 模型。

## 构建和运行

```bash
make clean
make check
```

当前验证环境：

```text
GCC 14.2.0
GNU binutils 2.44
x86-64 Linux
```

实际运行结果：

```text
result=37
```

计算过程为 `(7 + 5) * 3 + 1 = 37`。

## 检查 relocation

```bash
make inspect
```

当前环境中 `readelf -Wr caller.o` 的关键结果为：

```text
Offset 0x0f  R_X86_64_PC32   ext_data - 4
Offset 0x1e  R_X86_64_PLT32  target   - 4
```

`objdump -dr caller.o` 将它们定位到：

```asm
c:  48 8b 15 00 00 00 00    mov 0x0(%rip),%rdx
    f: R_X86_64_PC32 ext_data-0x4

1d: e8 00 00 00 00          call 22
    1e: R_X86_64_PLT32 target-0x4
```

注意 relocation 的 `Offset` 指向需要修补的 4-byte displacement 字段，而不是指令起始地址。

## 最终链接后的观察

当前链接结果中：

```asm
401159: 48 8b 15 b8 2e 00 00  mov 0x2eb8(%rip),%rdx  # 404018 <ext_data>
40116a: e8 06 00 00 00        call 401175 <target>
```

对于这两类 PC-relative relocation，可用：

```text
relocated_value = S + A - P
```

理解链接器写入的 32-bit signed displacement。

这里的 `P` 是 relocation field 本身的地址；因为 x86 指令硬件按“下一条指令地址 + displacement”形成目标地址，而 relocation field 到下一条指令末尾还差 4 字节，所以 GNU assembler 在这两个 entry 中给出 `A = -4`。

## 边界

- 本实验只讨论静态链接时可直接解析的基础 relocation，不展开动态链接 GOT/PLT；
- `R_X86_64_PLT32` 并不意味着最终一定经过 PLT。本实验中 `target` 由同一最终 executable 内的 object 提供，链接器最终生成了对 `target` 的直接相对调用；
- relocation entry 是链接期元数据，最终 executable 中相应静态 relocation 通常已经被消费，不应期待 `.rela.text` 仍以相同形式存在。

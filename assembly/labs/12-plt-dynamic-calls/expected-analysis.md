# 当前环境实测结果

验证环境：

```text
GCC: gcc (Debian 14.2.0-19) 14.2.0
GNU ld: GNU Binutils for Debian 2.44
```

## 1. 程序结果

```text
./plt_demo      -> plt_result=42
./plt_demo_now  -> plt_result=42
```

## 2. 输入对象 relocation

`readelf -Wr caller.o`：

```text
Offset 0x11  R_X86_64_PLT32  external_add - 4
```

`objdump -dr caller.o`：

```asm
10: e8 00 00 00 00        call 15 <call_external+0x15>
    11: R_X86_64_PLT32 external_add-0x4
```

这说明可重定位对象中的调用位移仍是占位值，静态链接器需要根据 relocation 决定最终目标。

## 3. 最终 PIE 调用点

当前构建：

```asm
1159: e8 e2 fe ff ff        call 1040 <external_add@plt>
```

调用方不直接编码 `libprovider.so` 中 `external_add` 的运行时地址，而是先调用本 PIE 内的 PLT entry。

## 4. `.plt` 与 `.got.plt`

`readelf -SW plt_demo` 显示：

```text
.rela.plt
.plt
.plt.got
.got
.got.plt
```

`external_add@plt` 当前为：

```asm
1040: ff 25 c2 2f 00 00    jmp *0x2fc2(%rip)  # 4008
1046: 68 01 00 00 00       push $0x1
104b: e9 d0 ff ff ff       jmp 1020
```

其中第一条间接跳转使用的 `0x4008` 地址落在 `.got.plt`。

## 5. 最终 dynamic relocation

`readelf -Wr plt_demo` 的 `.rela.plt`：

```text
0x4000  R_X86_64_JUMP_SLOT  printf
0x4008  R_X86_64_JUMP_SLOT  external_add
```

因此同一个 `0x4008` slot 同时可以从 PLT 反汇编和 `.rela.plt` relocation 两侧对应起来。

## 6. lazy 与 eager binding

默认 `plt_demo` 的 `readelf -d` 没有 `BIND_NOW`，只看到 PIE flag。

`plt_demo_now` 使用 `-Wl,-z,now` 后：

```text
FLAGS    BIND_NOW
FLAGS_1  Flags: NOW PIE
```

当前 glibc loader 的 `LD_DEBUG=bindings` 观察：

默认构建：

```text
transferring control: ./plt_demo
binding file ./plt_demo ... symbol `external_add'
```

`-z now`：

```text
binding file ./plt_demo_now ... symbol `external_add'
transferring control: ./plt_demo_now
```

所以在当前环境中，默认构建的 `external_add` 在程序获得控制后才完成首次 binding；`-z now` 构建在进入程序主体前已经完成 binding。

这些地址、PLT entry 字节和 `LD_DEBUG` 文本是当前工具链/loader 的观测结果。课程结论应依赖 ELF relocation 和控制流关系，不把具体地址或输出格式当作 ABI 保证。

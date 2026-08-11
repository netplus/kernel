# A12 PLT 动态函数调用实验

本实验验证外部函数调用从 `R_X86_64_PLT32` 到 `.plt/.got.plt`，再到最终 `R_X86_64_JUMP_SLOT` 的完整路径，并比较默认 lazy binding 与 `-z now` eager binding。

## 构建

```bash
make
```

会生成：

```text
libprovider.so   外部函数定义
caller.o         含 external_add 调用的输入对象
plt_demo         默认动态绑定策略的 PIE
plt_demo_now     使用 -Wl,-z,now 的 PIE
```

## 运行

```bash
make run
```

两个程序都应输出：

```text
plt_result=42
```

## 静态观察

```bash
make inspect
```

重点看：

1. `nm caller.o` 中 `external_add` 为 `U`；
2. `readelf -Wr caller.o` 中存在 `R_X86_64_PLT32 external_add - 4`；
3. `objdump -d plt_demo` 中 `call_external()` 调用 `external_add@plt`；
4. `.plt` 中 `external_add@plt` 第一条指令通过 RIP-relative indirect `jmp` 读取 `.got.plt` slot；
5. `readelf -Wr plt_demo` 的 `.rela.plt` 中存在 `R_X86_64_JUMP_SLOT external_add`；
6. 默认构建没有 `BIND_NOW`，`plt_demo_now` 带 `BIND_NOW/NOW`。

具体地址会随工具链和布局变化，不应把实验中的 `0x1040`、`0x4008` 写成固定地址。

## 绑定时机观察

```bash
make trace
```

在支持 glibc `LD_DEBUG=bindings` 的环境中，默认构建通常可看到 `transferring control` 之后才出现 `external_add` binding；`-z now` 构建则在 `transferring control` 之前完成该 binding。

如果当前 libc/loader 不支持 `LD_DEBUG=bindings`，`trace` 只能作为环境限制记录；静态的 ELF relocation 与 dynamic flag 检查仍可执行。

详细的当前环境实测记录见 [`expected-analysis.md`](expected-analysis.md)。

# A11 实验：强符号、弱符号与未定义符号

## 要验证的问题

本实验只验证链接期符号选择，不讨论 relocation 编码细节：

- `GLOBAL` strong definition 与 `WEAK` definition 同名时，链接器选择 strong definition；
- 两个 weak definition 同名时，链接可以成功，但不要把“选择第一个输入文件”当成跨链接器稳定 ABI 规则；
- 两个 strong definition 同名时，普通静态链接应报 multiple definition；
- `main.o` 中的 `UND` 引用由其他输入 object 提供定义后可以完成链接。

## 构建与运行

```bash
make clean
make check
make inspect
```

当前验证环境中，`strong-over-weak` 输出：

```text
choose=20 provided=7
```

说明 weak `choose()=10` 与 strong `choose()=20` 同时存在时，最终绑定到 strong definition。

`weak-weak` 在当前 GNU ld 输入顺序下输出：

```text
choose=10 provided=7
```

它证明多个 weak definition 不会像多个 strong definition 那样直接形成 multiple-definition error；具体选中哪个 weak definition 不应被程序依赖。

`make check` 还故意尝试链接 `strong.o` 与 `strong2.o`，期望失败。当前 GNU ld 2.44 报告 `multiple definition of 'choose'`，Makefile 把“链接失败”视为实验通过。

## 符号表观察

当前工具链可观察到：

```text
weak.o:   choose  FUNC WEAK   defined
strong.o: choose  FUNC GLOBAL defined
main.o:   choose  NOTYPE GLOBAL UND
main.o:   provided NOTYPE GLOBAL UND
```

`nm` 对应摘要为：

```text
weak.o     W choose
strong.o   T choose
main.o     U choose
main.o     U provided
```

这里的 `W/T/U` 是 `nm` 的摘要显示；判断 ELF binding 和定义状态仍以 `readelf -s` 的 `Bind` 与 `Ndx` 为准。

## 环境与边界

本实验已实际用 GCC 14.2.0、GNU binutils 2.44 构建。示例使用 `-fno-pie/-no-pie` 只是为了让最终 ELF 更容易观察，不改变本节要验证的 strong/weak resolution 基本问题。

本实验不把 weak+weak 的具体选择顺序描述成 ABI 保证，也不讨论共享库、symbol interposition、visibility、COMDAT、COMMON symbol 或动态链接；这些属于后续内容。

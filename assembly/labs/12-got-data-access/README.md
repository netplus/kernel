# A12 第二部分实验：GOT 数据访问

本实验验证一个外部数据符号怎样通过 GOT 在位置无关代码中被访问。

## 要验证的问题

`consumer.c` 只声明：

```c
extern int shared_value;
```

真正定义位于 `libprovider.so`。因此 `consumer.o` 在编译时不知道 `shared_value` 的最终运行时地址。

实验要确认下面的链路：

```text
consumer.o 的代码
    -> RIP-relative 定位 GOT slot
    -> 最终 ELF 保留针对该 slot 的 dynamic relocation
    -> 动态链接器把 shared_value 的运行时地址写入 slot
    -> read_shared() 再通过该地址读取变量值
```

## 构建

```bash
make clean
make
```

构建产物：

- `consumer.o`：使用 `-fPIC`；
- `libprovider.so`：定义 `shared_value = 41`；
- `got_demo`：PIE 主程序，链接 `consumer.o` 和 `libprovider.so`。

链接时给 `got_demo` 写入 `$ORIGIN` rpath，使实验程序可以直接找到同目录下的 `libprovider.so`。

## 运行

```bash
make run
```

当前验证环境输出：

```text
got_result=42
```

## 观察 relocation 和反汇编

```bash
make inspect
```

### 1. `consumer.o`

当前环境：

```text
GCC 14.2.0
GNU binutils 2.44
```

`readelf -Wr consumer.o` 实际显示：

```text
R_X86_64_REX_GOTPCRELX shared_value - 4
```

`objdump -dr consumer.o` 的关键部分为：

```asm
mov 0x0(%rip), %rax
    R_X86_64_REX_GOTPCRELX shared_value-0x4
mov (%rax), %eax
add $0x1, %eax
```

第一条 `mov` 读取 GOT slot 中的指针；第二条 `mov` 才读取 `shared_value`。

不同 GCC/binutils 版本或不同优化条件可能显示 `R_X86_64_GOTPCREL`、`R_X86_64_GOTPCRELX` 或 `R_X86_64_REX_GOTPCRELX`。实验结论应建立在 GOTPCREL 家族的“通过 PC-relative 方式定位 GOT entry”语义上，不依赖具体变体名称。

### 2. 最终 PIE

`readelf -Wr got_demo` 在当前环境实际显示：

```text
R_X86_64_GLOB_DAT shared_value + 0
```

对应 relocation offset 为：

```text
0x3fc8
```

`readelf -S got_demo` 可看到 `.got`，当前布局中上述位置属于 GOT 区域。

最终反汇编为：

```asm
mov 0x2e5e(%rip), %rax   # 3fc8 <shared_value@Base>
mov (%rax), %eax
add $0x1, %eax
```

这说明静态链接器已经确定“代码到 GOT slot”的相对距离；运行时还需要动态链接器把 `shared_value` 的真实地址写进该 slot。

## 进一步手工检查

查看动态符号：

```bash
readelf -Ws got_demo | grep shared_value
```

在主程序中应看到 `shared_value` 仍是 `UND`：定义由共享对象提供。

查看共享对象中的定义：

```bash
readelf -Ws libprovider.so | grep shared_value
```

这里应看到 defined `OBJECT GLOBAL` 符号。

如果希望观察运行时 loader 行为，可以在支持 glibc loader 调试输出的环境中使用：

```bash
LD_DEBUG=reloc,symbols ./got_demo 2>&1 | less
```

该输出依赖运行时 loader，实现和格式不属于 ELF ABI 的稳定接口，因此只作为辅助观察。

## 结果为什么如此

本实验把地址绑定拆成两层：

```text
静态层：RIP + disp32 -> GOT slot
动态层：GOT slot -> shared_value 的运行时地址
```

GOT slot 位于当前 PIE 中，所以代码可以稳定地用 RIP-relative 位移找到它；`shared_value` 位于动态选择的共享对象中，所以其绝对地址留到运行时写入 GOT。

## 当前环境限制

本次已实际执行 `make`、`make run` 和 `make inspect`，构建和运行成功。没有使用 GDB；本实验的核心结论已经由 `readelf`、`objdump` 和程序运行结果完成验证。

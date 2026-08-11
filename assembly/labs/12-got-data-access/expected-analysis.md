# 预期分析：从 GOTPCREL 到 GLOB_DAT

## 1. `consumer.o` 中发生了什么

`consumer.c` 只有 `extern int shared_value;`，因此 `shared_value` 在 `consumer.o` 的符号表中仍是未定义符号。`-fPIC` 不能把一个未知的运行时绝对地址直接写进代码，于是编译器生成“先取地址，再取值”的序列。

当前 GCC 14.2.0 / binutils 2.44 中：

```asm
mov 0x0(%rip), %rax
mov (%rax), %eax
```

第一条指令的 relocation 是：

```text
R_X86_64_REX_GOTPCRELX shared_value - 4
```

这里的核心不是 `REX_GOTPCRELX` 这个具体名字，而是 GOTPCREL 家族语义：链接器需要让这条 RIP-relative load 指向 `shared_value` 对应的 GOT entry。

## 2. 为什么不是直接 `mov shared_value(%rip), %eax`

直接 RIP-relative load 要求代码能够确定目标对象相对当前指令的位置，并且这个关系在运行时保持稳定。

本实验中 `shared_value` 的定义在 `libprovider.so` 中。它和主程序不是同一个固定布局单元，动态链接器还需要执行动态符号解析，因此编译器不能把最终对象地址当成一个普通的同映像相对距离。

GOT 提供一个属于当前映像的稳定中间点：

```text
read_shared() -> GOT slot -> shared_value
```

代码到 GOT slot 的距离可由静态链接器确定；GOT slot 里保存的绝对指针留到运行时确定。

## 3. 最终 ELF 为什么出现 `R_X86_64_GLOB_DAT`

链接 `got_demo` 后，静态链接器已经知道 `.got` 在 PIE 内部的布局，因此 `read_shared()` 中的 RIP-relative `disp32` 可以被最终写好。

但是 `shared_value` 仍来自共享对象，所以最终 ELF 的 `.rela.dyn` 保留：

```text
R_X86_64_GLOB_DAT shared_value + 0
```

当前实验中 relocation offset 为 `0x3fc8`。运行时动态链接器解析 `shared_value`，然后把它的地址写到这个位置。

因此两种 relocation 分属不同阶段：

```text
GOTPCREL family : 建立 code -> GOT slot
GLOB_DAT        : 建立 GOT slot -> runtime symbol address
```

## 4. 两条 `mov` 的寄存器和内存状态

假设动态链接器已经把：

```text
GOT[shared_value] = 0x7f...abcd
```

写入 GOT。

执行：

```asm
mov disp32(%rip), %rax
```

后：

```text
RAX = 0x7f...abcd
```

此时 `%rax` 保存的是地址，不是整数 `41`。

再执行：

```asm
mov (%rax), %eax
```

后：

```text
EAX = 41
RAX = 41
```

最后一行是因为写 `%eax` 会把 `%rax` 高 32 位清零。接着：

```asm
add $1, %eax
```

得到：

```text
EAX = 42
```

并按加法结果更新算术标志位。

## 5. 不应从实验中过度推导的结论

本实验不能推出：

- 所有 global 数据访问一定经过 GOT；
- 所有工具链都生成 `R_X86_64_REX_GOTPCRELX`；
- GOT 只服务数据符号；
- `.got` 与 `.got.plt` 永远按当前实验的 section 布局出现；
- 动态链接器一定使用某一固定内部函数完成 `GLOB_DAT`。

这些都受 visibility、symbol binding、链接器 relaxation、编译选项、工具链版本和运行时 loader 实现影响。

本实验真正验证的是更稳定的机制：**位置无关代码可以通过 RIP-relative 方式访问本映像中的 GOT entry，再由动态 relocation 把运行时解析出的外部数据地址写入该 entry。**

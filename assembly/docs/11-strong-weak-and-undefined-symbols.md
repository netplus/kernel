# 强符号、弱符号与未定义符号：链接器如何选择同名定义

上一节已经看到 `Elf64_Sym` 如何描述 LOCAL、GLOBAL 和 `UND`。但仅知道“符号表里有这个名字”还不够：多个输入 `.o` 可能同时出现同名符号，链接器必须决定哪个定义满足引用，或者何时拒绝继续链接。

本节聚焦最基础的 ELF static-link symbol resolution。这里讨论的是链接阶段的名字绑定规则，不讨论动态链接 symbol interposition，也不展开 relocation 的机器编码；PC-relative relocation 放到 A11 下一部分。

## 1. 问题背景

假设 `main.o` 中只有：

```text
choose      GLOBAL UND
provided    GLOBAL UND
```

而其他输入文件分别提供：

```text
weak.o      choose: WEAK definition
strong.o    choose: GLOBAL definition
provider.o  provided: GLOBAL definition
```

链接器处理这些输入时需要回答：

1. `UND` 引用能否找到一个可用定义；
2. 同名 strong 与 weak definition 同时存在时选谁；
3. 多个 weak definition 是否构成错误；
4. 多个 strong definition 是否允许。

这一步是 symbol resolution。完成 resolution 后，链接器才有条件把 relocation 指向最终被选择的定义。

## 2. strong、weak 与 `UND` 不是同一个维度

本课程在当前实验里使用下面的工作定义：

```text
strong definition
    普通外部链接的 GLOBAL defined symbol

weak definition
    ELF binding 为 STB_WEAK 且已经定义的 symbol

undefined reference
    st_shndx = SHN_UNDEF，readelf 显示 Ndx=UND
```

`UND` 不是一种“更弱的定义”。它根本没有为该名字提供实体，只表示当前 object 需要外部定义来满足引用。

同样，ELF `STB_GLOBAL`/`STB_WEAK` 是 object-file binding 属性；C 语言自身并没有名为 `weak` 的标准语言关键字。本实验使用 GCC `__attribute__((weak))` 让编译器生成 `STB_WEAK` symbol，这是工具链扩展。

## 3. strong + weak：strong definition 胜出

实验中：

```c
/* weak.c */
__attribute__((weak)) int choose(void) { return 10; }

/* strong.c */
int choose(void) { return 20; }
```

实际符号表：

```text
weak.o:   choose  FUNC WEAK   DEFAULT <section>
strong.o: choose  FUNC GLOBAL DEFAULT <section>
```

把 `main.o weak.o strong.o provider.o` 一起链接后，程序实际输出：

```text
choose=20 provided=7
```

因此，在这个普通 external-symbol 场景中，同名 strong 与 weak definition 同时参与链接时，引用绑定到 strong definition。weak definition 的典型用途之一，就是允许“存在默认实现，但调用者可以提供正常 strong definition 覆盖它”。

## 4. weak + weak：允许链接，但不要依赖具体选择顺序

实验再提供第二个 weak definition：

```c
__attribute__((weak)) int choose(void) { return 30; }
```

链接 `main.o weak.o weak2.o provider.o` 在当前 GNU ld 2.44 中成功，程序输出：

```text
choose=10 provided=7
```

这个结果说明两个 weak definition 不会像两个普通 strong definition 那样产生 multiple-definition error。

但课程不能进一步把“总是选择命令行最前面的 weak object”写成架构规则或 ABI 保证。当前实验只能确认当前 GNU ld、当前输入顺序下选择了 `weak.o` 的定义。程序设计不应依赖多个 weak definition 中具体哪一个被选中。

## 5. strong + strong：形成重复定义错误

`strong.o` 与 `strong2.o` 都提供普通 GLOBAL definition：

```text
strong.o:  choose = 20
strong2.o: choose = 40
```

实际执行：

```bash
gcc -no-pie main.o strong.o strong2.o provider.o -o strong-strong
```

GNU ld 2.44 拒绝链接，并报告：

```text
multiple definition of `choose'
```

这不是 CPU 运行期错误，而是链接阶段无法为同一个普通全局名字接受两个互相竞争的 strong definition，因此 executable 根本没有生成成功。

## 6. `UND` 如何得到满足

`main.c` 中只有声明：

```c
extern int choose(void);
extern int provided(void);
```

因此在 `main.o` 中实际看到：

```text
choose    GLOBAL UND
provided  GLOBAL UND
```

`provider.o` 则提供 `provided` 的 GLOBAL definition。链接器把各输入文件的 symbol information 放到同一次 resolution 过程中，于是：

```text
main.o: provided = UND
          +
provider.o: provided = GLOBAL defined
          ↓
最终引用可被解析
```

同理，`choose` 可以由 strong 或 weak definition 满足。只有当最终仍没有可接受的定义、且引用需要被解析时，才会得到 undefined-reference 类链接错误。

## 7. resolution 与 relocation 的边界

这里必须区分两个问题：

```text
symbol resolution
    “这个名字最终绑定到哪个定义？”

relocation
    “知道目标定义后，输入 section 中哪个字段要怎样修补？”
```

例如 `main.o` 中一条对 `choose()` 的调用，在编译 `.o` 时通常还不知道最终目标地址，因此既有 `choose = UND` symbol，也有针对调用位置的 relocation record。

本节只解决前一个问题。下一部分将检查 `readelf -r`/`objdump -dr`，把 symbol resolution 与 x86-64 PC-relative relocation 真正连接起来。

## 8. 本节实际验证

实验目录：

```text
assembly/labs/11-symbol-binding/
```

当前环境使用 GCC 14.2.0 / GNU binutils 2.44 实际完成：

```bash
make clean
make check
make inspect
```

结果：

```text
strong + weak  -> choose=20 provided=7
weak + weak    -> choose=10 provided=7   # 当前 GNU ld / 当前输入顺序
strong+strong  -> 链接失败，multiple definition
```

并实际用 `readelf -W -s` 与 `nm` 确认：

```text
weak.o     choose: WEAK defined / W
strong.o   choose: GLOBAL defined / T
main.o     choose: GLOBAL UND / U
main.o     provided: GLOBAL UND / U
```

## 9. 常见误区

### 9.1 weak 就是 LOCAL

不是。weak 是 ELF symbol binding 的一种；它仍然可以参与跨 object 的名字解析。LOCAL symbol 则不以同样方式参与外部名字绑定。

### 9.2 `UND` 是地址为 0 的弱定义

不是。`SHN_UNDEF` 表示当前 object 没有提供 definition；`st_value=0` 不能改变这个事实。

### 9.3 多个 weak definition 的具体选择是稳定 ABI 规则

不能这样依赖。本实验记录的是 GNU ld 2.44 的实际观察结果，而不是给程序员承诺“第一个 weak 永远胜出”。

### 9.4 multiple definition 是运行时冲突

不是。这里的重复 strong definition 在静态链接阶段已经使链接失败，程序没有进入运行阶段。

## 10. 本节工作模型

A11 到这里可以建立三层关系：

```text
section
  保存代码和数据内容

symbol table
  给 section 中的实体建立名字、binding、type 和定义状态

symbol resolution
  在多个链接输入之间为外部名字选择定义
```

下一步加入 relocation：检查一个 `UND` function call 在 `.o` 中留下什么 relocation entry，链接器选择 definition 后又怎样把 x86-64 PC-relative 位移修补成最终值。

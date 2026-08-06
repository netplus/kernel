# Linux x86-64 Assembly Learning Track

本目录是整个 Linux kernel 5.10 学习仓库中的“机器执行与架构基础维度”。仓库总体课程地图见 [`../README.md`](../README.md)。

汇编课程负责回答：

```text
CPU 实际执行了什么？
寄存器、栈、内存和标志位如何变化？
C 代码如何转换成机器指令？
系统调用、中断、异常和上下文切换的入口如何工作？
```

调度、时钟、内存和网络的完整子系统知识分别放在：

- [`../scheduler/`](../scheduler/)
- [`../timekeeping/`](../timekeeping/)
- [`../memory/`](../memory/)
- [`../network/`](../network/)
- [`../integrated-paths/`](../integrated-paths/)

本目录不会把这些子系统的全部内容塞入汇编课程，只在遇到相关指令和入口代码时建立必要联系。

课程采用统一闭环：

```text
问题背景 → 直观模型 → 指令语义 → C/汇编对照 → GDB 验证 → 内核联系
```

## 课程索引

0. [汇编课程总纲](docs/00-course-overview.md)
1. [CPU 执行模型、寄存器宽度与 mov](docs/01-cpu-execution-model-and-register-width.md)
2. [地址、解引用、数组、结构体与 lea](docs/02-addressing-dereference-and-lea.md)
3. [RFLAGS、比较、条件跳转与基本块](docs/03-rflags-comparison-and-control-flow.md)

后续依次补充：

```text
算术、移位、乘除法
循环、状态机与 switch
栈和初始用户栈
call、ret 与函数 ABI
ELF、重定位、PLT/GOT
系统调用入口和返回
异常、中断与 pt_regs
上下文切换汇编
内核启动
原子操作、内存屏障和内联汇编
```

## 实验索引

1. [寄存器宽度实验](labs/01-register-width/README.md)
2. [复合取址与结构体布局实验](labs/02-addressing/README.md)
3. [RFLAGS、比较与条件分支实验](labs/03-flags-and-branches/README.md)

## 课程讲述约定

为兼顾不同基础的学习者，后续课程统一按以下层次组织：

```text
主线
先用直观语言和最小示例说明“这是什么、解决什么问题”。

原理
解释 CPU、ABI、编译器或操作系统为什么采用这种设计。

进阶
分析优化形式、边界条件、不同实现和常见误区。

关联知识
在不打断主线的前提下，连接 ELF、页表、调度、时钟、网络栈和内核源码。

实验
通过可编译代码、objdump 和 GDB 验证，不把结论停留在文字层面。
```

首次阅读时可以只完成“主线 + 实验”；有一定基础后再阅读原理和进阶部分。

## 目录职责

```text
assembly/README.md        汇编维度导航和实验入口
assembly/docs/            汇编课程总纲与逐课教程
assembly/labs/            可编译、可调试的配套实验
```

## 默认环境

- x86-64 Linux
- GNU assembler（AT&T 语法）
- GCC、binutils、GDB
- System V AMD64 ABI
- Linux kernel 5.10

## 推荐工具

Debian/Ubuntu：

```bash
sudo apt install build-essential binutils gdb
```

openEuler/RHEL：

```bash
sudo dnf install gcc binutils gdb make
```

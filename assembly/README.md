# Linux x86-64 Assembly Labs

本目录用于系统学习 Linux x86-64 汇编，并逐步过渡到 Linux kernel 5.10 的启动、系统调用、中断、异常与上下文切换代码。

课程采用统一闭环：

```text
问题背景 → 直观模型 → 指令语义 → C/汇编对照 → GDB 验证 → 内核联系
```

## 课程索引

0. [课程总纲](docs/00-course-overview.md)
1. [CPU 执行模型、寄存器宽度与 mov](docs/01-cpu-execution-model-and-register-width.md)
2. [地址、解引用、数组、结构体与 lea](docs/02-addressing-dereference-and-lea.md)
3. [RFLAGS、比较、条件跳转与基本块](docs/03-rflags-comparison-and-control-flow.md)

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
在不打断主线的前提下，连接 ELF、页表、并发、网络栈和内核源码。

实验
通过可编译代码、objdump 和 GDB 验证，不把结论停留在文字层面。
```

首次阅读时可以只完成“主线 + 实验”；有一定基础后再阅读原理和进阶部分。课程不会假设所有读者已经熟悉编译器、ABI 或内核源码，遇到关联概念会先给出足够的上下文。

## 目录职责

```text
assembly/README.md        课程导航、学习方法和实验入口
assembly/docs/            课程总纲与逐课教程
assembly/labs/            可编译、可调试的配套实验
```

## 默认环境

- x86-64 Linux
- GNU assembler（AT&T 语法）
- GCC、binutils、GDB
- System V AMD64 ABI
- 后续内核源码基线：Linux kernel 5.10

## 推荐工具

Debian/Ubuntu：

```bash
sudo apt install build-essential binutils gdb
```

openEuler/RHEL：

```bash
sudo dnf install gcc binutils gdb make
```

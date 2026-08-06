# Linux x86-64 Assembly Labs

本目录用于系统学习 Linux x86-64 汇编，并逐步过渡到 Linux kernel 5.10 的启动、系统调用、中断、异常与上下文切换代码。

课程采用统一闭环：

```text
问题背景 → 架构设计 → 最小示例 → 编译/反汇编 → GDB 单步 → 状态还原 → 内核联系
```

## 课程索引

0. [课程总纲](docs/00-course-overview.md)
1. [CPU 执行模型、寄存器宽度与 mov](docs/01-cpu-execution-model-and-register-width.md)
2. [地址、解引用、复杂寻址与 lea](docs/02-addressing-dereference-and-lea.md)

## 实验索引

1. [寄存器宽度实验](labs/01-register-width/README.md)
2. [地址与复杂寻址实验](labs/02-addressing/README.md)

## 目录职责

```text
assembly/README.md        课程导航和实验入口
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

# Linux x86-64 Assembly Labs

本目录用于配合 [`docs/linux-x86-64-assembly-language.md`](../docs/linux-x86-64-assembly-language.md) 学习 Linux x86-64 汇编。

课程采用统一闭环：

```text
问题背景 → 架构设计 → 最小示例 → 编译/反汇编 → GDB 单步 → 状态还原 → 内核联系
```

## 课程索引

1. [CPU 执行模型、寄存器宽度与 mov](docs/01-cpu-execution-model-and-register-width.md)

## 实验索引

1. [寄存器宽度实验](labs/01-register-width/README.md)

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

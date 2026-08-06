# Lab 02 预期分析

假设链接完成后：

```text
array 首地址 = A
```

数组内存：

```text
memory[A + 0]  = 10
memory[A + 8]  = 20
memory[A + 16] = 30
memory[A + 24] = 40
```

每个 `.quad` 占 8 字节。

## 1. 初始状态

GDB 在 `_start` 处停止时，各通用寄存器的初始值不应作为程序输入依赖。我们只追踪程序明确写入的寄存器。

`RSP` 指向 Linux 为新进程构造的初始用户栈，其中包含：

```text
argc
argv[]
envp[]
auxiliary vector
```

本实验不修改栈。

## 2. 指令状态表

| 指令 | 有效地址/计算 | 内存访问 | 关键结果 |
|---|---|---|---|
| `leaq array(%rip), %rbx` | `A` | 否 | `RBX=A` |
| `movq %rbx, %rax` | 无 | 否 | `RAX=A` |
| `movq (%rbx), %rcx` | `A` | 读 8 字节 | `RCX=10` |
| `movq 8(%rbx), %rdx` | `A+8` | 读 8 字节 | `RDX=20` |
| `movq $2, %rsi` | 无 | 否 | `RSI=2` |
| `movq (%rbx,%rsi,8), %r8` | `A+2*8=A+16` | 读 8 字节 | `R8=30` |
| `leaq 16(%rbx), %r9` | `A+16` | 否 | `R9=A+16` |
| `movq (%r9), %r10` | `A+16` | 读 8 字节 | `R10=30` |
| `leaq 5(%rsi,%rsi,4), %r11` | `5+2+2*4=15` | 否 | `R11=15` |
| `movq $60, %rax` | 无 | 否 | `RAX=60`，系统调用号 `exit` |
| `movq %r11, %rdi` | 无 | 否 | `RDI=15`，退出状态 |
| `syscall` | 进入内核 | 入口机制访问内核状态 | 进程退出 |

## 3. 四组必须区分的语义

### 3.1 地址本身

```asm
movq %rbx, %rax
```

```text
RAX = A
```

### 3.2 地址处的数据

```asm
movq (%rbx), %rcx
```

```text
RCX = memory[A] = 10
```

### 3.3 计算新地址

```asm
leaq 16(%rbx), %r9
```

```text
R9 = A + 16
```

### 3.4 通过新地址读取数据

```asm
movq (%r9), %r10
```

```text
R10 = memory[A + 16] = 30
```

## 4. 比例索引分析

```asm
movq (%rbx,%rsi,8), %r8
```

统一公式：

```text
EA = disp + base + index × scale
```

代入：

```text
disp  = 0
base  = RBX = A
index = RSI = 2
scale = 8
```

所以：

```text
EA = A + 2 × 8 = A + 16
R8 = memory[A + 16] = 30
```

`scale=8` 是因为数组元素类型为 `.quad`，每个元素占 8 字节。

## 5. `lea` 算术分析

```asm
leaq 5(%rsi,%rsi,4), %r11
```

代入 `RSI=2`：

```text
R11 = 5 + 2 + 2 × 4
    = 15
```

这里表达式虽然使用内存操作数的语法，但没有内存访问。

## 6. RFLAGS 观察

以下指令通常不修改算术条件标志：

```text
mov
lea
```

因此，本实验中 `EFLAGS/RFLAGS` 的算术标志不应被这些数据传送和地址计算指令有意义地更新。

这为后续课程理解下列序列提供基础：

```asm
cmpq %rsi, %rdi
leaq 1(%rax), %rax
jg .Ltarget
```

`lea` 不会覆盖 `cmp` 为条件跳转准备的标志。

## 7. C 对照代码的 `-O2` 预期

### 7.1 数组访问

```c
return array[index];
```

典型汇编：

```asm
movq (%rdi,%rsi,8), %rax
ret
```

### 7.2 结构体成员

```c
return item->value;
```

典型汇编：

```asm
movq 8(%rdi), %rax
ret
```

### 7.3 乘加

```c
return x * 5 + 5;
```

典型汇编：

```asm
leaq 5(%rdi,%rdi,4), %rax
ret
```

具体标签和调试伪指令可能因 GCC 版本不同而变化，但核心机器指令应保持相近语义。

## 8. 最终验收

执行：

```bash
make run
```

预期：

```text
exit status=15 (expected 15)
```

执行：

```bash
make gdb
```

在最终 `syscall` 前应看到：

```text
RAX = 60
RDI = 15
R11 = 15
RCX = 10
RDX = 20
R8  = 30
R10 = 30
```

其中 `RBX` 是数组首地址，`R9 = RBX + 16`。

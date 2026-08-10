# 第 6 课（二）：`_start` 时的初始用户栈

上一部分已经建立了栈、`RSP`、`push` 和 `pop` 的基本模型。本节继续回答一个更具体的问题：

> Linux 启动一个新的 x86-64 ELF 用户程序时，程序入口 `_start` 最初看到的栈里有什么？

这部分非常重要，因为 `_start` 并不是普通 C 函数。程序刚进入用户态时，还没有调用 `main()`，也没有普通函数调用者替它准备参数寄存器。进程启动参数、环境变量以及辅助向量首先由内核放在初始用户栈中。

本节把三层规则分开理解：

```text
x86-64 指令层
    RSP 只是当前栈顶地址

ELF / System V 进程启动约定
    初始栈保存 argc、argv、envp 和 auxiliary vector

Linux 5.10 实现
    fs/binfmt_elf.c:create_elf_tables() 构造这张初始栈
```

---

## 1. 从 `_start` 的第一条指令开始

设程序入口处：

```asm
_start:
    movq %rsp, %rbx
```

这里保存的是**进程初始用户栈指针**。

在 Linux 5.10 的 64 位 ELF 正常向下增长栈路径中，`create_elf_tables()` 最终把 `bprm->p` 对齐后作为栈上最低地址，并首先写入 `argc`。因此 `_start` 入口处可以把：

```text
[RSP]
```

解释为参数数量 `argc`。

注意：这是进程入口约定，不是 `mov`、`push`、`pop` 等 CPU 指令本身规定的。

---

## 2. 初始栈的主布局

对本课程采用的 Linux 5.10 + x86-64 环境，可以先建立下面的主模型：

```text
低地址

RSP ->  argc
        argv[0]
        argv[1]
        ...
        argv[argc-1]
        NULL
        envp[0]
        envp[1]
        ...
        NULL
        auxv[0].a_type
        auxv[0].a_val
        auxv[1].a_type
        auxv[1].a_val
        ...
        AT_NULL
        0

        （更高地址还保存 argv/envp 指针指向的字符串，
          以及 AT_RANDOM、AT_PLATFORM 等条目引用的数据）

高地址
```

最重要的是不要把两种内容混在一起：

```text
argv[] / envp[] 区域保存的是“指针”
真正的参数字符串和环境字符串位于更高地址的字符串区域
```

例如：

```text
argv[1] = 0x7fffffffe7d0
```

表示栈表项中保存了一个地址；真正的 `"alpha\0"` 位于该地址指向的内存中。

---

## 3. `argc` 和 `argv[]`

入口处：

```asm
movq (%rsp), %r12
```

即可读取 `argc`。

因为 x86-64 用户地址和这里的 ELF 地址槽按 8 字节处理，所以第一个 `argv` 指针紧跟在 `argc` 后面：

```asm
leaq 8(%rsp), %r13
```

于是：

```text
R13       -> argv[0]
R13 + 8   -> argv[1]
R13 + 16  -> argv[2]
...
```

第 `argc` 个指针槽不是新的参数，而是终止标记：

```text
argv[argc] = NULL
```

因此可以直接计算：

```asm
cmpq $0, (%r13,%r12,8)
```

来验证 `argv[]` 的终止位置。

---

## 4. 如何找到 `envp[]`

已知：

```text
argv_base = initial_rsp + 8
argv[argc] = NULL
```

那么 `envp[0]` 位于这个 NULL 之后：

```text
envp = argv_base + argc * 8 + 8
```

对应汇编：

```asm
leaq 8(%r13,%r12,8), %r14
```

之后逐个检查 8 字节指针，直到再次遇到 NULL：

```asm
.Lenv_scan:
    cmpq $0, (%r15)
    je .Lenv_done
    addq $8, %r15
    jmp .Lenv_scan
```

因此初始栈上有两个非常重要的 NULL 分隔符：

```text
argv[] 末尾 NULL
envp[] 末尾 NULL
```

它们使 `_start` 即使事先不知道环境变量数量，也可以找到下一块数据。

---

## 5. Auxiliary Vector 是什么

环境变量末尾 NULL 之后是 auxiliary vector，通常简称 `auxv`。

在 64 位环境中，可以把每一项理解为两个连续的 64 位值：

```text
a_type
a_val
```

因此每个条目占 16 字节。

典型条目包括：

```text
AT_PAGESZ   页面大小
AT_PHDR     ELF program header 地址
AT_PHENT    每个 program header 的大小
AT_PHNUM    program header 数量
AT_ENTRY    程序入口地址
AT_UID      real uid
AT_EUID     effective uid
AT_GID      real gid
AT_EGID     effective gid
AT_RANDOM   指向 16 个随机字节
AT_EXECFN   指向可执行文件名字符串
```

这些值并不是普通命令行参数。它们是内核在启动 ELF 程序时向用户空间传递的运行时信息，动态链接器和 C 运行时可以直接使用。

---

## 6. `AT_NULL` 为什么重要

`auxv` 没有单独的“条目数量”放在最前面，因此消费者需要靠终止项判断结束。

Linux 5.10 在 `create_elf_tables()` 中把辅助向量剩余区域清零，并明确给 `AT_NULL` 留出一对槽位。

因此扫描时可以写成：

```asm
.Laux_scan:
    movq 0(%r15), %rax
    movq 8(%r15), %rcx
    testq %rax, %rax
    je .Laux_done
    addq $16, %r15
    jmp .Laux_scan
```

这里：

```text
AT_NULL == 0
```

所以 `a_type == 0` 表示辅助向量结束。

不要把 `AT_NULL` 与 `argv[]` 或 `envp[]` 的 NULL 指针混为一谈：

```text
argv/envp 的 NULL：一个 8 字节空指针槽
auxv 的 AT_NULL：一个 type/value 二元条目，type 为 0，value 也为 0
```

---

## 7. Linux 5.10 中是谁构造这张栈

本节对应的 Linux 5.10 源码入口是：

```text
fs/binfmt_elf.c
    create_elf_tables()
```

在 Linux v5.10 中，该函数先取得：

```text
bprm->argc
bprm->envc
bprm->p
```

然后生成辅助向量，包括 `AT_PAGESZ`、`AT_PHDR`、`AT_ENTRY`、`AT_RANDOM`、`AT_EXECFN` 等条目。

接着它计算最终栈位置，并按顺序执行：

```text
put_user(argc, sp++)

循环写 argv 指针
put_user(0, sp++)

循环写 envp 指针
put_user(0, sp++)

copy_to_user(sp, mm->saved_auxv, ...)
```

这直接对应本节使用的布局：

```text
argc
argv[]
NULL
envp[]
NULL
auxv[]
```

源码核验基线：Linux v5.10 `fs/binfmt_elf.c:create_elf_tables()`。

---

## 8. 参数字符串为什么在另一块位置

`create_elf_tables()` 写入 `argv[]` 时，并不是再次复制字符串本身，而是把已有参数字符串地址写成指针：

```text
argv[i] -> 参数字符串
```

Linux 同时维护：

```text
mm->arg_start
mm->arg_end
mm->env_start
mm->env_end
```

因此需要区分：

```text
初始栈上的“指针表”
```

和：

```text
这些指针指向的字符串内容
```

这也是为什么改变 `RSP` 并不会自动改变 `argv[1]` 字符串所在的地址。

---

## 9. `AT_RANDOM` 也展示了“表项指向数据”的模式

Linux 5.10 在构造初始栈时生成 16 个随机字节，并把它们放入用户栈区域，然后建立：

```text
AT_RANDOM -> 这 16 个字节的地址
```

因此 auxiliary vector 的 `a_val` 有时是普通整数：

```text
AT_PAGESZ -> 4096
```

有时是用户地址：

```text
AT_RANDOM -> pointer
AT_EXECFN -> pointer
AT_PLATFORM -> pointer（若架构提供）
```

分析 auxv 时必须先根据 `a_type` 判断 `a_val` 的语义，不能把所有值都当普通整数。

---

## 10. 初始 `RSP` 的 16 字节对齐

Linux 5.10 的 `create_elf_tables()` 对向下增长栈使用：

```text
STACK_ROUND(...)
```

其实现把最终位置向下对齐到 16 字节边界。

因此在本课程的 x86-64 ELF 实验中， `_start` 的初始：

```text
RSP % 16 == 0
```

可以直接验证。

这里必须和后面“普通函数调用边界的 ABI 对齐”分开理解。

当前讨论的是：

```text
内核把控制权交给 ELF 程序入口时的初始 RSP
```

A08 再分析：

```text
call 压入返回地址后
函数入口和调用点分别要求怎样的栈对齐
```

两者有关，但不是同一个观察时刻。

---

## 11. `_start` 与 `main` 不是一回事

很多学习材料直接从：

```c
int main(int argc, char **argv)
```

开始，因此容易形成一个错误印象：

> 内核直接调用 `main(argc, argv)`。

实际上，ELF 入口首先到达 `_start`（准确入口由 ELF header 和加载过程决定）。运行时启动代码解析初始进程状态并完成必要初始化，随后才按照 C 运行时约定进入 `main()`。

因此：

```text
内核 -> ELF entry / _start -> C runtime -> main
```

才是更接近真实执行过程的模型。

本节只分析 `_start` 能直接看到的初始栈，不提前展开 libc 启动流程。

---

## 12. 配套实验

实验目录：

[`../labs/06-initial-user-stack/`](../labs/06-initial-user-stack/)

实验使用自己定义的 `_start`，不链接 libc，并按下面的顺序解析初始栈：

```text
保存 initial RSP
→ 检查 16 字节对齐
→ 读取 argc
→ 定位 argv[]
→ 验证 argv[argc] == NULL
→ 定位并扫描 envp[]
→ 跳过 envp NULL
→ 每次 16 字节扫描 auxv
→ 找到 AT_PAGESZ
→ 扫描到 AT_NULL
```

运行方式固定为：

```bash
env -i DEMO=1 ./initial-stack alpha beta
```

因此：

```text
argc = 3
```

并至少存在一个环境变量。

实验把六个检查结果编码成退出状态，全部成功时为：

```text
63
```

---

## 13. 阅读初始栈时的判断方法

以后在 GDB、core dump 或入口汇编中看到初始 `RSP`，建议按下面的顺序恢复结构：

```text
1. [RSP] 读取 argc
2. RSP+8 得到 argv base
3. 依据 argc 定位 argv[argc] NULL
4. 下一槽得到 envp base
5. 扫描到 envp NULL
6. 下一槽得到 auxv base
7. 每 16 字节读取 type/value
8. 扫描到 AT_NULL
9. 对指针型条目继续解引用查看字符串或数据
```

这样做比从一大片十六进制栈内存中猜结构可靠得多。

---

## 14. 本节小结

需要牢固掌握下面的主线：

```text
_start
  |
  v
[RSP] = argc
  |
  +--> argv[] --> NULL
  |
  +--> envp[] --> NULL
  |
  +--> auxv(type,value) ... --> AT_NULL
```

以及四个边界：

1. `RSP` 的含义来自 x86-64 执行状态，而初始内容布局来自进程启动约定和 Linux ELF 加载实现；
2. `argv[]`、`envp[]` 保存的是指针，字符串位于它们指向的区域；
3. auxiliary vector 是 type/value 对，`AT_NULL` 用于结束扫描；
4. 初始入口栈对齐与普通函数调用时的 ABI 栈对齐要分开观察。

下一部分将在此基础上进一步衔接 A07 的 `call/ret` 和 A08 的 System V AMD64 ABI。
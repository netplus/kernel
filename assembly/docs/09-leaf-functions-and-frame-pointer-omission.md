# 第 9 课（第三部分）：leaf function 与 frame pointer omission

A09 前两部分已经建立了经典 `%rbp` 栈帧，并观察了局部变量与 spill/reload。接下来要处理一个很常见的反例：**很多真实函数根本没有 `push %rbp; mov %rsp,%rbp`，甚至有局部内存对象时也不一定修改 `%rsp`。这样的函数是否“没有栈帧”？栈展开又怎样理解它？**

本节先把两个容易混在一起的优化拆开：

1. frame pointer omission：不把 `%rbp` 固定为 frame base；
2. Red Zone：leaf function 在 SysV AMD64 用户态 ABI 下可以使用当前 `%rsp` 以下 128 字节而不先调整 `%rsp`。

它们可以同时出现，但不是同一个机制。

## 1. 什么是 leaf function

leaf function 指执行过程中不再调用其他函数的函数。

例如：

```c
long f(long a, long b)
{
    return a + b;
}
```

如果最终机器代码中没有 `call`，那么从调用图角度看它就是 leaf function。

注意这里看的是**最终机器代码**。源码中写了辅助函数调用，但编译器把它内联以后，最终函数仍可能变成 leaf；反过来，编译器也可能因为插桩、栈保护等选项加入额外调用，所以不能只看 C 源码判断。

## 2. `%rbp` 不是建立函数调用的必要条件

x86-64 的 `call` 和 `ret` 隐式使用的是 `%rsp`：

```text
call:
    RSP = RSP - 8
    [RSP] = return address
    RIP = callee

ret:
    RIP = [RSP]
    RSP = RSP + 8
```

CPU 并不要求 `%rbp` 参与函数调用。

SysV AMD64 ABI 要求 `%rbp` 作为 callee-saved 寄存器保持调用前后的值，但 ABI 也不要求每个函数必须把它用作 frame pointer。只要函数不修改 `%rbp`，或者修改后在返回前恢复原值，就满足保存规则。

因此：

```text
有没有函数调用          由 call/ret 和 ABI 边界决定
有没有 `%rbp` frame     由函数实现/编译器策略决定
```

## 3. frame pointer omission 到底省略了什么

经典 frame pointer 函数常见：

```asm
pushq %rbp
movq  %rsp, %rbp
...
popq  %rbp
ret
```

这里 `%rbp` 提供一个在函数执行期间较稳定的 frame base。

当编译器省略 frame pointer 时，它不再维护这条链。局部状态可以直接相对 `%rsp` 访问：

```asm
movq %rdi, -24(%rsp)
movq %rsi, -16(%rsp)
```

或者在显式分配栈空间后：

```asm
subq $24, %rsp
movq %rdi, 0(%rsp)
movq %rsi, 8(%rsp)
...
addq $24, %rsp
ret
```

这样做至少有两个直接效果：

- 少了维护 `%rbp` frame 的指令；
- `%rbp` 可以继续作为一个普通的 callee-saved 通用寄存器参与寄存器分配。

但代价是不能再假定 `0(%rbp)`/`8(%rbp)` 形成传统 frame pointer 链。

## 4. “省略 `%rbp`”不等于“不使用栈”

这是本节最重要的区分。

函数可以：

```text
省略 `%rbp`
但仍然修改 `%rsp`
仍然在栈中保存局部对象、spill、保存寄存器或 outgoing arguments
```

反过来，一个保留 `%rbp` 的 leaf function 也可能完全不执行 `sub %rsp`。

因此看到：

```asm
ret
```

前没有 `leave`，不能推断“这个函数没有栈状态”；必须实际观察 `%rsp` 的调整和内存访问。

## 5. Red Zone 为什么会让 leaf function 看起来“完全没有栈帧”

A08 已经讲过 SysV AMD64 用户态 ABI 的 128-byte Red Zone。对于不会继续调用其他函数的 leaf function，编译器可以把短生命周期的局部内存放在当前 `%rsp` 以下，而不先执行 `sub %rsp`。

本节实验：

```c
__attribute__((noinline)) long leaf_slots(long a, long b)
{
    volatile long slots[2];

    slots[0] = a + 3;
    slots[1] = b + 5;
    return slots[0] + slots[1];
}
```

`volatile` 的目的是让两个槽确实发生内存访问，避免 `-O2` 把它们完全消除。

当前 GCC 14.2.0 的默认 `-O2` 结果为：

```asm
add    $0x3,%rdi
add    $0x5,%rsi
mov    %rdi,-0x18(%rsp)
mov    %rsi,-0x10(%rsp)
mov    -0x18(%rsp),%rax
mov    -0x10(%rsp),%rdx
add    %rdx,%rax
ret
```

关键点有两个：

```text
没有 push %rbp / mov %rsp,%rbp
没有 sub/add %rsp
```

但函数依然真实访问了栈附近的内存：`-0x18(%rsp)` 和 `-0x10(%rsp)`。这些地址位于当前 `%rsp` 以下，属于 Red Zone 的使用。

因此更准确的描述是：

> 这个函数省略了 frame pointer，也没有显式移动 `%rsp`，但它仍然利用了当前调用栈附近的 Red Zone 内存。

## 6. 强制保留 frame pointer 后发生什么

同一个源文件改用：

```text
-O2 -fno-omit-frame-pointer
```

当前 GCC 14.2.0 生成：

```asm
push   %rbp
add    $0x3,%rdi
add    $0x5,%rsi
mov    %rsp,%rbp
mov    %rdi,-0x10(%rbp)
mov    %rsi,-0x8(%rbp)
mov    -0x10(%rbp),%rax
mov    -0x8(%rbp),%rdx
add    %rdx,%rax
pop    %rbp
ret
```

这里恢复了 `%rbp` frame，但仍没有：

```asm
subq $N, %rsp
```

这是因为 leaf function 仍可以使用 Red Zone。`push %rbp` 把 `%rsp` 降低 8 字节，`%rbp` 随后指向这个位置；`-16(%rbp)` 和 `-8(%rbp)` 对应的局部内存仍位于当前栈顶以下。

这个结果说明：

```text
是否保留 frame pointer
≠
是否需要显式分配局部栈空间
```

## 7. 关闭 Red Zone 后怎样组织栈槽

为了把 Red Zone 的影响单独去掉，实验再使用：

```text
-O2 -mno-red-zone
```

当前 GCC 生成：

```asm
sub    $0x18,%rsp
add    $0x3,%rdi
add    $0x5,%rsi
mov    %rdi,(%rsp)
mov    %rsi,0x8(%rsp)
mov    (%rsp),%rax
mov    0x8(%rsp),%rdx
add    $0x18,%rsp
add    %rdx,%rax
ret
```

这一次仍然没有 `%rbp` frame，但函数必须先真正移动 `%rsp`，为局部内存建立可用空间。

进入函数时普通 SysV AMD64 调用边界满足：

```text
RSP mod 16 = 8
```

减去 24 字节后：

```text
(RSP - 24) mod 16 = 0
```

虽然本函数是 leaf、后面没有 `call`，当前编译器仍选择了这个布局；具体 frame size 属于当前代码生成结果，不能把 `24` 当成 ABI 固定值。

返回前：

```asm
addq $24, %rsp
```

把 `%rsp` 恢复到函数入口值，然后 `ret` 再弹出 caller 压入的返回地址。

## 8. 三种版本放在一起看

同一个 C 函数形成了很清楚的对照：

```text
默认 -O2
  frame pointer: 省略
  Red Zone:      使用
  RSP 调整:      无
  局部访问:      负的 RSP 偏移

-O2 -fno-omit-frame-pointer
  frame pointer: 保留
  Red Zone:      仍可使用
  RSP 调整:      push/pop RBP
  局部访问:      负的 RBP 偏移

-O2 -mno-red-zone
  frame pointer: 省略
  Red Zone:      禁止
  RSP 调整:      sub/add 24
  局部访问:      当前 RSP 的 0/8 偏移
```

由此可以把三个问题独立判断：

1. `%rbp` 是否作为 frame pointer？
2. `%rsp` 是否发生显式调整？
3. 函数是否使用 Red Zone？

不能用其中一个现象替代另外两个。

## 9. 为什么这对后续栈展开很重要

如果所有函数都有传统 `%rbp` 链，那么可以直观地沿：

```text
current RBP
→ saved previous RBP
→ previous frame
```

回溯。

但默认优化代码经常省略 frame pointer。此时 `%rbp` 可能完全没有描述当前 frame 的意义，甚至可能保存普通数据。

这并不意味着调试器无法展开。编译器和汇编器可以通过 DWARF Call Frame Information（CFI）描述：

- 当前 Canonical Frame Address（CFA）怎样计算；
- 返回地址保存在哪里；
- callee-saved 寄存器怎样恢复。

A09 下一部分将从这里进入 `.cfi_*` 指令、`.eh_frame` 与基本 unwind 规则。

## 10. RFLAGS 与控制流观察

本实验三个 `leaf_slots` 版本都没有条件跳转，控制流都是线性的：

```text
函数入口
→ 算术与内存访问
→ 恢复必要的栈状态
→ ret
```

`add` 会更新算术标志位，但普通函数调用约定并不把这些算术状态标志作为跨函数返回值保存。本实验的正确性只依赖返回寄存器 `%rax`、callee-saved 规则和正确恢复 `%rsp`，不依赖 caller 在函数返回后继续读取本函数计算产生的 ZF/SF/CF/OF。

## 11. 本节实验

实验入口：[`../labs/09-leaf-frame-omission/`](../labs/09-leaf-frame-omission/)

本次实际验证环境：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
GNU objdump 2.44
```

三个版本均构建并运行通过：

```text
leaf-default        leaf_slots(7,11)=26
leaf-frame-pointer  leaf_slots(7,11)=26
leaf-no-red-zone    leaf_slots(7,11)=26
```

同时检查了：

- AT&T 反汇编；
- Intel 反汇编；
- `nm` 中的 `leaf_slots` 符号；
- `readelf -h` 的 ELF64 / x86-64 目标信息。

当前环境未安装 GDB，因此没有执行单步验证。

## 12. 本节完成后应能回答

1. leaf function 是按源码还是按最终机器代码判断？
2. 为什么 `%rbp` 不是函数调用的必要组成部分？
3. frame pointer omission 省略了什么，又没有省略什么？
4. 为什么“没有修改 `%rsp`”仍可能发生真实栈内存访问？
5. Red Zone 与 frame pointer omission 为什么是两个独立机制？
6. 关闭 Red Zone 后，省略 `%rbp` 的函数怎样访问局部栈空间？
7. 为什么省略 frame pointer 后不能再可靠依赖 `%rbp` 链展开？
8. 为什么 DWARF CFI 可以为下一阶段提供更一般的 unwind 描述？

下一最小单元继续 A09：DWARF CFI、CFA、返回地址恢复规则与最小调用栈展开实验。

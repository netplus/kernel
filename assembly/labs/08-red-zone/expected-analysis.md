# A08 Red Zone 实验结果分析

验证环境：

```text
GCC 14.2.0
GNU assembler 2.44
GNU ld 2.44
GNU objdump/nm/readelf 2.44
GDB：当前环境未安装
```

实际执行：

```text
asm leaf result=66
red-zone value survived nested call=0
compiler leaf result=50
```

程序退出码为 0。

## 1. 手写 leaf function

`red_zone_leaf` 的关键反汇编为：

```text
mov    %rsp,%r10
movq   $0xb,-0x8(%rsp)
movq   $0x16,-0x10(%rsp)
movq   $0x21,-0x78(%rsp)
...
cmp    %r10,%rsp
ret
```

三个槽分别位于入口 `%rsp` 下方 8、16 和 120 字节，都在 128-byte Red Zone 内。函数没有调整 `%rsp`，结果仍为 `11 + 22 + 33 = 66`。

## 2. 为什么 Red Zone 数据不能跨普通调用依赖

`red_zone_call_boundary` 在入口 `%rsp-16` 保存哨兵，然后执行：

```text
sub    $0x8,%rsp
call   red_zone_nested
add    $0x8,%rsp
```

设函数入口 `%rsp = S`。`sub $8` 后调用点为 `S-8`，满足普通 SysV 调用边界；`call` 再把返回地址压到 `S-16`，恰好覆盖原来的哨兵槽。

因此函数恢复到入口 `%rsp` 后，`S-16` 已不再是原值，程序输出 `survived=0`。

这个结果不意味着“任何 Red Zone 字节在任何调用后必然被修改”，而是说明 ABI 并不保证 caller 的 Red Zone 数据跨函数调用保存。需要跨调用存活的数据应放入正式栈帧、callee-saved 寄存器或其他具有明确生命周期的位置。

## 3. GCC leaf function

当前 GCC 14.2 `-O2` 下，`compiler_leaf()` 的局部 `volatile` 数组被放在：

```text
-0x28(%rsp)
-0x20(%rsp)
-0x18(%rsp)
-0x10(%rsp)
```

函数没有 `sub %rsp`，直接使用 Red Zone，并最终 `ret`。这是 leaf function 使用 Red Zone 减少 prologue/epilogue 指令的典型例子。

这属于当前编译器和优化结果，不应把具体偏移写成 ABI 固定布局。

## 4. Linux kernel 5.10 边界

Linux v5.10 `arch/x86/Makefile` 在 x86-64 路径给 `KBUILD_CFLAGS` 加入 `-mno-red-zone`。因此内核 C 代码不能依赖用户态 SysV ABI 的 Red Zone。其背景是内核执行期间可能发生中断、异常等入口活动，内核必须使用自己的栈和入口约束，而不是假定 `%rsp` 以下 128 字节由用户态 ABI 规则保护。

本实验只验证普通用户态 SysV 函数调用；Linux 5.10 的异常、中断和系统调用入口在后续章节结合源码单独分析。

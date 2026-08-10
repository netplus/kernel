# Lab 07：direct `call`、`ret` 与返回地址

## 1. 实验目标

本实验只验证 A07 的第一最小单元：x86-64 普通 near direct `call` 与 near `ret` 的核心语义。

需要确认：

1. direct `call` 把下一条指令地址保存到栈顶；
2. 64 位模式下该返回地址占 8 字节，因此进入被调用函数时 `RSP` 比调用前小 8；
3. `ret` 从当前栈顶取得返回地址，并把 `RSP` 增加 8；
4. 匹配的 `call`/`ret` 返回后，`RSP` 恢复到调用前值；
5. 当前实验中的 direct call 使用 `E8 rel32`，`ret` 使用 `C3`；
6. 退出状态只用于验证路径，不用于表达完整寄存器值。

对应教程：

[`../../docs/07-call-ret-and-return-address.md`](../../docs/07-call-ret-and-return-address.md)

## 2. 文件

```text
call_ret.s            纯汇编实验
Makefile              构建、运行、反汇编和符号查看
gdb.cmd               分阶段观察 RSP 和栈顶的 GDB 脚本
expected-analysis.md  预期结果与参考反汇编
```

## 3. 构建和运行

```bash
make clean all
make run
```

预期：

```text
exit status=37 (expected 37)
```

程序内部已经做两项检查：

```text
callee 入口 [RSP] == after_direct_call
返回以后 RSP == 调用前保存的 RSP
```

并检查 `direct_target` 把 `RAX` 从 10 增加到 13。

## 4. 反汇编

```bash
make disasm
```

重点寻找：

```text
before_direct_call
call direct_target
after_direct_call
direct_target_entry
before_ret
ret
```

当前参考构建中，关键字节为：

```text
E8 1B 00 00 00   direct near call
C3               near ret
```

同时输出 AT&T 和 Intel 两种语法，确认语法显示差异不会改变实际控制流语义。

## 5. 符号地址

```bash
make symbols
```

通过：

```text
before_direct_call
after_direct_call
direct_target
before_ret
```

可以直接验证 `call` 保存的“下一条指令地址”。

## 6. GDB 观察

具备 GDB 时运行：

```bash
make gdb
```

脚本会在四个位置停止：

```text
before_direct_call
 direct_target_entry
before_ret
after_direct_call
```

建议重点比较：

```text
调用前 RSP
callee 入口 RSP
callee 入口 [RSP]
ret 前 [RSP]
返回后 RSP
```

理论关系：

```text
callee_entry_rsp = caller_rsp - 8
[callee_entry_rsp] = after_direct_call
returned_rsp = caller_rsp
```

当前自动化执行环境没有安装 GDB，因此脚本已静态检查，但本次未执行 GDB。

## 7. 已实际验证

本实验对应的源文件已在 Linux x86-64 环境实际执行：

```text
as --64 -g     通过
ld             通过
程序运行       exit status=37
objdump        通过
objdump -Mintel 通过
nm -n          通过
GDB            环境未安装，未执行
```

详细地址与结果见 [`expected-analysis.md`](expected-analysis.md)。

## 8. 本实验暂不覆盖

下面内容属于 A07 后续最小单元：

- indirect `call`；
- 函数指针；
- 递归产生的多层返回地址；
- 返回地址损坏及其后果。

完成这些内容后再把 A07 标记为整章完成。
# A09 实验：正确、缺失与错误 CFI 的栈展开边界

## 1. 验证目标

本实验用同一条最小调用链比较三种汇编 frame：

```text
main -> c_top -> c_mid -> {good_frame|missing_frame|wrong_frame} -> capture_trace
```

三者机器指令都能正常执行并返回；区别只在 unwind 元数据：

- `good_frame`：`.cfi_def_cfa_offset` 与真实 `%rsp` 变化一致；
- `missing_frame`：完全不生成该函数自己的 FDE；
- `wrong_frame`：存在 FDE，但故意把 `subq $8,%rsp` 之后的 CFA offset 错写成 8，而真实 caller CFA 应为 `%rsp+16`。

实验要观察：**程序执行正确，不代表调用栈一定可正确恢复；unwinder 还依赖与当前 PC 和机器状态一致的恢复规则。**

## 2. 构建

```bash
make
```

默认使用：

```text
-g -O1 -fno-omit-frame-pointer -fno-optimize-sibling-calls -rdynamic
```

这里保留 C 层 frame pointer 并禁止 sibling-call 优化，是为了让实验把变量尽量集中在三个手写汇编 frame 上，而不是让外围 C 调用链本身成为干扰因素。

## 3. 运行

```bash
make run
```

本仓库维护时实际验证环境：

```text
GCC 14.2.0
GNU binutils 2.44
x86-64 glibc 环境
```

实际结果：

```text
good-cfi    backtrace 返回 8 层，可越过 good_frame 继续看到 c_mid/c_top/main 及 libc 启动帧
missing-cfi backtrace 返回 2 层，在 missing_frame 处停止
wrong-cfi   backtrace 返回 2 层，在 wrong_frame 处停止
三个进程均 exit 0
```

地址因 PIE/ASLR 和链接结果会变化，不应把某次地址写成固定结论。

## 4. 为什么三个程序都能正常返回

三个汇编函数真实执行的栈动作相同：

```asm
subq $8, %rsp
call capture_trace
addq $8, %rsp
ret
```

函数入口满足 SysV AMD64 常见状态 `%rsp mod 16 = 8`；`subq $8,%rsp` 后调用点恢复到 16 字节边界。`call`、`add` 和 `ret` 使用的是真实机器栈，并不会读取 `.cfi_*`。

所以即使 CFI 缺失或错误，普通控制流仍可正常返回。

## 5. 检查机器指令

```bash
objdump -drwC unwind-demo
objdump -drwC -Mintel unwind-demo
```

应确认三个函数都有相同的 `sub/call/add/ret` 轮廓。`.cfi_*` 不会出现在反汇编指令流中。

## 6. 检查 `.eh_frame`

```bash
readelf --debug-dump=frames unwind-demo
nm -n unwind-demo | grep -E 'good_frame|missing_frame|wrong_frame'
```

本次实际观察到：

- `good_frame` 的地址范围有 FDE，`subq $8,%rsp` 后出现 `DW_CFA_def_cfa_offset: 16`，返回前恢复为 8；
- `missing_frame` 的地址范围没有对应 FDE；
- `wrong_frame` 有 FDE，但在 `subq $8,%rsp` 后仍写成 `DW_CFA_def_cfa_offset: 8`。

将 `nm` 给出的函数范围与 FDE 的 PC 区间对照，可以区分“没有规则”和“存在错误规则”。

## 7. 观察边界

本实验记录的是当前 glibc/backtrace 实现和当前构建结果下的实际现象，不应扩大成下面这种绝对规则：

```text
缺少 CFI -> 所有 unwinder 都一定在这里停止
错误 CFI -> 所有 unwinder 都一定返回 2 帧
```

不同 unwinder 可以实现 frame-pointer fallback、启发式扫描或平台专用策略。因此可移植的结论是：

```text
正确 CFI 为标准 unwind 提供可靠恢复规则；
缺失 CFI 时不能再假定元数据展开可以跨过该 frame；
错误 CFI 比缺失更危险，因为它向 unwinder 提供了错误的恢复描述。
```

## 8. GDB

当前维护环境未安装 GDB，因此未执行动态 `bt`。安装 GDB 后可以分别执行：

```bash
gdb --args ./unwind-demo good
gdb --args ./unwind-demo missing
gdb --args ./unwind-demo wrong
```

在 `capture_trace` 断点处使用 `bt`，再与 `backtrace(3)` 结果比较。注意 GDB 可能采用不同的 fallback 策略，因此结果不要求与 glibc `backtrace()` 完全相同。

# Expected analysis

## 用户态可验收结论

第一次写匿名映射前，`mincore()` 应允许观察到该页尚未驻留；写入后该页应驻留，写入值 `0x5a` 可正常读回。`ru_minflt` 应体现一次或多次 minor fault 增量，但精确增量受运行时噪声影响，不作为 ABI 结论。

最关键的控制流结论是：成功处理 demand fault 后，CPU 返回到 faulting RIP，原 store 重新执行并完成。因此程序不会收到 SIGSEGV，也不需要用户态手工推进 RIP。

## Linux 5.10 内核侧预期

对于本实验的第一次用户态写访问，三类现场应满足：

```text
pt_regs->ip  = faulting_store() 中写内存的那条指令
CR2          = p 指向的 faulting linear address
error_code   = user + write + non-present 的组合
```

这里的 `error_code` 应按 x86 page-fault error-code 位定义解析，而不能直接当作 Linux `FAULT_FLAG_*`。CR2 也不属于 `struct pt_regs`。

若 VMA 权限允许写入且内存管理成功建立映射，`exc_page_fault()` 下游处理返回，异常返回路径恢复用户现场，faulting store 被重试。若把地址换成没有合法 VMA 的地址，则会进入另一类结果；该失败路径不属于本实验的主验收条件。

## 证据边界

当前维护环境只完成了用户态构建、运行、residency/minor-fault 观测和反汇编。Linux 5.10 kernel-GDB 现场仍待具备匹配 guest + `vmlinux` 的环境后执行。因此 CR2/error-code/`pt_regs` 的上述关系是源码与架构导出的验收预期，不是本次动态观测数据。

# A16 实验：可恢复的用户态 demand page fault

本实验验证 A16 第一部分最基础的一条路径：用户进程已经拥有一个合法的匿名 VMA，但对应页尚未驻留；第一次写访问触发 `#PF`，Linux 处理成功后返回原 faulting instruction，该 store 重新执行并成功完成。

## 1. 要验证什么

把以下对象严格分开：

```text
faulting RIP   CPU 保存的触发缺页指令地址
fault address  触发访问的线性地址；内核入口从 CR2 读取
PF error code  CPU 给出的 page-fault 原因位图
VMA            Linux 内存管理判断该地址是否合法的进程映射
```

用户态程序能够直接验证“页从未驻留到驻留、minor fault 增加、原 store 最终成功”；CR2、PF error code 和内核 `pt_regs->ip` 需要匹配 Linux 5.10 的 kernel-GDB/ftrace 环境进一步观察。

## 2. 构建与运行

```bash
make clean
make
make check
```

`make check` 会运行程序，并反汇编可执行文件。程序使用 `mmap(MAP_PRIVATE | MAP_ANONYMOUS)` 建立一页可读写映射，不在 `mmap()` 后主动访问该页；随后用 `mincore()` 检查 residency，再执行第一次 store。

## 3. 用户态观察点

典型关系应为：

```text
resident_before = 0
faulting_store(p)
resident_after  = 1
minor_fault_delta >= 1
value = 0x5a
```

`minor_fault_delta` 不是 ABI 常量，不能要求所有环境都精确等于 1；程序本身、动态链接器或观测调用可能引入其他 minor faults。真正稳定的结论是：第一次访问能够被内核恢复，页随后驻留，store 的值可读回。

反汇编中应定位真正访问映射页的指令。当前验证构建（GCC，`-O0 -g3`）观察到：

```asm
mov BYTE PTR [rax],0x5a
```

具体地址随 PIE/工具链变化，不应写死。

## 4. Linux 5.10 内核侧验证

需要隔离的 Linux 5.10 guest、与运行内核匹配的 `vmlinux` 和 kernel-GDB。源码事实基线见：

[`../../source-paths/16-page-fault-entry-linux-5.10.md`](../../source-paths/16-page-fault-entry-linux-5.10.md)

推荐在 `exc_page_fault()` 或由当前 `vmlinux` 反汇编确认的早期安全位置观察：

```text
regs->ip     是否对应 faulting_store() 中真正的 store
read_cr2()   是否等于映射页内被写入的地址
error_code   是否表示 user-mode write to a non-present page
```

随后继续执行，确认 `handle_page_fault()` 进入 user-address 路径并成功返回；回到用户态后应重新执行 faulting store，而不是跳过该指令。

不要硬编码 `exc_page_fault` 地址。KASLR、编译配置和具体构建都会改变符号地址。

## 5. 安全边界

本实验只制造合法匿名 VMA 上的可恢复 demand fault，不故意访问 unmapped address，也不修改内核页表。页表/VMA 查找、匿名页分配和 COW 的完整策略属于 `memory/` 课程；A16 只观察异常入口与内存管理的交接。

## 6. 当前实测

维护环境已实际执行 `make clean all check`。本次观察到：

```text
page_size=4096
resident_before=0
resident_after=1
minor_fault_delta=1
value=0x5a
```

反汇编确认 `faulting_store()` 的实际写指令为 `mov BYTE PTR [rax],0x5a`。当前环境没有匹配的 Linux 5.10 guest、`vmlinux` 与 kernel-GDB 会话，因此 CR2、PF error code 和内核 `pt_regs` 的动态值未执行，不将预期值写成实测结果。

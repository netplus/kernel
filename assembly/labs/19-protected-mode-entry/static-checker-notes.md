# A19 `startup_32` 静态验收脚本说明

本文件补充说明 `verify_startup32_contract.py` 的验收范围。脚本的目的不是替代 QEMU/GDB 动态观察，而是把第三部分已经由 Linux 5.10 源码事实核验确认的若干**顺序关系和接口契约**转换成可重复执行的检查，减少后续源码更新或文档修订时仅靠人工目测造成的遗漏。

## 1. 使用方法

在 Linux kernel 5.10 源码树旁执行：

```bash
python3 assembly/labs/19-protected-mode-entry/verify_startup32_contract.py /path/to/linux-5.10
```

脚本读取：

```text
arch/x86/boot/compressed/head_64.S
arch/x86/kernel/verify_cpu.S
```

它不修改内核源码，也不要求先构建 `bzImage`。

## 2. 当前自动检查的事实

`head_64.S` 部分检查以下顺序：

```text
.code32
  -> startup_32
  -> cld / cli
  -> lgdt
  -> __BOOT_DS 装载
  -> DS / ES / FS / GS / SS reload
  -> ESP = boot_stack_end
  -> call verify_cpu
  -> testl %eax,%eax
  -> 后续 CR4 write
```

这里检查的是**源码中的时间关系**，不是用正则表达式证明 CPU 已经进入某种运行模式。例如，`.code32` 只说明 assembler 的编码上下文；`lgdt` 只说明 GDTR 被重新装载；data-segment reload 也不能替代后续 far `lret` 对 `CS` 的更新。

`verify_cpu.S` 部分检查：

- probing 前后存在 flags 保存/恢复路径；
- success path 把 `%eax` 置为 0；
- failure path 把 `%eax` 置为 1。

因此脚本可以自动守住“feature gate 成功发生在后续 CR4 preparation 之前”这一课程边界，但不能据此推出 `CR4.PAE`、`CR3`、`EFER.LME`、`CR0.PG` 或 `CS.L` 已经建立。

## 3. 脚本不能证明什么

即使全部检查通过，也**不能**把下面内容写成实测结果：

```text
运行时 GDTR.base
DS/ES/FS/GS/SS hidden descriptor cache 的具体值
boot_stack_end 的运行时线性/物理地址
verify_cpu probing 期间每一个 EFLAGS 快照
CR4、CR3、EFER、CR0 的运行时值
far lret 前后的 CS/RIP
```

这些仍需要匹配 Linux 5.10 构建产物的反汇编或 QEMU/GDB early-boot 现场验证。

## 4. 验收方式

脚本成功时应逐项输出 `PASS:`，最后输出通过的检查数量；任一关键源码模式缺失或顺序关系不满足时，以非零状态退出并输出 `FAIL:`。因此后续若在 Linux 5.10 基线上调整第三部分教程、实验或 source-path，应先运行该脚本，再判断是源码事实发生变化、脚本模式过窄，还是课程内容需要修订。

当前维护环境已对脚本本身完成 Python 语法检查，但没有可执行的 Linux v5.10 checkout，因此尚未执行针对真实 `head_64.S` / `verify_cpu.S` 文件的整套检查。这个限制只影响“脚本已在真实源码树运行”的证据，不改变已经单独完成的 Linux 5.10 源码事实核验。
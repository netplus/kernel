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

- probing 前保存 caller flags；
- failure path 在返回前 `popf`，随后返回 `%eax=1`；
- success path 在返回前 `popf`，随后返回 `%eax=0`。

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

## 5. 本轮对 Linux v5.10 实际源码的核验记录

本轮重新读取 upstream Linux `v5.10` 的两个真实源文件，并把 checker 当前使用的模式逐项对照到实际文本：

```text
arch/x86/boot/compressed/head_64.S
  .code32
  SYM_FUNC_START(startup_32)
  cld / cli
  lgdt
  __BOOT_DS -> DS/ES/FS/GS/SS
  ESP = rva(boot_stack_end)(EBP)
  call verify_cpu
  testl %eax,%eax
  ...
  movl %eax,%cr4

arch/x86/kernel/verify_cpu.S
  pushf                         # 保存 caller flags
  ...
.Lverify_cpu_no_longmode:
  popf
  movl $1,%eax
  ret
.Lverify_cpu_sse_ok:
  popf
  xorl %eax,%eax
  ret
```

随后使用 checker 的同一组正则和顺序判定，对上述 Linux v5.10 实际源码片段执行 `check_text()`；入口顺序、caller-flags 保存、failure return 和 success return 四类检查均通过。这一步比仅做 Python 语法检查更强：它确认当前 checker 的关键模式能够匹配 v5.10 的真实源码写法，而不是只匹配自测试构造的 fixture。

当前环境仍没有完整 Linux v5.10 文件系统 checkout，因此尚未通过脚本的命令行 `main()` 直接打开 `/path/to/linux-5.10` 执行整文件检查，也没有运行 Kbuild、objdump 或 QEMU/GDB。这里记录的结果只证明 **checker 核心匹配/顺序逻辑已经对照真实 v5.10 源码文本执行通过**；不能把它扩大为构建产物或动态机器状态的验证结果。

## 6. checker 自测试的实际执行记录

本轮把仓库当前的 `verify_startup32_contract.py` 与 `test_verify_startup32_contract.py` 放入可执行 Python 环境，实际运行：

```bash
python3 -m unittest -v test_verify_startup32_contract.py
```

结果为：

```text
Ran 9 tests in 0.001s
OK
```

九个测试全部通过，覆盖一个正例和八类回归拒绝条件：

- 正常 `startup_32` / `verify_cpu` fixture 可以通过；
- `lgdt` 晚于 data-segment reload 会被拒绝；
- `DS/ES/FS/GS/SS` reload 顺序被破坏会被拒绝；
- `boot_stack_end` 晚于 `verify_cpu()` 建立会被拒绝；
- `testl %eax,%eax` 之前提前写 CR4 会被拒绝；
- failure path 缺失 `popf` 会被拒绝；
- success path 缺失 `popf` 会被拒绝；
- failure path 返回错误 `%eax` 值会被拒绝；
- success path 返回错误 `%eax` 值会被拒绝。

这次实际执行验证的是 checker 自身对已设计契约的接受/拒绝行为，不等价于在完整 Linux v5.10 checkout 上执行 `check-source`。因此证据层次仍保持为：fixture self-test 已实际运行；真实 v5.10 源码文本的核心匹配已验证；完整 checkout CLI、Kbuild/objdump 和 QEMU/GDB 仍待相应环境。

## 7. objdump checker 自测试的实际执行记录

本轮继续把仓库当前的 `verify_startup32_disassembly.py` 与 `test_verify_startup32_disassembly.py` 放入可执行 Python 环境，实际运行：

```bash
python3 test_verify_startup32_disassembly.py
```

进程返回值为 `0`，输出为：

```text
PASS: A19 disassembly checker positive fixture
PASS: A19 disassembly checker negative fixtures
```

正例验证 checker 能从 GNU `objdump` 风格文本中解析 `startup_32` 和 `verify_cpu`，并接受预期的 `cld -> cli -> lgdt -> DS/ES/FS/GS/SS reload -> call verify_cpu -> test %eax -> CR4 write` 顺序，以及 failure/success 两条 `popf -> EAX -> ret` terminal path。

负例则实际确认 checker 会拒绝：缺失 `lgdt`、segment reload 顺序破坏、在检查 `verify_cpu()` 返回值之前提前写 CR4、failure path 错误返回零、success path 错误返回一，以及 success path 缺失 `popf`。因此当前 parser/contract logic 的正负 fixture 行为已经实际执行，而不是仅完成脚本编写。

这一步仍然只是 **objdump checker 自身的 fixture 验证**。当前环境没有 Linux v5.10 的真实构建产物，所以尚未执行 `make check-disassembly DISASM=...`；也不能据此声称真实 `startup_32` 机器码或运行时 GDTR、segment hidden state、CR4/CR3/EFER/CS/RIP 已经动态验证。
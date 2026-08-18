# B05 source-contract checker self-test results

本文件记录 `test_verify_source_contract.py` 对 B05 L1 source-contract checker 自身的验收结果。它属于**工具证据**，只证明 checker 对正/负 fixture 的 acceptance/rejection 行为；不能替代真实 Linux v5.10 checkout 上的 L1 核验，也不能替代匹配 `vmlinux` 的 L2 或 QEMU/GDB/`initcall_debug` 的 L3 证据。

## 2026-08-18 执行结果

执行对象：

```text
boot-crash/labs/05-rest-init-to-userspace/verify_source_contract.py
boot-crash/labs/05-rest-init-to-userspace/test_verify_source_contract.py
```

执行命令等价于：

```bash
cd boot-crash/labs/05-rest-init-to-userspace
python3 -m unittest -v test_verify_source_contract.py
```

结果：

```text
Ran 9 tests
OK
exit code: 0
```

覆盖范围为 **1 个完整正例 + 8 个针对性负例**：

1. 完整正例必须通过全部 8 组 B05 source-contract；
2. 拒绝 `kthreadd` 先于 `kernel_init` / PID 1 创建；
3. 拒绝 `schedule_preempt_disabled()` 先于 `complete(&kthreadd_done)`；
4. 拒绝 `do_basic_setup()` 先于 `wait_for_completion(&kthreadd_done)`；
5. 拒绝 `do_basic_setup()` 不再拥有 `do_initcalls()`；
6. 拒绝 pure/core/postcore/arch/subsys/fs/device/late 顺序被破坏；
7. 拒绝把 `prepare_namespace()` 从 early `/init` 不可访问条件中移出、改成无条件调用；
8. 拒绝在 `SYSTEM_RUNNING` 之前开始 init exec 尝试；
9. 拒绝 `/sbin/init → /etc/init → /bin/init → /bin/sh` fallback 顺序被破坏。

## 执行环境说明

Python 测试进程启动时，宿主环境附带的 spreadsheet runtime warmup 输出了一条与本实验无关的初始化错误；随后 `unittest` 正常执行全部 9 个测试并返回 exit code 0。该 warmup 不参与 checker/test 的 import、fixture 构造或断言，因此不改变本次 self-test 结论。

本次运行使用从 GitHub 当前仓库读取的 checker 与 fixture 内容在本地临时目录复现执行；未取得 Linux v5.10 完整源码树，因此**没有**把本次结果标记为真实 v5.10 checkout 上的 L1 checker 通过。

## 证据边界

当前可以声称：

```text
工具证据：PASS
  9 unittest = 1 positive + 8 negative
  positive covers 8 contract groups
  exit code = 0
```

当前仍不能声称：

```text
L1：真实 Linux v5.10 checkout 上 checker CLI 已执行通过
L2：匹配构建的 vmlinux/nm/readelf/objdump 已验证
L3：QEMU/GDB/initcall_debug 已验证实际 PID、调度、rootfs 与 exec 路径
```

后续在实验 README 接入本结果时，应继续保持这四类证据的区别。
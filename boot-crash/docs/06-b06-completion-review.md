# B06 收章复核：Kexec 的问题模型与生命周期

本文是 B06《Kexec 解决什么问题》的收章复核。复核目标不是增加新的 Kexec 机制，而是确认正文、Linux 5.10 source-path、实验、expected analysis 与自动 source-contract checker 对同一组事实使用一致的边界，并判断 B06 是否已经达到可以进入 B07 的独立验收标准。

源码基线：upstream Linux v5.10，x86-64。

复核材料：

- [`06-kexec-why-and-lifecycle.md`](06-kexec-why-and-lifecycle.md)
- [`../source-paths/06-kexec-model-linux-5.10.md`](../source-paths/06-kexec-model-linux-5.10.md)
- [`../labs/06-kexec-lifecycle/README.md`](../labs/06-kexec-lifecycle/README.md)
- [`../labs/06-kexec-lifecycle/expected-analysis.md`](../labs/06-kexec-lifecycle/expected-analysis.md)
- [`../labs/06-kexec-lifecycle/verify_source_contract.py`](../labs/06-kexec-lifecycle/verify_source_contract.py)
- [`../labs/06-kexec-lifecycle/test_verify_source_contract.py`](../labs/06-kexec-lifecycle/test_verify_source_contract.py)
- [`../labs/06-kexec-lifecycle/selftest-results.md`](../labs/06-kexec-lifecycle/selftest-results.md)

---

## 1. 章节边界复核

B06 的问题是：**为什么 Kexec 必须把“准备下一映像”和“真正切换机器状态”拆成两个生命周期，以及 normal/crash image 为什么从准备阶段就具有不同资源假设。**

本章没有把后续内容提前混入主线：

```text
B06  生命周期、ownership、normal/crash 前置假设
B07  segment / page-list / file loader 的具体装载机制
B08  machine_kexec() / relocate_kernel 的机器切换
B09  purgatory
B10+ crashkernel、panic/crash execute、capture kernel 与 vmcore
```

正文和实验虽然会引用 segment、transition page table、`relocate_kernel` 与 `crashk_res`，但只把它们作为 B06 生命周期边界的证据，没有在本章完整展开后续机制。因此章节职责保持单一。

## 2. load 与 execute 的生命周期一致性

正文、source-path 与实验都采用同一个两阶段模型：

```text
healthy old kernel
  → load / validate / allocate / prepare
  → install struct kimage
  → syscall returns; old kernel continues running

later independent event
  → quiesce / crash handoff
  → machine_kexec()
  → architecture transition
  → new kernel
```

复核中没有发现把 `kexec_load()` / `kexec_file_load()` 成功误写成“CPU 已进入新内核”的位置。

`machine_kexec_prepare()` 也始终被放在 load phase：它可以准备 x86 transition page-table state，而这一阶段仍允许资源分配、失败和回滚。`machine_kexec()` 则被作为 point-of-no-return 一侧的 architecture transition 入口。Linux v5.10 中“不再分配内存/不要失败”的注释位于 `machine_kexec()` 定义之前；checker 已按这一真实源码布局验证，而不是假定注释位于函数体内。

这一边界是 B06 最重要的收章条件，当前材料一致。

## 3. `struct kimage` ownership 一致性

所有材料都把 `struct kimage` 解释为跨越 load syscall 生命周期的内核对象，而不是 syscall 栈帧中的临时描述。

成功加载后的 ownership handoff 为：

```text
normal image → kexec_image
crash image  → kexec_crash_image
```

traditional/file 两条路径最终都通过 `xchg()` 安装新的 image；被替换的旧 image 才进入释放路径。因此 syscall 返回后，下一映像仍由当前 kernel 的全局 Kexec 状态持有，等待未来 execute/crash event 消费。

实验把这一静态 ownership 结论与未来 L3 动态观察分开：`kexec -l` 后旧 kernel 的 uptime 继续增长，只能作为 load/execute 分离的运行时证据，不能反过来代替源码 ownership 核验。

## 4. 加载 API 与 image purpose 的二维模型

B06 全章一致地区分：

```text
加载 API：
  kexec_load
  kexec_file_load

image purpose：
  KEXEC_TYPE_DEFAULT
  KEXEC_TYPE_CRASH
```

traditional path 可以通过 `KEXEC_ON_CRASH` 表达 crash image；file path 可以通过 `KEXEC_FILE_ON_CRASH` 表达 crash image。因此不存在：

```text
kexec_load      == normal Kexec
kexec_file_load == crash Kexec
```

这种一一对应关系。

正文、source-path、实验和 checker 均保持这一二维模型。具体发行版是否允许某个组合，还受 `CONFIG_KEXEC`、`CONFIG_KEXEC_FILE`、签名、lockdown、LSM/IMA 和 userspace 工具等条件影响；课程没有把“源码接口可表达”夸大成“任意运行环境都可用”。

## 5. normal/crash 资源边界复核

B06 只选择了足以证明“crash image 从 healthy-time load phase 就已经特殊”的三组资源事实：

1. crash segment destination 受 `crashk_res` 范围约束；
2. control-page allocation 对 crash image 使用 crash-specific policy；
3. traditional/file 两条路径都只为 non-crash image 准备 `image->swap_page`。

三项结论在 source-path、正文、实验和 checker 中一致。

这里没有把 `crashk_res` 的建立过程提前写成 B06 内容；`crashkernel=` 参数解析和 reserved-memory 生命周期留给 B10。也没有把 `swap_page` 误解成普通 VM swap；它只作为后续 Kexec relocation/copy 算法所需的内部对象出现，具体用途留给 B07/B08。

## 6. normal execute 与 crash execute 的前置假设

B06 对两条 execute 路径只建立前置假设，而没有提前展开完整调用链：

```text
normal execute
  旧 kernel 被假定仍然健康，可以按计划收缩 ordinary activity

crash execute
  生产 kernel 已发生 fatal failure，不能把普通锁、调度、workqueue、设备 shutdown
  或普通内存分配继续当作可靠前提
```

因此 crash image 必须在健康时期预留、加载和安装。这个结论与 Kdump 后续课程衔接，但本章没有把 `panic()`、`crash_kexec()`、CPU stopping、`elfcorehdr` 或 capture kernel 混入 B06 主线。

## 7. 自动验收与证据等级复核

B06 当前自动 checker 固定 7 组 L1 source-contract：

1. traditional/file API 与 normal/crash purpose 维度分离；
2. `struct kimage` 通过 `xchg()` 安装到 persistent global slot；
3. crash destination 受 `crashk_res` 约束；
4. crash-specific control-page policy；
5. traditional/file path 的 normal-only `swap_page`；
6. `machine_kexec_prepare()` 位于 image installation 之前；
7. x86 prepare 建立 transition page-table state，且 point-of-no-return 注释与 `machine_kexec()` 定义关系符合 Linux v5.10 源码布局。

fixture suite 已实际执行：

```text
1 个完整正例
8 个针对性负例
Ran 9 tests
OK
exit code 0
```

完整正例返回全部 7 组 contract；负例分别破坏上述关键约束并被 checker 拒绝。

必须继续保持证据边界：

```text
fixture self-test        工具证据，已完成
真实 upstream v5.10     L1，当前未执行 checker CLI
匹配 vmlinux             L2，当前未执行
隔离 Kexec/Kdump VM      L3，当前未执行
```

因此 B06 可以说“checker/fixture 工具闭环已通过”，不能说“真实 v5.10 L1/L2/L3 已全部通过”。当前 README 与 expected analysis 对这一点表述一致。

## 8. 配置、术语和调用方向检查

本次收章复核重点检查了以下容易出错的表达：

- `CONFIG_KEXEC_CORE`、`CONFIG_KEXEC`、`CONFIG_KEXEC_FILE`、`CONFIG_CRASH_DUMP` 被作为需要区分的配置条件，而不是假定所有路径无条件存在；
- traditional/file 表示加载接口，normal/crash 表示映像用途；
- `machine_kexec_prepare()` 是 load-side architecture preparation，不是 execute；
- `machine_kexec()` 是从旧内核进入最小 transition 环境的方向，不是新内核回调旧内核；
- `crashk_res` 在 B06 中只承担 crash destination constraint 的事实角色；
- `swap_page` 没有与普通内存管理 swap 混淆；
- “load success”“image installed”“execute event”“new kernel running”保持为不同状态。

未发现需要阻止收章的新事实冲突。

## 9. B06 收章结论

B06 已满足当前课程的独立验收标准：

- 已有 Linux 5.10 source-path；
- 已有从问题背景到设计边界的正式教程；
- 已有对应实验和 expected analysis；
- 已有 7 组自动 L1 source-contract checker；
- 已有 1 正 + 8 负 fixture，并实际执行 9 / 9 PASS、exit code 0；
- 正文、源码记录、实验和自动验收对 load/execute、ownership、API/purpose、normal/crash resource policy 与 point-of-no-return 使用一致模型；
- 未执行的真实 v5.10 L1、匹配构建 L2 和隔离 VM L3 均被明确标记，没有伪造成已完成证据。

因此 B06 内容层面可以收章。下一步应更新 `boot-crash/README.md`，把 B06 标记为【已完成】并接入本 completion review；README 收口完成后再进入 B07，对 Kexec image/segments 的实际装载机制做 Linux 5.10 源码事实核验。

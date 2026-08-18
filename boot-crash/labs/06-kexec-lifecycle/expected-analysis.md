# B06 实验预期分析：Kexec 生命周期与 normal/crash 资源边界

本文给出 B06 实验的独立验收基线。它回答的是“观察到什么才足以支持 B06 的结论”，而不是提前展开 B07 的 segment/page-list 算法、B08 的 `relocate_kernel` 机器切换或 B10 之后的完整 Kdump crash path。

源码基线：upstream Linux v5.10，x86-64。

相关材料：

- [`README.md`](README.md)
- [`../../docs/06-kexec-why-and-lifecycle.md`](../../docs/06-kexec-why-and-lifecycle.md)
- [`../../source-paths/06-kexec-model-linux-5.10.md`](../../source-paths/06-kexec-model-linux-5.10.md)

---

## 1. 首先固定证据等级

B06 使用三层证据，三者不能互相冒充。

### L1：Linux v5.10 source contract

L1 用源码证明设计和实现关系，例如：

- 两种 load API 与 normal/crash 两种 image purpose 是两个维度；
- load path 构造并安装 `struct kimage`；
- normal/crash image 分别进入 `kexec_image` / `kexec_crash_image`；
- crash destination、control-page policy、`swap_page` 与 normal image 存在差异；
- `machine_kexec_prepare()` 属于 load phase，而 `machine_kexec()` 属于最终 transition phase。

L1 不能证明某个发行版当前启用了哪些配置，也不能证明某次 `kexec -e` 的动态机器状态。

### L2：匹配构建的 ELF / 机器码

L2 用与被测 kernel 匹配的 `.config`、`vmlinux`、`nm/readelf/objdump` 确认：

- 相关配置路径确实被编译进当前构建；
- generic load code 到 x86 `machine_kexec_prepare()` / `machine_kexec()` 的实际 call/control-flow 与源码模型相符；
- 配置裁剪、inline 等没有让当前构建偏离实验假设。

不能用函数地址在 ELF 中的排列顺序代替调用关系。

### L3：隔离 VM runtime

L3 才能证明某次运行中：

```text
load 成功
→ old kernel 继续运行
→ 后续独立 execute
→ new kernel 启动
```

crash image 的动态测试还需要可靠的 `crashkernel=` 配置、可丢弃 VM、串口日志和恢复手段。没有这些条件时，不触发 panic。

当前仓库尚未记录真实 v5.10 checkout、匹配 `vmlinux` 或可控 QEMU/Kexec runtime 的执行结果；因此这些层级必须继续标为“未执行”，不能用源码推导填写假数据。

---

## 2. 验收基线一：load API 与 image purpose 是二维关系

必须能够从 Linux v5.10 源码分别证明：

```text
traditional API: kexec_load
file API:        kexec_file_load

normal purpose:  KEXEC_TYPE_DEFAULT
crash purpose:   KEXEC_TYPE_CRASH
```

traditional path 使用 `KEXEC_ON_CRASH` 表达 crash image，file path 使用 `KEXEC_FILE_ON_CRASH` 表达 crash image。因此正确模型是：

```text
                    normal              crash
traditional load    可表达              可表达
file load           可表达              可表达
```

这里的“可表达”是接口/源码模型，不等于任意发行版运行环境都允许四种组合。实际可用性还受 `CONFIG_KEXEC`、`CONFIG_KEXEC_FILE`、签名、lockdown、LSM/IMA、userspace 工具等条件影响。

以下结论应判定失败：

```text
kexec_load      == normal Kexec
kexec_file_load == crash Kexec
```

因为它把“输入接口”和“映像用途”错误地合并成一个维度。

---

## 3. 验收基线二：`struct kimage` 跨越 syscall 生命周期

traditional 与 file path 的前半段不同，但 B06 必须观察到相同的 ownership 语义：

```text
load syscall
→ allocate/prepare struct kimage
→ machine_kexec_prepare()
→ segment loading / termination / post-load
→ xchg() install image
→ syscall returns
```

成功安装后：

```text
normal → kexec_image
crash  → kexec_crash_image
```

关键验收点不是某个局部变量名字，而是对象生命周期：`struct kimage` 在 syscall 栈帧消失后仍然存在，由当前 kernel 的全局 Kexec 状态持有，等待未来独立的 execute/crash event。

因此：

```text
load success != CPU control transfer
```

如果 L3 中执行 `kexec -l` 后旧 kernel 的 `/proc/uptime` 继续增长、PID 1 和 `/proc/cmdline` 仍属于旧 kernel，这正是该 ownership/lifecycle 模型的动态证据。

---

## 4. 验收基线三：normal/crash 从 load phase 就采用不同资源假设

### 4.1 crash destination

`KEXEC_TYPE_CRASH` 的 segment destination 必须接受 `crashk_res` 范围约束。B06 只要求证明“目标受预留资源限制”，不在这里展开 `crashkernel=` 参数如何建立 reservation；后者属于 B10。

### 4.2 control pages

`kimage_alloc_control_pages()` 对 normal/crash 使用不同的 allocation policy。验收时应确认分支依据 image/crash type，而不是把 crash image 当作 normal image 到 panic 时才临时改变行为。

### 4.3 `swap_page`

traditional/file 两条 load path 都只为 non-crash image 准备 `image->swap_page`。

这里的 `swap_page` 是 Kexec relocation/copy 使用的内部资源，不是普通 VM swap。B06 只确认 ownership/policy 差异，具体复制算法留给 B07/B08。

三项事实共同支持：

> crash Kexec 的特殊性从 healthy-time load phase 就已经存在，而不是 fatal event 到来后才第一次出现。

---

## 5. 验收基线四：prepare 与 execute 之间存在 point-of-no-return 边界

Linux v5.10 x86-64 的 `machine_kexec_prepare(struct kimage *image)` 应在 load path 中被调用。它可以建立 transition page-table state，并且仍处于允许资源准备、允许失败和回滚 load operation 的阶段。

`machine_kexec()` 则属于之后的 execute/transition phase。验收时应确认源码注释和实现都表达以下约束：

```text
machine_kexec_prepare()
    old kernel ordinary services still available
    resource preparation may fail

machine_kexec()
    point of no return has been crossed
    do not introduce new ordinary allocations
    do not design recoverable failure paths
```

因此不能因为两者名字都带 `machine_kexec` 就把它们解释成同一阶段，也不能说 `machine_kexec_prepare()` 已经开始真正执行下一内核。

---

## 6. 验收基线五：normal execute 与 crash execute 的前置假设不同

B06 只要求建立前置假设，不展开完整 execute 调用链。

normal execute 假设旧 kernel 仍然健康，能够按计划 quiesce ordinary activity、协调 CPU/设备并进入最终 architecture transition。

crash execute 的生产 kernel 已发生 fatal failure，不能继续把普通锁、scheduler、workqueue、设备 shutdown 或普通内存分配当作可靠前提。因此 crash image 必须在健康时期预留和预加载。

正确的时间模型是：

```text
healthy production kernel
→ reserve/preload crash image
→ install kexec_crash_image
→ production kernel continues running

fatal event later
→ consume already prepared crash image
```

如果没有隔离 VM，本章只需要静态证明这一生命周期，并记录 crash transition 未执行；不能为了“完成实验”在不可恢复环境中主动 panic。

---

## 7. L2 结果应如何解释

在匹配 Linux v5.10 build 上，至少记录：

```text
kernel tag/commit
.config 中 CONFIG_KEXEC_CORE / CONFIG_KEXEC / CONFIG_KEXEC_FILE / CONFIG_CRASH_DUMP
vmlinux Build ID（如存在）
相关符号是否存在
关键 call/control-flow 是否与 L1 一致
```

如果某个 symbol 因 inline、配置裁剪或编译优化不可见，不能立即判定源码模型错误；应先结合 `.config`、反汇编和 call site 判断。

反过来，仅看到 `machine_kexec_prepare` 和 `machine_kexec` 两个符号都存在，也不能证明 prepare/execute 的生命周期顺序；需要检查真实控制流。

---

## 8. L3 normal Kexec 的最小通过现场

隔离 VM 中，一个足够清晰的最小动态证据应包含两个时间段。

### T0：load 之前

记录：

```text
uname -a
/proc/uptime
/proc/cmdline
PID 1 identity
```

### T1：`kexec -l` 成功之后、`kexec -e` 之前

再次记录同样信息，并等待数秒确认旧 kernel uptime 继续增长。

这一阶段如果旧 kernel 仍可正常执行 userspace 命令，就直接证明 load 没有越过 execute boundary。

### T2：显式 execute 之后

执行 `kexec -e` 后，在新 kernel 记录：

```text
uname -a
/proc/uptime
/proc/cmdline
```

最好让新旧 kernel 的 release 或 command line 有可识别差异，避免仅凭 uptime 重置推断切换成功。

B06 不要求在这里观察 `relocate_kernel` 的 CR3、GDT/IDT 或 page-list copy；这些属于 B08。

---

## 9. 常见错误结果及判定

### 错误一：load command 返回 0，因此记录“已经进入新内核”

不通过。load 成功只证明 image 已被接受并持有。

### 错误二：看到 `KEXEC_FILE_ON_CRASH`，因此记录“file loader 只服务 crash Kexec”

不通过。file loader 同时支持 normal purpose。

### 错误三：看到 `machine_kexec_prepare()` 建 transition page table，因此记录“execute 已开始”

不通过。prepare 正是为了把可能失败的工作留在 point of no return 之前。

### 错误四：把 `swap_page` 解释为普通 swap subsystem 页面

不通过。它是 Kexec 内部 relocation/copy 资源；普通 swap 机制不属于本章。

### 错误五：没有隔离 VM 却为了获得 L3 结果主动触发 panic

不通过。破坏性实验必须有隔离、日志和恢复条件；缺环境时明确记录未执行才是正确结果。

---

## 10. B06 独立通过标准

B06 实验在当前层次至少应能够回答：

1. 为什么 load/prepare 与 execute/transition 必须分离？
2. `struct kimage` 为什么能在 syscall 返回后继续存在？
3. traditional/file 与 normal/crash 为什么是两个维度？
4. crash image 在 destination、control pages、`swap_page` 上与 normal image有什么 load-time 差异？
5. 为什么 `machine_kexec_prepare()` 可以失败，而进入 `machine_kexec()` 后不应再依赖普通分配和恢复？
6. normal/crash execute 为什么不能共享同一套“旧 kernel 仍健康”的前置假设？
7. L1、L2、L3 各自能够证明什么，不能证明什么？

如果上述问题能够由正文、Linux v5.10 source-path 和实验相互印证，则 B06 的概念与实验模型已经闭环。

当前尚未执行的增强证据：

- 在完整 Linux v5.10 checkout 上执行后续 source-contract checker；
- 对匹配构建执行 `nm/readelf/objdump`；
- 在隔离 VM 中完成 normal `load → continue → execute → new kernel` 动态验证；
- 在具备安全条件的 Kdump VM 中验证 crash image healthy-time preload 与 later crash consumption。

下一最小单元是把上述稳定的 L1 条件转换成自动 source-contract checker，并用正/负 fixture 验证 checker 自身。
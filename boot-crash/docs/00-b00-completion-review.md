# B00 收章复核：x86_64 Linux 启动过程概览

本文对 B00 的正文、Linux 5.10 源码事实核验和实验验收基线做一次收章复核。目标不是增加新的启动细节，而是确认本章已经建立一条一致、可继续展开 B01–B05 的启动阶段模型，并明确尚未取得的证据。

## 1. B00 要解决的问题

B00 的任务是建立完整启动主线，而不是提前讲完 boot protocol、compressed kernel、正式内核早期页表或 initramfs。

本章应使读者能够回答：

```text
当前是谁在执行？
当前代码属于哪个映像？
这一阶段具备哪些最小运行条件？
这一阶段完成什么责任？
控制权或状态怎样交给下一阶段？
```

现有正文采用“执行环境与责任交接”而不是伪 C 调用链来组织启动过程，这一点与领域大纲一致。

## 2. 已固定的 Linux 5.10 主线

B00 当前使用的主线为：

```text
firmware
    ↓
boot loader
    ↓  Linux x86 boot protocol
setup / boot_params
    ↓
compressed kernel
    ↓
extract_kernel()
    ↓
formal-kernel startup_64
    ↓
x86_64_start_kernel()
    ↓
x86_64_start_reservations()
    ↓
start_kernel()
    ↓
rest_init()
    ↓
kernel_init / kthreadd / idle
    ↓
exec init
    ↓
user space
```

这里的箭头表示控制权或状态交接，并不都表示普通 C ABI `call`。

源码事实核验已经把主要入口固定到 Linux 5.10 的下列文件：

```text
arch/x86/boot/main.c
arch/x86/boot/compressed/head_64.S
arch/x86/boot/compressed/misc.c
arch/x86/kernel/head_64.S
arch/x86/kernel/head64.c
init/main.c
```

因此正文没有依靠其他版本的启动调用图补全 Linux 5.10 路径。

## 3. 四个必须保持的阶段边界

### 3.1 setup `main()` 不是通用内核初始化入口

`arch/x86/boot/main.c:main()` 属于 setup 环境。它与 `init/main.c:start_kernel()` 不处于同一阶段，也不能因为函数名普通就忽略映像归属。

### 3.2 两个 `startup_64` 属于不同映像

必须始终带路径区分：

```text
arch/x86/boot/compressed/head_64.S : startup_64
arch/x86/kernel/head_64.S          : startup_64
```

前者服务于 compressed kernel；后者属于解压后的正式内核。不能跨两个 ELF 直接比较符号地址来推断启动先后，也不能写成 `startup_64()` 调用另一个 `startup_64()`。

### 3.3 `extract_kernel()` 调用与进入正式内核不是同一种控制流事件

`extract_kernel()` 是 compressed kernel 内部的 C 交接点；解压完成后进入正式 kernel entry 则是映像阶段交接。B00 只固定这一区别，具体参数寄存器、解压目标、重定位和跳转细节留给 B02。

### 3.4 PID 1 创建不等于用户态 init 已开始

`rest_init()` 创建执行 `kernel_init()` 的 PID 1 后，该任务仍执行内核代码。只有后续成功越过 exec 边界，才开始执行新的用户空间 init 映像。init 候选路径、initramfs/rootfs 细节留给 B05。

## 4. 与其他章节和领域的边界

B00 已避免重复 assembly A19 的机器机制。compressed `startup_32` 中 GDT、segment state、early page tables、CR4/CR3/EFER/CR0 和 far transfer 仍由 assembly 负责完整解释。

B00 后续章节的分工保持为：

```text
B01  boot protocol、bzImage 与 boot_params
B02  compressed kernel、解压、重定位/KASLR
B03  formal head_64.S 与正式内核早期地址空间
B04  x86_64_start_kernel() 到 start_kernel()
B05  start_kernel() 到用户空间 init
```

完整页表和物理内存管理机制仍属于 memory；B00 只说明它们在启动主线中的交接位置。

## 5. 实验闭环复核

`labs/00-boot-overview/` 已提供：

```text
README.md
expected-analysis.md
verify_source_ownership.py
test_verify_source_ownership.py
```

实验的硬验收条件与正文一致：

- setup `main()` 的阶段归属；
- compressed/formal 两个 `startup_64` 的独立归属；
- `extract_kernel()` 的 compressed-kernel 责任；
- `x86_64_start_kernel()` 与 `start_kernel()` 的架构/通用边界；
- PID 1 创建与 exec init 的边界。

checker fixture self-test 已实际执行，8 个测试全部通过，退出码为 0。这证明 matcher 自身的正/负契约已经运行过。

## 6. 当前证据等级

必须继续区分三层证据。

### 已完成

- Linux 5.10 源码路径和关键入口事实核验；
- 正式教程；
- 实验与 expected analysis；
- source-contract checker；
- checker 的 8-case fixture self-test 实际执行。

### 尚未执行

当前维护环境没有完整 Linux v5.10 checkout 和对应构建产物，因此尚未完成：

```text
verify_source_ownership.py /path/to/linux-5.10
nm/readelf/objdump 对 compressed vmlinux 与正式 vmlinux 的实际验证
QEMU/GDB 对真实启动现场的动态观察
```

这些是增强证据，不应被 fixture self-test 或源码阅读冒充。

## 7. 收章结论

从课程内容和独立验收标准看，B00 已经达到收章条件：

- 有明确的问题背景和阶段模型；
- 有 Linux 5.10 源码事实核验；
- 能区分映像、架构入口、通用初始化和用户态 exec 边界；
- 有与正文结论一一对应的实验；
- 已记录实际执行过的验证与尚未执行的验证；
- 没有提前展开 B01–B05 或其他领域的完整机制。

因此 B00 内容层面可以标记完成。领域 `README.md` 仍需加入正文、source-path、实验和本收章复核的入口；该 README 接入是进入 B01 前的下一最小单元。

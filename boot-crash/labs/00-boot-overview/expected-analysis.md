# B00 实验预期分析：x86_64 启动阶段、映像归属与交接边界

本文是 [`README.md`](README.md) 的验收基线。它固定 B00 实验中哪些结论必须成立、哪些证据可以由源码确认、哪些结论必须等待真实构建产物或运行时调试后才能声称已经验证。

B00 的目标不是证明整个启动过程中的每一条指令，而是建立可靠的阶段模型：**当前代码属于哪个映像、运行在哪个启动阶段、承担什么责任，以及通过什么边界把控制权或状态交给下一阶段。**

## 1. 八个入口的归属是硬验收条件

源码定位至少应得到下面的归属关系。

| 名称 | Linux 5.10 源码位置 | 阶段/映像 | B00 中应理解的责任 |
| --- | --- | --- | --- |
| `main()` | `arch/x86/boot/main.c` | setup | 整理启动参数和 setup 环境，准备进入 protected-mode payload |
| `startup_64` | `arch/x86/boot/compressed/head_64.S` | compressed kernel | 建立解压器所需的早期 64 位执行环境 |
| `extract_kernel()` | `arch/x86/boot/compressed/misc.c` | compressed kernel | 解压并处理正式 kernel image，产生后续入口 |
| `startup_64` | `arch/x86/kernel/head_64.S` | formal kernel | 解压后的正式内核 64 位早期入口 |
| `x86_64_start_kernel()` | `arch/x86/kernel/head64.c` | formal kernel / x86 arch C | 完成进入通用初始化前的 x86-64 早期 C 初始化 |
| `start_kernel()` | `init/main.c` | formal kernel / generic init | 进入通用内核初始化主线 |
| `rest_init()` | `init/main.c` | task-model transition | 创建 PID 1 与 kthreadd，并让 boot CPU 进入 idle/调度语义 |
| `kernel_init()` | `init/main.c` | PID 1 的内核上下文 | 完成剩余初始化，并最终尝试 exec 用户态 init |

如果某次验证只能找到名字而不能说明映像/阶段，则 B00 仍未通过。这里检查的是**归属关系**，不是函数名记忆。

## 2. 两个 `startup_64` 必须按两个映像理解

下面两个符号同名，但不能合并：

```text
arch/x86/boot/compressed/head_64.S : startup_64
arch/x86/kernel/head_64.S          : startup_64
```

前者属于 compressed kernel；后者属于解压后的正式 kernel。二者处在不同的映像和链接语境中，各自解决本阶段的早期执行环境问题。

因此下列描述不合格：

```text
startup_64() 调用 startup_64()
```

它既没有说明映像，也错误暗示了普通 C 函数调用关系。

合格的描述应至少表达：compressed kernel 在完成解压和必要准备后，把控制权交给解压后的正式内核入口；正式内核入口在自己的映像中也命名为 `startup_64`。

### 构建产物验收

如果已经有 Linux 5.10 构建产物，应分别检查：

```text
arch/x86/boot/compressed/vmlinux
vmlinux
```

使用 `nm`、`readelf` 或 `objdump` 时，记录中必须同时写出输入 ELF。两个 ELF 中的符号地址属于各自链接地址空间，不能因为名字相同就直接进行“前后地址”比较。

如果没有真实构建产物，只能写“源码归属已确认”，不能写“ELF 符号已经验证”。

## 3. `extract_kernel()` 的返回与阶段交接不是同一个控制流概念

在 compressed kernel 内部，调用 `extract_kernel()` 是本阶段内部的函数调用。它完成解压/处理并把后续所需结果返回给汇编入口。

随后把控制权交给解压后的正式 kernel entry，则是**映像阶段交接**。

因此 B00 图中的：

```text
compressed startup_64
    ↓
extract_kernel()
    ↓
formal kernel startup_64
```

只表示主线上的责任和控制权顺序，不表示三个节点之间全部使用相同的 C ABI `call/ret` 关系。

验收时应能够分别指出：

1. 哪一段是 compressed kernel 内部调用；
2. 哪一段结束当前 compressed-kernel 执行阶段并进入 formal kernel。

具体参数寄存器、解压目标和跳转指令留给 B02；B00 不应提前把这些细节扩展成第二份 compressed-kernel 教程。

## 4. `x86_64_start_kernel()` 与 `start_kernel()` 的层次必须分开

正式内核的主线应理解为：

```text
formal startup_64
    ↓
x86_64_start_kernel()
    ↓
x86_64_start_reservations()
    ↓
start_kernel()
```

`x86_64_start_kernel()` 仍属于 x86-64 架构早期初始化；`start_kernel()` 才进入通用初始化主线。

硬验收条件是不能把二者解释成“同一个初始化入口的两个名字”。这个边界很重要，因为后续 B03 负责正式内核早期机器环境，B04 才系统展开从架构入口进入 `start_kernel()` 的初始化顺序。

## 5. PID 1 创建与 exec 用户态 init 是两个时刻

`rest_init()` 中创建 `kernel_init` 对应的 PID 1，只说明第一个 init 任务已经作为内核执行上下文建立。

它之后还要继续完成内核侧初始化，最终才通过 exec 路径尝试运行 init 程序。概念上应保持：

```text
rest_init()
    ↓
创建 PID 1：kernel_init
    ↓
PID 1 继续执行内核代码
    ↓
kernel_init_freeable() 等剩余初始化
    ↓
run_init_process()/相关 exec 路径
    ↓
成功 exec 后才开始执行用户态 init 映像
```

因此：

```text
PID 1 已创建
```

不能推导为：

```text
/sbin/init 已经开始执行用户态指令
```

如果 exec 候选失败，PID 1 还可能继续尝试其他 init 路径；具体候选顺序和 initramfs/rootfs 过程属于 B05。

## 6. B00 的证据等级

本实验应把证据分成三层。

### 6.1 源码证据

可确认：

- 八个入口/函数的源码路径；
- 两个 `startup_64` 的源码和映像职责不同；
- compressed kernel、formal kernel、arch C、generic init 和 PID 1 阶段的边界；
- `rest_init()` 创建任务与后续 exec init 不是同一事件。

源码证据足以完成 B00 的基本阶段模型。

### 6.2 ELF / 反汇编证据

真实构建产物可进一步确认：

- compressed `startup_64` 出现在 compressed ELF 的机器码中；
- formal `startup_64`、`x86_64_start_kernel`、`start_kernel` 等属于正式 `vmlinux` 的符号/机器码语境；
- 某些交接点在当前配置和工具链下的实际指令形式。

这些结果必须记录 kernel commit/config、工具版本和输入 ELF。源码中存在函数不保证它一定以预想的全局符号形式出现在所有优化/链接配置的 `nm` 输出中；必要时结合 `readelf -Ws` 和 `objdump -dr` 判断。

### 6.3 运行时证据

静态源码和反汇编不能单独证明某次机器启动已经实际经过所有节点，也不能证明节点处的完整寄存器、页表、栈和任务状态。

若以后用 QEMU/GDB 或其他早期启动调试方法观察运行时，应把结果作为额外证据记录，而不能反过来用一次运行覆盖 Linux 5.10 源码的架构/配置条件。

## 7. 常见错误判定

出现下面任意一项，B00 实验不能判定通过：

- 把 setup `main()` 当作通用 kernel `main`；
- 不注明映像就混用两个 `startup_64`；
- 把 `extract_kernel()` 返回和进入 formal kernel 描述成同一个普通函数调用；
- 把 `x86_64_start_kernel()` 与 `start_kernel()` 合并为同一层初始化；
- 把 `kernel_thread(kernel_init, ...)` 等同于 `/sbin/init` 已经执行；
- 没有构建产物却写出伪造的 `nm/readelf/objdump` 实测结果；
- 从不同 ELF 中取得两个符号地址后直接按地址大小推断启动顺序。

## 8. 独立验收清单

B00 实验完成时，应能逐项回答：

- [ ] setup `main()` 属于哪个阶段？
- [ ] compressed `startup_64` 属于哪个 ELF/映像？
- [ ] `extract_kernel()` 在哪个阶段执行？
- [ ] formal-kernel `startup_64` 与 compressed `startup_64` 为什么不是同一符号语境？
- [ ] `x86_64_start_kernel()` 与 `start_kernel()` 的职责边界是什么？
- [ ] `rest_init()` 创建 PID 1 后，为什么仍不能说用户态 init 已经开始？
- [ ] 当前结论中哪些来自源码，哪些已经由真实 ELF/反汇编验证？
- [ ] 若尚无构建产物，是否明确记录了未执行项？

全部满足后，B00 的“启动阶段概览”才形成独立验证闭环。后续 B01–B05 可以在此阶段模型上逐段深入，而不需要重新发明另一条启动主线。

## 9. 当前验证状态

B00 的 Linux 5.10 source-path、正文、实验流程和本验收基线已经形成一致的阶段模型。实验目录中的 `verify_source_ownership.py` 已配套 `test_verify_source_ownership.py`；fixture self-test 已实际执行，**8 个测试全部通过，进程退出码为 0**。这些测试验证 matcher 能接受完整契约，并能拒绝 setup `main()`、两个独立 `startup_64`、`extract_kernel()`、架构 C 交接、PID 1 创建边界或 `run_init_process()` exec 边界缺失等负例。

这一级结果证明的是 **checker 自身的 source-contract 接受/拒绝逻辑已经实际运行**，不能提升为真实 Linux v5.10 源码树、ELF/机器码或运行时启动路径已经实测。

当前维护环境仍没有完整 Linux v5.10 checkout 和对应构建产物，因此尚未执行：

```text
verify_source_ownership.py /path/to/linux-5.10
nm/readelf/objdump 对 compressed vmlinux 与正式 vmlinux 的验证
QEMU/GDB 运行时启动观察
```

因此当前证据等级应准确写为：**Linux 5.10 源码事实核验 + 已实际执行的 checker fixture self-test + 实验验收标准固定**。真实源码树 checker、ELF/机器码和运行时验证继续作为后续环境具备时的增强证据，不把它们伪写为已完成。

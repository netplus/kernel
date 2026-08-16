# B00 实验：用源码与符号归属验证 x86_64 启动阶段

## 1. 实验目标

B00 的核心不是记住一条很长的函数名列表，而是学会判断一个入口**属于哪个映像、处于哪个启动阶段、通过什么方式向下一阶段交接**。

本实验验证下面几组容易混淆的事实：

1. `arch/x86/boot/main.c:main()` 属于 setup，而不是通用内核初始化；
2. `arch/x86/boot/compressed/head_64.S:startup_64` 与 `arch/x86/kernel/head_64.S:startup_64` 是两个不同映像中的同名符号；
3. `extract_kernel()` 属于 compressed kernel 解压器；
4. `x86_64_start_kernel()` 属于正式内核的 x86-64 早期 C 入口；
5. `start_kernel()`、`rest_init()`、`kernel_init()` 位于 `init/main.c`，但承担不同阶段的责任；
6. 源码中的“下一阶段”不一定表现为普通 C ABI `call`。

本实验只验证 B00 的**阶段归属和交接点**。boot protocol 字段留给 B01，compressed kernel 内部细节留给 B02，正式内核早期页表留给 B03。

## 2. 环境

建议使用完整 Linux v5.10 源码树：

```bash
git -C /path/to/linux describe --tags --exact-match HEAD
# 预期为 v5.10；若使用发行版 5.10 补丁树，应记录准确 commit。
```

工具：

```text
grep / git grep
nm
readelf
objdump
file
```

符号工具需要实际构建产物。没有构建环境时仍可完成源码定位，但必须把“源码已确认”和“ELF/反汇编已确认”分开记录。

## 3. 第一层：源码定位

在 Linux v5.10 源码根目录执行：

```bash
git grep -n 'void main(void)' -- arch/x86/boot/main.c
git grep -n 'startup_64' -- arch/x86/boot/compressed/head_64.S arch/x86/kernel/head_64.S
git grep -n 'extract_kernel' -- arch/x86/boot/compressed
git grep -n 'x86_64_start_kernel' -- arch/x86/kernel/head64.c
git grep -n '^asmlinkage __visible void __init start_kernel' -- init/main.c
git grep -n 'rest_init' -- init/main.c
git grep -n 'kernel_init' -- init/main.c
```

不要只记录“搜索到了名字”，而要填写下面的归属表：

| 名称 | 源码路径 | 映像/阶段 | 主要责任 |
| --- | --- | --- | --- |
| `main` | `arch/x86/boot/main.c` | setup | 整理 boot 参数并准备进入 protected-mode payload |
| `startup_64` | `arch/x86/boot/compressed/head_64.S` | compressed kernel | 建立解压器所需 64 位早期环境 |
| `extract_kernel` | `arch/x86/boot/compressed/misc.c` | compressed kernel | 解压/处理正式 kernel image，并产生后续入口 |
| `startup_64` | `arch/x86/kernel/head_64.S` | formal kernel | 正式内核 64 位早期入口 |
| `x86_64_start_kernel` | `arch/x86/kernel/head64.c` | formal kernel / arch C | x86-64 架构早期 C 初始化 |
| `start_kernel` | `init/main.c` | formal kernel / generic init | 通用内核初始化主线 |
| `rest_init` | `init/main.c` | task model transition | 建立 PID 1、kthreadd，并使 boot CPU 进入 idle 语义 |
| `kernel_init` | `init/main.c` | PID 1 kernel context | 完成剩余初始化并最终尝试 exec init |

### 验收点 A：两个 `startup_64`

必须能回答：

```text
为什么同名不代表同一个阶段？
```

最低验收标准是同时给出**文件路径 + 所属映像**。只写“先进入 startup_64，再进入 startup_64”不合格。

## 4. 第二层：检查 compressed kernel 的交接方式

在 `arch/x86/boot/compressed/head_64.S` 中围绕 `extract_kernel` 阅读上下文：

```bash
git grep -n -C 20 'extract_kernel' -- arch/x86/boot/compressed/head_64.S
```

记录：

- 调用 `extract_kernel()` 前，汇编准备了哪些参数；
- 返回后哪个寄存器/值代表下一阶段入口；
- 最终如何把控制权交给解压后的正式内核。

这里的验收重点不是展开 B02 的全部寄存器细节，而是确认：

```text
call extract_kernel
```

与

```text
跳到正式 kernel entry
```

是两个不同性质的控制流事件。前者可以是普通函数调用；后者是启动阶段交接，不能在 B00 图中一律画成 C 调用链。

## 5. 第三层：检查正式内核 C 入口链

阅读：

```bash
git grep -n -C 20 'x86_64_start_kernel' -- arch/x86/kernel/head64.c
git grep -n -C 20 'x86_64_start_reservations' -- arch/x86/kernel/head64.c
git grep -n -C 20 'start_kernel' -- arch/x86/kernel/head64.c init/main.c
```

要求手工整理成：

```text
formal startup_64
    ↓  汇编到 C 的入口交接
x86_64_start_kernel()
    ↓
x86_64_start_reservations()
    ↓
start_kernel()
```

验收时必须说明：`x86_64_start_kernel()` 与 `start_kernel()` 不是同一层次的两个名字；前者仍属于 x86 架构早期初始化，后者进入通用初始化。

## 6. 第四层：检查 PID 1 与用户态 init 的边界

在 `init/main.c` 中阅读 `rest_init()` 与 `kernel_init()`：

```bash
git grep -n -C 35 'rest_init' -- init/main.c
git grep -n -C 35 'kernel_init(void' -- init/main.c
git grep -n -C 20 'run_init_process' -- init/main.c
```

回答两个问题：

1. PID 1 在什么时候被创建？
2. PID 1 在什么时候才真正越过 exec 边界开始执行用户空间 init 映像？

硬验收条件：不能把“`kernel_thread(kernel_init, ...)` 已创建 PID 1”写成“`/sbin/init` 已经开始执行”。

## 7. 第五层：有构建产物时检查符号属于哪个 ELF

Linux x86 `bzImage` 的不同阶段并不全部位于同一个 ELF 中。若本地已经构建 v5.10，可先定位实际产物：

```bash
find arch/x86/boot -maxdepth 2 -type f \( -name 'vmlinux' -o -name 'vmlinux.bin*' -o -name 'setup.elf' \) -print
file vmlinux arch/x86/boot/compressed/vmlinux 2>/dev/null || true
```

然后分别检查符号：

```bash
nm -n arch/x86/boot/compressed/vmlinux | grep -E ' startup_64$| extract_kernel$'
nm -n vmlinux | grep -E ' startup_64$| x86_64_start_kernel$| start_kernel$| rest_init$| kernel_init$'
```

具体符号可见性会受链接脚本、LTO/编译配置和符号类型影响；如果某个 C 符号未按预期出现在 `nm` 输出中，不要直接判定源码路径错误，应结合：

```bash
readelf -Ws <ELF>
objdump -dr <ELF>
```

继续确认。

### 验收点 B：同名符号的地址不能跨 ELF 直接比较

compressed `startup_64` 与 formal-kernel `startup_64` 位于不同映像/ELF 语境。即使两边都能通过 `nm` 找到，也不能把它们当成同一符号表里的两个阶段标签来解释。

## 8. 建议的反汇编观察

有真实构建产物时：

```bash
objdump -dr arch/x86/boot/compressed/vmlinux > compressed.dis
objdump -dr vmlinux > kernel.dis
```

分别搜索：

```bash
grep -n -A30 -B10 '<startup_64>:' compressed.dis
grep -n -A30 -B10 '<startup_64>:' kernel.dis
grep -n -A20 -B10 '<x86_64_start_kernel>:' kernel.dis
grep -n -A20 -B10 '<start_kernel>:' kernel.dis
```

记录时必须注明输入 ELF，避免把两个 `startup_64` 的反汇编片段混在一起。

本实验不要求从一次静态反汇编证明完整运行时启动顺序。真实控制流还受链接地址、重定位、启动协议和配置影响。

## 9. 结果记录模板

```text
Kernel source/tag:
Kernel config:
Build completed: yes/no

[Source ownership]
setup main:
compressed startup_64:
extract_kernel:
formal startup_64:
x86_64_start_kernel:
start_kernel:
rest_init:
kernel_init:

[ELF evidence]
compressed ELF:
formal kernel ELF:
nm/readelf result:

[Control-transfer observations]
extract_kernel call:
transfer to formal kernel:
formal asm -> x86_64_start_kernel:
x86_64_start_kernel -> start_kernel:
PID 1 creation:
exec init boundary:

[Unverified items]
...
```

## 10. 通过标准

本实验通过至少要求：

- 源码层面准确定位八个入口/函数及其阶段；
- 明确区分两个 `startup_64` 的映像归属；
- 明确 `extract_kernel()` 调用与跳到正式内核入口不是同一种交接；
- 明确 `x86_64_start_kernel()` 与 `start_kernel()` 的架构/通用初始化边界；
- 明确 PID 1 创建与 exec 用户态 init 的时间边界；
- 若有构建产物，实际执行 `nm/readelf/objdump` 并记录输入 ELF；
- 若没有构建产物，明确写出哪些结论只有源码证据，不把预期反汇编写成实测。

## 11. 当前环境状态

本实验 README 本次已按 Linux 5.10 的既有 source-path 核验结果设计并提交。当前维护环境没有可执行的 Linux v5.10 checkout/构建产物，因此没有填写 `nm`、`readelf` 或 `objdump` 的虚构结果。

下一步应补充 `expected-analysis.md`，把源码归属、ELF 边界和 PID 1/exec 边界固定成独立验收基线；具备真实 v5.10 构建环境后，再补机器码级实际记录。

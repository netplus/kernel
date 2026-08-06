# Linux Kernel 5.10 基础执行过程

本目录把汇编、启动、内存、时钟和调度知识串联起来，用于分析一个过程怎样从入口一直运行到结束。

单独学习一个子系统时，容易只看到局部函数。综合分析则需要继续回答：

```text
当前代码处于什么执行上下文？
CPU 状态和内核栈发生了什么变化？
使用了哪些关键数据结构？
是否可能阻塞、抢占或切换任务？
内存从哪里获得，地址映射如何变化？
时间或中断如何推动下一步执行？
```

本阶段只选择最基础的执行过程。网络收发、VFS、cgroup、namespace 等专题以后再单独补充。

## 综合课程大纲

### I01：用户系统调用进入和返回

```text
用户函数
→ syscall 指令
→ entry_SYSCALL_64
→ 构造 pt_regs
→ do_syscall_64
→ 具体系统调用
→ 返回用户态前检查
→ sysretq 或 iretq
```

重点分析：

- 用户栈和内核栈；
- 系统调用 ABI；
- CPU 自动保存的状态；
- 入口代码手工保存的状态；
- 返回用户态前为何需要检查调度、信号和其他工作。

关联：assembly、scheduler、memory。

### I02：x86_64 内核正常启动

```text
引导程序
→ 压缩内核入口
→ 解压和重定位
→ 早期页表
→ startup_64
→ x86_64_start_kernel
→ start_kernel
→ rest_init
→ 第一个用户空间进程
```

重点分析：

- 启动参数和内存地图；
- 处理器模式和页表；
- memblock；
- 调度器、时钟和中断的初始化顺序；
- 汇编代码如何把控制权交给 C 代码。

关联：boot-crash、assembly、memory、timekeeping、scheduler。

### I03：缺页异常

```text
CPU 访问内存
→ 页表遍历或权限检查失败
→ #PF
→ 异常入口
→ 读取 CR2 和错误码
→ 查找 VMA
→ 分配页或处理权限
→ 更新页表
→ 返回并重新执行原指令
```

重点分析：

- CPU、异常入口和内存管理之间如何交接；
- anonymous fault、file-backed fault 和 protection fault；
- 缺页过程中何时可能分配内存或阻塞；
- 无法处理时如何转化为信号或内核错误。

关联：assembly、memory、scheduler。

### I04：任务睡眠和唤醒

```text
任务检查条件
→ 设置任务状态
→ 加入等待队列
→ schedule
→ 事件发生
→ wake_up
→ try_to_wake_up
→ 加入运行队列
→ 调度器选择任务运行
```

重点分析：

- 为什么要先设置状态再检查条件；
- 等待队列和任务状态的关系；
- 唤醒为何不等于立即运行；
- 并发和内存屏障为何重要。

关联：scheduler、timekeeping、memory ordering。

### I05：时钟中断触发重新调度

```text
local APIC timer
→ 中断入口
→ tick handler
→ scheduler_tick
→ 更新当前任务运行时间
→ 设置 TIF_NEED_RESCHED
→ 中断返回或抢占检查
→ schedule
```

重点分析：

- clockevent 如何产生中断；
- tick 如何更新时间和调度统计；
- 设置重新调度标志与真正调用 `schedule()` 的区别；
- 中断上下文为什么不能直接进行普通睡眠。

关联：assembly、timekeeping、scheduler。

### I06：上下文切换和地址空间切换

```text
schedule
→ __schedule
→ context_switch
→ switch_mm_irqs_off
→ CR3/PCID 处理
→ switch_to
→ 切换内核栈和寄存器
→ 新任务继续执行
```

重点分析：

- 旧任务的状态保存在哪里；
- 新任务的状态从哪里恢复；
- 为什么切换 `RSP` 后当前任务随之变化；
- 同一进程线程切换与不同进程切换的差别；
- TLB 和地址空间切换的关系。

关联：assembly、scheduler、memory。

### I07：Fork 和 Copy-on-Write

```text
fork
→ 复制进程地址空间描述
→ 父子进程共享只读物理页
→ 任一进程首次写入
→ 写保护缺页
→ 分配新页
→ 复制旧内容
→ 更新 PTE
→ 继续执行
```

重点分析：

- 为什么 fork 不立即复制全部物理页；
- VMA、PTE、page refcount 和 mapcount 的关系；
- COW 缺页如何连接进程创建、内存分配和页表更新。

关联：memory、scheduler、assembly。

### I08：Kexec 切换到新内核

```text
当前内核加载新内核
→ 准备目标物理内存
→ 安置过渡代码
→ 停止其他 CPU 和设备活动
→ machine_kexec
→ relocate_kernel
→ 跳转到新内核入口
```

重点分析：

- 为什么 Kexec 可以绕过固件重新启动；
- 新内核、initramfs 和命令行放在什么位置；
- 过渡代码为什么必须独立可靠；
- CPU 和设备状态需要怎样处理。

关联：boot-crash、assembly、memory、scheduler。

### I09：从 Panic 到 Vmcore

```text
内核故障
→ panic
→ crash_kexec
→ machine_crash_shutdown
→ 保存 CPU 状态并停止其他 CPU
→ 启动捕获内核
→ 读取旧内核物理内存
→ /proc/vmcore
→ makedumpfile
→ crash 分析
```

重点分析：

- 生产内核与捕获内核；
- `crashkernel=` 预留内存；
- `elfcorehdr` 和 `VMCOREINFO`；
- 为什么捕获内核不能覆盖旧内核内存；
- `vmcore` 与 `vmlinux`、模块符号和 Build ID 的匹配；
- 如何从寄存器、调用栈和故障指令还原根因。

关联：boot-crash、assembly、memory、scheduler、timekeeping。

## 建议学习方法

进入某个综合专题前，先完成相关的基础章节。例如学习上下文切换前，应先掌握：

```text
assembly：栈、函数调用、寄存器保存
scheduler：task state、运行队列和 schedule
memory：mm_struct、CR3 和 TLB
```

学习 Kdump 前，应先掌握：

```text
assembly：启动入口、寄存器和栈
memory：物理内存、页表和 memblock
boot-crash：正常启动、Kexec 和双内核结构
scheduler：多 CPU 停止和任务状态的基本概念
```

综合分析的目标不是记住一串函数名，而是能够说明每一步为什么发生，以及下一步依赖哪些状态。
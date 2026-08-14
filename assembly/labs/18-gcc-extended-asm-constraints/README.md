# A18 实验：GCC extended asm constraints 与 `-O2` 生成代码

本实验对应：

- `docs/18-gcc-extended-asm-constraints.md`
- `source-paths/18-gcc-extended-asm-constraints-linux-5.10.md`

目标不是背 constraint 字符，而是验证 GCC 看到的数据流必须与 x86 指令真实的数据流一致。

## 1. 要验证的问题

实验覆盖五组 contract：

1. `+r`：同一 operand 在 asm 前后既是输入又是输出；
2. matching constraint `"0"`：两个 C 逻辑角色必须共享同一 machine location；
3. early-clobber `&`：output 在其他 input 消费完之前就会被覆盖时，禁止危险寄存器重叠；
4. `cmpxchg` 的 `+m`、`+a`、`cc`、`memory`：分别描述精确内存 RMW、accumulator 输入/输出、flags side effect 和宽泛 compiler-visible memory side effect；
5. 精确 `+m` operand：与全局 `"memory"` clobber 不是同一个工具。

实验使用 `-O2`，因为 constraints 的价值正体现在优化和寄存器分配阶段。

## 2. 构建与运行

```bash
make clean
make
make run
```

应记录 GCC 版本：

```bash
gcc --version | head -1
```

程序的确定性语义应满足：

```text
read_write = 12
matching = 13
early_clobber = 42
第一次 cmpxchg 成功：value 从 11 变为 42，expected 仍为 11
第二次 cmpxchg 失败：value 保持 42，expected 被 actual 42 覆盖
xchg：old=55，memory 最终为 3
```

不要把具体寄存器分配写成 ABI 保证；寄存器选择由编译器决定，只有 constraint 所表达的位置关系是 contract。

## 3. 检查 AT&T 与 Intel 反汇编

```bash
make disasm-att
make disasm-intel

objdump -drwC constraints | less
objdump -drwC -Mintel constraints | less
```

重点定位：

```text
read_write_operand
matching_operand
early_clobber_example
cmpxchg_contract
precise_memory_operand
```

### 3.1 `+r`

`read_write_operand()` 中，进入 asm 的 `x` 与 `addq $7` 的 destination 必须是同一 machine operand；返回值必须来自更新后的值。

### 3.2 matching `"0"`

`matching_operand()` 的 `x` input 使用 `"0"` 绑定 output 0。反汇编中应能看到：初始 `x` 被放入最终承载 `out` 的同一寄存器，然后再把 `y` 加到该位置。

不要把 `"0"` 解释成“input 的数值等于 output”；它约束的是 location identity。

### 3.3 early-clobber

`early_clobber_example()` 的第一条模板指令先写 `tmp`，第二条才继续读取 `b`。`"=&r"(tmp)` 因此禁止 GCC 把 `tmp` 与尚未消费的 `b` 错误分配到同一寄存器。

具体使用哪两个寄存器不是验收条件；验收的是生成代码必须保留 `b` 到第二条指令仍可正确读取。

### 3.4 `cmpxchg`

`cmpxchg_contract()` 应出现 memory `cmpxchgq`，并满足：

```text
RAX/EAX family 进入指令前承载 expected
memory operand 是 compare/update target
desired 位于另一个允许的 GPR
sete 消费 ZF 形成 success
失败路径能够使用 accumulator 返回的 actual 更新 *expected
```

源码中的 `+a` 是关键：accumulator 既需要旧 expected，又可能在失败后产生 actual。

`"cc"` 说明 flags 被修改；`"memory"` 是 compiler memory clobber。二者都不是 `LOCK` 原子性的来源。

### 3.5 精确 memory operand

`precise_memory_operand()` 使用 `+m(*p)` 描述具体对象的 read/write dependency。memory `xchg` 自身具有 x86 锁定语义，因此模板不需要额外写 `lock`。

这也说明：

```text
+m(*p)    !=    "memory"
```

前者描述一个精确 C object dependency，后者描述更宽的 compiler-visible memory side effect。

## 4. 为什么不提交“错误 constraint 必然 miscompile”的运行测试

错误 constraint 的危险来自编译器获得了错误的数据流事实，但某一次 GCC 版本、寄存器压力和优化决策可能恰好没有暴露问题。因此本实验不把“错误程序必须输出某个错误值”作为验收条件。

如果要自行做错误对照，应只在独立临时文件中修改 constraint，然后比较 `-O0` 与 `-O2` 生成代码；观察到某次仍然正确不能证明错误 contract 合法。

## 5. `volatile` 的观察边界

本实验在具有 compiler-visible memory side effect 的 `cmpxchg` 上使用 `asm volatile`。阅读生成代码时应保持以下边界：

```text
volatile 约束 compiler 对 asm statement 的部分删除/移动
memory clobber 约束 compiler 对内存状态的假设
LOCK / memory xchg 决定相关 x86 原子 RMW 语义
CPU ordering 还要按 x86 与 Linux barrier API 分析
```

不能从 `volatile` 单独推出 atomic、full barrier 或禁止 speculation。

## 6. 验收清单

完成实验后至少应能解释：

```text
为什么 read/write operand 使用 + 而不是 =？
matching constraint 绑定的是数值还是 machine location？
为什么多指令模板可能需要 early-clobber &？
cmpxchg 为什么需要 accumulator input/output contract？
+ m operand 与 memory clobber 分别告诉 GCC 什么？
cc、memory、volatile 为什么都不能替代 LOCK/fence？
为什么必须检查 -O2 生成代码？
```

## 7. 当前执行状态

当前课程维护环境只有 GitHub 仓库内容接口，没有可执行 checkout，因此本次已完成源码与构建规则审查，但**没有实际执行** `make`、`objdump` 或程序。不能把上面的确定性语义和反汇编验收条件写成当前环境的实测输出。

获得 Linux/x86-64 checkout 后，应按第 2、3 节实际构建运行，并把 GCC/binutils 版本与关键反汇编记录下来。

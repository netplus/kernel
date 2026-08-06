    .section .data
    .align 8
array:
    .quad 10, 20, 30, 40

    .section .text
    .global _start
_start:
    # RBX = array 的运行时地址；lea 不读取数组内容。
    leaq array(%rip), %rbx

    # 复制地址本身。
    movq %rbx, %rax

    # 解引用 array[0]。
    movq (%rbx), %rcx

    # 基址 + 位移：读取 array[1]。
    movq 8(%rbx), %rdx

    # 比例索引：读取 array[2]。
    movq $2, %rsi
    movq (%rbx,%rsi,8), %r8

    # 先计算 array[2] 地址，再显式解引用。
    leaq 16(%rbx), %r9
    movq (%r9), %r10

    # 把 lea 当作整数乘加：2 + 2*4 + 5 = 15。
    leaq 5(%rsi,%rsi,4), %r11

    # exit(R11)，shell 中应观察到退出状态 15。
    movq $60, %rax
    movq %r11, %rdi
    syscall

    .section .data
    .align 8
long_array:
    .quad 1, 2, 3, 4

    # struct record {
    #     int id;        // offset 0
    #     int flags;     // offset 4
    #     long value;    // offset 8
    #     long stamp;    // offset 16
    # };                 // sizeof = 24
    .align 8
records:
    .long 1, 0
    .quad 11, 101
    .long 2, 0
    .quad 22, 202

    # struct bucket {
    #     long count;    // offset 0
    #     int values[4]; // offset 8
    # };                 // sizeof = 24
    .align 8
bucket:
    .quad 4
    .long 5, 6, 7, 8

    # struct inner {
    #     int state;     // offset 0
    #     int flags;     // offset 4
    #     long value;    // offset 8
    # };                 // sizeof = 16
    # struct outer {
    #     long seq;      // offset 0
    #     struct inner in; // offset 8
    # };                 // sizeof = 24
    .align 8
outer:
    .quad 9
    .long 1, 2
    .quad 44

    # long matrix[3][4]
    .align 8
matrix:
    .quad 1, 2, 3, 4
    .quad 5, 6, 7, 8
    .quad 9, 10, 11, 12

    # long *rows[2]：这是“指针数组”，不是连续二维数组。
    .align 8
row0:
    .quad 10, 20, 30
row1:
    .quad 50, 60, 70
rows:
    .quad row0, row1

    .section .text
    .global _start
    .type _start, @function
_start:
    # 1. 一维数组：long_array[2]。
    leaq long_array(%rip), %rbx
    movq $2, %rsi
    movq (%rbx,%rsi,8), %r8

after_array:
    # 2. 结构体数组：records[1].value。
    # sizeof(struct record) = 24 = 3 * 8。
    leaq records(%rip), %rbx
    movq $1, %rsi
    leaq (%rsi,%rsi,2), %rax
    movq 8(%rbx,%rax,8), %r9

after_struct_array:
    # 3. 结构体内数组：bucket.values[2]。
    # values 起始偏移为 8，int 元素大小为 4。
    leaq bucket(%rip), %rbx
    movq $2, %rsi
    movslq 8(%rbx,%rsi,4), %r10

after_embedded_array:
    # 4. 嵌套结构体：outer.in.value。
    # outer.in 偏移 8，inner.value 偏移 8，总偏移 16。
    leaq outer(%rip), %rbx
    movq 16(%rbx), %r11

after_nested_struct:
    # 5. 连续二维数组：matrix[1][2]。
    # 每行 4 个 long，因此线性下标 = row * 4 + col。
    leaq matrix(%rip), %rbx
    movq $1, %rsi
    movq $2, %rdx
    leaq (%rdx,%rsi,4), %rax
    movq (%rbx,%rax,8), %r12

after_matrix:
    # 6. 指针数组：rows[1][2]。
    # 第一次解引用取得 row1 指针，第二次解引用取得元素。
    leaq rows(%rip), %rbx
    movq $1, %rsi
    movq $2, %rdx
    movq (%rbx,%rsi,8), %rax
    movq (%rax,%rdx,8), %r13

after_pointer_chain:
    # 7. lea 作为普通整数乘加：5 + x + 4*x，x=2，结果 15。
    movq $2, %rsi
    leaq 5(%rsi,%rsi,4), %r14

after_lea_arithmetic:
    # 校验和：3 + 22 + 7 + 44 + 7 + 70 + 15 = 168。
    xorl %edi, %edi
    addl %r8d, %edi
    addl %r9d, %edi
    addl %r10d, %edi
    addl %r11d, %edi
    addl %r12d, %edi
    addl %r13d, %edi
    addl %r14d, %edi

    movq $60, %rax
    syscall

    .size _start, .-_start

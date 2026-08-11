    .section .rodata
.Lgood:
    .string "good-cfi"
.Lmissing:
    .string "missing-cfi"
.Lwrong:
    .string "wrong-cfi"

    .text
    .globl good_frame
    .type good_frame, @function
good_frame:
    .cfi_startproc
    subq $8, %rsp
    .cfi_def_cfa_offset 16
    leaq .Lgood(%rip), %rdi
    call capture_trace@PLT
    addq $8, %rsp
    .cfi_def_cfa_offset 8
    ret
    .cfi_endproc
    .size good_frame, .-good_frame

    .globl missing_frame
    .type missing_frame, @function
missing_frame:
    subq $8, %rsp
    leaq .Lmissing(%rip), %rdi
    call capture_trace@PLT
    addq $8, %rsp
    ret
    .size missing_frame, .-missing_frame

    .globl wrong_frame
    .type wrong_frame, @function
wrong_frame:
    .cfi_startproc
    subq $8, %rsp
    /* Intentionally wrong: real caller CFA is now RSP+16. */
    .cfi_def_cfa_offset 8
    leaq .Lwrong(%rip), %rdi
    call capture_trace@PLT
    addq $8, %rsp
    .cfi_def_cfa_offset 8
    ret
    .cfi_endproc
    .size wrong_frame, .-wrong_frame

    .section .note.GNU-stack,"",@progbits

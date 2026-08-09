set pagination off
set disassembly-flavor att

break after_add_sub
break after_bitops
break after_not
break after_shifts
break after_imul
break after_mul
break after_idiv
break after_div

run

printf "\n===== after_add_sub =====\n"
info registers rbx eflags
x/4i $pc
continue

printf "\n===== after_bitops =====\n"
info registers rsi eflags
x/4i $pc
continue

printf "\n===== after_not =====\n"
info registers rsi eflags
x/5i $pc
continue

printf "\n===== after_shifts =====\n"
info registers r8 r9 r10 rcx eflags
x/5i $pc
continue

printf "\n===== after_imul =====\n"
info registers r11 eflags
x/5i $pc
continue

printf "\n===== after_mul =====\n"
info registers rax rdx r12 eflags
x/6i $pc
continue

printf "\n===== after_idiv =====\n"
info registers rax rdx r13 r14
x/7i $pc
continue

printf "\n===== after_div =====\n"
info registers rax rdx r15
x/12i $pc

quit

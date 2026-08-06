set pagination off
set disassembly-flavor att
set confirm off

break _start
break after_cmp_equal
break after_test_zero
break after_cmp_signed_unsigned
break after_signed_overflow
break after_unsigned_carry
break negative
break after_sign_branch
break select_first
break max_done

run

printf "\n=== program entry ===\n"
x/8i $pc
info registers rip rsp rax eflags
continue

printf "\n=== after cmp 7,7: expect ZF=1 and RAX still 7 ===\n"
info registers rax eflags
continue

printf "\n=== after test 0,0: expect ZF=1 ===\n"
info registers rcx eflags
continue

printf "\n=== after cmp (-1),1 ===\n"
printf "signed view: -1 < 1; unsigned view: ULONG_MAX > 1\n"
info registers r8 eflags
continue

printf "\n=== after LONG_MAX + 1 ===\n"
printf "expect OF=1, CF=0, SF=1\n"
info registers r11 eflags
continue

printf "\n=== after ULONG_MAX + 1 ===\n"
printf "expect CF=1, ZF=1, OF=0\n"
info registers r14 eflags
continue

printf "\n=== negative basic block selected ===\n"
x/6i $pc
info registers rax eflags
continue

printf "\n=== sign branches merge here ===\n"
x/6i $pc
continue

printf "\n=== first max-selection block selected ===\n"
x/6i $pc
info registers rax rcx eflags
continue

printf "\n=== max merge block: expect RDX=9 ===\n"
info registers rax rcx rdx eflags
continue

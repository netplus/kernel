set pagination off
set disassembly-flavor att
break stack_after_push1
break stack_after_push2
break stack_after_pop1
break stack_after_pop2
break manual_after_sub
break manual_after_add
run

commands 1
silent
printf "\n== after push1 ==\n"
info registers rsp r12 r13 rax rbx eflags
x/4gx $rsp
continue
end

commands 2
silent
printf "\n== after push2 ==\n"
info registers rsp r12 r14 rcx rdx r8 eflags
x/4gx $rsp
continue
end

commands 3
silent
printf "\n== after pop1 ==\n"
info registers rsp r9 eflags
x/4gx $rsp-8
continue
end

commands 4
silent
printf "\n== after pop2 ==\n"
info registers rsp r10 eflags
x/4gx $rsp-16
continue
end

commands 5
silent
printf "\n== after manual sub ==\n"
info registers rsp eflags
x/4gx $rsp
continue
end

commands 6
silent
printf "\n== after manual add ==\n"
info registers rsp r11 eflags
continue
end

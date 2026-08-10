set pagination off
set disassembly-flavor att
break recursive_entry
break before_recursive_call
break after_recursive_call
break recursive_base
commands
silent
printf "\n--- stop at %s ---\n", $_hit_bpnum
info registers rax rdi rsp rip
x/6gx $rsp
continue
end
run

set pagination off
set disassembly-flavor att

break after_while
commands
  silent
  printf "\n[after_while]\n"
  info registers rax rcx r8 eflags
  x/8i $pc-16
  continue
end

break after_do_while
commands
  silent
  printf "\n[after_do_while]\n"
  info registers rax rcx r9 eflags
  x/8i $pc-16
  continue
end

break after_array_loop
commands
  silent
  printf "\n[after_array_loop]\n"
  info registers rax rcx rsi r10 eflags
  x/8i $pc-20
  continue
end

break after_state_machine
commands
  silent
  printf "\n[after_state_machine]\n"
  info registers rax rcx r11 eflags
  x/12i $pc-32
  continue
end

break after_switch
commands
  silent
  printf "\n[after_switch]\n"
  info registers rax rdi rdx r12 eflags
  x/16i $pc-48
  continue
end

run

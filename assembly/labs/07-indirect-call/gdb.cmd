set pagination off
set disassembly-flavor att

break before_register_call
commands
  silent
  printf "\n== before register-indirect call ==\n"
  info registers rip rsp r12
  x/4gx $rsp
  continue
end

break register_target_entry
commands
  silent
  printf "\n== register target entry ==\n"
  info registers rip rsp r12 r13 r14
  x/4gx $rsp
  continue
end

break after_register_call
commands
  silent
  printf "\n== after register-indirect call ==\n"
  info registers rip rsp rax
  continue
end

break before_memory_call
commands
  silent
  printf "\n== before memory-indirect call ==\n"
  info registers rip rsp
  x/gx &memory_target_ptr
  continue
end

break memory_target_entry
commands
  silent
  printf "\n== memory target entry ==\n"
  info registers rip rsp r13 r14
  x/4gx $rsp
  continue
end

break after_memory_call
commands
  silent
  printf "\n== after memory-indirect call ==\n"
  info registers rip rsp rax
  continue
end

run
quit

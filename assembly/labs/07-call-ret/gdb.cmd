set pagination off
set disassembly-flavor att

break before_direct_call
commands
  silent
  printf "\n== before_direct_call ==\n"
  info registers rip rsp rax
  x/4gx $rsp
  x/4i $rip
  continue
end

break direct_target_entry
commands
  silent
  printf "\n== direct_target_entry ==\n"
  info registers rip rsp r12 r13 r14 rax
  x/4gx $rsp
  x/5i $rip
  continue
end

break before_ret
commands
  silent
  printf "\n== before_ret ==\n"
  info registers rip rsp r12 r13 r14 rax
  x/4gx $rsp
  x/4i $rip
  continue
end

break after_direct_call
commands
  silent
  printf "\n== after_direct_call ==\n"
  info registers rip rsp r12 rax
  x/4gx $rsp
  x/4i $rip
  continue
end

run

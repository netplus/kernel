set pagination off
set disassembly-flavor att

break corrupt_return_address
commands
  silent
  printf "\n== enter corrupt_return_address ==\n"
  printf "RSP = 0x%lx\n", $rsp
  x/gx $rsp
  x/i *(void **)$rsp
  continue
end

break before_corrupted_ret
commands
  silent
  printf "\n== before corrupted ret ==\n"
  printf "RSP = 0x%lx\n", $rsp
  x/gx $rsp
  x/i *(void **)$rsp
  continue
end

break redirected_target
commands
  silent
  printf "\n== redirected_target reached ==\n"
  printf "RSP = 0x%lx, saved original return in R13 = 0x%lx\n", $rsp, $r13
  x/i $pc
  continue
end

break after_corrupt_call
commands
  silent
  printf "\n== original continuation resumed ==\n"
  printf "RSP = 0x%lx, R12 = 0x%lx\n", $rsp, $r12
  x/i $pc
  continue
end

run

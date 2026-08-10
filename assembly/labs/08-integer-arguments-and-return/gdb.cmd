set pagination off
break abi_probe6
run
printf "entry RDI=%ld RSI=%ld RDX=%ld RCX=%ld R8=%ld R9=%ld\n", $rdi, $rsi, $rdx, $rcx, $r8, $r9
x/gx $rsp
finish
printf "return RAX=%ld\n", $rax
quit

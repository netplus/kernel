set pagination off
set disassembly-flavor att
break abi_probe8
run
printf "\nabi_probe8 entry\n"
printf "rsp = %#lx\n", $rsp
printf "rdi=%ld rsi=%ld rdx=%ld rcx=%ld r8=%ld r9=%ld\n", $rdi, $rsi, $rdx, $rcx, $r8, $r9
printf "[rsp]    return address = %#lx\n", *(unsigned long *)$rsp
printf "[rsp+8]  arg7 = %ld\n", *(long *)($rsp + 8)
printf "[rsp+16] arg8 = %ld\n", *(long *)($rsp + 16)
printf "(rsp+8) mod 16 = %ld\n", ($rsp + 8) & 15
x/3gx $rsp
quit

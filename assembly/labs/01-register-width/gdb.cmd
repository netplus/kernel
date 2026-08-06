set pagination off
set disassembly-flavor att
break _start
run

display/i $pc
display/x $rax
display/x $rdi
display/x $rsp

printf "\nUse 'si' to execute one instruction at a time.\n"
printf "Expected RAX sequence:\n"
printf "  0x1122334455667788\n"
printf "  0x11223344556677ff\n"
printf "  0x112233445566abcd\n"
printf "  0x0000000012345678\n\n"

set pagination off
set confirm off
set disassembly-flavor att

break _start
break after_array
break after_struct_array
break after_embedded_array
break after_nested_struct
break after_matrix
break after_pointer_chain
break after_lea_arithmetic

run

printf "\n=== data layout ===\n"
printf "long_array=%p records=%p bucket=%p outer=%p matrix=%p rows=%p\n", &long_array, &records, &bucket, &outer, &matrix, &rows
x/4gd &long_array
x/12wx &records
x/6wx &bucket
x/6wx &outer
x/12gd &matrix
x/2gx &rows
continue

printf "\n=== long_array[2] ===\n"
printf "EA = base + index*8; expect R8=3\n"
info registers rbx rsi r8
continue

printf "\n=== records[1].value ===\n"
printf "EA = records + 1*24 + 8; expect R9=22\n"
info registers rbx rsi rax r9
continue

printf "\n=== bucket.values[2] ===\n"
printf "EA = bucket + 8 + 2*4; expect R10=7\n"
info registers rbx rsi r10
continue

printf "\n=== outer.in.value ===\n"
printf "EA = outer + 8 + 8; expect R11=44\n"
info registers rbx r11
continue

printf "\n=== matrix[1][2] ===\n"
printf "linear index = 1*4+2=6; expect R12=7\n"
info registers rbx rsi rdx rax r12
continue

printf "\n=== rows[1][2] pointer chain ===\n"
printf "first load row pointer, second load element; expect R13=70\n"
info registers rbx rsi rdx rax r13
x/3gd $rax
continue

printf "\n=== lea arithmetic ===\n"
printf "5 + 2 + 2*4 = 15; expect R14=15\n"
info registers rsi r14
continue

printf "\n=== before exit syscall ===\n"
printf "checksum expect RDI=168; syscall number expect RAX=60\n"
info registers rax rdi r8 r9 r10 r11 r12 r13 r14 rip rsp eflags
continue
quit

set pagination off
set confirm off
set disassembly-flavor att

break _start
run

printf "\n===== initial array memory =====\n"
printf "array address: %p\n", &array
x/4gd &array
x/4gx &array

printf "\n===== instruction-by-instruction state =====\n"
set $step = 0
while $step < 11
    printf "\n--- before step %d ---\n", $step
    x/i $rip
    info registers rax rbx rcx rdx rsi r8 r9 r10 r11 rdi rip rsp eflags
    si
    set $step = $step + 1
end

printf "\n===== before final syscall =====\n"
x/i $rip
info registers rax rdi rbx rcx rdx rsi r8 r9 r10 r11 rip rsp eflags
printf "expected: rax=60, rdi=15, r11=15\n"

continue
quit

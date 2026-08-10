set pagination off
break clobber_probe
run
printf "entry clobber_probe: rbx=%#lx r12=%#lx r10=%#lx r11=%#lx rsp=%#lx\n", $rbx, $r12, $r10, $r11, $rsp
finish
printf "after return:        rbx=%#lx r12=%#lx r10=%#lx r11=%#lx rsp=%#lx\n", $rbx, $r12, $r10, $r11, $rsp
quit

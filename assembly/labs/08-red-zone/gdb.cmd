set pagination off
break red_zone_leaf
break red_zone_call_boundary
run
printf "red_zone_leaf entry rsp = 0x%lx\n", $rsp
x/4gx $rsp-32
continue
printf "red_zone_call_boundary entry rsp = 0x%lx\n", $rsp
x/4gx $rsp-32
continue

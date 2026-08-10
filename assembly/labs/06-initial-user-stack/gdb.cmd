set pagination off
set disassembly-flavor att
break *_start
run alpha beta

printf "initial rsp = 0x%lx\n", $rsp
printf "argc        = %ld\n", *(long *)$rsp
x/12gx $rsp

set $argc = *(long *)$rsp
set $argv = $rsp + 8
printf "argv base   = 0x%lx\n", $argv
x/s *(char **)($argv)
x/s *(char **)($argv + 8)
x/s *(char **)($argv + 16)

set $envp = $argv + ($argc + 1) * 8
printf "envp base   = 0x%lx\n", $envp
x/s *(char **)($envp)

continue

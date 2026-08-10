set pagination off
set disassembly-flavor att

break probe_alignment
commands
  silent
  printf "probe_alignment entry rsp=%p rsp%%16=%lu\n", $rsp, ((unsigned long)$rsp & 15)
  x/gx $rsp
  continue
end

break nested_probe
commands
  silent
  printf "nested_probe entry rsp=%p rsp%%16=%lu\n", $rsp, ((unsigned long)$rsp & 15)
  x/gx $rsp
  continue
end

run

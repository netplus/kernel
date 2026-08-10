# Expected analysis

## Verified build

The lab was built and run on Linux x86-64 with GNU `as` and `ld`.

```text
exit status=6 (expected 6)
```

`nm -n` showed:

```text
0000000000401000 T _start
000000000040102a t recursive_entry
000000000040102a t recursive_sum
0000000000401030 t before_recursive_call
0000000000401039 t after_recursive_call
000000000040103e t recursive_base
0000000000401042 t fail
```

The relevant AT&T disassembly was:

```asm
40102a: 48 85 ff              test   %rdi,%rdi
40102d: 74 0f                 je     40103e <recursive_base>
40102f: 57                    push   %rdi
401030: 48 83 ef 01           sub    $0x1,%rdi
401034: e8 f1 ff ff ff        call   40102a <recursive_entry>
401039: 5f                    pop    %rdi
40103a: 48 01 f8              add    %rdi,%rax
40103d: c3                    ret
40103e: 48 31 c0              xor    %rax,%rax
401041: c3                    ret
```

## Stack reasoning

For every non-base invocation, after entry with `RSP=S`:

```text
push %rdi      -> RSP=S-8,  [RSP]=saved n
recursive call -> RSP=S-16, [RSP]=0x401039
```

For `recursive_sum(3)`, three non-base recursive layers are created before reaching the base case. Relative to the `RSP` observed at the first `recursive_sum(3)` entry, the deepest base-case entry is therefore 48 bytes lower.

All recursive calls originate from the same instruction at `0x401034`, so all three recursive return-address values are `0x401039`. They are separate stack entries despite containing the same numeric address.

Unwinding happens in reverse order:

```text
base returns 0
n=1 layer: pop 1, add -> 1, ret
n=2 layer: pop 2, add -> 3, ret
n=3 layer: pop 3, add -> 6, ret
```

The caller checks both `RAX==6` and that `RSP` has returned to its pre-call value.

## Validation limits

`gdb` was not installed in the execution environment, so interactive stack snapshots were not captured. The GDB script is provided for an environment where GDB is available.

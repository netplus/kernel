#!/usr/bin/env python3
"""Self-tests for verify_startup32_disassembly.py.

These fixtures test the checker itself; they are not substitutes for running the
checker against an objdump listing produced from a Linux v5.10 build.
"""

from verify_startup32_disassembly import (
    check_startup32,
    check_verify_cpu,
    instruction_lines,
    symbol_body,
)


GOOD = r"""
00000000 <startup_32>:
   0: fc                    cld
   1: fa                    cli
   2: 0f 01 10              lgdtl  (%eax)
   5: 8e d8                 mov    %eax,%ds
   7: 8e c0                 mov    %eax,%es
   9: 8e e0                 mov    %eax,%fs
   b: 8e e8                 mov    %eax,%gs
   d: 8e d0                 mov    %eax,%ss
   f: e8 00 00 00 00        call   14 <verify_cpu>
  14: 85 c0                 test   %eax,%eax
  16: 0f 22 e0              mov    %eax,%cr4

00000020 <verify_cpu>:
  20: 9c                    pushf
  21: 90                    nop
  22: 9d                    popf
  23: b8 01 00 00 00        mov    $0x1,%eax
  28: c3                    ret
  29: 9d                    popf
  2a: 31 c0                 xor    %eax,%eax
  2c: c3                    ret
"""


def parse(text=GOOD):
    startup = instruction_lines(symbol_body(text, "startup_32"))
    verify = instruction_lines(symbol_body(text, "verify_cpu"))
    return startup, verify


def must_fail(fn, lines, label):
    try:
        fn(lines)
    except AssertionError:
        return
    raise AssertionError(f"negative fixture unexpectedly passed: {label}")


def replace_once(text, old, new):
    if old not in text:
        raise AssertionError(f"fixture mutation target missing: {old!r}")
    return text.replace(old, new, 1)


def main():
    startup, verify = parse()
    assert len(check_startup32(startup)) == 4
    assert len(check_verify_cpu(verify)) == 2

    # startup_32 ordering failures.
    bad = replace_once(GOOD, "   2: 0f 01 10              lgdtl  (%eax)\n", "")
    s, _ = parse(bad)
    must_fail(check_startup32, s, "missing lgdt")

    bad = GOOD.replace(
        "   5: 8e d8                 mov    %eax,%ds\n   7: 8e c0                 mov    %eax,%es\n",
        "   5: 8e c0                 mov    %eax,%es\n   7: 8e d8                 mov    %eax,%ds\n",
    )
    s, _ = parse(bad)
    must_fail(check_startup32, s, "segment reload order")

    bad = GOOD.replace(
        "  14: 85 c0                 test   %eax,%eax\n  16: 0f 22 e0              mov    %eax,%cr4\n",
        "  14: 0f 22 e0              mov    %eax,%cr4\n  16: 85 c0                 test   %eax,%eax\n",
    )
    s, _ = parse(bad)
    must_fail(check_startup32, s, "CR4 write before result test")

    # verify_cpu terminal-path failures.  Keep two popf/ret instructions so the
    # failure proves path semantics are checked, not merely instruction counts.
    bad = replace_once(GOOD, "  23: b8 01 00 00 00        mov    $0x1,%eax", "  23: 31 c0                 xor    %eax,%eax")
    _, v = parse(bad)
    must_fail(check_verify_cpu, v, "failure path returns zero")

    bad = replace_once(GOOD, "  2a: 31 c0                 xor    %eax,%eax", "  2a: b8 01 00 00 00        mov    $0x1,%eax")
    _, v = parse(bad)
    must_fail(check_verify_cpu, v, "success path returns one")

    bad = replace_once(GOOD, "  29: 9d                    popf", "  29: 90                    nop")
    _, v = parse(bad)
    must_fail(check_verify_cpu, v, "success path missing popf")

    print("PASS: A19 disassembly checker positive fixture")
    print("PASS: A19 disassembly checker negative fixtures")


if __name__ == "__main__":
    main()

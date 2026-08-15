#!/usr/bin/env python3
"""Check key A19 startup_32/verify_cpu instructions in an objdump listing.

This checker intentionally verifies only machine-code evidence that is stable enough
for the course contract.  It does not infer runtime CPU mode or register values.

Usage:
    objdump -dr <compressed-object-or-image> > disasm.txt
    python3 verify_startup32_disassembly.py disasm.txt

The input must contain disassembly for both startup_32 and verify_cpu.  If they live
in different build artifacts, concatenate the two objdump outputs first.
"""

import argparse
import re
import sys
from pathlib import Path


def symbol_body(text: str, symbol: str) -> str:
    # Accept GNU objdump labels such as "00000000 <startup_32>:".
    start = re.search(rf"(?m)^\s*[0-9a-fA-F]+\s+<{re.escape(symbol)}>:\s*$", text)
    if not start:
        raise AssertionError(f"missing disassembly symbol: {symbol}")
    rest = text[start.end():]
    nxt = re.search(r"(?m)^\s*[0-9a-fA-F]+\s+<[^>]+>:\s*$", rest)
    return rest[:nxt.start()] if nxt else rest


def instruction_lines(body: str):
    lines = []
    for raw in body.splitlines():
        # GNU objdump instruction lines contain an address followed by ':'; keep
        # the textual instruction tail and ignore relocation-only lines.
        m = re.match(r"^\s*[0-9a-fA-F]+:\s+(?:[0-9a-fA-F]{2}\s+)+\s*(.*)$", raw)
        if m and m.group(1):
            lines.append(m.group(1).strip())
    return lines


def first_index(lines, pattern, label, start=0):
    rx = re.compile(pattern)
    for i in range(start, len(lines)):
        if rx.search(lines[i]):
            return i
    raise AssertionError(f"missing instruction: {label}")


def check_startup32(lines):
    checks = []
    def mark(name, cond):
        if not cond:
            raise AssertionError(name)
        checks.append(name)

    i_cld = first_index(lines, r"^cld\b", "cld")
    i_cli = first_index(lines, r"^cli\b", "cli", i_cld)
    i_lgdt = first_index(lines, r"^lgdt[lq]?\b", "lgdt", i_cli)

    cursor = i_lgdt
    seg_idx = []
    for seg in ("ds", "es", "fs", "gs", "ss"):
        # AT&T objdump normally prints e.g. "mov %eax,%ds"; Intel output is not
        # required because the lab asks the user to generate both views, while
        # this checker consumes the canonical AT&T listing.
        idx = first_index(lines, rf"^mov\w*\b.*,%{seg}\b", f"reload %{seg}", cursor)
        seg_idx.append(idx)
        cursor = idx + 1

    i_call = first_index(lines, r"^call\w*\b.*<verify_cpu>", "call verify_cpu", cursor)
    i_test = first_index(lines, r"^test\w*\b.*%eax.*%eax", "test verify_cpu result", i_call + 1)
    i_cr4 = first_index(lines, r"^mov\w*\b.*%cr4", "CR4 write", i_test + 1)

    mark("cld precedes cli", i_cld < i_cli)
    mark("lgdt precedes data-segment reloads", i_lgdt < min(seg_idx))
    mark("DS/ES/FS/GS/SS reload in order", seg_idx == sorted(seg_idx))
    mark("verify_cpu result tested before CR4 write", i_call < i_test < i_cr4)
    return checks


def check_verify_cpu(lines):
    checks = []
    def mark(name, cond):
        if not cond:
            raise AssertionError(name)
        checks.append(name)

    pushf = [i for i, insn in enumerate(lines) if re.search(r"^pushf\w*\b", insn)]
    popf = [i for i, insn in enumerate(lines) if re.search(r"^popf\w*\b", insn)]
    rets = [i for i, insn in enumerate(lines) if re.search(r"^ret\w*\b", insn)]
    if not pushf:
        raise AssertionError("verify_cpu missing pushf")
    if len(popf) < 2:
        raise AssertionError("verify_cpu must expose both success/failure flag restores")
    if len(rets) < 2:
        raise AssertionError("verify_cpu must expose both success/failure returns")

    # The two terminal paths in Linux v5.10 restore flags before setting EAX and
    # returning.  Match machine instructions, not source labels.
    terminal = []
    for p in popf:
        tail = lines[p:p + 4]
        joined = "\n".join(tail)
        if re.search(r"mov\w*\s+\$0x?1,%eax", joined) and any(re.match(r"^ret\w*\b", x) for x in tail):
            terminal.append("failure")
        if re.search(r"xor\w*\s+%eax,%eax", joined) and any(re.match(r"^ret\w*\b", x) for x in tail):
            terminal.append("success")

    mark("failure path restores flags then returns EAX=1", "failure" in terminal)
    mark("success path restores flags then returns EAX=0", "success" in terminal)
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("disassembly", type=Path)
    args = ap.parse_args()
    text = args.disassembly.read_text()
    startup = instruction_lines(symbol_body(text, "startup_32"))
    verify = instruction_lines(symbol_body(text, "verify_cpu"))
    checks = check_startup32(startup) + check_verify_cpu(verify)
    for item in checks:
        print(f"PASS: {item}")
    print(f"PASS: {len(checks)} A19 disassembly-contract checks")


if __name__ == "__main__":
    try:
        main()
    except (OSError, AssertionError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)

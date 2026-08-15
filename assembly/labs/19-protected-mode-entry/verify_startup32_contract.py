#!/usr/bin/env python3
"""Static acceptance checks for A19 protected-mode-entry source facts.

Usage:
    python3 verify_startup32_contract.py /path/to/linux-5.10
"""
import argparse
import re
import sys
from pathlib import Path


def pos(text, pattern, label):
    m = re.search(pattern, text, re.M)
    if not m:
        raise AssertionError(f"missing: {label}")
    return m.start()


def check_text(head, verify):
    checks = []

    def ok(name, cond):
        if not cond:
            raise AssertionError(name)
        checks.append(name)

    p_code32 = pos(head, r"^\s*\.code32\s*$", ".code32")
    p_start = pos(head, r"^\s*SYM_FUNC_START\(startup_32\)", "startup_32")
    p_cld = pos(head[p_start:], r"\bcld\b", "cld") + p_start
    p_cli = pos(head[p_start:], r"\bcli\b", "cli") + p_start
    p_lgdt = pos(head[p_start:], r"\blgdt\b", "lgdt") + p_start
    p_bootds = pos(head[p_lgdt:], r"movl\s+\$__BOOT_DS", "__BOOT_DS load") + p_lgdt

    seg_positions = []
    cursor = p_bootds
    for seg in ("ds", "es", "fs", "gs", "ss"):
        p = pos(head[cursor:], rf"mov[lw]?\s+%[a-z]+,\s*%{seg}\b", f"{seg} reload") + cursor
        seg_positions.append(p)
        cursor = p

    p_stack = pos(
        head[cursor:],
        r"leal\s+rva\(boot_stack_end\)\(%ebp\),\s*%esp",
        "boot_stack_end",
    ) + cursor
    p_verify = pos(head[p_stack:], r"\bcall\s+verify_cpu\b", "call verify_cpu") + p_stack
    p_test = pos(head[p_verify:], r"\btestl\s+%eax,\s*%eax\b", "test verify_cpu result") + p_verify
    p_cr4 = pos(head[p_test:], r"\bmovl\s+%eax,\s*%cr4\b", "CR4 write") + p_test

    ok(".code32 precedes startup_32", p_code32 < p_start)
    ok("cld/cli occur after startup_32", p_start < p_cld and p_start < p_cli)
    ok("lgdt precedes data-segment reloads", p_lgdt < min(seg_positions))
    ok("DS/ES/FS/GS/SS reload in source order", seg_positions == sorted(seg_positions))
    ok("boot stack established before verify_cpu", max(seg_positions) < p_stack < p_verify)
    ok("verify_cpu result tested before CR4 preparation", p_verify < p_test < p_cr4)

    p_pushf = pos(verify, r"\bpushf[lq]?\b", "verify_cpu pushf")
    p_popf = pos(verify[p_pushf:], r"\bpopf[lq]?\b", "verify_cpu popf") + p_pushf
    ok("verify_cpu saves/restores flags", p_pushf < p_popf)

    # Linux v5.10 verify_cpu returns 0 on success and 1 on failure.
    ok("verify_cpu has success zeroing of eax", bool(re.search(r"\bxorl\s+%eax,\s*%eax\b", verify)))
    ok("verify_cpu has failure value 1", bool(re.search(r"\bmovl\s+\$1,\s*%eax\b", verify)))

    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kernel", type=Path)
    args = ap.parse_args()

    head_path = args.kernel / "arch/x86/boot/compressed/head_64.S"
    verify_path = args.kernel / "arch/x86/kernel/verify_cpu.S"
    head = head_path.read_text()
    verify = verify_path.read_text()

    checks = check_text(head, verify)
    for item in checks:
        print(f"PASS: {item}")
    print(f"PASS: {len(checks)} static A19 startup_32 contract checks")


if __name__ == "__main__":
    try:
        main()
    except (OSError, AssertionError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Verify B03 formal head_64.S early-paging contracts against Linux v5.10.

This is an L1 source-contract checker.  It deliberately does not claim that a
particular vmlinux has the same machine-code layout, or that a boot actually
observed the implied CR3/RIP/register states.

Usage:
    python3 verify_source_contract.py /path/to/linux-5.10
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class CheckError(RuntimeError):
    pass


def read(root: Path, rel: str) -> str:
    path = root / rel
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckError(f"cannot read {rel}: {exc}") from exc


def require(text: str, pattern: str, label: str) -> re.Match[str]:
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise CheckError(f"missing contract: {label}")
    return match


def ordered(text: str, checks: list[tuple[str, str]], label: str) -> None:
    positions = []
    for name, pattern in checks:
        positions.append((name, require(text, pattern, name).start()))
    if [pos for _, pos in positions] != sorted(pos for _, pos in positions):
        rendered = " -> ".join(name for name, _ in positions)
        raise CheckError(f"wrong source order for {label}: {rendered}")


def function_body(text: str, signature: str, label: str) -> str:
    """Return the lexical body of a C function using balanced braces."""
    match = require(text, signature, label)
    brace = text.find("{", match.start())
    if brace < 0:
        raise CheckError(f"missing opening brace for {label}")
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1:index]
    raise CheckError(f"unterminated body for {label}")


def symbol_region(text: str, start_pattern: str, end_pattern: str, label: str) -> str:
    start = require(text, start_pattern, f"{label} start").start()
    end_match = re.search(end_pattern, text[start:], re.MULTILINE)
    if end_match is None:
        raise CheckError(f"missing contract: {label} end")
    return text[start:start + end_match.end()]


def check(root: Path) -> list[str]:
    head_s = read(root, "arch/x86/kernel/head_64.S")
    head_c = read(root, "arch/x86/kernel/head64.c")
    pgtable_types = read(root, "arch/x86/include/asm/pgtable_64_types.h")

    passed: list[str] = []

    startup = symbol_region(
        head_s,
        r"SYM_CODE_START_NOALIGN\(startup_64\)",
        r"SYM_CODE_END\(startup_64\)",
        "startup_64",
    )
    require(startup, r"64bit mode.*?identity mapped page table", "formal-entry 64-bit/identity-map contract")
    require(startup, r"%rsi holds a physical pointer to real_mode_data", "formal-entry RSI contract")
    ordered(
        startup,
        [
            ("verify_cpu", r"\bcall\s+verify_cpu\b"),
            ("__startup_64", r"\bcall\s+__startup_64\b"),
            ("early_top_pgt CR3 component", r"addq\s+\$\(early_top_pgt\s*-\s*__START_KERNEL_map\),\s*%rax"),
        ],
        "BSP startup_64",
    )
    passed.append("formal startup_64 entry and BSP call order")

    body = function_body(
        head_c,
        r"unsigned\s+long\s+__head\s+__startup_64\s*\(",
        "__startup_64",
    )
    require(
        body,
        r"load_delta\s*=\s*physaddr\s*-\s*\(unsigned long\)\(_text\s*-\s*__START_KERNEL_map\)\s*;",
        "load_delta formula",
    )
    require(body, r"load_delta\s*&\s*~PMD_PAGE_MASK", "PMD alignment check")
    require(body, r"fixup_pointer\s*\(\s*&early_top_pgt\s*,\s*physaddr\s*\)", "early_top_pgt fixup")
    require(body, r"fixup_pointer\s*\(\s*early_dynamic_pgts\s*\[", "early_dynamic_pgts switchover pool")
    require(body, r"__PAGE_KERNEL_LARGE_EXEC\s*&\s*~_PAGE_GLOBAL", "non-global switchover PMD")
    require(
        body,
        r"fixup_long\s*\(\s*&phys_base\s*,\s*physaddr\s*\)\s*\+=\s*load_delta\s*-\s*sme_get_me_mask\s*\(\s*\)\s*;",
        "phys_base update without SME mask",
    )
    require(body, r"return\s+sme_get_me_mask\s*\(\s*\)\s*;", "__startup_64 SME-modifier return")
    passed.append("load_delta, early mappings, phys_base and SME return")

    require(
        pgtable_types,
        r"#define\s+EARLY_DYNAMIC_PAGE_TABLES\s+64\b",
        "EARLY_DYNAMIC_PAGE_TABLES == 64",
    )
    passed.append("early dynamic page-table pool size")

    shared = head_s[require(head_s, r"^1:\s*$", "BSP/AP shared label").start():]
    ordered(
        shared,
        [
            ("phys_base CR3 component", r"addq\s+phys_base\(%rip\),\s*%rax"),
            ("sev_verify_cbit", r"\bcall\s+sev_verify_cbit\b"),
            ("CR3 write", r"movq\s+%rax,\s*%cr3"),
            ("virtual-address target", r"movq\s+\$1f,\s*%rax"),
            ("indirect virtual-address jump", r"jmp\s+\*%rax"),
            ("kernel GDT", r"lgdt\s+early_gdt_descr\(%rip\)"),
            ("initial stack", r"movq\s+initial_stack\(%rip\),\s*%rsp"),
            ("early IDT", r"\bcall\s+early_setup_idt\b"),
            ("RFLAGS clear", r"pushq\s+\$0\s*\n\s*popfq"),
            ("RSI to RDI ABI handoff", r"movq\s+%rsi,\s*%rdi"),
            ("far return", r"\blretq\b"),
        ],
        "CR3/address-context/C handoff",
    )
    require(head_s, r"SYM_DATA\(initial_code,\s*\.quad\s+x86_64_start_kernel\)", "initial_code target")
    passed.append("CR3 switch, virtual jump and x86_64_start_kernel handoff")

    secondary = symbol_region(
        head_s,
        r"SYM_CODE_START\(secondary_startup_64\)",
        r"SYM_CODE_END\(secondary_startup_64\)",
        "secondary_startup_64",
    )
    require(secondary, r"\bcall\s+__startup_secondary_64\b", "secondary C setup")
    require(secondary, r"addq\s+\$\(init_top_pgt\s*-\s*__START_KERNEL_map\),\s*%rax", "secondary init_top_pgt")
    require(
        secondary,
        r"secondary_startup_64_no_verify.*?only used by.*?SEV-ES guests",
        "SEV-ES no-verify boundary",
    )
    passed.append("BSP/AP page-table ownership and SEV-ES special entry")

    require(
        head_c,
        r"5-level paging is detected and enabled at kernel decomression\s*\* stage\.\s*\* Only check if it has been enabled there\.",
        "LA57 handoff from decompressor",
    )
    passed.append("LA57 is inherited rather than first enabled here")

    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel", type=Path, help="Linux v5.10 source tree")
    args = parser.parse_args()
    try:
        passed = check(args.kernel)
    except CheckError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    for item in passed:
        print(f"PASS: {item}")
    print(f"PASS: {len(passed)} B03 L1 source-contract groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

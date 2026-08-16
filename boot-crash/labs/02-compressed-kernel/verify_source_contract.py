#!/usr/bin/env python3
"""Verify B02 compressed-kernel source/build contracts in Linux 5.10.

This is an L1 checker only.  It validates source/build relationships; it does
not prove the configuration of a built kernel, ELF properties, machine code,
or runtime addresses.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class CheckError(RuntimeError):
    pass


def read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckError(f"cannot read {rel}: {exc}") from exc


def require(text: str, pattern: str, label: str, flags: int = re.MULTILINE) -> re.Match[str]:
    match = re.search(pattern, text, flags)
    if match is None:
        raise CheckError(f"missing {label}")
    return match


def function_body(text: str, name: str) -> str:
    """Return a brace-balanced C function body containing name(...)."""
    match = require(text, rf"\b{name}\s*\([^;]*?\)\s*\{{", name,
                    re.MULTILINE | re.DOTALL)
    start = text.find("{", match.start())
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise CheckError(f"unterminated function body: {name}")


def ordered(text: str, items: list[tuple[str, str]], label: str) -> None:
    positions = []
    for item_label, pattern in items:
        positions.append(require(text, pattern, item_label,
                                 re.MULTILINE | re.DOTALL).start())
    if positions != sorted(positions):
        raise CheckError(f"wrong order: {label}")


def check(root: Path) -> list[str]:
    makefile = read(root, "arch/x86/boot/compressed/Makefile")
    head = read(root, "arch/x86/boot/compressed/head_64.S")
    misc = read(root, "arch/x86/boot/compressed/misc.c")
    kaslr = read(root, "arch/x86/boot/compressed/kaslr.c")

    passed: list[str] = []

    for flag, pattern in (
        ("-fPIE", r"\bKBUILD_CFLAGS\s*\+=.*(?:^|\s)-fPIE(?:\s|$)"),
        ("-ffreestanding", r"\bKBUILD_CFLAGS\s*\+=.*(?:^|\s)-ffreestanding(?:\s|$)"),
        ("-fno-stack-protector", r"\bKBUILD_CFLAGS\s*\+=.*(?:^|\s)-fno-stack-protector(?:\s|$)"),
    ):
        require(makefile, pattern, f"compressed C flag {flag}")
        passed.append(f"compressed C uses {flag}")

    require(makefile, r"\bLDFLAGS_vmlinux\b[^\n]*\+=?[^\n]*\s-pie(?:\s|$)",
            "compressed vmlinux PIE link")
    passed.append("compressed vmlinux links as PIE")

    require(makefile,
            r"^\s*vmlinux-objs-\$\(CONFIG_RANDOMIZE_BASE\)\s*\+=\s*kaslr\.o\s*$",
            "CONFIG_RANDOMIZE_BASE controls kaslr.o")
    passed.append("CONFIG_RANDOMIZE_BASE controls kaslr.o")

    require(makefile,
            r"^\s*ifdef\s+CONFIG_X86_NEED_RELOCS\s*$.*?vmlinux\.relocs.*?^\s*endif\s*$",
            "CONFIG_X86_NEED_RELOCS relocation payload",
            re.MULTILINE | re.DOTALL)
    passed.append("CONFIG_X86_NEED_RELOCS gates relocation payload")

    require(head, r"\bstartup_32\b", "compressed startup_32")
    require(head, r"\bstartup_64\b", "compressed startup_64")
    require(head, r"\bcall\s+extract_kernel\b", "assembly call to extract_kernel")
    passed.append("compressed assembly owns startup_32/startup_64 and calls extract_kernel")

    body = function_body(misc, "extract_kernel")
    require(body, r"\bboot_params\s*=\s*rmode\s*;", "boot_params = rmode")
    require(body,
            r"\bneeded_size\s*=\s*max_t\s*\([^;]*\boutput_len\b[^;]*\bkernel_total_size\b[^;]*\)\s*;",
            "needed_size max(output_len, kernel_total_size)")
    passed.append("extract_kernel receives boot_params and computes needed_size")

    ordered(body, [
        ("choose_random_location", r"\bchoose_random_location\s*\("),
        ("__decompress", r"\b__decompress\s*\("),
        ("parse_elf", r"\bparse_elf\s*\("),
        ("handle_relocations", r"\bhandle_relocations\s*\("),
    ], "extract_kernel placement/decompression/ELF/relocation")
    passed.append("extract_kernel orders KASLR, decompression, ELF placement, relocation")

    require(kaslr, r"\bMEM_AVOID_ZO_RANGE\b", "MEM_AVOID_ZO_RANGE")
    require(kaslr, r"\bMEM_AVOID_INITRD\b", "MEM_AVOID_INITRD")
    require(kaslr, r"\bMEM_AVOID_CMDLINE\b", "MEM_AVOID_CMDLINE")
    require(kaslr, r"\bMEM_AVOID_BOOTPARAMS\b", "MEM_AVOID_BOOTPARAMS")
    passed.append("KASLR avoids decompressor, initrd, command line and boot_params")

    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel", type=Path, help="path to a Linux 5.10 source tree")
    args = parser.parse_args()
    try:
        passed = check(args.kernel)
    except CheckError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    for item in passed:
        print(f"PASS: {item}")
    print(f"PASS: {len(passed)} B02 L1 source/build contract checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

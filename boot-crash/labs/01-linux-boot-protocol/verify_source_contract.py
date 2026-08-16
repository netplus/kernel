#!/usr/bin/env python3
"""Verify B01 Linux 5.10 boot-protocol source contracts.

Usage:
    python3 verify_source_contract.py /path/to/linux-5.10

This is an L1 source/UAPI checker.  It does not prove the bytes in a built
bzImage or the boot_params contents supplied by a particular boot loader.
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
        raise CheckError(f"missing {label}")
    return match


def position(text: str, pattern: str, label: str) -> int:
    return require(text, pattern, label).start()


def check(root: Path) -> list[str]:
    header = read(root, "arch/x86/boot/header.S")
    bootparam = read(root, "arch/x86/include/uapi/asm/bootparam.h")
    main = read(root, "arch/x86/boot/main.c")

    passed: list[str] = []

    require(header, r'\.ascii\s+"HdrS"', "HdrS signature")
    passed.append("header.S exposes HdrS")

    require(header, r"\.word\s+0x020f\b", "protocol version 0x020f")
    passed.append("header.S protocol version is 0x020f (2.15)")

    # These comments are part of the v5.10 UAPI source and make the ABI offsets
    # explicit.  A compiled offsetof test remains a stronger layout check.
    offset_contracts = {
        "e820_entries": "0x1e8",
        "sentinel": "0x1ef",
        "hdr": "0x1f1",
        "e820_table": "0x2d0",
    }
    for field, offset in offset_contracts.items():
        require(
            bootparam,
            rf"\b{field}\b[^\n]*/\*\s*{re.escape(offset)}\s*\*/",
            f"boot_params.{field} offset {offset}",
        )
        passed.append(f"boot_params.{field} source offset is {offset}")

    require(
        bootparam,
        r"struct\s+setup_header\s+hdr\s*;[^\n]*/\*\s*setup header\s*\*/[^\n]*/\*\s*0x1f1\s*\*/",
        "embedded setup_header hdr",
    )
    passed.append("boot_params embeds struct setup_header hdr")

    require(bootparam, r"#define\s+E820_MAX_ENTRIES_ZEROPAGE\s+128\b", "E820 zeropage capacity")
    passed.append("zeropage E820 capacity is 128 entries")

    require(main, r"BUILD_BUG_ON\s*\(\s*sizeof\s*\(\s*boot_params\s*\)\s*!=\s*4096\s*\)", "4 KiB boot_params BUILD_BUG_ON")
    passed.append("setup enforces sizeof(boot_params) == 4096")

    require(main, r"memcpy\s*\(\s*&boot_params\.hdr\s*,\s*&hdr\s*,\s*sizeof\s*\(\s*hdr\s*\)\s*\)", "copy_boot_params header copy")
    passed.append("copy_boot_params copies image hdr into boot_params.hdr")

    main_start = position(main, r"\bvoid\s+main\s*\(\s*void\s*\)\s*\{", "setup main")
    body = main[main_start:]
    order = [
        ("copy_boot_params", r"\bcopy_boot_params\s*\(\s*\)"),
        ("validate_cpu", r"\bvalidate_cpu\s*\(\s*\)"),
        ("set_bios_mode", r"\bset_bios_mode\s*\(\s*\)"),
        ("detect_memory", r"\bdetect_memory\s*\(\s*\)"),
        ("set_video", r"\bset_video\s*\(\s*\)"),
        ("go_to_protected_mode", r"\bgo_to_protected_mode\s*\(\s*\)"),
    ]
    positions = [(name, position(body, pattern, name)) for name, pattern in order]
    if [p for _, p in positions] != sorted(p for _, p in positions):
        rendered = " -> ".join(f"{name}@{p}" for name, p in positions)
        raise CheckError(f"unexpected setup main order: {rendered}")
    passed.append("setup main preserves copy/CPU/BIOS/memory/video/protected-mode order")

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
    print(f"PASS: {len(passed)} B01 source-contract checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

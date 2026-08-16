#!/usr/bin/env python3
"""Verify B00 boot-stage source ownership against a Linux 5.10 tree.

This checker intentionally proves source-level ownership only. It must not be
used as evidence for ELF symbol visibility or runtime execution.

Usage:
    python3 verify_source_ownership.py /path/to/linux-5.10
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


def require(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, re.MULTILINE) is None:
        raise CheckError(f"missing {label}")
    print(f"PASS: {label}")


def check(root: Path) -> None:
    """Check the B00 source-ownership contract under *root*.

    Keeping the contract separate from CLI parsing lets the fixture tests call
    exactly the same matcher used for a real Linux 5.10 source tree.
    """
    setup = read(root, "arch/x86/boot/main.c")
    compressed_head = read(root, "arch/x86/boot/compressed/head_64.S")
    compressed_misc = read(root, "arch/x86/boot/compressed/misc.c")
    formal_head = read(root, "arch/x86/kernel/head_64.S")
    head64 = read(root, "arch/x86/kernel/head64.c")
    init_main = read(root, "init/main.c")

    require(setup, r"\bvoid\s+main\s*\(\s*void\s*\)",
            "setup main() in arch/x86/boot/main.c")
    require(compressed_head, r"\bstartup_64\b",
            "compressed startup_64 in arch/x86/boot/compressed/head_64.S")
    require(compressed_misc, r"\bextract_kernel\s*\(",
            "extract_kernel() in compressed/misc.c")
    require(formal_head, r"\bstartup_64\b",
            "formal-kernel startup_64 in arch/x86/kernel/head_64.S")
    require(head64, r"\bx86_64_start_kernel\s*\(",
            "x86_64_start_kernel() in arch/x86/kernel/head64.c")
    require(head64, r"\bx86_64_start_reservations\s*\(",
            "x86_64_start_reservations() in arch/x86/kernel/head64.c")
    require(init_main, r"\bstart_kernel\s*\(",
            "start_kernel() in init/main.c")
    require(init_main, r"\brest_init\s*\(",
            "rest_init() in init/main.c")
    require(init_main, r"\bkernel_init\s*\(",
            "kernel_init() in init/main.c")
    require(init_main, r"kernel_thread\s*\(\s*kernel_init\b",
            "rest_init path creates kernel_init task")
    require(init_main, r"\brun_init_process\s*\(",
            "run_init_process() exists for later exec boundary")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel", type=Path, help="Linux 5.10 source tree")
    args = parser.parse_args()
    check(args.kernel)

    # The two startup_64 checks deliberately read different files. Their
    # success demonstrates two source ownership contexts; it does not compare
    # addresses or claim that both symbols are visible in one ELF.
    print("PASS: B00 source ownership contract")
    print("NOTE: ELF/nm/objdump and runtime execution remain separate evidence")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)

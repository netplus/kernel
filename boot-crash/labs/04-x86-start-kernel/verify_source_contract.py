#!/usr/bin/env python3
"""Validate B04 Linux v5.10 early-C/start_kernel source contracts.

This checker is intentionally L1-only.  It checks source ownership and ordering
contracts; it does not prove the shape of a built vmlinux or runtime CPU state.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


class CheckError(RuntimeError):
    pass


def read(root: Path, rel: str) -> str:
    path = root / rel
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckError(f"cannot read {path}: {exc}") from exc


def require(text: str, pattern: str, label: str) -> re.Match[str]:
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise CheckError(f"missing contract: {label}")
    return match


def function_body(text: str, signature: str, label: str) -> str:
    match = require(text, signature, label)
    brace = text.find("{", match.start())
    if brace < 0:
        raise CheckError(f"missing function body: {label}")

    depth = 0
    for pos in range(brace, len(text)):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1 : pos]
    raise CheckError(f"unterminated function body: {label}")


def ordered(text: str, checks: list[tuple[str, str]], label: str) -> None:
    positions: list[tuple[str, int]] = []
    for name, pattern in checks:
        positions.append((name, require(text, pattern, f"{label}: {name}").start()))
    offsets = [offset for _, offset in positions]
    if offsets != sorted(offsets):
        detail = " -> ".join(f"{name}@{offset}" for name, offset in positions)
        raise CheckError(f"wrong source order for {label}: {detail}")


def check(root: Path) -> list[str]:
    head64 = read(root, "arch/x86/kernel/head64.c")
    main = read(root, "init/main.c")
    setup = read(root, "arch/x86/kernel/setup.c")
    passed: list[str] = []

    # 1. copy_bootdata() transfers ownership from the early boot-data area to
    # formal-kernel-owned boot_params / boot_command_line before unmapping it.
    copy = function_body(
        head64,
        r"static\s+void\s+__init\s+copy_bootdata\s*\(\s*char\s*\*\s*real_mode_data\s*\)",
        "copy_bootdata()",
    )
    ordered(
        copy,
        [
            ("boot_params copy", r"memcpy\s*\(\s*&boot_params\s*,\s*real_mode_data\s*,\s*sizeof\s*\(\s*boot_params\s*\)\s*\)"),
            ("sanitize", r"sanitize_boot_params\s*\(\s*&boot_params\s*\)"),
            ("command-line pointer", r"cmd_line_ptr\s*=\s*get_cmd_line_ptr\s*\(\s*\)"),
            ("command-line copy", r"memcpy\s*\(\s*boot_command_line\s*,\s*command_line\s*,\s*COMMAND_LINE_SIZE\s*\)"),
            ("old boot-data unmap", r"sme_unmap_bootdata\s*\(\s*real_mode_data\s*\)"),
        ],
        "boot-data ownership",
    )
    passed.append("boot-data ownership copy/sanitize/command-line/unmap")

    # 2. Normal x86-64 BSP early-C path copies boot data before reservations;
    # reservations keeps the defensive version check and then enters start_kernel().
    start64 = function_body(
        head64,
        r"asmlinkage\s+__visible\s+void\s+__init\s+x86_64_start_kernel\s*\(",
        "x86_64_start_kernel()",
    )
    ordered(
        start64,
        [
            ("early IDT", r"idt_setup_early_handler\s*\(\s*\)"),
            ("copy_bootdata", r"copy_bootdata\s*\(\s*__va\s*\(\s*real_mode_data\s*\)\s*\)"),
            ("reservations", r"x86_64_start_reservations\s*\(\s*real_mode_data\s*\)"),
        ],
        "x86_64_start_kernel()",
    )
    reservations = function_body(
        head64,
        r"void\s+__init\s+x86_64_start_reservations\s*\(\s*char\s*\*\s*real_mode_data\s*\)",
        "x86_64_start_reservations()",
    )
    require(
        reservations,
        r"if\s*\(\s*!boot_params\.hdr\.version\s*\)\s*copy_bootdata\s*\(\s*__va\s*\(\s*real_mode_data\s*\)\s*\)",
        "defensive boot-data copy",
    )
    ordered(
        reservations,
        [
            ("platform quirks", r"x86_early_init_platform_quirks\s*\(\s*\)"),
            ("start_kernel", r"start_kernel\s*\(\s*\)"),
        ],
        "reservations handoff",
    )
    passed.append("x86_64_start_kernel() -> reservations -> start_kernel()")

    # 3. setup_arch() is called by start_kernel(), not before the generic entry.
    start = function_body(
        main,
        r"asmlinkage\s+__visible\s+void\s+__init\s+__no_sanitize_address\s+start_kernel\s*\(\s*void\s*\)",
        "start_kernel()",
    )
    require(start, r"setup_arch\s*\(\s*&command_line\s*\)", "start_kernel() -> setup_arch()")
    require(setup, r"void\s+__init\s+setup_arch\s*\(\s*char\s*\*\s*\*\s*cmdline_p\s*\)", "x86 setup_arch() definition")
    passed.append("setup_arch() is inside start_kernel()")

    # 4. Early local-IRQ software state is established before setup_arch().
    ordered(
        start,
        [
            ("local IRQ disable", r"local_irq_disable\s*\(\s*\)"),
            ("software IRQ flag", r"early_boot_irqs_disabled\s*=\s*true\s*;"),
            ("setup_arch", r"setup_arch\s*\(\s*&command_line\s*\)"),
        ],
        "early IRQ state",
    )
    passed.append("early local-IRQ disable/software flag before setup_arch()")

    # 5. The memory/scheduler/RCU/IRQ/time foundations are built before IRQs
    # are enabled.  This is a source-order contract, not a claim that adjacent
    # entries directly call one another.
    ordered(
        start,
        [
            ("setup_arch", r"setup_arch\s*\(\s*&command_line\s*\)"),
            ("zonelists", r"build_all_zonelists\s*\(\s*NULL\s*\)"),
            ("page_alloc_init", r"page_alloc_init\s*\(\s*\)"),
            ("mm_init", r"mm_init\s*\(\s*\)"),
            ("sched_init", r"sched_init\s*\(\s*\)"),
            ("rcu_init", r"rcu_init\s*\(\s*\)"),
            ("early_irq_init", r"early_irq_init\s*\(\s*\)"),
            ("init_IRQ", r"init_IRQ\s*\(\s*\)"),
            ("tick_init", r"tick_init\s*\(\s*\)"),
            ("init_timers", r"init_timers\s*\(\s*\)"),
            ("hrtimers_init", r"hrtimers_init\s*\(\s*\)"),
            ("softirq_init", r"softirq_init\s*\(\s*\)"),
            ("timekeeping_init", r"timekeeping_init\s*\(\s*\)"),
            ("clear software IRQ flag", r"early_boot_irqs_disabled\s*=\s*false\s*;"),
            ("local IRQ enable", r"local_irq_enable\s*\(\s*\)"),
            ("rest-init boundary", r"arch_call_rest_init\s*\(\s*\)"),
        ],
        "generic initialization capability order",
    )
    passed.append("memory -> scheduler/RCU -> IRQ/time -> IRQ enable -> rest-init order")

    # 6. mm_init() is the point where several ordinary allocator facilities are
    # brought up; page_alloc_init() alone must not be treated as all allocators.
    mm = function_body(main, r"static\s+void\s+__init\s+mm_init\s*\(\s*void\s*\)", "mm_init()")
    ordered(
        mm,
        [
            ("mem_init", r"mem_init\s*\(\s*\)"),
            ("kmem_cache_init", r"kmem_cache_init\s*\(\s*\)"),
            ("vmalloc_init", r"vmalloc_init\s*\(\s*\)"),
        ],
        "mm_init allocator progression",
    )
    passed.append("mm_init(): mem_init -> kmem_cache_init -> vmalloc_init")

    # 7. B04 stops at arch_call_rest_init(); its weak default belongs to the
    # next chapter's rest_init() path.
    rest = function_body(
        main,
        r"void\s+__init\s+__weak\s+arch_call_rest_init\s*\(\s*void\s*\)",
        "arch_call_rest_init()",
    )
    require(rest, r"rest_init\s*\(\s*\)", "weak arch_call_rest_init() -> rest_init()")
    passed.append("arch_call_rest_init() boundary to rest_init()")

    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kernel_tree", type=Path, help="Linux v5.10 source tree")
    args = parser.parse_args()

    try:
        passed = check(args.kernel_tree)
    except CheckError as exc:
        print(f"FAIL: {exc}")
        return 1

    for item in passed:
        print(f"PASS: {item}")
    print(f"PASS: {len(passed)} B04 L1 source-contract groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

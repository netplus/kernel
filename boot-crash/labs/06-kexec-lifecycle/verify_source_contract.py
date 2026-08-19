#!/usr/bin/env python3
"""Check the Linux v5.10 source contracts used by boot-crash B06.

This is deliberately an L1 source checker. It does not prove that a
particular distro build enables Kexec, nor does it prove runtime transition
state. Run it against an upstream Linux v5.10 source checkout.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


class CheckError(RuntimeError):
    pass


def read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckError(f"cannot read {rel}: {exc}") from exc


def require(text: str, pattern: str, label: str) -> re.Match[str]:
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise CheckError(f"missing contract: {label}")
    return match


def ordered(text: str, checks: list[tuple[str, str]], label: str) -> None:
    positions = [(name, require(text, pattern, name).start()) for name, pattern in checks]
    offsets = [offset for _, offset in positions]
    if offsets != sorted(offsets):
        raise CheckError(
            f"wrong source order for {label}: expected "
            + " -> ".join(name for name, _ in positions)
        )


def function_body(text: str, signature: str, label: str) -> str:
    match = require(text, signature, label)
    brace = text.find("{", match.start())
    if brace < 0:
        raise CheckError(f"missing function body: {label}")

    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1 : index]
    raise CheckError(f"unterminated function body: {label}")


def check(root: Path) -> list[str]:
    traditional = read(root, "kernel/kexec.c")
    file_load = read(root, "kernel/kexec_file.c")
    core = read(root, "kernel/kexec_core.c")
    x86 = read(root, "arch/x86/kernel/machine_kexec_64.c")
    passed: list[str] = []

    # 1. Loading API and image purpose are independent dimensions.
    require(traditional, r"SYSCALL_DEFINE4\s*\(\s*kexec_load\b", "traditional kexec_load syscall")
    require(traditional, r"KEXEC_ON_CRASH", "traditional crash-purpose flag")
    require(file_load, r"SYSCALL_DEFINE5\s*\(\s*kexec_file_load\b", "file kexec_file_load syscall")
    require(file_load, r"KEXEC_FILE_ON_CRASH", "file crash-purpose flag")
    passed.append("load API and normal/crash purpose remain independent")

    # 2. Both loaders select both persistent global slots and install the image
    # with xchg(). Do not impose source ordering on the two slot assignments:
    # v5.10 traditional load spells crash first, while file load initializes
    # the normal slot first and then overrides it for crash mode.
    traditional_load = function_body(traditional, r"static\s+int\s+do_kexec_load\s*\(", "do_kexec_load")
    require(traditional_load, r"dest_image\s*=\s*&kexec_crash_image\s*;", "traditional crash destination slot")
    require(traditional_load, r"dest_image\s*=\s*&kexec_image\s*;", "traditional normal destination slot")
    require(traditional_load, r"xchg\s*\(\s*dest_image\s*,\s*image\s*\)", "traditional image installation")

    file_syscall = function_body(file_load, r"SYSCALL_DEFINE5\s*\(\s*kexec_file_load\b", "kexec_file_load")
    require(file_syscall, r"dest_image\s*=\s*&kexec_crash_image\s*;", "file crash destination slot")
    require(file_syscall, r"dest_image\s*=\s*&kexec_image\s*;", "file normal destination slot")
    require(file_syscall, r"xchg\s*\(\s*dest_image\s*,\s*image\s*\)", "file image installation")
    passed.append("struct kimage ownership transfers to persistent global slot")

    # 3. Crash image destinations are constrained by crashk_res at load time.
    # In upstream v5.10 sanity_check_segment_list() is global, not static.
    sanity = function_body(core, r"int\s+sanity_check_segment_list\s*\(", "sanity_check_segment_list")
    require(sanity, r"image->type\s*==\s*KEXEC_TYPE_CRASH", "crash segment branch")
    require(sanity, r"crashk_res\.start", "crash reserved range start")
    require(sanity, r"crashk_res\.end", "crash reserved range end")
    passed.append("crash segment destinations are constrained by crashk_res")

    # 4. Control-page allocation has a crash-specific policy. Upstream v5.10
    # dispatches with switch (image->type), not an if (type == CRASH) branch.
    control = function_body(core, r"struct\s+page\s*\*kimage_alloc_control_pages\s*\(", "kimage_alloc_control_pages")
    require(control, r"switch\s*\(\s*image->type\s*\)", "control-page type dispatch")
    require(control, r"case\s+KEXEC_TYPE_CRASH\s*:", "crash control-page case")
    require(control, r"kimage_alloc_crash_control_pages\s*\(", "crash control-page allocator")
    passed.append("normal/crash control-page allocation policy differs")

    # 5. Both load APIs allocate swap_page only for non-crash images.
    # Upstream v5.10 kimage_alloc_init() returns int via an out-parameter.
    traditional_alloc = function_body(traditional, r"static\s+int\s+kimage_alloc_init\s*\(", "kimage_alloc_init")
    require(
        traditional_alloc,
        r"if\s*\(\s*!kexec_on_panic\s*\).*?image->swap_page\s*=\s*kimage_alloc_control_pages\s*\(",
        "traditional normal-only swap_page",
    )
    file_alloc = function_body(file_load, r"static\s+int\s+kimage_file_alloc_init\s*\(", "kimage_file_alloc_init")
    require(
        file_alloc,
        r"if\s*\(\s*!kexec_on_panic\s*\).*?image->swap_page\s*=\s*kimage_alloc_control_pages\s*\(",
        "file normal-only swap_page",
    )
    passed.append("swap_page is allocated only for non-crash images")

    # 6. Architecture preparation occurs during both load paths, before the
    # prepared image is installed into the persistent slot.
    ordered(
        traditional_load,
        [
            ("machine_kexec_prepare", r"machine_kexec_prepare\s*\(\s*image\s*\)"),
            ("install image", r"xchg\s*\(\s*dest_image\s*,\s*image\s*\)"),
        ],
        "traditional prepare before install",
    )
    ordered(
        file_syscall,
        [
            ("machine_kexec_prepare", r"machine_kexec_prepare\s*\(\s*image\s*\)"),
            ("install image", r"xchg\s*\(\s*dest_image\s*,\s*image\s*\)"),
        ],
        "file prepare before install",
    )
    passed.append("machine_kexec_prepare belongs to load/prepare phase")

    # 7. x86 machine_kexec_prepare builds transition mappings. Linux v5.10
    # documents the point-of-no-return rule in the comment immediately before
    # machine_kexec(), so check that source ordering rather than pretending the
    # comment lives inside the function body.
    prepare = function_body(x86, r"int\s+machine_kexec_prepare\s*\(", "machine_kexec_prepare")
    require(prepare, r"init_pgtable\s*\(\s*image\s*,", "x86 transition page-table preparation")
    ordered(
        x86,
        [
            (
                "point-of-no-return comment",
                r"Do\s+not\s+allocate\s+memory\s*\(or\s+fail\s+in\s+any\s+way\)\s+in\s+machine_kexec\s*\(\s*\)\s*\.\s*.*?past\s+the\s+point\s+of\s+no\s+return",
            ),
            ("machine_kexec definition", r"void\s+machine_kexec\s*\("),
        ],
        "point-of-no-return contract before machine_kexec",
    )
    passed.append("x86 prepare and point-of-no-return transition are separate phases")

    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("linux_tree", type=Path, help="path to an upstream Linux v5.10 source tree")
    args = parser.parse_args()

    try:
        passed = check(args.linux_tree)
    except CheckError as exc:
        print(f"FAIL: {exc}")
        return 1

    for index, item in enumerate(passed, 1):
        print(f"PASS {index}: {item}")
    print(f"PASS: {len(passed)} B06 Linux v5.10 source-contract groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

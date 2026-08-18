#!/usr/bin/env python3
"""Verify Linux v5.10 B05 rest_init-to-userspace source contracts.

This checker is deliberately source-level (L1).  It does not prove a
particular vmlinux layout or a runtime scheduling/rootfs/exec path.
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
        order = " -> ".join(name for name, _ in positions)
        raise CheckError(f"wrong source order for {label}: expected {order}")


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
    main_c = read(root, "init/main.c")
    passed: list[str] = []

    rest = function_body(main_c, r"noinline\s+void\s+__ref\s+rest_init\s*\(\s*void\s*\)", "rest_init")
    ordered(
        rest,
        [
            ("create kernel_init/PID 1", r"kernel_thread\s*\(\s*kernel_init\s*,\s*NULL\s*,\s*CLONE_FS\s*\)"),
            ("create kthreadd", r"kernel_thread\s*\(\s*kthreadd\s*,\s*NULL\s*,\s*CLONE_FS\s*\|\s*CLONE_FILES\s*\)"),
        ],
        "PID 1 before kthreadd",
    )
    passed.append("PID 1 is created before kthreadd")

    ordered(
        rest,
        [
            ("SYSTEM_SCHEDULING", r"system_state\s*=\s*SYSTEM_SCHEDULING\s*;"),
            ("complete kthreadd_done", r"complete\s*\(\s*&kthreadd_done\s*\)"),
            ("first explicit schedule", r"schedule_preempt_disabled\s*\(\s*\)"),
            ("idle handoff", r"cpu_startup_entry\s*\(\s*CPUHP_ONLINE\s*\)"),
        ],
        "rest_init scheduling handoff",
    )
    passed.append("SYSTEM_SCHEDULING -> completion -> schedule -> idle")

    freeable = function_body(main_c, r"static\s+noinline\s+void\s+__init\s+kernel_init_freeable\s*\(\s*void\s*\)", "kernel_init_freeable")
    wait = require(freeable, r"wait_for_completion\s*\(\s*&kthreadd_done\s*\)", "PID 1 waits for kthreadd_done")
    basic = require(freeable, r"do_basic_setup\s*\(\s*\)", "PID 1 do_basic_setup")
    if wait.start() >= basic.start():
        raise CheckError("wrong source order: kthreadd_done wait must precede do_basic_setup")
    passed.append("PID 1 waits for kthreadd_done before basic setup")

    basic_body = function_body(main_c, r"static\s+void\s+__init\s+do_basic_setup\s*\(\s*void\s*\)", "do_basic_setup")
    require(basic_body, r"do_initcalls\s*\(\s*\)", "do_basic_setup calls do_initcalls")
    passed.append("do_basic_setup -> do_initcalls")

    require(
        main_c,
        r"static\s+const\s+char\s*\*\s*initcall_level_names\[\]\s*=\s*\{\s*"
        r"\"pure\"\s*,\s*\"core\"\s*,\s*\"postcore\"\s*,\s*\"arch\"\s*,\s*"
        r"\"subsys\"\s*,\s*\"fs\"\s*,\s*\"device\"\s*,\s*\"late\"\s*\}",
        "initcall level order",
    )
    passed.append("initcall levels are pure -> core -> postcore -> arch -> subsys -> fs -> device -> late")

    require(main_c, r"static\s+const\s+char\s*ramdisk_execute_command\s*\[.*?\]\s*=\s*\"/init\"\s*;", "default /init")
    require(
        freeable,
        r"console_on_rootfs\s*\(\s*\)\s*;.*?"
        r"if\s*\(\s*init_eaccess\s*\(\s*ramdisk_execute_command\s*\)\s*!=\s*0\s*\)\s*\{.*?"
        r"ramdisk_execute_command\s*=\s*NULL\s*;.*?prepare_namespace\s*\(\s*\)\s*;.*?\}",
        "conditional prepare_namespace",
    )
    passed.append("prepare_namespace is conditional on early /init accessibility")

    kernel_init = function_body(main_c, r"static\s+int\s+__ref\s+kernel_init\s*\(\s*void\s*\*\s*unused\s*\)", "kernel_init")
    ordered(
        kernel_init,
        [
            ("SYSTEM_RUNNING", r"system_state\s*=\s*SYSTEM_RUNNING\s*;"),
            ("early /init", r"if\s*\(\s*ramdisk_execute_command\s*\).*?run_init_process\s*\(\s*ramdisk_execute_command\s*\)"),
        ],
        "SYSTEM_RUNNING before init exec",
    )
    passed.append("SYSTEM_RUNNING precedes user-space init exec attempts")

    ordered(
        kernel_init,
        [
            ("ramdisk /init", r"if\s*\(\s*ramdisk_execute_command\s*\)"),
            ("init=", r"if\s*\(\s*execute_command\s*\)"),
            ("CONFIG_DEFAULT_INIT", r"if\s*\(\s*CONFIG_DEFAULT_INIT\[0\]\s*!=\s*'\\0'\s*\)"),
            ("/sbin/init", r"try_to_run_init_process\s*\(\s*\"/sbin/init\"\s*\)"),
            ("/etc/init", r"try_to_run_init_process\s*\(\s*\"/etc/init\"\s*\)"),
            ("/bin/init", r"try_to_run_init_process\s*\(\s*\"/bin/init\"\s*\)"),
            ("/bin/sh", r"try_to_run_init_process\s*\(\s*\"/bin/sh\"\s*\)"),
            ("panic", r"panic\s*\(\s*\"No working init found"),
        ],
        "init fallback",
    )
    passed.append("init fallback order is preserved")

    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel_tree", type=Path, help="Linux v5.10 source checkout")
    args = parser.parse_args()

    try:
        passed = check(args.kernel_tree)
    except CheckError as exc:
        print(f"FAIL: {exc}")
        return 1

    for index, item in enumerate(passed, 1):
        print(f"PASS {index}: {item}")
    print(f"PASS: {len(passed)} B05 L1 source-contract groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

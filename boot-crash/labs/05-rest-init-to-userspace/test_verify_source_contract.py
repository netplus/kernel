#!/usr/bin/env python3
"""Fixture self-tests for the B05 Linux v5.10 source-contract checker.

These tests validate the checker itself. They do not replace running the checker
against a real Linux v5.10 source tree, nor L2/L3 build/runtime evidence.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_source_contract import CheckError, check


MAIN = r'''
static const char *initcall_level_names[] = {
    "pure", "core", "postcore", "arch", "subsys", "fs", "device", "late"
};

static const char ramdisk_execute_command[COMMAND_LINE_SIZE] = "/init";

noinline void __ref rest_init(void)
{
    kernel_thread(kernel_init, NULL, CLONE_FS);
    kernel_thread(kthreadd, NULL, CLONE_FS | CLONE_FILES);
    system_state = SYSTEM_SCHEDULING;
    complete(&kthreadd_done);
    schedule_preempt_disabled();
    cpu_startup_entry(CPUHP_ONLINE);
}

static void __init do_basic_setup(void)
{
    do_initcalls();
}

static noinline void __init kernel_init_freeable(void)
{
    wait_for_completion(&kthreadd_done);
    do_basic_setup();
    console_on_rootfs();
    if (init_eaccess(ramdisk_execute_command) != 0) {
        ramdisk_execute_command = NULL;
        prepare_namespace();
    }
}

static int __ref kernel_init(void *unused)
{
    system_state = SYSTEM_RUNNING;

    if (ramdisk_execute_command)
        run_init_process(ramdisk_execute_command);

    if (execute_command)
        run_init_process(execute_command);

    if (CONFIG_DEFAULT_INIT[0] != '\\0')
        run_init_process(CONFIG_DEFAULT_INIT);

    try_to_run_init_process("/sbin/init");
    try_to_run_init_process("/etc/init");
    try_to_run_init_process("/bin/init");
    try_to_run_init_process("/bin/sh");
    panic("No working init found");
}
'''


class B05SourceContractFixtureTests(unittest.TestCase):
    def run_fixture(self, main: str = MAIN) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "init/main.c"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(main, encoding="utf-8")
            return check(root)

    def reject(self, main: str) -> None:
        self.assertNotEqual(main, MAIN, "negative fixture mutation must change the source")
        with self.assertRaises(CheckError):
            self.run_fixture(main)

    def test_complete_fixture_passes_all_groups(self) -> None:
        self.assertEqual(len(self.run_fixture()), 8)

    def test_rejects_kthreadd_before_pid1(self) -> None:
        broken = MAIN.replace(
            "kernel_thread(kernel_init, NULL, CLONE_FS);\n    kernel_thread(kthreadd, NULL, CLONE_FS | CLONE_FILES);",
            "kernel_thread(kthreadd, NULL, CLONE_FS | CLONE_FILES);\n    kernel_thread(kernel_init, NULL, CLONE_FS);",
        )
        self.reject(broken)

    def test_rejects_schedule_before_kthreadd_completion(self) -> None:
        broken = MAIN.replace(
            "complete(&kthreadd_done);\n    schedule_preempt_disabled();",
            "schedule_preempt_disabled();\n    complete(&kthreadd_done);",
        )
        self.reject(broken)

    def test_rejects_basic_setup_before_kthreadd_wait(self) -> None:
        broken = MAIN.replace(
            "wait_for_completion(&kthreadd_done);\n    do_basic_setup();",
            "do_basic_setup();\n    wait_for_completion(&kthreadd_done);",
        )
        self.reject(broken)

    def test_rejects_missing_do_initcalls_ownership(self) -> None:
        broken = MAIN.replace("    do_initcalls();\n", "    driver_init();\n")
        self.reject(broken)

    def test_rejects_wrong_initcall_level_order(self) -> None:
        broken = MAIN.replace(
            '"subsys", "fs", "device", "late"',
            '"subsys", "device", "fs", "late"',
        )
        self.reject(broken)

    def test_rejects_unconditional_prepare_namespace(self) -> None:
        broken = MAIN.replace(
            "ramdisk_execute_command = NULL;\n        prepare_namespace();",
            "ramdisk_execute_command = NULL;\n    }\n    prepare_namespace();\n    if (0) {",
        )
        self.reject(broken)

    def test_rejects_exec_before_system_running(self) -> None:
        broken = MAIN.replace(
            "system_state = SYSTEM_RUNNING;\n\n    if (ramdisk_execute_command)",
            "if (ramdisk_execute_command)\n        run_init_process(ramdisk_execute_command);\n\n    system_state = SYSTEM_RUNNING;\n\n    if (0)",
        )
        self.reject(broken)

    def test_rejects_init_fallback_reordering(self) -> None:
        broken = MAIN.replace(
            'try_to_run_init_process("/etc/init");\n    try_to_run_init_process("/bin/init");',
            'try_to_run_init_process("/bin/init");\n    try_to_run_init_process("/etc/init");',
        )
        self.reject(broken)


if __name__ == "__main__":
    unittest.main()

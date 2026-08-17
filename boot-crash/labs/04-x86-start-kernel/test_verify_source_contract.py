#!/usr/bin/env python3
"""Fixture self-tests for the B04 Linux v5.10 source-contract checker.

These tests validate the checker itself. They do not replace running the checker
against a real Linux v5.10 source tree, nor L2/L3 build/runtime evidence.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_source_contract import CheckError, check


HEAD64 = r'''
static void __init copy_bootdata(char *real_mode_data)
{
    memcpy(&boot_params, real_mode_data, sizeof(boot_params));
    sanitize_boot_params(&boot_params);
    cmd_line_ptr = get_cmd_line_ptr();
    memcpy(boot_command_line, command_line, COMMAND_LINE_SIZE);
    sme_unmap_bootdata(real_mode_data);
}

asmlinkage __visible void __init x86_64_start_kernel(char *real_mode_data)
{
    idt_setup_early_handler();
    copy_bootdata(__va(real_mode_data));
    x86_64_start_reservations(real_mode_data);
}

void __init x86_64_start_reservations(char *real_mode_data)
{
    if (!boot_params.hdr.version)
        copy_bootdata(__va(real_mode_data));
    x86_early_init_platform_quirks();
    start_kernel();
}
'''

MAIN = r'''
static void __init mm_init(void)
{
    mem_init();
    kmem_cache_init();
    vmalloc_init();
}

void __init __weak arch_call_rest_init(void)
{
    rest_init();
}

asmlinkage __visible void __init __no_sanitize_address start_kernel(void)
{
    local_irq_disable();
    early_boot_irqs_disabled = true;
    setup_arch(&command_line);
    build_all_zonelists(NULL);
    page_alloc_init();
    mm_init();
    sched_init();
    rcu_init();
    early_irq_init();
    init_IRQ();
    tick_init();
    init_timers();
    hrtimers_init();
    softirq_init();
    timekeeping_init();
    early_boot_irqs_disabled = false;
    local_irq_enable();
    arch_call_rest_init();
}
'''

SETUP = r'''
void __init setup_arch(char **cmdline_p)
{
}
'''


class B04SourceContractFixtureTests(unittest.TestCase):
    def run_fixture(self, overrides: dict[str, str] | None = None) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "arch/x86/kernel/head64.c": HEAD64,
                "init/main.c": MAIN,
                "arch/x86/kernel/setup.c": SETUP,
            }
            if overrides:
                files.update(overrides)
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            return check(root)

    def reject(self, overrides: dict[str, str]) -> None:
        with self.assertRaises(CheckError):
            self.run_fixture(overrides)

    def test_complete_fixture_passes_all_groups(self) -> None:
        self.assertEqual(len(self.run_fixture()), 7)

    def test_rejects_bootdata_unmap_before_command_line_copy(self) -> None:
        broken = HEAD64.replace(
            "memcpy(boot_command_line, command_line, COMMAND_LINE_SIZE);\n    sme_unmap_bootdata(real_mode_data);",
            "sme_unmap_bootdata(real_mode_data);\n    memcpy(boot_command_line, command_line, COMMAND_LINE_SIZE);",
        )
        self.reject({"arch/x86/kernel/head64.c": broken})

    def test_rejects_start_kernel_before_platform_quirks(self) -> None:
        broken = HEAD64.replace(
            "x86_early_init_platform_quirks();\n    start_kernel();",
            "start_kernel();\n    x86_early_init_platform_quirks();",
        )
        self.reject({"arch/x86/kernel/head64.c": broken})

    def test_rejects_setup_arch_outside_start_kernel(self) -> None:
        broken = MAIN.replace("    setup_arch(&command_line);\n", "")
        self.reject({"init/main.c": broken})

    def test_rejects_irq_software_flag_before_local_irq_disable(self) -> None:
        broken = MAIN.replace(
            "local_irq_disable();\n    early_boot_irqs_disabled = true;",
            "early_boot_irqs_disabled = true;\n    local_irq_disable();",
        )
        self.reject({"init/main.c": broken})

    def test_rejects_irq_enable_before_timekeeping(self) -> None:
        broken = MAIN.replace(
            "timekeeping_init();\n    early_boot_irqs_disabled = false;\n    local_irq_enable();",
            "early_boot_irqs_disabled = false;\n    local_irq_enable();\n    timekeeping_init();",
        )
        self.reject({"init/main.c": broken})

    def test_rejects_vmalloc_before_slab_initialization(self) -> None:
        broken = MAIN.replace(
            "kmem_cache_init();\n    vmalloc_init();",
            "vmalloc_init();\n    kmem_cache_init();",
        )
        self.reject({"init/main.c": broken})

    def test_rejects_rest_init_boundary_loss(self) -> None:
        broken = MAIN.replace("    rest_init();\n", "    kernel_init();\n")
        self.reject({"init/main.c": broken})


if __name__ == "__main__":
    unittest.main()

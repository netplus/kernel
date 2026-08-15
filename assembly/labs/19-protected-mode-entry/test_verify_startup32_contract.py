#!/usr/bin/env python3
"""Self-tests for verify_startup32_contract.py.

These tests do not replace running the checker against a Linux v5.10 checkout.
They verify that the checker accepts the intended source ordering and rejects
important ordering/contract regressions instead of silently passing.
"""

import importlib.util
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "verify_startup32_contract", HERE / "verify_startup32_contract.py"
)
CHECKER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CHECKER)


HEAD_OK = r"""
.code32
SYM_FUNC_START(startup_32)
        cld
        cli
        lgdt    (%eax)
        movl    $__BOOT_DS, %eax
        movl    %eax, %ds
        movl    %eax, %es
        movl    %eax, %fs
        movl    %eax, %gs
        movl    %eax, %ss
        leal    rva(boot_stack_end)(%ebp), %esp
        call    verify_cpu
        testl   %eax, %eax
        jnz     .Lno_longmode
        movl    %cr4, %eax
        orl     $0x20, %eax
        movl    %eax, %cr4
"""

VERIFY_OK = r"""
SYM_FUNC_START_LOCAL(verify_cpu)
        pushf
        push    $0
        popf
        nop
.Lverify_cpu_no_longmode:
        popf
        movl $1,%eax
        ret
.Lverify_cpu_sse_ok:
        popf
        xorl %eax, %eax
        ret
SYM_FUNC_END(verify_cpu)
"""


class Startup32ContractTests(unittest.TestCase):
    def test_accepts_expected_contract(self):
        checks = CHECKER.check_text(HEAD_OK, VERIFY_OK)
        self.assertGreaterEqual(len(checks), 9)

    def test_rejects_lgdt_after_segment_reload(self):
        bad = HEAD_OK.replace(
            "        lgdt    (%eax)\n        movl    $__BOOT_DS, %eax\n",
            "        movl    $__BOOT_DS, %eax\n        movl    %eax, %ds\n        lgdt    (%eax)\n",
        ).replace(
            "        movl    %eax, %ds\n        movl    %eax, %es\n",
            "        movl    %eax, %es\n",
            1,
        )
        with self.assertRaises(AssertionError):
            CHECKER.check_text(bad, VERIFY_OK)

    def test_rejects_segment_reload_order_change(self):
        bad = HEAD_OK.replace(
            "        movl    %eax, %fs\n        movl    %eax, %gs\n",
            "        movl    %eax, %gs\n        movl    %eax, %fs\n",
        )
        with self.assertRaises(AssertionError):
            CHECKER.check_text(bad, VERIFY_OK)

    def test_rejects_boot_stack_after_verify_cpu(self):
        bad = HEAD_OK.replace(
            "        leal    rva(boot_stack_end)(%ebp), %esp\n        call    verify_cpu\n",
            "        call    verify_cpu\n        leal    rva(boot_stack_end)(%ebp), %esp\n",
        )
        with self.assertRaises(AssertionError):
            CHECKER.check_text(bad, VERIFY_OK)

    def test_rejects_cr4_preparation_before_verify_result_test(self):
        bad = HEAD_OK.replace(
            "        testl   %eax, %eax\n        jnz     .Lno_longmode\n        movl    %cr4, %eax\n        orl     $0x20, %eax\n        movl    %eax, %cr4\n",
            "        movl    %cr4, %eax\n        orl     $0x20, %eax\n        movl    %eax, %cr4\n        testl   %eax, %eax\n        jnz     .Lno_longmode\n",
        )
        with self.assertRaises(AssertionError):
            CHECKER.check_text(bad, VERIFY_OK)

    def test_rejects_missing_failure_flags_restore(self):
        bad = VERIFY_OK.replace(
            ".Lverify_cpu_no_longmode:\n        popf\n        movl $1,%eax\n",
            ".Lverify_cpu_no_longmode:\n        nop\n        movl $1,%eax\n",
        )
        with self.assertRaises(AssertionError):
            CHECKER.check_text(HEAD_OK, bad)

    def test_rejects_missing_success_flags_restore(self):
        bad = VERIFY_OK.replace(
            ".Lverify_cpu_sse_ok:\n        popf\n        xorl %eax, %eax\n",
            ".Lverify_cpu_sse_ok:\n        nop\n        xorl %eax, %eax\n",
        )
        with self.assertRaises(AssertionError):
            CHECKER.check_text(HEAD_OK, bad)

    def test_rejects_wrong_failure_value(self):
        bad = VERIFY_OK.replace("        movl $1,%eax\n", "        movl $2,%eax\n")
        with self.assertRaises(AssertionError):
            CHECKER.check_text(HEAD_OK, bad)

    def test_rejects_wrong_success_value(self):
        bad = VERIFY_OK.replace("        xorl %eax, %eax\n", "        movl $2,%eax\n")
        with self.assertRaises(AssertionError):
            CHECKER.check_text(HEAD_OK, bad)


if __name__ == "__main__":
    unittest.main()

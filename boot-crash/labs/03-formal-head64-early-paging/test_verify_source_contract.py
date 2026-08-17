#!/usr/bin/env python3
"""Positive/negative fixture tests for the B03 L1 source-contract checker."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_source_contract import CheckError, check


HEAD_S = """SYM_CODE_START_NOALIGN(startup_64)
# 64bit mode with an identity mapped page table
# %rsi holds a physical pointer to real_mode_data
call verify_cpu
call __startup_64
addq $(early_top_pgt - __START_KERNEL_map), %rax
SYM_CODE_END(startup_64)
1:
addq phys_base(%rip), %rax
call sev_verify_cbit
movq %rax, %cr3
movq $1f, %rax
jmp *%rax
lgdt early_gdt_descr(%rip)
movq initial_stack(%rip), %rsp
call early_setup_idt
pushq $0
popfq
movq %rsi, %rdi
lretq
SYM_DATA(initial_code, .quad x86_64_start_kernel)
SYM_CODE_START(secondary_startup_64)
call __startup_secondary_64
addq $(init_top_pgt - __START_KERNEL_map), %rax
# secondary_startup_64_no_verify is only used by SEV-ES guests
SYM_CODE_END(secondary_startup_64)
"""

HEAD_C = """unsigned long __head __startup_64(unsigned long physaddr, struct boot_params *bp)
{
load_delta = physaddr - (unsigned long)(_text - __START_KERNEL_map);
if (load_delta & ~PMD_PAGE_MASK) return 0;
fixup_pointer(&early_top_pgt, physaddr);
fixup_pointer(early_dynamic_pgts[0], physaddr);
x = __PAGE_KERNEL_LARGE_EXEC & ~_PAGE_GLOBAL;
fixup_long(&phys_base, physaddr) += load_delta - sme_get_me_mask();
return sme_get_me_mask();
}
/* 5-level paging is detected and enabled at kernel decomression
 * stage.
 * Only check if it has been enabled there.
 */
"""

PGTABLE_TYPES = "#define EARLY_DYNAMIC_PAGE_TABLES 64\n"


def make_tree(root: Path, overrides: dict[str, str] | None = None) -> None:
    files = {
        "arch/x86/kernel/head_64.S": HEAD_S,
        "arch/x86/kernel/head64.c": HEAD_C,
        "arch/x86/include/asm/pgtable_64_types.h": PGTABLE_TYPES,
    }
    files.update(overrides or {})
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class SourceContractTests(unittest.TestCase):
    def run_tree(self, overrides: dict[str, str] | None = None) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root, overrides)
            return check(root)

    def reject(self, overrides: dict[str, str]) -> None:
        with self.assertRaises(CheckError):
            self.run_tree(overrides)

    def test_accepts_complete_contract(self) -> None:
        self.assertEqual(len(self.run_tree()), 6)

    def test_rejects_missing_formal_entry_contract(self) -> None:
        self.reject({
            "arch/x86/kernel/head_64.S": HEAD_S.replace(
                "identity mapped page table", "temporary mapping"
            )
        })

    def test_rejects_wrong_load_delta_formula(self) -> None:
        self.reject({
            "arch/x86/kernel/head64.c": HEAD_C.replace(
                "physaddr - (unsigned long)(_text - __START_KERNEL_map)",
                "physaddr - (unsigned long)_text",
            )
        })

    def test_rejects_wrong_sme_return(self) -> None:
        self.reject({
            "arch/x86/kernel/head64.c": HEAD_C.replace(
                "return sme_get_me_mask();", "return physaddr;", 1
            )
        })

    def test_rejects_cr3_after_virtual_target_setup(self) -> None:
        self.reject({
            "arch/x86/kernel/head_64.S": HEAD_S.replace(
                "movq %rax, %cr3\nmovq $1f, %rax",
                "movq $1f, %rax\nmovq %rax, %cr3",
            )
        })

    def test_rejects_wrong_initial_code_target(self) -> None:
        self.reject({
            "arch/x86/kernel/head_64.S": HEAD_S.replace(
                "x86_64_start_kernel", "other_start_kernel"
            )
        })

    def test_rejects_ap_using_bsp_top_page_table(self) -> None:
        self.reject({
            "arch/x86/kernel/head_64.S": HEAD_S.replace(
                "$(init_top_pgt - __START_KERNEL_map)",
                "$(early_top_pgt - __START_KERNEL_map)",
            )
        })

    def test_rejects_wrong_early_dynamic_pool_size(self) -> None:
        self.reject({
            "arch/x86/include/asm/pgtable_64_types.h":
                "#define EARLY_DYNAMIC_PAGE_TABLES 32\n"
        })


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Fixture tests for the B01 Linux boot-protocol source checker."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_source_contract import CheckError, check


HEADER = r'''
        .ascii  "HdrS"
        .word   0x020f
'''

BOOTPARAM = r'''
#define E820_MAX_ENTRIES_ZEROPAGE 128
struct setup_header { unsigned char dummy; };
struct boot_params {
        unsigned char e820_entries;                 /* 0x1e8 */
        unsigned char sentinel;                     /* 0x1ef */
        struct setup_header hdr; /* setup header */ /* 0x1f1 */
        unsigned char e820_table[1];                /* 0x2d0 */
};
'''

MAIN = r'''
struct boot_params_type { int hdr; } boot_params;
int hdr;
void copy_boot_params(void)
{
        BUILD_BUG_ON(sizeof(boot_params) != 4096);
        memcpy(&boot_params.hdr, &hdr, sizeof(hdr));
}
void main(void)
{
        copy_boot_params();
        validate_cpu();
        set_bios_mode();
        detect_memory();
        set_video();
        go_to_protected_mode();
}
'''

FILES = {
    "arch/x86/boot/header.S": HEADER,
    "arch/x86/include/uapi/asm/bootparam.h": BOOTPARAM,
    "arch/x86/boot/main.c": MAIN,
}


def make_tree(root: Path, overrides: dict[str, str] | None = None) -> None:
    files = dict(FILES)
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

    def assert_rejected(self, overrides: dict[str, str]) -> None:
        with self.assertRaises(CheckError):
            self.run_tree(overrides)

    def test_accepts_complete_contract(self) -> None:
        passed = self.run_tree()
        self.assertEqual(len(passed), 11)

    def test_rejects_wrong_protocol_version(self) -> None:
        self.assert_rejected({"arch/x86/boot/header.S": HEADER.replace("0x020f", "0x020e")})

    def test_rejects_missing_hdrs_signature(self) -> None:
        self.assert_rejected({"arch/x86/boot/header.S": HEADER.replace('"HdrS"', '"Bad!"')})

    def test_rejects_single_abi_offset_drift(self) -> None:
        self.assert_rejected({
            "arch/x86/include/uapi/asm/bootparam.h": BOOTPARAM.replace("/* 0x2d0 */", "/* 0x2d8 */")
        })

    def test_rejects_wrong_e820_capacity(self) -> None:
        self.assert_rejected({
            "arch/x86/include/uapi/asm/bootparam.h": BOOTPARAM.replace(
                "E820_MAX_ENTRIES_ZEROPAGE 128", "E820_MAX_ENTRIES_ZEROPAGE 127"
            )
        })

    def test_rejects_missing_4k_contract(self) -> None:
        self.assert_rejected({
            "arch/x86/boot/main.c": MAIN.replace(
                "BUILD_BUG_ON(sizeof(boot_params) != 4096);", ""
            )
        })

    def test_rejects_missing_header_copy(self) -> None:
        self.assert_rejected({
            "arch/x86/boot/main.c": MAIN.replace(
                "memcpy(&boot_params.hdr, &hdr, sizeof(hdr));", ""
            )
        })

    def test_rejects_setup_main_order_regression(self) -> None:
        bad = MAIN.replace(
            "        detect_memory();\n        set_video();",
            "        set_video();\n        detect_memory();",
        )
        self.assert_rejected({"arch/x86/boot/main.c": bad})


if __name__ == "__main__":
    unittest.main()

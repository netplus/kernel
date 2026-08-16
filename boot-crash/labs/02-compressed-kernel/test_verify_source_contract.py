#!/usr/bin/env python3
"""Fixture tests for the B02 compressed-kernel L1 source/build checker."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_source_contract import CheckError, check


MAKEFILE = r"""
KBUILD_CFLAGS += -fPIE -ffreestanding -fno-stack-protector
LDFLAGS_vmlinux += -pie
vmlinux-objs-$(CONFIG_RANDOMIZE_BASE) += kaslr.o
ifdef CONFIG_X86_NEED_RELOCS
quiet_cmd_relocs = RELOCS  $@
      cmd_relocs = arch/x86/tools/relocs $< > vmlinux.relocs
endif
"""

HEAD = r"""
SYM_FUNC_START(startup_32)
    call extract_kernel
SYM_FUNC_END(startup_32)
SYM_FUNC_START(startup_64)
    call extract_kernel
SYM_FUNC_END(startup_64)
"""

MISC = r"""
unsigned long extract_kernel(void *rmode)
{
    unsigned long needed_size;
    boot_params = rmode;
    needed_size = max_t(unsigned long, output_len, kernel_total_size);
    choose_random_location();
    __decompress();
    parse_elf();
    handle_relocations();
    return 0;
}
"""

KASLR = r"""
enum mem_avoid_index {
    MEM_AVOID_ZO_RANGE,
    MEM_AVOID_INITRD,
    MEM_AVOID_CMDLINE,
    MEM_AVOID_BOOTPARAMS,
};
"""

FILES = {
    "arch/x86/boot/compressed/Makefile": MAKEFILE,
    "arch/x86/boot/compressed/head_64.S": HEAD,
    "arch/x86/boot/compressed/misc.c": MISC,
    "arch/x86/boot/compressed/kaslr.c": KASLR,
}


def write_tree(root: Path, overrides: dict[str, str] | None = None) -> None:
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
            write_tree(root, overrides)
            return check(root)

    def assert_rejected(self, overrides: dict[str, str]) -> None:
        with self.assertRaises(CheckError):
            self.run_tree(overrides)

    def test_accepts_complete_contract(self) -> None:
        self.assertEqual(len(self.run_tree()), 10)

    def test_rejects_missing_fpie(self) -> None:
        self.assert_rejected({"arch/x86/boot/compressed/Makefile": MAKEFILE.replace("-fPIE ", "")})

    def test_rejects_missing_ffreestanding(self) -> None:
        self.assert_rejected({"arch/x86/boot/compressed/Makefile": MAKEFILE.replace("-ffreestanding ", "")})

    def test_rejects_broken_kaslr_config_boundary(self) -> None:
        self.assert_rejected({"arch/x86/boot/compressed/Makefile": MAKEFILE.replace("vmlinux-objs-$(CONFIG_RANDOMIZE_BASE)", "vmlinux-objs-y")})

    def test_rejects_broken_relocation_config_boundary(self) -> None:
        self.assert_rejected({"arch/x86/boot/compressed/Makefile": MAKEFILE.replace("ifdef CONFIG_X86_NEED_RELOCS", "ifdef CONFIG_OTHER")})

    def test_rejects_wrong_needed_size_contract(self) -> None:
        self.assert_rejected({"arch/x86/boot/compressed/misc.c": MISC.replace("max_t(unsigned long, output_len, kernel_total_size)", "output_len")})

    def test_rejects_wrong_extract_kernel_order(self) -> None:
        bad = MISC.replace("    __decompress();\n    parse_elf();", "    parse_elf();\n    __decompress();")
        self.assert_rejected({"arch/x86/boot/compressed/misc.c": bad})

    def test_rejects_missing_bootparams_avoidance(self) -> None:
        self.assert_rejected({"arch/x86/boot/compressed/kaslr.c": KASLR.replace("    MEM_AVOID_BOOTPARAMS,\n", "")})


if __name__ == "__main__":
    unittest.main()

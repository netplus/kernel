#!/usr/bin/env python3
"""Positive and negative fixture tests for verify_source_ownership.py."""

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from verify_source_ownership import CheckError, check


FILES = {
    "arch/x86/boot/main.c": "void main(void) {}\n",
    "arch/x86/boot/compressed/head_64.S": "startup_64:\n",
    "arch/x86/boot/compressed/misc.c": "void extract_kernel(void) {}\n",
    "arch/x86/kernel/head_64.S": "startup_64:\n",
    "arch/x86/kernel/head64.c":
        "void x86_64_start_kernel(void) {}\n"
        "void x86_64_start_reservations(void) {}\n",
    "init/main.c":
        "void start_kernel(void) {}\n"
        "static noinline void __ref rest_init(void) { "
        "kernel_thread(kernel_init, NULL, 0); }\n"
        "static int __ref kernel_init(void *unused) { return 0; }\n"
        "static int run_init_process(const char *init_filename) { return 0; }\n",
}


def make_tree(root: Path, overrides=None) -> None:
    data = dict(FILES)
    data.update(overrides or {})
    for rel, content in data.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class SourceOwnershipTests(unittest.TestCase):
    def run_tree(self, overrides=None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root, overrides)
            # Keep unittest output focused on accept/reject behavior rather
            # than the checker's PASS lines.
            with redirect_stdout(StringIO()):
                check(root)

    def test_accepts_complete_contract(self):
        self.run_tree()

    def test_rejects_missing_setup_main(self):
        with self.assertRaises(CheckError):
            self.run_tree({"arch/x86/boot/main.c":
                           "int other(void) { return 0; }\n"})

    def test_requires_compressed_startup64_independently(self):
        with self.assertRaises(CheckError):
            self.run_tree({"arch/x86/boot/compressed/head_64.S": "other:\n"})

    def test_requires_formal_startup64_independently(self):
        with self.assertRaises(CheckError):
            self.run_tree({"arch/x86/kernel/head_64.S": "other:\n"})

    def test_rejects_missing_extract_kernel(self):
        with self.assertRaises(CheckError):
            self.run_tree({"arch/x86/boot/compressed/misc.c":
                           "void other(void) {}\n"})

    def test_rejects_missing_arch_c_handoff(self):
        with self.assertRaises(CheckError):
            self.run_tree({"arch/x86/kernel/head64.c":
                           "void x86_64_start_kernel(void) {}\n"})

    def test_rejects_missing_pid1_creation_boundary(self):
        bad = FILES["init/main.c"].replace(
            "kernel_thread(kernel_init, NULL, 0);", "")
        with self.assertRaises(CheckError):
            self.run_tree({"init/main.c": bad})

    def test_rejects_missing_exec_boundary(self):
        bad = FILES["init/main.c"].replace(
            "static int run_init_process(const char *init_filename) "
            "{ return 0; }\n", "")
        with self.assertRaises(CheckError):
            self.run_tree({"init/main.c": bad})


if __name__ == "__main__":
    unittest.main()

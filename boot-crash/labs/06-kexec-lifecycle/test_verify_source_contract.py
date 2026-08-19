#!/usr/bin/env python3
"""Self-tests for the B06 Linux v5.10 source-contract checker.

The fixtures test the checker itself. They are tool evidence, not a
substitute for running verify_source_contract.py against a real v5.10 tree.
The positive fixtures deliberately mirror the relevant upstream v5.10
function signatures, control-page dispatch, and normal/crash destination-slot
ordering.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_source_contract import CheckError, check


TRADITIONAL = r'''
#define KEXEC_ON_CRASH 0x1
SYSCALL_DEFINE4(kexec_load, unsigned long, entry, unsigned long, nr_segments,
                struct kexec_segment __user *, segments, unsigned long, flags)
{
    if (flags & KEXEC_ON_CRASH) { }
    return do_kexec_load(entry, nr_segments, segments, flags);
}
static int kimage_alloc_init(struct kimage **rimage, unsigned long entry,
                             unsigned long nr_segments,
                             struct kexec_segment __user *segments,
                             unsigned long flags)
{
    bool kexec_on_panic = flags & KEXEC_ON_CRASH;
    struct kimage *image;
    if (!kexec_on_panic)
        image->swap_page = kimage_alloc_control_pages(image, 0);
    *rimage = image;
    return 0;
}
static int do_kexec_load(unsigned long entry, unsigned long nr_segments,
                         struct kexec_segment __user *segments, unsigned long flags)
{
    struct kimage **dest_image;
    struct kimage *image;
    if (flags & KEXEC_ON_CRASH)
        dest_image = &kexec_crash_image;
    else
        dest_image = &kexec_image;
    machine_kexec_prepare(image);
    image = xchg(dest_image, image);
    return 0;
}
'''

FILE_LOAD = r'''
#define KEXEC_FILE_ON_CRASH 0x2
static int kimage_file_alloc_init(struct kimage **rimage, int kernel_fd,
                                  int initrd_fd, const char *cmdline_ptr,
                                  unsigned long cmdline_len,
                                  unsigned long flags)
{
    bool kexec_on_panic = flags & KEXEC_FILE_ON_CRASH;
    struct kimage *image;
    if (!kexec_on_panic)
        image->swap_page = kimage_alloc_control_pages(image, 0);
    *rimage = image;
    return 0;
}
SYSCALL_DEFINE5(kexec_file_load, int, kernel_fd, int, initrd_fd,
                unsigned long, cmdline_len, const char __user *, cmdline_ptr,
                unsigned long, flags)
{
    struct kimage **dest_image;
    struct kimage *image;
    dest_image = &kexec_image;
    if (flags & KEXEC_FILE_ON_CRASH)
        dest_image = &kexec_crash_image;
    machine_kexec_prepare(image);
    image = xchg(dest_image, image);
    return 0;
}
'''

CORE = r'''
int sanity_check_segment_list(struct kimage *image)
{
    if (image->type == KEXEC_TYPE_CRASH) {
        if (image->segment[0].mem < crashk_res.start)
            return -EADDRNOTAVAIL;
        if (image->segment[0].mem + image->segment[0].memsz - 1 > crashk_res.end)
            return -EADDRNOTAVAIL;
    }
    return 0;
}
struct page *kimage_alloc_control_pages(struct kimage *image, unsigned int order)
{
    struct page *pages = NULL;
    switch (image->type) {
    case KEXEC_TYPE_DEFAULT:
        pages = kimage_alloc_normal_control_pages(image, order);
        break;
    case KEXEC_TYPE_CRASH:
        pages = kimage_alloc_crash_control_pages(image, order);
        break;
    }
    return pages;
}
'''

X86 = r'''
int machine_kexec_prepare(struct kimage *image)
{
    return init_pgtable(image, image->control_code_page);
}
/*
 * Do not allocate memory (or fail in any way) in machine_kexec().
 * We are past the point of no return, committed to rebooting now.
 */
void machine_kexec(struct kimage *image)
{
    relocate_kernel();
}
'''


class B06CheckerTests(unittest.TestCase):
    def run_tree(self, overrides: dict[str, str] | None = None) -> list[str]:
        files = {
            "kernel/kexec.c": TRADITIONAL,
            "kernel/kexec_file.c": FILE_LOAD,
            "kernel/kexec_core.c": CORE,
            "arch/x86/kernel/machine_kexec_64.c": X86,
        }
        files.update(overrides or {})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            return check(root)

    def reject(self, overrides: dict[str, str]) -> None:
        with self.assertRaises(CheckError):
            self.run_tree(overrides)

    def test_complete_fixture_passes_all_contracts(self) -> None:
        self.assertEqual(len(self.run_tree()), 7)

    def test_rejects_file_api_without_crash_purpose(self) -> None:
        self.reject({"kernel/kexec_file.c": FILE_LOAD.replace("KEXEC_FILE_ON_CRASH", "FILE_CRASH_FLAG")})

    def test_rejects_missing_persistent_image_install(self) -> None:
        self.reject({"kernel/kexec.c": TRADITIONAL.replace("image = xchg(dest_image, image);", "image = *dest_image;")})

    def test_rejects_file_missing_persistent_image_install(self) -> None:
        self.reject({"kernel/kexec_file.c": FILE_LOAD.replace("image = xchg(dest_image, image);", "image = *dest_image;")})

    def test_rejects_missing_crash_reserved_range_end(self) -> None:
        self.reject({"kernel/kexec_core.c": CORE.replace("crashk_res.end", "ULONG_MAX")})

    def test_rejects_shared_control_page_allocator(self) -> None:
        self.reject({"kernel/kexec_core.c": CORE.replace("pages = kimage_alloc_crash_control_pages(image, order);", "pages = kimage_alloc_normal_control_pages(image, order);")})

    def test_rejects_crash_swap_page_allocation(self) -> None:
        self.reject({"kernel/kexec.c": TRADITIONAL.replace("if (!kexec_on_panic)\n        image->swap_page", "if (kexec_on_panic)\n        image->swap_page")})

    def test_rejects_file_crash_swap_page_allocation(self) -> None:
        self.reject({"kernel/kexec_file.c": FILE_LOAD.replace("if (!kexec_on_panic)\n        image->swap_page", "if (kexec_on_panic)\n        image->swap_page")})

    def test_rejects_prepare_after_install(self) -> None:
        self.reject({"kernel/kexec.c": TRADITIONAL.replace("machine_kexec_prepare(image);\n    image = xchg(dest_image, image);", "image = xchg(dest_image, image);\n    machine_kexec_prepare(image);")})

    def test_rejects_file_prepare_after_install(self) -> None:
        self.reject({"kernel/kexec_file.c": FILE_LOAD.replace("machine_kexec_prepare(image);\n    image = xchg(dest_image, image);", "image = xchg(dest_image, image);\n    machine_kexec_prepare(image);")})

    def test_rejects_prepare_without_transition_pgtable(self) -> None:
        self.reject({"arch/x86/kernel/machine_kexec_64.c": X86.replace("return init_pgtable(image, image->control_code_page);", "return 0;")})

    def test_rejects_missing_point_of_no_return_contract(self) -> None:
        self.reject({"arch/x86/kernel/machine_kexec_64.c": X86.replace("past the point of no return", "final transition begins here")})


if __name__ == "__main__":
    unittest.main()

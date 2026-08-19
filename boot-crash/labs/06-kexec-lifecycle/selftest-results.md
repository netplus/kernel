# B06 source-contract checker self-test execution record

This file records **tool execution evidence** for the B06 checker fixtures. It is not Linux v5.10 L1 source evidence and must not be used as a substitute for running `verify_source_contract.py` against a real upstream Linux v5.10 checkout.

## 1. Upstream v5.10 revalidation after checker correction

The current B06 checker was corrected after re-reading upstream Linux v5.10 Kexec sources. The correction aligned the checker/fixture model with the real v5.10 source shape, including these facts:

```text
kernel/kexec.c
  kimage_alloc_init() returns int and returns the image through
  struct kimage **rimage.

kernel/kexec_file.c
  kimage_file_alloc_init() likewise returns int through an out-parameter.
  kexec_file_load() initializes dest_image to &kexec_image and overrides it
  with &kexec_crash_image when KEXEC_FILE_ON_CRASH is set.

kernel/kexec_core.c
  sanity_check_segment_list() is a global int function in upstream v5.10,
  not a static function.

arch/x86/kernel/machine_kexec_64.c
  the "Do not allocate memory ... point of no return" comment appears
  immediately before machine_kexec(), not inside the function body.
```

These facts were rechecked against upstream Linux v5.10 source during the maintenance run that corrected the checker. They are source facts, not conclusions imported from a secondary web source.

## 2. Earlier 9-test execution is historical tool evidence

An earlier revision of the checker/fixture pair was materialized together in an isolated Python environment and executed with:

```bash
python3 -m unittest -v test_verify_source_contract.py
```

The observed result for that earlier revision was:

```text
test_complete_fixture_passes_all_contracts ... ok
test_rejects_crash_swap_page_allocation ... ok
test_rejects_file_api_without_crash_purpose ... ok
test_rejects_missing_crash_reserved_range_end ... ok
test_rejects_missing_persistent_image_install ... ok
test_rejects_missing_point_of_no_return_contract ... ok
test_rejects_prepare_after_install ... ok
test_rejects_prepare_without_transition_pgtable ... ok
test_rejects_shared_control_page_allocator ... ok

Ran 9 tests

OK
```

Process exit code: `0`.

This remains useful historical evidence that the fixture framework itself can execute, but **it must not be described as a PASS for the current corrected checker/fixture pair**. The checker and positive fixture were subsequently changed to match upstream Linux v5.10 more precisely, so the current pair requires a fresh execution.

## 3. Current exact-pair status

The repository currently contains:

```text
boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py
boot-crash/labs/06-kexec-lifecycle/test_verify_source_contract.py
```

The current fixture suite still represents:

```text
1 complete positive fixture
8 targeted negative fixtures
7 B06 source-contract groups
```

But after the upstream-v5.10-driven checker/fixture correction, the exact current pair has **not yet obtained a directly observed unittest PASS** in an environment that can execute the repository files unchanged.

Therefore the current evidence status is:

```text
current fixture source present:                         yes
current corrected checker source present:               yes
historical earlier-revision 9/9 PASS observed:          yes
current corrected exact-pair self-test executed:        no
current corrected exact-pair PASS observed:             no
current corrected exact-pair unittest PASS count:       not established
current corrected exact-pair unittest exit code:        not established
manual upstream Linux v5.10 source revalidation:        yes
automated checker against full upstream v5.10 tree:     no
matching-vmlinux L2 executed:                            no
Kexec/Kdump VM L3 executed:                              no
```

## 4. Why the distinction matters

A fixture PASS is tied to the exact checker and fixture revisions that were executed. Once either file changes, an older PASS cannot automatically be carried forward.

This matters especially here because the corrections were not cosmetic: they changed the checker model to match real upstream Linux v5.10 function signatures and source ordering. Treating the earlier 9/9 result as proof for the corrected pair would create false provenance and could hide a regression introduced by the correction itself.

Likewise, even a fresh current-pair fixture PASS would only be **tool evidence**. The real Linux v5.10 L1 acceptance still requires running the checker against a complete upstream v5.10 source tree, or equivalently verifying every contract directly against that tree.

## 5. CI path and cost boundary

The repository contains:

```text
.github/workflows/boot-crash-b06-selftest.yml
```

which is intended to checkout the repository and run the fixture suite against exact committed files. However, a workflow definition is not a PASS result by itself.

The project currently has no additional runner budget. Do not solve this evidence gap by assuming a paid GitHub-hosted runner. Prefer, in order:

```text
1. an already available local execution environment;
2. a jointly configured self-hosted GitHub Actions runner;
3. another zero-new-cost environment that executes the exact committed files.
```

Any runner used for repository automation should have explicit permissions, isolation, labels and workspace cleanup policy.

## 6. Next acceptance action

The next B06 acceptance unit is deliberately narrow:

```text
A. execute the current exact checker/fixture pair unchanged;
B. require 9 tests, OK, exit code 0;
C. execute verify_source_contract.py against a complete upstream Linux v5.10 tree;
D. require all 7 source-contract groups to PASS;
E. only then update README.md / expected-analysis.md to restore PASS status.
```

If either A/B or C/D fails, the failure itself becomes the next correction unit. Do not bypass it by weakening the checker or by copying conclusions from online material.

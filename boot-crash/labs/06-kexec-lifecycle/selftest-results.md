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

The observed result for that earlier revision was 9 tests, `OK`, exit code `0`. That result remains useful historical evidence, but it is not used as proof for the corrected pair because the checker and positive fixture subsequently changed to match upstream v5.10 more precisely.

## 3. Current corrected exact-pair execution

The current repository pair is:

```text
boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py
boot-crash/labs/06-kexec-lifecycle/test_verify_source_contract.py
```

During the current maintenance run, both files were fetched from the repository and materialized in an isolated local execution directory. Before running the suite, the materialized bytes were verified using Git's blob-object hash rule:

```text
verify_source_contract.py
  repository blob SHA: cd38c6c849d8c1d33449b4d01f0039c0de23c1bc
  materialized blob SHA: cd38c6c849d8c1d33449b4d01f0039c0de23c1bc

 test_verify_source_contract.py
  repository blob SHA: 74dc63d9e4bba24c5278224513b5a640be267478
  materialized blob SHA: 74dc63d9e4bba24c5278224513b5a640be267478
```

The exact-pair suite was then executed with:

```bash
python3 -m unittest -v test_verify_source_contract.py
```

Observed result:

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

A Python-environment spreadsheet-runtime warmup emitted an unrelated diagnostic before unittest output. It did not change the unittest process result; all nine B06 tests completed and the process returned `0`.

Therefore the current exact checker/fixture pair now has direct tool-execution evidence:

```text
current fixture source present:                         yes
current corrected checker source present:               yes
current corrected exact-pair self-test executed:        yes
current corrected exact-pair PASS observed:             yes
current corrected exact-pair unittest PASS count:       9/9
current corrected exact-pair unittest exit code:        0
manual upstream Linux v5.10 source revalidation:        yes
automated checker against full upstream v5.10 tree:     not yet established
matching-vmlinux L2 executed:                            no
Kexec/Kdump VM L3 executed:                              no
```

## 4. Why the distinction still matters

The current fixture PASS is tied to the exact blob pair listed above. If either checker or fixture changes, this PASS must not be carried forward automatically; a fresh execution is required.

Likewise, fixture PASS is only **tool evidence**. It proves that the checker accepts the current complete synthetic contract and rejects all eight targeted regressions. It does not itself prove that all seven contracts match a complete upstream Linux v5.10 tree.

The real Linux v5.10 L1 acceptance still requires running the same checker against a complete upstream v5.10 source tree. The correction points have already been manually revalidated against upstream v5.10 source, but full-tree automated PASS remains a separate evidence item.

## 5. CI path and cost boundary

The repository contains:

```text
.github/workflows/boot-crash-b06-selftest.yml
```

which can checkout the repository and run the fixture suite against committed files. The current exact-pair PASS, however, was obtained in the already available local execution environment, so no paid GitHub-hosted runner was required.

The project currently has no additional runner budget. For future repository automation prefer, in order:

```text
1. an already available local execution environment;
2. a jointly configured self-hosted GitHub Actions runner;
3. another zero-new-cost environment that executes exact committed files.
```

Any runner used for repository automation should have explicit permissions, isolation, labels and workspace cleanup policy.

## 6. Next acceptance action

The exact-pair tool-evidence half of the B06 acceptance gate is now complete. The remaining narrow acceptance unit is:

```text
A. execute verify_source_contract.py against a complete upstream Linux v5.10 tree;
B. require all 7 source-contract groups to PASS;
C. record the exact upstream tag/commit and checker blob SHA used;
D. only then proceed to B06 completion review.
```

If the full-tree L1 checker fails, that failure itself becomes the next correction unit. Do not weaken the checker or substitute a secondary online conclusion for upstream v5.10 source evidence.

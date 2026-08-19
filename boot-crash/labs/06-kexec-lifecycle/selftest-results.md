# B06 source-contract checker self-test execution record

This file records **tool execution evidence** for the B06 checker fixtures. It is not Linux v5.10 L1 source evidence and must not be used as a substitute for running `verify_source_contract.py` against upstream Linux v5.10 source.

## 1. Upstream v5.10 correction history

The B06 checker has been repeatedly corrected by going back to upstream Linux v5.10 source rather than preserving assumptions from fixtures or secondary material.

Already-established v5.10 corrections include:

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

A further upstream-v5.10 check found another concrete checker defect:

```text
kernel/kexec_core.c
  kimage_alloc_control_pages() dispatches with:

    switch (image->type) {
    case KEXEC_TYPE_DEFAULT:
        ... kimage_alloc_normal_control_pages(...)
        break;
    case KEXEC_TYPE_CRASH:
        ... kimage_alloc_crash_control_pages(...)
        break;
    }

  It is not written as:

    if (image->type == KEXEC_TYPE_CRASH)
        ...
```

The checker now verifies the real `switch (image->type)` / `case KEXEC_TYPE_CRASH:` source shape, and the positive fixture mirrors that v5.10 dispatch.

## 2. Historical exact-pair PASS evidence

Before the latest control-page-dispatch correction, the then-current checker/fixture blobs were executed exactly and produced:

```text
Ran 9 tests
OK
exit code 0
```

That result is retained only as historical tool evidence. It **does not transfer** to the checker/fixture pair after the `switch (image->type)` correction.

The superseded blob pair was:

```text
verify_source_contract.py
  cd38c6c849d8c1d33449b4d01f0039c0de23c1bc

test_verify_source_contract.py
  74dc63d9e4bba24c5278224513b5a640be267478
```

## 3. Current checker/fixture revision

The latest repository revisions are now based on the upstream v5.10 control-page dispatcher:

```text
verify_source_contract.py
  current blob after correction: 5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py
  current blob after correction: 5a3b4d41f0a0b9c46575904431136f26cc46ab5d
```

The current exact pair has **not yet been re-executed after this correction**. Therefore the current evidence state is:

```text
current checker source present:                         yes
current fixture source present:                         yes
current exact-pair self-test after latest correction:   not yet executed
current exact-pair PASS after latest correction:        not established
current exact-pair PASS count:                          not established
current exact-pair exit code:                           not established
manual upstream-v5.10 source revalidation:              yes
full upstream-v5.10 automated L1 checker PASS:           not established
matching-vmlinux L2 executed:                            no
Kexec/Kdump VM L3 executed:                              no
```

Do not copy the earlier 9/9 result into the current revision without executing these exact blobs.

## 4. Upstream v5.10 source audit recorded on 2026-08-19

The source facts used by the current checker were re-audited against the upstream `v5.10` tag itself, not against a secondary article or a later kernel version.

The tag resolves to:

```text
upstream repository: torvalds/linux
ref:                 v5.10
commit:              2c85ebc57b3e1817b6ce1a6b703928e113a90442
commit subject:      Linux 5.10
```

The four source blobs read for B06 were:

```text
kernel/kexec.c
  c82c6c06f0518f3591de33431904d60175e69bc2

kernel/kexec_file.c
  e21f6b9234f7a2dbcfe17df61d1611b5d3bbb9d7

kernel/kexec_core.c
  8798a8183974e3b3d52ac53dc4b981f4055f0b52

arch/x86/kernel/machine_kexec_64.c
  a29a44a98e5bef10751af769bd198d783e23b9fd
```

The audit reconfirmed the checker model:

```text
1. kexec_load and kexec_file_load are distinct load APIs; each has a
   crash-purpose flag in the v5.10 source.

2. both load paths select persistent normal/crash image slots and install
   the prepared image with xchg(); the textual order of slot selection is
   not identical between the two loaders.

3. sanity_check_segment_list() constrains KEXEC_TYPE_CRASH segment
   destinations to the crashk_res range.

4. kimage_alloc_control_pages() dispatches on image->type with a switch and
   uses kimage_alloc_crash_control_pages() for KEXEC_TYPE_CRASH.

5. kimage_alloc_init() and kimage_file_alloc_init() allocate swap_page only
   when !kexec_on_panic.

6. machine_kexec_prepare(image) occurs in both load paths before the image
   is installed into the persistent destination slot.

7. x86-64 machine_kexec_prepare() calls init_pgtable(); the source then
   states the point-of-no-return rule immediately before machine_kexec().
```

This is **manual L1 source revalidation**, not an automated checker PASS. It is recorded separately so a source-reading result cannot be mistaken for execution evidence.

An attempt to materialize a complete `v5.10` checkout in the current local execution environment with:

```text
git clone --depth 1 --branch v5.10 https://github.com/torvalds/linux.git ...
```

failed because that execution environment could not resolve `github.com`. The GitHub connector could still read the exact upstream tag and source blobs listed above, so the source audit itself was not blocked; only the planned end-to-end CLI run on a materialized checkout remains blocked in this environment.

## 5. Why the latest correction matters

The old contract checked:

```text
image->type == KEXEC_TYPE_CRASH
```

inside `kimage_alloc_control_pages()`.

That condition does not exist in upstream Linux v5.10 because the function uses a `switch` statement. A checker that requires the equality expression would reject the real v5.10 file even though the underlying design conclusion—crash images use `kimage_alloc_crash_control_pages()`—is correct.

This is exactly the type of failure the course rules require us to fix: implementation facts must follow upstream v5.10 source shape, not a synthetic fixture or a remembered equivalent implementation.

## 6. CI and cost boundary

The repository contains:

```text
.github/workflows/boot-crash-b06-selftest.yml
```

The workflow originally used `runs-on: ubuntu-latest`, which conflicted with the project's no-additional-runner-budget constraint. It has now been corrected to:

```text
workflow_dispatch only
runs-on: [self-hosted, linux, x64, kernel-course]
```

This is intentional. The B06 exact-suite CI path must not silently consume potentially billable GitHub-hosted runner minutes. Until a matching self-hosted runner is registered, this workflow is an execution path but not execution evidence.

Preferred execution order remains:

```text
1. an already available local execution environment;
2. a jointly configured self-hosted GitHub Actions runner with the
   self-hosted/linux/x64/kernel-course labels;
3. another zero-new-cost environment that executes exact committed files.
```

A self-hosted runner must be treated as infrastructure: use a dedicated low-privilege account or VM where practical, restrict repository access, keep the `kernel-course` label explicit, and clean the work directory between jobs. Do not expose unrelated credentials to course test jobs.

## 7. Repeated execution attempt on 2026-08-19

A fresh attempt was made from the current local execution environment to fetch the **exact committed checker and fixture** plus the four upstream Linux `v5.10` source files needed by the checker. The intended sequence was:

```text
curl -fsSL https://raw.githubusercontent.com/netplus/kernel/main/boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py ...
curl -fsSL https://raw.githubusercontent.com/netplus/kernel/main/boot-crash/labs/06-kexec-lifecycle/test_verify_source_contract.py ...
curl -fsSL https://raw.githubusercontent.com/torvalds/linux/v5.10/kernel/kexec.c ...
curl -fsSL https://raw.githubusercontent.com/torvalds/linux/v5.10/kernel/kexec_file.c ...
curl -fsSL https://raw.githubusercontent.com/torvalds/linux/v5.10/kernel/kexec_core.c ...
curl -fsSL https://raw.githubusercontent.com/torvalds/linux/v5.10/arch/x86/kernel/machine_kexec_64.c ...
python3 -m unittest -v test_verify_source_contract.py
python3 verify_source_contract.py <materialized-v5.10-tree>
```

The first network operation failed before any test could start:

```text
curl: (6) Could not resolve host: raw.githubusercontent.com
```

This independently reproduces the earlier DNS/network limitation seen for `github.com`. It is an **execution-environment blocker**, not a checker failure and not a Linux v5.10 source failure. Therefore this run must not record either 9/9 fixture PASS or 7/7 upstream-source PASS.

The GitHub connector remains able to read repository content and upstream `v5.10` source, so source review and repository maintenance can continue. What remains unavailable here is a filesystem-materialized exact revision that Python can execute end to end.

When an execution-capable zero-new-cost environment is available, use the exact current blobs already recorded above and require both commands to return exit code 0 before changing the evidence state to PASS.

## 8. Next acceptance action

The next minimum acceptance unit remains two-part and must use the latest corrected checker:

```text
A. execute the exact current checker/fixture pair;
   require 9 tests, OK, exit code 0;

B. execute the same checker against a materialized upstream Linux v5.10
   checkout at commit 2c85ebc57b3e1817b6ce1a6b703928e113a90442;
   require all 7 source-contract groups to PASS;

C. record the checker blob SHA, fixture blob SHA and upstream v5.10 commit;

D. if either A or B fails, make that concrete failure the next correction unit.
```

Do not weaken the checker merely to obtain PASS. First compare every failure with upstream Linux v5.10 source and correct the checker, fixture or course statement according to that source.

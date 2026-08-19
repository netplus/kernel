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
manual upstream-v5.10 control-page revalidation:        yes
full upstream-v5.10 automated L1 checker PASS:           not established
matching-vmlinux L2 executed:                            no
Kexec/Kdump VM L3 executed:                              no
```

Do not copy the earlier 9/9 result into the current revision without executing these exact blobs.

## 4. Why the latest correction matters

The old contract checked:

```text
image->type == KEXEC_TYPE_CRASH
```

inside `kimage_alloc_control_pages()`.

That condition does not exist in upstream Linux v5.10 because the function uses a `switch` statement. A checker that requires the equality expression would reject the real v5.10 file even though the underlying design conclusion—crash images use `kimage_alloc_crash_control_pages()`—is correct.

This is exactly the type of failure the course rules require us to fix: implementation facts must follow upstream v5.10 source shape, not a synthetic fixture or a remembered equivalent implementation.

## 5. CI and cost boundary

The repository contains:

```text
.github/workflows/boot-crash-b06-selftest.yml
```

for exact committed fixture execution. The project has no additional runner budget. Prefer, in order:

```text
1. an already available local execution environment;
2. a jointly configured self-hosted GitHub Actions runner;
3. another zero-new-cost environment that executes exact committed files.
```

Do not silently switch to a potentially billable GitHub-hosted runner merely to obtain this evidence.

## 6. Next acceptance action

The next minimum acceptance unit is now two-part and must use the latest corrected checker:

```text
A. execute the exact current checker/fixture pair;
   require 9 tests, OK, exit code 0;

B. execute the same checker against upstream Linux v5.10 source;
   require all 7 source-contract groups to PASS;

C. record the checker blob SHA and upstream v5.10 ref used;

D. if either A or B fails, make that concrete failure the next correction unit.
```

Do not weaken the checker merely to obtain PASS. First compare every failure with upstream Linux v5.10 source and correct the checker, fixture or course statement according to that source.

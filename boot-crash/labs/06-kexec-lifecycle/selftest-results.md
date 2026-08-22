# B06 source-contract checker self-test execution record

This file records **tool execution evidence** for the B06 checker fixtures. It is not Linux v5.10 L1 source evidence and must not be used as a substitute for running `verify_source_contract.py` against upstream Linux v5.10 source.

## 1. Upstream v5.10 correction history

The B06 checker has been repeatedly corrected by going back to upstream Linux v5.10 source rather than preserving assumptions from fixtures or secondary material.

Established corrections include:

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
  kimage_alloc_control_pages() dispatches with switch (image->type), with a
  KEXEC_TYPE_CRASH case using kimage_alloc_crash_control_pages().

arch/x86/kernel/machine_kexec_64.c
  the "Do not allocate memory ... point of no return" comment appears
  immediately before machine_kexec(), not inside the function body.
```

## 2. Historical exact-pair PASS evidence

Before the later upstream-v5.10 checker corrections and fixture expansion, an older checker/fixture pair was executed exactly and produced:

```text
Ran 9 tests
OK
exit code 0
```

That result is retained only as historical tool evidence. It **does not transfer** to the current checker/fixture revision.

The superseded blob pair was:

```text
verify_source_contract.py
  cd38c6c849d8c1d33449b4d01f0039c0de23c1bc

test_verify_source_contract.py
  74dc63d9e4bba24c5278224513b5a640be267478
```

## 3. Current checker/fixture revision

Current repository blobs at this record update:

```text
verify_source_contract.py
  5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py
  f18918cfbe0b01ffba59be3ac083a9971295a2f8
```

The fixture now contains **22 unittest cases: 1 complete positive case plus 21 negative regression cases**. The current exact pair has not yet been executed in an environment that can materialize the committed files, so the evidence state is:

```text
current checker source present:                         yes
current fixture source present:                         yes
current fixture case count:                             22 (1 positive + 21 negative)
current exact-pair self-test:                           not yet executed
current exact-pair PASS:                                not established
current exact-pair exit code:                           not established
manual upstream-v5.10 source revalidation:              yes
full upstream-v5.10 automated L1 checker PASS:           not established
matching-vmlinux L2 executed:                            no
Kexec/Kdump VM L3 executed:                              no
```

Do not copy the historical 9-test result into the current 22-case revision.

## 4. Current negative-coverage matrix

The 21 negative cases are now sufficient to close the fixture-expansion subtask. They exercise each compound contract at the level where the checker makes an independent assertion:

```text
Contract 1: load API vs image purpose
  traditional crash-purpose flag missing
  file-loader crash-purpose flag missing

Contract 2: persistent image ownership
  traditional xchg install missing
  file-loader xchg install missing
  traditional crash destination slot missing
  traditional normal destination slot missing
  file-loader crash destination slot missing
  file-loader normal destination slot missing

Contract 3: crashk_res destination constraint
  crashk_res.start constraint missing
  crashk_res.end constraint missing
  crash-type guard inverted/missing semantically

Contract 4: control-page allocation policy
  image->type switch dispatch broken
  KEXEC_TYPE_CRASH case missing
  crash-specific allocator replaced by normal allocator

Contract 5: swap_page only for non-crash images
  traditional loader allocates swap_page for crash image
  file loader allocates swap_page for crash image

Contract 6: architecture prepare before persistent install
  traditional prepare moved after xchg
  file-loader prepare moved after xchg

Contract 7: x86 transition preparation and no-return boundary
  init_pgtable preparation missing
  point-of-no-return contract text missing
  point-of-no-return contract moved after machine_kexec definition
```

This matrix is a **checker-regression coverage statement**, not proof that the checker accepts real upstream source. No further synthetic fixture expansion should be performed merely to increase case count. The next acceptance work is execution of the current exact suite and then execution against upstream v5.10.

## 5. Upstream v5.10 source audit

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

A fresh repository-API audit on 2026-08-22 fetched these four paths explicitly at commit `2c85ebc57b3e1817b6ce1a6b703928e113a90442` and reconfirmed the same blob identities. This matters because it independently checks that the manual source baseline has not drifted while local Git/DNS access remains unavailable. It is still **source-provenance evidence, not execution evidence**: the connector fetch does not create a local Git worktree on which `verify_source_contract.py` can be executed.

The audit reconfirmed the checker model:

```text
1. kexec_load and kexec_file_load are distinct load APIs; each has a
   crash-purpose flag in the v5.10 source.
2. both load paths select persistent normal/crash image slots and install
   the prepared image with xchg(); textual slot-selection order differs.
3. sanity_check_segment_list() constrains KEXEC_TYPE_CRASH segment
   destinations to the crashk_res range.
4. kimage_alloc_control_pages() switches on image->type and uses the crash
   allocator for KEXEC_TYPE_CRASH.
5. kimage_alloc_init() and kimage_file_alloc_init() allocate swap_page only
   when !kexec_on_panic.
6. machine_kexec_prepare(image) occurs in both load paths before persistent
   installation.
7. x86-64 machine_kexec_prepare() calls init_pgtable(); the source states
   the point-of-no-return rule immediately before machine_kexec().
```

This is **manual L1 source revalidation**, not an automated checker PASS.

## 6. Execution-environment blocker and cost boundary

Attempts to materialize the exact files from the current local execution environment have failed at DNS resolution for `github.com` / `raw.githubusercontent.com`. This is an execution-environment blocker, not a checker failure and not a Linux v5.10 source failure. The GitHub connector can read exact repository files (including the upstream files above at a pinned commit) and update course content, but it does not expose those fetched files as a local Git filesystem tree to the acceptance script.

The repository workflow `.github/workflows/boot-crash-b06-selftest.yml` is intentionally `workflow_dispatch` only and targets `[self-hosted, linux, x64, kernel-course]`. Do not silently switch it to a potentially billable GitHub-hosted runner. Preferred execution order is an already available local environment, then a dedicated low-privilege self-hosted runner, then another zero-new-cost environment capable of executing exact committed files.

The current workflow is itself part of the acceptance boundary. Before it can establish B06 PASS evidence, it now enforces all of the following:

```text
runner prerequisites:
  actual uname platform must be Linux on x86-64 (x86_64/amd64)
  Git >= 2.18
  Python >= 3.9
  git, python3, uname, grep, tee, mktemp and rm must all be available
  RUNNER_TEMP must be non-empty, absolute, an existing directory, and not '/'
  prerequisite failures occur before checkout/test evidence is produced

run identity and serialization:
  workflow_dispatch establishes the selected GITHUB_SHA
  checked-out course HEAD must equal that GITHUB_SHA
  concurrency group boot-crash-b06-selftest serializes evidence-producing runs
  cancel-in-progress is false, so a queued manual run does not cancel an
  already-running validation

course provenance:
  clean course checkout
  checker committed blob == 5c89b67628cf55560089656d5b65e80ff74c556f
  fixture committed blob == f18918cfbe0b01ffba59be3ac083a9971295a2f8
  worktree blobs == committed blobs
  post-execution HEAD/clean checks run only if this run's course checkout
  succeeded, so a checkout failure cannot inspect a stale persistent worktree

fixture evidence:
  unittest command exits successfully
  output states exactly "Ran 22 tests ..."
  output contains a standalone "OK"

upstream provenance:
  torvalds/linux is materialized with native Git under RUNNER_TEMP, not as a
  nested course checkout
  checkout is pinned to 2c85ebc57b3e1817b6ce1a6b703928e113a90442
  git rev-parse HEAD must equal that commit before and after checker execution
  upstream worktree must be clean before and after checker execution

upstream L1 evidence:
  checker exits successfully
  exactly seven PASS group lines are present
  PASS groups 1 through 7 are each present
  final summary is "PASS: 7 B06 Linux v5.10 source-contract groups"

persistent-runner hygiene:
  checkout credentials are not persisted
  checkout does not add safe.directory entries to global Git config
  the only removable upstream scratch object is the exact path reconstructed
    from RUNNER_TEMP + GITHUB_RUN_ID + GITHUB_RUN_ATTEMPT:
    $RUNNER_TEMP/kernel-course-b06-linux-v5.10-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT
  prepare removes only that exact path before publishing B06_UPSTREAM_DIR
  cleanup independently reconstructs the same exact path; if a published
    B06_UPSTREAM_DIR differs byte-for-byte, cleanup refuses rm -rf
  cleanup can reconstruct the exact path even when preparation failed before
    B06_UPSTREAM_DIR was published
  cleanup treats both existing paths and symbolic links (-e or -L) as removable
    inputs, then asserts that neither a path nor a dangling symlink remains
  temporary upstream checkout is removed on success or failure
  final course HEAD must still equal GITHUB_SHA and its worktree must be clean
```

The cleanup rule above is an **exact-path identity gate**, not a glob/prefix namespace check. A damaged value with an injected suffix or path-traversal component is not authorized merely because its string begins with the B06 scratch prefix.

The workflow uses a full-SHA-pinned `actions/checkout` revision rather than a mutable major-version tag. These controls make a future workflow PASS attributable to a specific dispatch-selected course commit, the actual checked-out course commit, a specific checker/fixture pair, and a specific upstream Linux source revision. They **do not constitute execution evidence by themselves**; until a real run produces the required outputs, the current 22/22 and upstream 7/7 states remain unestablished.

## 7. Next acceptance action

Fixture coverage review is now closed. The next minimum acceptance unit is execution, not more synthetic cases:

```text
A. materialize the exact current blobs above;
B. run python3 -m unittest -v test_verify_source_contract.py;
   require 22 tests, OK, exit code 0;
C. run the same verify_source_contract.py against upstream Linux v5.10
   commit 2c85ebc57b3e1817b6ce1a6b703928e113a90442;
   require all 7 source-contract groups to PASS;
D. record dispatch GITHUB_SHA, checked-out course HEAD, checker blob SHA,
   fixture blob SHA, upstream commit and outputs;
E. if either execution fails, make that concrete failure the next correction
   unit and resolve it against upstream v5.10 source before changing claims.
```

Do not weaken the checker merely to obtain PASS.
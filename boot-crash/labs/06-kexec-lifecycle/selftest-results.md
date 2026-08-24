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

The fixture contains **22 unittest cases: 1 complete positive case plus 21 negative regression cases**. The current exact pair has not yet been executed in an environment that can materialize the committed files, so the evidence state is:

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

The 21 negative cases close the fixture-expansion subtask. They exercise each compound contract at the level where the checker makes an independent assertion:

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

The source facts used by the current checker were re-audited against the upstream `v5.10` tag itself.

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

The latest independent audit is recorded in [`upstream-source-audit-2026-08-24.md`](upstream-source-audit-2026-08-24.md). It reconfirmed the checker model, including crash-purpose selection, persistent normal/crash slots, `crashk_res` destination constraints, crash-specific control-page allocation, non-crash-only `swap_page`, architecture preparation before persistent installation, and x86-64 transition identity mappings. This remains **manual L1 source revalidation**, not automated checker PASS evidence.

## 6. Execution-environment blocker and cost boundary

Attempts to materialize exact Git worktrees in the current execution environment have failed at DNS resolution for GitHub. This is an execution-environment blocker, not a checker failure and not a Linux v5.10 source failure. The repository workflow `.github/workflows/boot-crash-b06-selftest.yml` remains `workflow_dispatch` only and targets `[self-hosted, linux, x64, kernel-course]`; do not silently switch it to a potentially billable GitHub-hosted runner.

The workflow acceptance boundary currently includes:

```text
runner prerequisites:
  Linux x86-64; Git >= 2.18; Python >= 3.9
  required shell tools present, including mkdir for owned scratch creation
  RUNNER_TEMP is a non-root, existing, absolute, non-symlink, CR/LF-free,
    canonical physical directory path
  GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT are positive decimal integers

course provenance:
  checkout Action pinned to a full SHA
  checked-out HEAD == GITHUB_SHA and worktree clean
  checker blob == 5c89b67628cf55560089656d5b65e80ff74c556f
  fixture blob == f18918cfbe0b01ffba59be3ac083a9971295a2f8

fixture evidence:
  unittest exits successfully
  output states exactly "Ran 22 tests ..."
  output contains standalone "OK"

upstream provenance and evidence:
  exact upstream commit 2c85ebc57b3e1817b6ce1a6b703928e113a90442
  clean upstream worktree before and after checker
  exactly seven PASS group lines and final 7-group PASS summary
```

### Persistent-runner scratch ownership contract

Path identity and object ownership are separate conditions. A path that can be reconstructed from run identity is **not** automatically owned by the current run, and publishing a path name is not by itself sufficient to establish ownership of a filesystem object.

The current workflow therefore uses this fail-closed contract:

```text
1. Prepare computes exactly:
   $RUNNER_TEMP/kernel-course-b06-linux-v5.10-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT

2. If that exact path already exists, including as a dangling symbolic link,
   prepare fails immediately and does not delete it.
   A pre-existing object is a runner-hygiene/ownership blocker, not evidence
   that the current run may reclaim it.

3. After confirming absence, prepare creates the exact directory with mkdir.
   It then verifies that the new object is a directory and not a symbolic link.

4. Only after successful creation and validation does prepare publish
   B06_UPSTREAM_DIR through GITHUB_ENV. Publication propagates ownership of
   the object that this run has already created; it does not create ownership
   merely by naming a path.

5. The always() cleanup step independently revalidates RUNNER_TEMP and run
   identity, then reconstructs the same exact expected path.

6. If B06_UPSTREAM_DIR was never published, cleanup has no completed ownership
   evidence and refuses deletion, even though it can reconstruct the expected
   name. This also covers prepare failures before or during mkdir/validation.

7. If B06_UPSTREAM_DIR was published but differs byte-for-byte from the
   independently reconstructed path, cleanup refuses deletion.

8. Only established object ownership plus published propagation plus
   exact-path identity authorizes rm -rf. After deletion, cleanup asserts that
   neither a path nor dangling symlink remains.
```

This supersedes the older evidence wording that treated publication immediately after an absence check as ownership establishment. The current contract is stronger: **create → validate → publish**. It also continues to supersede still older wording that allowed prepare to remove a pre-existing exact path or cleanup to delete an unpublished path merely because the run identity could reconstruct its name.

The canonical-physical-path condition remains stronger than checking only `! -L "$RUNNER_TEMP"`: it also rejects a scratch root reached through a symlinked parent or a logical path containing `.`/`..` whose byte string differs from the filesystem's physical canonical path. Because cleanup runs under `always()`, destructive-root and run-identity validation are repeated inside cleanup rather than inherited from an earlier step.

The pinned checkout revision declares a Node 20 Action runtime. The dependency audit establishes that metadata identity; only a real workflow run can establish compatibility with the selected self-hosted runner. A runtime incompatibility is a runner prerequisite failure, not fixture or Linux v5.10 source-contract failure.

These controls do **not** constitute execution evidence by themselves. Until a real run produces the required outputs, current 22/22 and upstream 7/7 PASS remain unestablished.

## 7. Next acceptance action

Fixture coverage review is closed. The next minimum acceptance unit is execution:

```text
A. materialize the exact current checker/fixture blobs;
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

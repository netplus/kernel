# B06 source-contract checker self-test execution record

This file records **tool execution evidence** for the B06 checker fixtures. It is not Linux v5.10 L1 source evidence and must not be used as a substitute for running `verify_source_contract.py` against upstream Linux v5.10 source.

## 1. Current exact acceptance target

Current repository blobs are:

```text
verify_source_contract.py
  5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py
  f18918cfbe0b01ffba59be3ac083a9971295a2f8
```

The fixture contains **22 unittest cases: 1 complete positive case plus 21 negative regression cases**. Current acceptance still requires:

```text
fixture:  Ran 22 tests / OK / exit code 0
upstream: Linux v5.10 commit
          2c85ebc57b3e1817b6ce1a6b703928e113a90442
          7/7 source-contract groups PASS
```

Current evidence state:

```text
current checker source present:                         yes
current fixture source present:                         yes
current fixture case count:                             22 (1 positive + 21 negative)
current exact 22-case self-test PASS:                    not established
manual upstream-v5.10 source revalidation:              yes
full upstream-v5.10 automated L1 checker PASS:           not established
matching-vmlinux L2 executed:                            no
Kexec/Kdump VM L3 executed:                              no
```

## 2. Historical real workflow evidence

A real GitHub Actions run has been re-audited:

```text
run id:       32230874907
run date:     2026-08-19
workflow:     boot-crash B06 checker self-test
event:        push
course SHA:   4cb6c9b6c9d870ab037e75fb2c9c9d80a25e4284
runner:       GitHub-hosted Ubuntu 24.04
conclusion:   success
fixture run:  Ran 9 tests / OK
```

At that exact course revision the blobs were:

```text
verify_source_contract.py
  5c89b67628cf55560089656d5b65e80ff74c556f

test_verify_source_contract.py
  5a3b4d41f0a0b9c46575904431136f26cc46ab5d
```

This is stronger than the older superseded-pair note because it proves that the **current checker blob** has in fact executed successfully in a real GitHub Actions job. However, it executed with the historical 9-case fixture, not the current 22-case fixture. That run also did not execute the current upstream-v5.10 7-group source checker.

Therefore the permitted claim is narrowly scoped:

> current checker blob + historical 9-case fixture: real workflow PASS established.

The following claims remain forbidden until new execution evidence exists:

```text
current checker + current 22-case fixture: PASS
current exact-pair 22/22: PASS
upstream v5.10 automated 7/7: PASS
B06 complete / ready for B07
```

The historical run used a GitHub-hosted runner. It is retained only as pre-existing evidence and does not authorize current acceptance to switch back to a potentially billable hosted runner.

### Historical failure immediately before the 9-case PASS

The preceding real workflow run `32230850551` is also useful execution evidence and has now been re-audited from its job log rather than inferred from commit history:

```text
run id:       32230850551
run date:     2026-08-19
course SHA:   8434c3176fd27e9a607a34c6de6506c8130814c6
runner:       GitHub-hosted Ubuntu 24.04
conclusion:   failure
fixture run:  Ran 9 tests / FAILED (errors=1)
failed test:  test_complete_fixture_passes_all_contracts
checker error:
  missing contract: control-page type dispatch
```

The traceback shows the failure came from the check for the Linux-v5.10-shaped control-page dispatch:

```text
switch (image->type)
```

The eight negative tests in that historical fixture still passed; the complete positive fixture alone failed because it did not yet mirror the control-page `switch (image->type)` shape required by the checker. The immediately following course revision `4cb6c9b6...` updated the fixture and the real workflow became 9/9 `OK` while retaining the same current checker blob.

This failure-to-pass pair is evidence that the checker was not merely returning success unconditionally: a concrete positive-fixture drift was rejected in a real workflow and the corrected fixture subsequently passed. It remains **historical 9-case tool evidence only**. It does not prove the current 22-case fixture or the upstream-v5.10 7/7 acceptance target.

## 3. Why the fixture is now 22 cases

The 21 negative cases close the checker-regression coverage subtask. They exercise each independent assertion used by the 7 source-contract groups:

```text
Contract 1: load API vs image purpose
  traditional crash-purpose flag missing
  file-loader crash-purpose flag missing

Contract 2: persistent image ownership
  traditional/file xchg install missing
  traditional/file crash destination slot missing
  traditional/file normal destination slot missing

Contract 3: crashk_res destination constraint
  crashk_res.start missing
  crashk_res.end missing
  crash-type guard broken

Contract 4: control-page allocation policy
  image->type switch broken
  KEXEC_TYPE_CRASH case missing
  crash-specific allocator replaced

Contract 5: swap_page only for non-crash images
  traditional crash swap_page allocation
  file-loader crash swap_page allocation

Contract 6: architecture prepare before persistent install
  traditional prepare moved after xchg
  file-loader prepare moved after xchg

Contract 7: x86 transition preparation and no-return boundary
  init_pgtable missing
  point-of-no-return contract text missing
  point-of-no-return contract moved after machine_kexec
```

No further synthetic fixture expansion should be performed merely to increase case count. The next acceptance work is execution of the current exact suite and then execution against real upstream v5.10.

## 4. Upstream Linux v5.10 fact baseline

The source facts used by the checker were re-audited against upstream `v5.10`:

```text
repository: torvalds/linux
ref:        v5.10
commit:     2c85ebc57b3e1817b6ce1a6b703928e113a90442
subject:    Linux 5.10
```

Relevant source blobs:

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

The latest independent audit is recorded in [`upstream-source-audit-2026-08-24.md`](upstream-source-audit-2026-08-24.md). It remains **manual L1 source revalidation**, not automated checker PASS evidence.

## 5. Pinned checkout Action: provenance versus runtime

The current self-hosted workflow pins:

```text
actions/checkout@11d5960a326750d5838078e36cf38b85af677262
```

The dependency audit establishes that this revision corresponds to checkout v4.4.0 and its `action.yml` declares `runs.using: node20`.

The real historical run `32230874907` adds an important runtime fact: its runner log states that Node 20 was deprecated and the Action was **forced to run with Node 24 by the runner**, while checkout completed successfully.

Therefore `node20` is an Action metadata/provenance fact, not a sufficient statement of the runtime a future runner will actually select. The valid self-hosted prerequisite is:

> the selected GitHub Actions runner must be able to execute this pinned checkout Action under its actual runner/runtime policy.

If checkout fails because of runner version, Action runtime policy, or runtime compatibility, classify that as a **runner / Action-runtime prerequisite failure**. Do not classify it as a B06 fixture failure or Linux v5.10 source-contract failure.

## 6. Current self-hosted acceptance contract

The repository workflow remains `workflow_dispatch` only and targets:

```text
[self-hosted, linux, x64, kernel-course]
```

Do not silently switch it to a potentially billable GitHub-hosted runner.

Runner and execution prerequisites include:

```text
Linux x86-64
Git >= 2.18
Python >= 3.9
required shell tools present
RUNNER_TEMP is non-root, existing, absolute, non-symlink, CR/LF-free,
and equal to its pwd -P canonical physical path
GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT are positive decimal integers
trusted/isolated runner deployment whose RUNNER_TEMP namespace cannot be
mutated by untrusted local principals during the job
pinned checkout Action executable under the runner's actual Action-runtime policy
```

Course provenance gates require:

```text
checked-out HEAD == GITHUB_SHA
course worktree clean before and after evidence production
checker committed/worktree blob == 5c89b67628cf55560089656d5b65e80ff74c556f
fixture committed/worktree blob == f18918cfbe0b01ffba59be3ac083a9971295a2f8
```

Fixture evidence gates require:

```text
unittest command succeeds
output states exactly Ran 22 tests ...
output contains standalone OK
```

Upstream provenance/evidence gates require:

```text
exact upstream commit 2c85ebc57b3e1817b6ce1a6b703928e113a90442
clean upstream worktree before and after checker
exactly seven numbered PASS group lines
final PASS: 7 B06 Linux v5.10 source-contract groups
```

These controls define what a valid future run must prove. They do **not** constitute current execution evidence by themselves.

## 7. Persistent-runner scratch ownership and cleanup

Path identity, object ownership, child mode, and parent namespace trust are separate conditions.

The workflow uses this fail-closed model:

```text
1. derive one run-specific scratch path from RUNNER_TEMP + run id + attempt;
2. if an object already exists there, fail and never reclaim it as this run's own;
3. umask 077 and mkdir the exact directory;
4. install a prepare-local EXIT trap after successful mkdir;
5. verify non-symlink directory and exact mode 0700;
6. publish B06_UPSTREAM_DIR only after successful validation;
7. disarm the local trap after publication;
8. final always() cleanup independently revalidates destructive-root and run identity;
9. final cleanup requires published ownership plus exact-path identity before rm -rf.
```

The prepare-local trap may reclaim an unpublished object only because the same shell just created it after an absence check. Later steps must never infer ownership merely from a predictable path name. A pre-existing object remains a runner-hygiene blocker.

Mode `0700` is defense in depth inside a trusted runner deployment; it does not make arbitrary hostile shared-host execution safe.

## 8. Execution-environment blocker and next acceptance action

The current local execution environment has repeatedly failed to materialize exact Git worktrees because GitHub DNS resolution fails. That is an infrastructure blocker, not a checker or Linux source failure.

The next minimum acceptance unit remains execution:

```text
A. materialize the exact current course revision/checker/fixture;
B. run the 22-case fixture suite and require 22 tests / OK / exit 0;
C. materialize upstream v5.10 commit
   2c85ebc57b3e1817b6ce1a6b703928e113a90442;
D. run the same checker and require all 7 source-contract groups PASS;
E. record course SHA, checker blob, fixture blob, upstream commit and outputs;
F. if execution fails, make that concrete failure the next correction unit.
```

Do not weaken the checker merely to obtain PASS.

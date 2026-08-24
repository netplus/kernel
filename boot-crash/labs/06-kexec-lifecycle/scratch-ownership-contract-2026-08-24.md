# B06 self-hosted scratch ownership contract correction

This note corrects the persistent-runner hygiene wording in `selftest-results.md` for the current B06 workflow. It is an execution/provenance contract note, not Linux v5.10 source evidence and not a substitute for the required 22/22 fixture run or upstream 7/7 source-contract run.

## Problem being corrected

The older evidence wording conflates two different properties:

```text
path identity   = the workflow can deterministically compute the path name
object ownership = this workflow attempt is authorized to delete the object at that path
```

For a persistent self-hosted runner, deterministic naming alone does not prove ownership. A pre-existing file, directory, mount point, or symbolic link at the computed path may belong to an earlier failed run, an administrator, or another process. Deleting it merely because its name matches the expected B06 path is not a valid ownership rule.

The current `.github/workflows/boot-crash-b06-selftest.yml` therefore uses a fail-closed ownership contract.

## Current contract

The scratch path is derived from:

```text
$RUNNER_TEMP/kernel-course-b06-linux-v5.10-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT
```

Before this path is used, the workflow independently validates the runner scratch root and run identity. `RUNNER_TEMP` must be a non-root existing absolute non-symlink directory, contain no CR/LF, and equal its canonical physical path from `pwd -P`; `GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT` must be positive decimal integers.

Preparation then follows this rule:

```text
computed path absent
  -> publish B06_UPSTREAM_DIR
  -> later materialization may create the upstream Git tree

computed path already exists, including a dangling symlink
  -> fail preparation
  -> do not delete the pre-existing object
  -> do not publish B06_UPSTREAM_DIR
```

Publishing `B06_UPSTREAM_DIR` is therefore the workflow's ownership declaration: preparation first observed the exact path as unused, then declared that exact path as the scratch object assigned to this run attempt.

Cleanup runs under `always()`, so it must not inherit trust from earlier steps. It revalidates `RUNNER_TEMP`, canonical physical-path identity, and the positive numeric run identity. It independently reconstructs the expected path and then applies the ownership rule:

```text
B06_UPSTREAM_DIR absent
  -> no ownership declaration exists
  -> do not run rm -rf, even if the expected path can be reconstructed

B06_UPSTREAM_DIR present but byte-for-byte different from expected path
  -> refuse cleanup

B06_UPSTREAM_DIR present and exactly equal to expected path
  -> cleanup is authorized for that exact object only
  -> remove an existing path or symbolic link
  -> assert that neither an object nor dangling symlink remains
```

This means the ability to reconstruct a run-specific path is **not** deletion authority. Deletion requires both exact path identity and a successful ownership declaration from this run.

## Superseded wording

For the current workflow, the following older statements in `selftest-results.md` must not be used as the active contract:

```text
prepare removes only that exact path before publishing B06_UPSTREAM_DIR
cleanup can reconstruct the exact path even when preparation failed before
B06_UPSTREAM_DIR was published
```

The first statement is no longer true: preparation refuses a pre-existing object instead of deleting it. The second is incomplete in a security-relevant way: cleanup can reconstruct the expected **name**, but if `B06_UPSTREAM_DIR` was never published it deliberately refuses to delete the unowned object.

The current workflow file and `06-b06-completion-review.md` are authoritative for this ownership behavior. This note exists to make the evidence correction explicit until the older prose in `selftest-results.md` is consolidated directly.

## Evidence boundary

This correction improves failure isolation on a persistent self-hosted runner. It does not establish any of the B06 closing evidence:

```text
current exact fixture: 22 tests + OK + exit code 0      not established here
upstream Linux v5.10 checker: PASS groups 1..7          not established here
matching-vmlinux L2                                      not established here
Kexec/Kdump VM L3                                        not established here
```

B06 therefore remains pending automated acceptance. The next evidence-producing unit is still a real execution of the exact fixture pair and the checker against upstream Linux v5.10 commit `2c85ebc57b3e1817b6ce1a6b703928e113a90442`.
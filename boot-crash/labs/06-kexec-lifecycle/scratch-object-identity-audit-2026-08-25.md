# B06 self-hosted scratch object identity audit (2026-08-25)

This note audits one remaining boundary in `.github/workflows/boot-crash-b06-selftest.yml`: the difference between **path identity** and **filesystem-object identity** during the lifetime of the run-owned upstream scratch directory.

It is execution-safety evidence only. It is not Linux v5.10 source evidence and does not count as the required 22/22 fixture PASS or upstream 7/7 source-contract PASS.

## Current workflow facts

The workflow currently establishes the scratch directory as follows:

```text
validate RUNNER_TEMP and run identity
→ derive one exact run-specific path
→ fail if any object already occupies that path
→ umask 077
→ mkdir the exact path
→ require a non-symlink directory
→ require mode 0700
→ publish B06_UPSTREAM_DIR
```

Cleanup independently revalidates `RUNNER_TEMP` and run identity, reconstructs the exact expected path, requires the published `B06_UPSTREAM_DIR` to match it byte-for-byte, and only then permits `rm -rf`.

These checks establish strong **path provenance** and fail closed for a pre-existing object. They do not record a filesystem object identifier such as `(st_dev, st_ino)` at creation time and compare it again before deletion.

## What is and is not proved

The current contract proves that the run created an object at the expected path before publishing that path, and that cleanup is acting on the same path string derived independently from the same validated run identity.

It does **not**, by itself, prove that the directory entry still names the identical inode created by prepare. A process capable of mutating the parent `RUNNER_TEMP` namespace could theoretically rename/unlink/replace the child after publication while leaving the path string unchanged.

This is why the existing deployment assumption is a hard part of the evidence contract rather than commentary: the `kernel-course` runner must be dedicated or equivalently isolated, and untrusted local principals must not be able to mutate the `RUNNER_TEMP` namespace during the job. Under that assumption, inode replacement by an adversarial local principal is outside the accepted threat model. Mode `0700`, exact-path reconstruction and publication checks are defense in depth inside that boundary; they are not a substitute for it.

## Decision for the current B06 acceptance path

Do **not** add inode/device identity machinery merely to make the workflow appear more sophisticated. Such a change would add another cross-step state value and another failure mode without removing the need to trust the parent namespace: a principal that can arbitrarily mutate the runner's local filesystem is already outside the workflow's supported deployment model.

For B06, the independent acceptance boundary therefore remains:

```text
trusted/isolated RUNNER_TEMP parent namespace
+ run-created scratch object
+ verified non-symlink directory and mode 0700
+ published ownership propagation
+ independently reconstructed exact path identity
```

If the deployment model is later widened to an untrusted shared host, this conclusion must be revisited. At that point an inode/device check alone would still be insufficient; the runner isolation and parent-directory mutation model would need a complete redesign.

## Practical consequence

A prepare failure after `mkdir` but before `B06_UPSTREAM_DIR` publication can intentionally leave a run-created scratch directory behind, because cleanup has no published ownership evidence and refuses deletion. That stale object is a visible runner-hygiene blocker on a later attempt rather than an object the workflow silently reclaims. This behavior is fail-closed and should not be weakened to obtain a green run.

The next acceptance work remains execution of the exact current fixture and upstream-v5.10 checker on a qualifying zero-additional-cost environment. Any concrete runtime failure should become the next correction unit.
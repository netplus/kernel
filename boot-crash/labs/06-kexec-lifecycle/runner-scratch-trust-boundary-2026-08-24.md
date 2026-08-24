# B06 self-hosted runner scratch trust-boundary audit

This note records one execution-safety boundary of `.github/workflows/boot-crash-b06-selftest.yml`. It is infrastructure evidence only; it is not Linux v5.10 source evidence and does not establish the pending 22/22 fixture or upstream 7/7 PASS.

## Finding

The workflow now creates the run-specific upstream directory itself, verifies that the object is a non-symlink directory with mode `0700`, publishes the exact path only after those checks, and requires exact-path identity before cleanup.

Those controls establish privacy of the created directory's contents against ordinary access by other local users. They do **not**, by themselves, prove that an arbitrary multi-user host is safe against a hostile local user who can mutate the parent `RUNNER_TEMP` namespace.

The distinction matters because mode `0700` is checked on the child object. Whether another local principal can rename, unlink, or replace a directory entry is governed by permissions and sticky-bit semantics on its parent directory. The workflow currently validates that `RUNNER_TEMP` is an existing canonical physical non-symlink directory, but it does not validate parent ownership/mode or attempt to define a hostile-local-user threat model.

Therefore the B06 runner contract must be read as follows:

```text
required deployment assumption:
  the self-hosted runner account has exclusive administrative control of the
  selected runner instance and its RUNNER_TEMP namespace for the duration of
  the job; untrusted local principals are not allowed to mutate that namespace.

workflow-enforced controls:
  deterministic run-specific path identity;
  fail-closed handling of a pre-existing target;
  run-created scratch object before publication;
  non-symlink directory validation;
  exact mode 0700 validation;
  exact published-path identity before rm -rf;
  independent cleanup revalidation under always().
```

`0700` must not be described as making the workflow safe on an otherwise untrusted shared host. It is a defense-in-depth local-permission control inside a runner that is already assumed to be administratively trusted and isolated.

### Wording audit of the current workflow

The current `Prepare isolated upstream workspace` comment says that persistent self-hosted runners "may be multi-user" and then explains `umask 077` as keeping the scratch object private to the runner account. Read without the deployment assumption above, that wording is too broad: it can be mistaken for a claim that mode `0700` makes this job safe on an arbitrary shared host.

For B06 evidence purposes, that comment must be interpreted narrowly: `0700` protects the child directory contents from ordinary access by other local accounts **after** the runner deployment has already guaranteed that untrusted principals cannot mutate the `RUNNER_TEMP` parent namespace. A future workflow edit should replace the broad "may be multi-user" wording with this trusted-runner assumption rather than treating child mode bits as the whole isolation boundary.

This wording issue does not weaken the existing fail-closed deletion gates, but it matters for how a self-hosted runner is provisioned and reviewed. It is therefore classified as a runner deployment/evidence-contract issue, not as a Linux v5.10 source-contract issue.

## Consequence for runner setup

When a `kernel-course` self-hosted runner is provisioned, use a dedicated runner VM/guest or equivalently isolated host account and a runner-owned temporary namespace. Do not place this job on a general-purpose shared shell host where unrelated users can modify the runner's temporary parent directory.

Before treating a real B06 run as acceptance evidence, the runner deployment should satisfy all of the following:

```text
runner instance:
  dedicated to trusted kernel-course jobs, or equivalently isolated;

runner account:
  not shared with untrusted interactive workloads;

RUNNER_TEMP namespace:
  controlled by the runner deployment;
  not mutable by untrusted local principals during the job;

workflow scratch child:
  created by this run only;
  validated as a non-symlink directory;
  validated as mode 0700 before publication;
  removed only after published ownership and exact-path identity agree.
```

This is consistent with the course's cost boundary: a self-hosted runner is preferred over silently switching to a potentially billable GitHub-hosted runner, but self-hosting also makes host isolation and lifecycle cleanup part of the acceptance environment.

## Evidence boundary

This audit changes no checker contract and no Linux v5.10 implementation claim. A real workflow execution is still required to establish:

```text
current exact fixture: 22 tests + OK
upstream v5.10:         7/7 source-contract groups PASS
```

If a future workflow revision adds explicit parent-directory ownership/mode checks, this note should be revisited rather than treating the present deployment assumption as a permanent implementation guarantee.

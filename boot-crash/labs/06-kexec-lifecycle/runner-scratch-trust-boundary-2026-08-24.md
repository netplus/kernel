# B06 self-hosted runner scratch trust-boundary audit

This note records one execution-safety boundary of `.github/workflows/boot-crash-b06-selftest.yml`. It is infrastructure evidence only; it is not Linux v5.10 source evidence and does not establish the pending 22/22 fixture or upstream 7/7 PASS.

## Finding

The workflow creates the run-specific upstream directory itself, verifies that the object is a non-symlink directory with mode `0700`, publishes the exact path only after those checks, and requires exact-path identity before final cleanup.

Those controls establish privacy of the created directory's contents against ordinary access by other local users. They do **not**, by themselves, prove that an arbitrary multi-user host is safe against a hostile local user who can mutate the parent `RUNNER_TEMP` namespace.

The distinction matters because mode `0700` is checked on the child object. Whether another local principal can rename, unlink, or replace a directory entry is governed by permissions and sticky-bit semantics on its parent directory. The workflow validates that `RUNNER_TEMP` is an existing canonical physical non-symlink directory, but it deliberately does not try to derive a hostile-local-user security boundary from parent mode bits. Instead, trusted parent-namespace control is a deployment prerequisite.

Therefore the B06 runner contract is:

```text
required deployment assumption:
  the self-hosted runner account has exclusive administrative control of the
  selected runner instance and its RUNNER_TEMP namespace for the duration of
  the job; untrusted local principals are not allowed to mutate that namespace.

workflow-enforced controls:
  deterministic run-specific path identity;
  fail-closed handling of a pre-existing target;
  run-created scratch object before publication;
  prepare-local cleanup of a run-created object if validation/publication fails;
  non-symlink directory validation;
  exact mode 0700 validation;
  exact published-path identity before final rm -rf;
  independent cleanup revalidation under always().
```

`0700` must not be described as making the workflow safe on an otherwise untrusted shared host. It is a defense-in-depth local-permission control inside a runner that is already assumed to be administratively trusted and isolated.

### Wording audit of the current workflow

The earlier workflow wording said that persistent self-hosted runners "may be multi-user" and could be read too broadly. That wording has since been corrected. The current `Prepare isolated upstream workspace` comment now states directly that the job assumes a **trusted, isolated self-hosted runner whose `RUNNER_TEMP` namespace cannot be mutated by untrusted local users**, and describes `0700` as defense in depth.

The workflow, B06 completion review, and `selftest-results.md` therefore now express the same deployment boundary. This audit must not retain the superseded claim that the current workflow still needs that wording correction.

This deployment assumption is a runner/evidence-contract property, not a Linux v5.10 source-contract property.

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
  if created but not yet published, reclaimable only by the creating prepare shell;
  after publication, removable only when published ownership and exact-path
  identity agree in the final cleanup step.
```

This is consistent with the course's cost boundary: a self-hosted runner is preferred over silently switching to a potentially billable GitHub-hosted runner, but self-hosting also makes host isolation and lifecycle cleanup part of the acceptance environment.

## Evidence boundary

This audit changes no checker contract and no Linux v5.10 implementation claim. A real workflow execution is still required to establish:

```text
current exact fixture: 22 tests + OK
upstream v5.10:         7/7 source-contract groups PASS
```

If a future workflow revision changes the parent-namespace trust model or adds a different object-identity mechanism, this note must be re-audited rather than treating the present deployment assumption as a permanent implementation guarantee.

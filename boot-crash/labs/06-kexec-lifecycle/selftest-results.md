# B06 source-contract checker self-test execution record

This file records **tool execution evidence** for the B06 checker fixtures. It is not Linux v5.10 L1 source evidence and must not be used as a substitute for running `verify_source_contract.py` against a real upstream v5.10 checkout.

## 2026-08-19 local execution attempt

Intended command from a fresh checkout of this course repository:

```bash
cd boot-crash/labs/06-kexec-lifecycle
python3 -m unittest -v test_verify_source_contract.py
```

The local execution environment did not contain a checkout of `netplus/kernel`. A fresh clone was attempted before running the test:

```bash
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/kernel-course
```

The clone failed before any repository bytes were downloaded:

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

Therefore the 9-case fixture suite in `test_verify_source_contract.py` is **not recorded as PASS from this local attempt**. The repository contains one complete positive fixture and eight negative fixtures, but their presence is source/tool design evidence only until the exact committed files are executed together.

## Exact-commit CI path

Commit `4c34c3e7e4f5d1ffd880423067664ad41c0095cf` added:

```text
.github/workflows/boot-crash-b06-selftest.yml
```

The workflow checks out the repository and runs exactly:

```bash
cd boot-crash/labs/06-kexec-lifecycle
python3 -m unittest -v test_verify_source_contract.py
```

This is the preferred provenance path because the runner executes the committed checker and fixture files rather than a manually reconstructed copy.

On 2026-08-19 the GitHub connector was used to query CI state for commit `4c34c3e7e4f5d1ffd880423067664ad41c0095cf`. The combined commit-status response contained no status entries, and the available commit-workflow-run query returned no workflow runs. That query is documented by the connector as returning pull-request-triggered runs, while this workflow is configured for `push` and `workflow_dispatch`; therefore an empty result is **not evidence that the workflow passed, failed, or did not run**.

Consequently the course must still not claim an exact-suite PASS. The absence of a visible result is an observability limitation of the current tool path, not a test result.

## Evidence status

```text
fixture source present:                    yes
exact committed CI execution path:         yes
exact committed fixture PASS observed:     no
unittest PASS count:                       not established
unittest exit code:                        not established
real Linux v5.10 L1 checker executed:      no
matching-vmlinux L2 executed:              no
Kexec/Kdump VM L3 executed:                no
```

## Next acceptance action

Use either of these provenance-preserving paths:

1. obtain a checkout and run:

   ```bash
   cd boot-crash/labs/06-kexec-lifecycle
   python3 -m unittest -v test_verify_source_contract.py
   ```

2. obtain the GitHub Actions run/job result for `boot-crash-b06-selftest.yml` and inspect the `Run exact committed B06 fixture suite` step.

Only if one of those paths reports all nine tests passing with exit code 0 should the experiment README and this record claim fixture self-test PASS. If any test fails, treat the failure as the next course unit: determine whether the checker, fixture, or Linux v5.10 source assumption is wrong, fix it, rerun the full suite, and commit the correction.

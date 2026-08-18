# B06 source-contract checker self-test execution record

This file records **tool execution evidence** for the B06 checker fixtures. It is not Linux v5.10 L1 source evidence and must not be used as a substitute for running `verify_source_contract.py` against a real upstream v5.10 checkout.

## 2026-08-19 execution attempt

Intended command from a fresh checkout of this course repository:

```bash
cd boot-crash/labs/06-kexec-lifecycle
python3 -m unittest -v test_verify_source_contract.py
```

The execution environment available for this run did not contain a checkout of `netplus/kernel`. A fresh clone was attempted before running the test:

```bash
git clone --depth 1 https://github.com/netplus/kernel.git /tmp/kernel-course
```

The clone failed before any repository bytes were downloaded:

```text
fatal: unable to access 'https://github.com/netplus/kernel.git/':
Could not resolve host: github.com
```

Therefore the 9-case fixture suite in `test_verify_source_contract.py` is **not recorded as PASS in this file**. The repository currently contains one complete positive fixture and eight negative fixtures, but their presence is source/tool design evidence only until the exact committed files are executed together.

The GitHub repository API remained usable for reading and writing files, but it does not provide a shell for executing the committed Python tests. Copying or reconstructing the checker manually in another runtime would weaken provenance, so it is deliberately not treated as equivalent to executing the exact committed files.

## Evidence status

```text
fixture source present:                    yes
exact committed fixture suite executed:    no
unittest PASS count:                       not established
unittest exit code:                        not established
real Linux v5.10 L1 checker executed:      no
matching-vmlinux L2 executed:              no
Kexec/Kdump VM L3 executed:                no
```

## Next acceptance action

As soon as a runtime can obtain the repository checkout, run exactly:

```bash
cd boot-crash/labs/06-kexec-lifecycle
python3 -m unittest -v test_verify_source_contract.py
```

Only if that command reports all nine tests passing with exit code 0 should the experiment README and this record be updated to claim fixture self-test PASS. If any test fails, treat the failure as the next course unit: determine whether the checker, fixture, or Linux v5.10 source assumption is wrong, fix it, rerun the full suite, and commit the correction.

# B06 source-contract checker self-test execution record

This file records **tool execution evidence** for the B06 checker fixtures. It is not Linux v5.10 L1 source evidence and must not be used as a substitute for running `verify_source_contract.py` against a real upstream v5.10 checkout.

## 2026-08-19 fixture execution

The current GitHub versions of:

```text
boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py
boot-crash/labs/06-kexec-lifecycle/test_verify_source_contract.py
```

were fetched in the same maintenance run and materialized together in an isolated Python environment. The fixture suite was then executed with the same command used by the repository workflow:

```bash
python3 -m unittest -v test_verify_source_contract.py
```

Observed result:

```text
test_complete_fixture_passes_all_contracts ... ok
test_rejects_crash_swap_page_allocation ... ok
test_rejects_file_api_without_crash_purpose ... ok
test_rejects_missing_crash_reserved_range_end ... ok
test_rejects_missing_persistent_image_install ... ok
test_rejects_missing_point_of_no_return_contract ... ok
test_rejects_prepare_after_install ... ok
test_rejects_prepare_without_transition_pgtable ... ok
test_rejects_shared_control_page_allocator ... ok

Ran 9 tests

OK
```

Process exit code: `0`.

The suite therefore establishes tool evidence for one complete positive fixture and eight negative fixtures. The positive fixture returns all seven B06 contract groups; each negative fixture demonstrates rejection when one targeted source contract is broken.

The execution environment emitted an unrelated spreadsheet-runtime warmup warning before the unittest output. It did not affect Python unittest execution: all nine tests completed and the test process returned exit code 0.

## Provenance boundary

This result is stronger than merely inspecting the fixture source, but it must not be overstated. The files were fetched from GitHub and executed together in an isolated environment; this record is **fixture/checker tool evidence**. It is not a run of `verify_source_contract.py` against an upstream Linux v5.10 source tree, and it is not L2 or L3 evidence.

The repository also contains:

```text
.github/workflows/boot-crash-b06-selftest.yml
```

which checks out the repository and runs the same unittest command. A GitHub Actions job result is useful additional provenance, but it is no longer required to establish that the fixture/checker pair itself executes successfully because this run produced a directly observed 9-test PASS.

## Evidence status

```text
fixture source present:                    yes
fixture/checker pair executed together:    yes
fixture self-test PASS observed:           yes
unittest PASS count:                       9 / 9
positive / negative fixtures:              1 / 8
unittest exit code:                        0
real Linux v5.10 L1 checker executed:      no
matching-vmlinux L2 executed:              no
Kexec/Kdump VM L3 executed:                no
```

## Next acceptance action

The fixture/checker tool-evidence unit is complete. The next course-maintenance step is to update the B06 experiment README and expected-analysis state so that they record the observed `9 / 9`, `OK`, exit-code-0 result while preserving the evidence boundary:

```text
fixture self-test        = tool evidence, completed
real upstream v5.10 run  = L1, not yet executed
matching vmlinux         = L2, not yet executed
isolated Kexec/Kdump VM  = L3, not yet executed
```

A future environment with a complete upstream Linux v5.10 checkout should run `verify_source_contract.py` against that tree. Matching-build ELF/assembly and isolated VM runtime observations remain enhancement evidence rather than prerequisites for claiming the fixture self-test itself complete.

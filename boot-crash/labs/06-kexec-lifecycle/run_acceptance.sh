#!/usr/bin/env bash
set -euo pipefail

# Run the two B06 hard acceptance gates without GitHub Actions.  The caller
# supplies an already-materialized upstream Linux v5.10 tree; this keeps the
# script usable in a zero-new-cost local/self-hosted environment and avoids
# hiding network acquisition inside the evidence-producing step.

repo_root="$(git rev-parse --show-toplevel)"
lab="$repo_root/boot-crash/labs/06-kexec-lifecycle"
upstream="${1:?usage: run_acceptance.sh /path/to/linux-v5.10}"

expected_upstream=2c85ebc57b3e1817b6ce1a6b703928e113a90442
expected_checker=5c89b67628cf55560089656d5b65e80ff74c556f
expected_fixture=f18918cfbe0b01ffba59be3ac083a9971295a2f8
checker="$lab/verify_source_contract.py"
fixture="$lab/test_verify_source_contract.py"

for command in git python3 grep tee mktemp rm; do
    command -v "$command" >/dev/null
done

# Bind the run to the same exact source identities used by the self-hosted
# workflow.  A different checker/fixture or a modified upstream worktree is a
# different experiment and must not inherit B06 completion evidence.
test "$(git -C "$upstream" rev-parse HEAD)" = "$expected_upstream"
test -z "$(git -C "$upstream" status --porcelain)"
test "$(git -C "$repo_root" hash-object "$checker")" = "$expected_checker"
test "$(git -C "$repo_root" hash-object "$fixture")" = "$expected_fixture"

fixture_log="$(mktemp)"
upstream_log="$(mktemp)"
trap 'rm -f "$fixture_log" "$upstream_log"' EXIT

(
    cd "$lab"
    python3 -m unittest -v test_verify_source_contract.py
) 2>&1 | tee "$fixture_log"
grep -Eq '^Ran 22 tests in ' "$fixture_log"
grep -Eq '^OK$' "$fixture_log"

python3 "$checker" "$upstream" 2>&1 | tee "$upstream_log"
test "$(grep -Ec '^PASS [1-7]: ' "$upstream_log")" -eq 7
for group in 1 2 3 4 5 6 7; do
    grep -Eq "^PASS ${group}: " "$upstream_log"
done
grep -Fxq 'PASS: 7 B06 Linux v5.10 source-contract groups' "$upstream_log"

printf 'PASS: B06 exact fixture 22/22 and upstream Linux v5.10 source contracts 7/7\n'

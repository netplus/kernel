#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

# Run the two B06 hard acceptance gates without GitHub Actions. The caller
# supplies an already-materialized upstream Linux v5.10 tree; this keeps the
# script usable in a zero-new-cost local/self-hosted environment and avoids
# hiding network acquisition inside the evidence-producing step.

# Resolve the course checkout from this script rather than from the caller's
# current directory. A local acceptance entry point must behave identically
# when invoked from the repository root or through an absolute script path.
# dirname is needed before repository discovery, so validate both early
# commands before using either one.
for command in git dirname; do
    command -v "$command" >/dev/null || {
        printf 'FAIL: required command not found: %s\n' "$command" >&2
        exit 1
    }
done
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
lab="$repo_root/boot-crash/labs/06-kexec-lifecycle"
upstream="${1:?usage: run_acceptance.sh /path/to/linux-v5.10}"

expected_upstream=2c85ebc57b3e1817b6ce1a6b703928e113a90442
expected_checker=5c89b67628cf55560089656d5b65e80ff74c556f
expected_fixture=f18918cfbe0b01ffba59be3ac083a9971295a2f8
checker_rel=boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py
fixture_rel=boot-crash/labs/06-kexec-lifecycle/test_verify_source_contract.py
checker="$repo_root/$checker_rel"
fixture="$repo_root/$fixture_rel"

# Fail before producing course evidence when the local execution environment
# does not satisfy the same basic platform/tool contract as the self-hosted
# workflow. git and dirname were checked before repository discovery above;
# keep them in this list so the complete prerequisite contract remains visible
# in one place.
for command in git dirname python3 uname grep tee mktemp rm; do
    command -v "$command" >/dev/null || {
        printf 'FAIL: required command not found: %s\n' "$command" >&2
        exit 1
    }
done

test "$(uname -s)" = Linux
case "$(uname -m)" in
    x86_64|amd64) ;;
    *) printf 'FAIL: B06 acceptance requires x86-64, got %s\n' "$(uname -m)" >&2; exit 1 ;;
esac

python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit(f"FAIL: Python >= 3.9 required, got {sys.version.split()[0]}")
print(f"python={sys.version.split()[0]}")
PY

git_version_output="$(git version)"
git_version="${git_version_output#git version }"
python3 - "$git_version" <<'PY'
import re
import sys
m = re.match(r"^(\d+)\.(\d+)", sys.argv[1])
if not m:
    raise SystemExit(f"FAIL: cannot parse Git version: {sys.argv[1]}")
if tuple(map(int, m.groups())) < (2, 18):
    raise SystemExit(f"FAIL: Git >= 2.18 required, got {sys.argv[1]}")
print(f"git={sys.argv[1]}")
PY

# Bind the run to committed course files, not merely to whatever bytes happen
# to be present in the worktree. A dirty course tree is a different experiment
# and must not inherit B06 completion evidence.
test -z "$(git -C "$repo_root" status --porcelain)"
checker_head="$(git -C "$repo_root" rev-parse "HEAD:$checker_rel")"
fixture_head="$(git -C "$repo_root" rev-parse "HEAD:$fixture_rel")"
checker_worktree="$(git -C "$repo_root" hash-object "$checker")"
fixture_worktree="$(git -C "$repo_root" hash-object "$fixture")"

test "$checker_head" = "$expected_checker"
test "$fixture_head" = "$expected_fixture"
test "$checker_worktree" = "$checker_head"
test "$fixture_worktree" = "$fixture_head"
printf 'course HEAD=%s\n' "$(git -C "$repo_root" rev-parse HEAD)"
printf 'checker blob=%s\n' "$checker_head"
printf 'fixture blob=%s\n' "$fixture_head"

# Bind L1 evidence to the exact upstream v5.10 commit and a clean source tree.
test "$(git -C "$upstream" rev-parse HEAD)" = "$expected_upstream"
test -z "$(git -C "$upstream" status --porcelain)"
printf 'upstream HEAD=%s\n' "$(git -C "$upstream" rev-parse HEAD)"

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

# The checker and fixture should not mutate the course checkout.
test -z "$(git -C "$repo_root" status --porcelain)"

printf 'PASS: B06 exact fixture 22/22 and upstream Linux v5.10 source contracts 7/7\n'

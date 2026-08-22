#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

# Run the two B06 hard acceptance gates without GitHub Actions. The caller
# supplies an already-materialized upstream Linux v5.10 tree; this keeps the
# script usable in a zero-new-cost local/self-hosted environment and avoids
# hiding network acquisition inside the evidence-producing step.

for command in git dirname; do
    command -v "$command" >/dev/null || {
        printf 'FAIL: required command not found: %s\n' "$command" >&2
        exit 1
    }
done
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null)" || {
    printf 'FAIL: acceptance script is not inside a Git course checkout: %s\n' "$script_dir" >&2
    exit 1
}
lab="$repo_root/boot-crash/labs/06-kexec-lifecycle"
if test "$#" -ne 1; then
    printf 'FAIL: expected exactly one upstream Linux v5.10 worktree path\n' >&2
    printf 'usage: %s /path/to/linux-v5.10\n' "$0" >&2
    exit 2
fi
upstream="$1"

expected_upstream=2c85ebc57b3e1817b6ce1a6b703928e113a90442
expected_checker=5c89b67628cf55560089656d5b65e80ff74c556f
expected_fixture=f18918cfbe0b01ffba59be3ac083a9971295a2f8
checker_rel=boot-crash/labs/06-kexec-lifecycle/verify_source_contract.py
fixture_rel=boot-crash/labs/06-kexec-lifecycle/test_verify_source_contract.py
checker="$repo_root/$checker_rel"
fixture="$repo_root/$fixture_rel"

for command in git dirname python3 uname grep tee mktemp rm; do
    command -v "$command" >/dev/null || {
        printf 'FAIL: required command not found: %s\n' "$command" >&2
        exit 1
    }
done

os="$(uname -s)"
if test "$os" != Linux; then
    printf 'FAIL: B06 acceptance requires Linux, got %s\n' "$os" >&2
    exit 1
fi
arch="$(uname -m)"
case "$arch" in
    x86_64|amd64) ;;
    *) printf 'FAIL: B06 acceptance requires x86-64, got %s\n' "$arch" >&2; exit 1 ;;
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

if test -n "$(git -C "$repo_root" status --porcelain)"; then
    printf 'FAIL: course worktree is dirty: %s\n' "$repo_root" >&2
    exit 1
fi
checker_head="$(git -C "$repo_root" rev-parse "HEAD:$checker_rel")"
fixture_head="$(git -C "$repo_root" rev-parse "HEAD:$fixture_rel")"
checker_worktree="$(git -C "$repo_root" hash-object "$checker")"
fixture_worktree="$(git -C "$repo_root" hash-object "$fixture")"

if test "$checker_head" != "$expected_checker"; then
    printf 'FAIL: checker committed blob must be %s, got %s\n' "$expected_checker" "$checker_head" >&2
    exit 1
fi
if test "$fixture_head" != "$expected_fixture"; then
    printf 'FAIL: fixture committed blob must be %s, got %s\n' "$expected_fixture" "$fixture_head" >&2
    exit 1
fi
if test "$checker_worktree" != "$checker_head"; then
    printf 'FAIL: checker worktree blob %s differs from committed blob %s\n' "$checker_worktree" "$checker_head" >&2
    exit 1
fi
if test "$fixture_worktree" != "$fixture_head"; then
    printf 'FAIL: fixture worktree blob %s differs from committed blob %s\n' "$fixture_worktree" "$fixture_head" >&2
    exit 1
fi
printf 'course HEAD=%s\n' "$(git -C "$repo_root" rev-parse HEAD)"
printf 'checker blob=%s\n' "$checker_head"
printf 'fixture blob=%s\n' "$fixture_head"

if ! git -C "$upstream" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'FAIL: upstream path is not a Git worktree: %s\n' "$upstream" >&2
    exit 1
fi
upstream_head="$(git -C "$upstream" rev-parse HEAD)"
if test "$upstream_head" != "$expected_upstream"; then
    printf 'FAIL: upstream HEAD must be %s, got %s\n' "$expected_upstream" "$upstream_head" >&2
    exit 1
fi
if test -n "$(git -C "$upstream" status --porcelain)"; then
    printf 'FAIL: upstream Linux v5.10 worktree is dirty: %s\n' "$upstream" >&2
    exit 1
fi
printf 'upstream HEAD=%s\n' "$upstream_head"

fixture_log="$(mktemp)"
upstream_log="$(mktemp)"
trap 'rm -f "$fixture_log" "$upstream_log"' EXIT

(
    cd "$lab"
    python3 -m unittest -v test_verify_source_contract.py
) 2>&1 | tee "$fixture_log"
if ! grep -Eq '^Ran 22 tests in ' "$fixture_log"; then
    printf 'FAIL: fixture suite did not report exactly the expected 22-test run\n' >&2
    exit 1
fi
if ! grep -Eq '^OK$' "$fixture_log"; then
    printf 'FAIL: fixture suite did not report unittest OK\n' >&2
    exit 1
fi

python3 "$checker" "$upstream" 2>&1 | tee "$upstream_log"
pass_count="$(grep -Ec '^PASS [1-7]: ' "$upstream_log" || true)"
if test "$pass_count" -ne 7; then
    printf 'FAIL: upstream checker must report exactly 7 numbered PASS groups, got %s\n' "$pass_count" >&2
    exit 1
fi
for group in 1 2 3 4 5 6 7; do
    if ! grep -Eq "^PASS ${group}: " "$upstream_log"; then
        printf 'FAIL: upstream checker did not report PASS group %s\n' "$group" >&2
        exit 1
    fi
done
if ! grep -Fxq 'PASS: 7 B06 Linux v5.10 source-contract groups' "$upstream_log"; then
    printf 'FAIL: upstream checker did not report the exact 7-group summary\n' >&2
    exit 1
fi

# Treat the upstream source tree as immutable verifier input. A successful
# 7/7 result is not acceptable evidence if the checker changed the tree that
# it inspected. This mirrors the self-hosted workflow's post-checker gate.
if test -n "$(git -C "$upstream" status --porcelain)"; then
    printf 'FAIL: upstream Linux v5.10 worktree became dirty during B06 acceptance: %s\n' "$upstream" >&2
    exit 1
fi

if test -n "$(git -C "$repo_root" status --porcelain)"; then
    printf 'FAIL: course worktree became dirty during B06 acceptance: %s\n' "$repo_root" >&2
    exit 1
fi

printf 'PASS: B06 exact fixture 22/22 and upstream Linux v5.10 source contracts 7/7\n'

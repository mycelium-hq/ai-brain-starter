#!/usr/bin/env bash
#
# scripts/test-meta-resolution-guard.sh - negative-control test for
# scripts/check-meta-resolution.sh. Proves the guard FAILS on a reintroduced
# naive "*Meta" glob and PASSES on a script that uses the resolver. A guard that
# is only ever seen pass is worthless (deployed-not-committed-not-working.md).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$HERE/check-meta-resolution.sh"

fail=0
check() {  # check <description> <expected-rc> <actual-rc>
  if [ "$2" = "$3" ]; then
    echo "  ok: $1"
  else
    echo "  FAIL: $1 (expected rc=$2, got rc=$3)"
    fail=1
  fi
}

base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT

# --- a clean script (uses the resolver) -> guard PASSES (rc 0) ---------------
mkdir -p "$base/clean"
cat > "$base/clean/good.sh" <<'SH'
#!/usr/bin/env bash
META_DIR="$(python3 "$SCRIPT_DIR/_meta_resolver.py" "$VAULT" Sessions Decisions 2>/dev/null || true)"
[ -z "$META_DIR" ] && META_DIR="$VAULT/Meta"
SH
rc=0
bash "$GUARD" "$base/clean" >/dev/null 2>&1 || rc=$?
check "resolver-based script passes the guard" 0 "$rc"

# --- a script with the banned glob -> guard FAILS (rc 1) --------------------
mkdir -p "$base/bad"
cat > "$base/bad/regression.sh" <<'SH'
#!/usr/bin/env bash
for candidate in "$VAULT"/*Meta; do
  [ -d "$candidate" ] && { META_DIR="$candidate"; break; }
done
SH
rc=0
bash "$GUARD" "$base/bad" >/dev/null 2>&1 || rc=$?
check "reintroduced *Meta glob is caught" 1 "$rc"

if [ "$fail" != 0 ]; then
  echo "FAILED: meta-resolution guard test"
  exit 1
fi
echo "PASSED: meta-resolution guard test (2 assertions)"

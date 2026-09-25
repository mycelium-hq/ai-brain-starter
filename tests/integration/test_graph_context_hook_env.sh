#!/usr/bin/env bash
# Regression test for scripts/graph-context-hook.sh's env-override CONFIG
# (PR #682): every CONFIG value can be set from ~/.claude/settings.json ->
# env instead of editing the file, which install-hooks-user-level.py
# overwrites unconditionally on every auto-update.
#
# The one subtlety worth a dedicated test: SECONDARY_GRAPH is spelled with a
# bare `${SECONDARY_GRAPH-default}`, not `${SECONDARY_GRAPH:-default}`. Only
# the bare form honours an EXPORTED EMPTY value -- the documented way to say
# "I only have one graph." The `:-` form treats unset and empty the same and
# would silently re-enable the default Work/ graph the vault owner just
# turned off (see docs/CHANGELOG.md, 2026-09-19 entry, for the incident this
# traces to). The other CONFIG values use `:-` on purpose: emptying them is
# not a supported configuration.
#
# Asserts:
#   1. SECONDARY_GRAPH="" (exported empty) really disables the secondary
#      branch on a prompt that matches SECONDARY_PATTERN: exit 0, silent
#      passthrough, no secondary-scope routing, no missing/LOST-graph text.
#   2. SECONDARY_GRAPH left UNSET (same prompt, same vault) falls back to the
#      documented default `$VAULT_ROOT/Work/...` path, which does not exist
#      in the fixture vault, so the missing-graph text for the secondary
#      scope DOES appear. This proves case 1's silence is the env value's
#      effect, not an artifact of the fixture.
#   3. PRIMARY_PATTERN overrides the default pattern rather than extending
#      it: a custom keyword fires primary routing once set, and a default
#      keyword that fired before the override no longer does.
#
# Negative control (performed manually against a scratch mutant during
# authoring, not shipped here -- see the repo convention in
# test_floor_name_map_canonical.sh, whose in-memory negative control is the
# closest analogue for a pure-bash script with no importable data structure):
# changing the hook's `${SECONDARY_GRAPH-` to `${SECONDARY_GRAPH:-` makes
# case 1 below go RED against the mutant (it re-enables the default Work/
# graph on an exported-empty value); restoring the original makes it GREEN.
# Case 1, run against the real, unmodified script on every CI run, IS that
# regression guard -- there is nothing further to embed permanently.
#
# Self-contained. Exit 0 = pass, 1 = fail.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
HOOK="$ROOT/scripts/graph-context-hook.sh"
# HOME alone does not sandbox ~ on Windows -- see lib/sandbox_home.sh. This
# hook only reads HOME as VAULT_ROOT's own fallback default, which every case
# below overrides explicitly, but every suite here sandboxes on principle.
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$HERE/lib/sandbox_home.sh"

[[ -f "$HOOK" ]] || { echo "FAIL: hook not found: $HOOK"; exit 1; }

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
sandbox_home "$TMP/home"

# Fixture vault: a real primary GRAPH_REPORT.md, no Work/ subfolder at all --
# so a secondary-scope hit in this vault can only come from the default path
# in case 2, never from a file that happens to exist.
VAULT="$TMP/vault"
mkdir -p "$VAULT/graphify-out"
printf '# fixture graph report\n' > "$VAULT/graphify-out/GRAPH_REPORT.md"

# call_hook PROMPT [env/-u args...] -- sets HOOK_OUT and HOOK_RC.
#
# Captured via set +e/set -e around the call (not a bare `out=$(...)`),
# because under `set -e` a failing command substitution aborts the script
# right there -- the same idiom test_daily_maintenance_exit_code.sh uses to
# assert on a non-zero exit without that exit killing the test itself.
call_hook() {
  local prompt="$1"; shift
  local payload
  payload=$(printf '{"hook_event_name":"UserPromptSubmit","prompt":"%s"}' "$prompt")
  set +e
  HOOK_OUT=$(printf '%s' "$payload" | env "$@" bash "$HOOK" 2>"$TMP/stderr")
  HOOK_RC=$?
  set -e
}

# --- 1. SECONDARY_GRAPH exported empty disables the secondary branch -------
call_hook "team meeting" VAULT_ROOT="$VAULT" SECONDARY_GRAPH=""
[[ "$HOOK_RC" -eq 0 ]] || fail "case 1: hook exited $HOOK_RC, expected 0 (stderr: $(cat "$TMP/stderr"))"
echo "$HOOK_OUT" | grep -q '"continue":true' || fail "case 1: expected silent passthrough, got: $HOOK_OUT"
if echo "$HOOK_OUT" | grep -q "keyword match: secondary scope"; then
  fail "case 1: secondary-scope routing fired despite exported-empty SECONDARY_GRAPH (output: $HOOK_OUT)"
fi
if echo "$HOOK_OUT" | grep -q "LOST"; then
  fail "case 1: LOST-graph text leaked despite exported-empty SECONDARY_GRAPH (output: $HOOK_OUT)"
fi
if echo "$HOOK_OUT" | grep -q "missing (run /graphify"; then
  fail "case 1: missing-graph text leaked despite exported-empty SECONDARY_GRAPH (output: $HOOK_OUT)"
fi
echo "OK: SECONDARY_GRAPH=\"\" turns the secondary branch off (exit 0, silent)"

# --- 2. SECONDARY_GRAPH left unset falls back to the default path ----------
# Same prompt, same vault -- the only difference from case 1 is that
# SECONDARY_GRAPH is genuinely ABSENT from the environment (env -u), not set
# to "". This is what proves case 1's silence is the env value's own effect.
call_hook "team meeting" -u SECONDARY_GRAPH VAULT_ROOT="$VAULT"
[[ "$HOOK_RC" -eq 0 ]] || fail "case 2: hook exited $HOOK_RC, expected 0 (stderr: $(cat "$TMP/stderr"))"
echo "$HOOK_OUT" | grep -q "keyword match: secondary scope" ||
  fail "case 2: secondary-scope routing did NOT fire with SECONDARY_GRAPH unset (output: $HOOK_OUT)"
echo "$HOOK_OUT" | grep -q "missing (run /graphify on Work/ to build it)" ||
  fail "case 2: expected the default Work/ graph's missing-graph text (output: $HOOK_OUT)"
echo "OK: SECONDARY_GRAPH unset falls back to the default Work/ path (missing-graph text present)"

# --- 3. PRIMARY_PATTERN overrides the default, it does not extend it -------
# 3a. Baseline: the default pattern's own keyword fires primary routing.
call_hook "journal" VAULT_ROOT="$VAULT" SECONDARY_GRAPH=""
echo "$HOOK_OUT" | grep -q "keyword match: primary scope" ||
  fail "case 3a: default PRIMARY_PATTERN did not fire on its own keyword 'journal' (output: $HOOK_OUT)"

# 3b. A custom keyword fires once PRIMARY_PATTERN is overridden to it.
call_hook "zebra" VAULT_ROOT="$VAULT" SECONDARY_GRAPH="" PRIMARY_PATTERN="zebra"
echo "$HOOK_OUT" | grep -q "keyword match: primary scope" ||
  fail "case 3b: overridden PRIMARY_PATTERN='zebra' did not fire on 'zebra' (output: $HOOK_OUT)"

# 3c. With the override still set, the DEFAULT keyword from 3a no longer
# matches -- proving the override REPLACES the pattern instead of adding to
# it (an additive override would still fire here).
call_hook "journal" VAULT_ROOT="$VAULT" SECONDARY_GRAPH="" PRIMARY_PATTERN="zebra"
if echo "$HOOK_OUT" | grep -q "keyword match: primary scope"; then
  fail "case 3c: default keyword 'journal' still fired after PRIMARY_PATTERN was overridden to 'zebra' -- override is being added to, not replacing, the default (output: $HOOK_OUT)"
fi
echo "$HOOK_OUT" | grep -q '"continue":true' || fail "case 3c: expected silent passthrough, got: $HOOK_OUT"
echo "OK: PRIMARY_PATTERN override replaces the default pattern rather than extending it"

# --- 4. GNU stat semantics: routing still fires with an age note -----------
# On Linux, `stat -f` means --file-system: `stat -f %m FILE` prints file-system
# text and then fails. The hook used to try it first, captured that text along
# with the fallback's number, and did arithmetic on the mix, so it died
# silently on every Linux prompt that matched an existing graph (CI caught it
# on ubuntu; macOS never sees it). lib/gnu_stat_shim.sh reproduces the
# measured GNU behavior on any host.
# Mutation that turns this red: put `stat -f %m` back first in freshness_note.
# shellcheck source=tests/integration/lib/gnu_stat_shim.sh
. "$HERE/lib/gnu_stat_shim.sh"
SHIM="$TMP/gnu-stat"
install_gnu_stat_shim "$SHIM"
call_hook "journal" VAULT_ROOT="$VAULT" SECONDARY_GRAPH="" PATH="$SHIM:$PATH"
[[ "$HOOK_RC" -eq 0 ]] || fail "case 4: hook exited $HOOK_RC under GNU stat semantics (stderr: $(cat "$TMP/stderr"))"
echo "$HOOK_OUT" | grep -q "keyword match: primary scope" ||
  fail "case 4: primary routing did not fire under GNU stat semantics (output: $HOOK_OUT)"
echo "$HOOK_OUT" | grep -q "updated 0 day(s) ago" ||
  fail "case 4: expected a numeric age note under GNU stat semantics (output: $HOOK_OUT)"
echo "OK: under GNU stat semantics the hook still routes and reports a numeric age"

echo "PASS: test_graph_context_hook_env"

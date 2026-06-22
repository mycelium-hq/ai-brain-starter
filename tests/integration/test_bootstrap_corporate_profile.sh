#!/usr/bin/env bash
# Test the corporate / hardened install profile in bootstrap.sh.
#
# Surfaced by an enterprise security review of the workshop install: corporate
# rollouts need a compliance-ready profile. This test pins that contract so a
# future refactor of bootstrap.sh can't silently un-harden the corporate path.
#
# Asserts, via --dry-run (no real install, no network):
#   1. `--profile corporate --dry-run` exits 0
#   2. The hardening markers appear: banner, manifest, telemetry-off enforcement,
#      external-egress MCP skip, playwright exclusion, the PHANTOMPULSE rationale
#   3. The minimal first-party skill set still installs (graphify present)
#   4. The env-var form CORPORATE_PROFILE=1 activates the same path
#   5. NEGATIVE CONTROL: standard mode is unchanged — no corporate banner, MCPs
#      registered, playwright enabled. (A guard earns trust by failing on the
#      thing it catches: if corporate logic leaked into standard mode, this fails.)
#
# Self-contained. Same harness as test_bootstrap_dry_run.sh: HOME=tmpdir, the
# repo symlinked into SKILL_DIR, email marker pre-staged. Writes nothing outside
# its tmpdir.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/bootstrap.sh"

if [ ! -f "$BOOTSTRAP" ]; then
  echo "ERROR: $BOOTSTRAP not found" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP"
mkdir -p "$HOME/.claude/skills"
ln -s "$REPO_ROOT" "$HOME/.claude/skills/ai-brain-starter"
# Pre-stage the email marker so a standalone run never tries to mint a token.
touch "$HOME/.claude/.ai-brain-starter-email-on-file"

fail=0

# run_bootstrap <out_file> <args...> -> echoes exit code, never aborts the test
run_bootstrap() {
  local out="$1"; shift
  set +e
  EMAIL="ci@example.com" NAME="CI Test" LANG_HINT="en" \
    bash "$BOOTSTRAP" "$@" > "$out" 2>&1
  local code=$?
  set -e
  return "$code"
}

assert_grep() {  # <file> <pattern> <human label>
  if grep -qF "$2" "$1"; then
    echo "PASS: $3"
  else
    echo "FAIL: $3 (pattern not found: $2)" >&2
    fail=1
  fi
}

assert_absent() {  # <file> <pattern> <human label>
  if grep -qF "$2" "$1"; then
    echo "FAIL: $3 (pattern unexpectedly present: $2)" >&2
    fail=1
  else
    echo "PASS: $3"
  fi
}

# ─── 1. Corporate via --profile corporate ──────────────────────────────────
CORP_OUT="$TMP/corp.out"
if run_bootstrap "$CORP_OUT" --profile corporate --dry-run; then
  echo "PASS: --profile corporate --dry-run exited 0"
else
  echo "FAIL: --profile corporate --dry-run exited nonzero" >&2
  tail -30 "$CORP_OUT" >&2
  fail=1
fi

assert_grep   "$CORP_OUT" "CORPORATE / HARDENED PROFILE ACTIVE" "corporate banner shown"
assert_grep   "$CORP_OUT" "Corporate component manifest"        "component manifest emitted"
assert_grep   "$CORP_OUT" "skipping external-egress MCPs"       "granola/chatprd MCPs skipped"
assert_grep   "$CORP_OUT" "playwright EXCLUDED"                 "playwright excluded from minimal set"
assert_grep   "$CORP_OUT" "would ENFORCE telemetry-off"        "telemetry-off env enforced"
assert_grep   "$CORP_OUT" "DISABLE_TELEMETRY"                  "manifest names telemetry env vars"
assert_grep   "$CORP_OUT" "REF6598 / PHANTOMPULSE"             "shell-exec-plugin threat cited"
assert_grep   "$CORP_OUT" ".ai-brain-starter-pinned"           "version-pin sentinel named"
assert_grep   "$CORP_OUT" "graphify"                           "minimal first-party skill set still present"
assert_absent "$CORP_OUT" "would register granola + chatprd"   "no external MCP registration in corporate mode"

# ─── 2. Corporate via CORPORATE_PROFILE=1 env var ──────────────────────────
ENV_OUT="$TMP/env.out"
set +e
CORPORATE_PROFILE=1 EMAIL="ci@example.com" NAME="CI" LANG_HINT="en" \
  bash "$BOOTSTRAP" --dry-run > "$ENV_OUT" 2>&1
env_code=$?
set -e
if [ "$env_code" -eq 0 ]; then
  echo "PASS: CORPORATE_PROFILE=1 --dry-run exited 0"
else
  echo "FAIL: CORPORATE_PROFILE=1 --dry-run exited $env_code" >&2
  fail=1
fi
assert_grep "$ENV_OUT" "CORPORATE / HARDENED PROFILE ACTIVE" "env-var form activates corporate profile"

# ─── 3. NEGATIVE CONTROL: standard mode is unchanged ───────────────────────
STD_OUT="$TMP/std.out"
if run_bootstrap "$STD_OUT" --dry-run; then
  echo "PASS: standard --dry-run exited 0"
else
  echo "FAIL: standard --dry-run exited nonzero" >&2
  fail=1
fi
assert_absent "$STD_OUT" "CORPORATE / HARDENED PROFILE ACTIVE" "no corporate banner in standard mode"
assert_absent "$STD_OUT" "Corporate component manifest"        "no manifest in standard mode"
assert_grep   "$STD_OUT" "would register granola + chatprd"    "standard mode registers MCPs"
assert_grep   "$STD_OUT" "obsidian, context7, playwright"      "standard mode enables playwright"

echo
if [ "$fail" -eq 0 ]; then
  echo "All assertions passed. Corporate profile is hardened and standard mode is intact."
else
  echo "One or more corporate-profile assertions failed." >&2
  exit 1
fi

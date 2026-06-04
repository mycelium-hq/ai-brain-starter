#!/usr/bin/env bash
# Test scripts/post-update-email-ask.py — the hook that REPLACED the
# every-session email gate. Asserts the email is asked at the right moment
# and ONLY there:
#   A. marker present                -> passthrough (settled, never ask)
#   B. EMAIL_GATE_BYPASS=1           -> passthrough
#   C. first run, no marker          -> passthrough + records HEAD (SILENT;
#                                       first-install is Phase 24.4's job)
#   D. HEAD unchanged since last run -> passthrough (no update = no ask)
#   E. HEAD changed (a pull landed)  -> ASK, and the ask is gentle + token-free
#   F. another update inside cooldown-> passthrough (no double-ask)
#
# Negative controls baked in: case D proves it does NOT ask on a normal
# session; case E proves the ask never tells the user to paste a token.
#
# Self-contained. Builds a throwaway git repo as the "installed skill clone"
# and never writes outside its tmpdir.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/scripts/post-update-email-ask.py"

if [ ! -f "$HOOK" ]; then
  echo "ERROR: $HOOK not found" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP"
MARKER="$HOME/.claude/.ai-brain-starter-email-on-file"
STATE="$HOME/.claude/.ai-brain-starter-email-ask-state.json"
SKILL_DIR="$HOME/.claude/skills/ai-brain-starter"
mkdir -p "$SKILL_DIR"

# Build the fake installed clone as a real git repo so the hook's
# `git rev-parse HEAD` works and we can simulate `git pull` via new commits.
git -C "$SKILL_DIR" init -q
git -C "$SKILL_DIR" config user.email "t@t.t"
git -C "$SKILL_DIR" config user.name "t"
git -C "$SKILL_DIR" commit -q --allow-empty -m c1

run_hook() { python3 "$HOOK" 2>/dev/null; }
fail() { echo "FAIL: $1" >&2; exit 1; }

# --- A. marker present -> passthrough ---
mkdir -p "$HOME/.claude"
printf 'deadbeefdeadbeefdeadbeefdeadbeef\n' > "$MARKER"
OUT="$(run_hook)"
echo "$OUT" | grep -q '"continue": true' || fail "A: expected passthrough with marker present"
echo "$OUT" | grep -q "additionalContext" && fail "A: must NOT ask when marker present"
rm -f "$MARKER" "$STATE"

# --- B. bypass env -> passthrough ---
OUT="$(EMAIL_GATE_BYPASS=1 run_hook)"
echo "$OUT" | grep -q '"continue": true' || fail "B: expected passthrough under bypass"
echo "$OUT" | grep -q "additionalContext" && fail "B: must NOT ask under bypass"
[ -f "$STATE" ] && fail "B: bypass must not write ask-state"

# --- C. first run, no marker -> silent, records HEAD ---
OUT="$(run_hook)"
echo "$OUT" | grep -q '"continue": true' || fail "C: first run must be passthrough"
echo "$OUT" | grep -q "additionalContext" && fail "C: first run must be SILENT"
[ -f "$STATE" ] || fail "C: first run must record ask-state"
HEAD1="$(git -C "$SKILL_DIR" rev-parse HEAD)"
grep -q "$HEAD1" "$STATE" || fail "C: ask-state must record current HEAD"

# --- D. HEAD unchanged -> passthrough (no update, no ask) ---
OUT="$(run_hook)"
echo "$OUT" | grep -q '"continue": true' || fail "D: unchanged HEAD must passthrough"
echo "$OUT" | grep -q "additionalContext" && fail "D: must NOT ask on a normal session (HEAD unchanged)"

# --- E. HEAD changed (pull landed) -> ASK, gentle + token-free ---
git -C "$SKILL_DIR" commit -q --allow-empty -m c2
OUT="$(run_hook)"
echo "$OUT" | grep -q "additionalContext" || fail "E: must ASK after a version change"
echo "$OUT" | grep -q "optional" || fail "E: ask must be framed optional"
echo "$OUT" | grep -q "Never a token" || fail "E: ask must carry the token-free guard"
# The retired annoying framing must be gone.
echo "$OUT" | grep -qi "paste the token" && fail "E: ask must NOT tell the user to paste a token"
echo "$OUT" | grep -qi "welcome email with a token" && fail "E: ask must NOT reference a token email"

# --- F. another update inside the cooldown -> no double-ask ---
git -C "$SKILL_DIR" commit -q --allow-empty -m c3
OUT="$(run_hook)"
echo "$OUT" | grep -q '"continue": true' || fail "F: cooldown must passthrough"
echo "$OUT" | grep -q "additionalContext" && fail "F: must NOT ask again inside cooldown"

echo "PASS: post-update-email-ask asks only after a real update, stays silent otherwise, token-free, cooldown holds"

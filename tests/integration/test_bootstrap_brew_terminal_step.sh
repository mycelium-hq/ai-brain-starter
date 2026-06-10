#!/usr/bin/env bash
# Test bootstrap.sh degrades gracefully when Homebrew is missing inside a
# non-interactive shell (the user pasted the install prompt into Claude Code,
# which has no TTY to type the Mac password into).
#
# Bug (MYC-739, 2026-06-09 workshop): the brew install was attempted anyway,
# failed on the password prompt, and dragged Obsidian + gh + node + every
# brew-installed tool down with it — a wall of red "failed" lines and no setup
# interview. Amanda: "it hasn't prompted any setup interview. I'm not sure what
# I did wrong." Fix: source an already-installed brew first (Terminal step 4 of
# the web guide may have installed it where Claude Code's non-login shell can't
# see it); if brew is genuinely missing AND stdin is not a TTY, print ONE framed
# Terminal command (print_terminal_step) and exit cleanly instead of cascading.
#
# CI runs on Linux with no Mac/brew, so the brew runtime path itself can't be
# executed here. This test covers what CAN be made deterministic:
#   1. print_terminal_step renders the EN sentinel + the exact Terminal command.
#   2. print_terminal_step renders the ES sentinel (bilingual install).
#   3. The brew block sources an existing brew BEFORE deciding to reinstall.
#   4. The non-interactive guard ([[ ! -t 0 ]]) + print_terminal_step + exit
#      come BEFORE the "homebrew install failed" err — so the cascade is averted,
#      not merely reported after the fact (negative control on ordering).
#   5. bootstrap.sh is syntactically valid (bash -n).
#
# Self-contained; never writes outside its tmpdir.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/bootstrap.sh"
[ -f "$BOOTSTRAP" ] || { echo "ERROR: $BOOTSTRAP not found" >&2; exit 1; }

fail() { echo "FAIL: $1" >&2; exit 1; }

# ── 5. syntax ──
bash -n "$BOOTSTRAP" || fail "5: bootstrap.sh has a syntax error"

# ── 1 + 2. behavioral: render the message in both languages ──
# Extract the real print_terminal_step() from bootstrap.sh and run it with
# minimal stubs, so the message can never silently drift from the source.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
HARNESS="$TMP/render.sh"
{
  echo 'SKILL_DIR="/home/u/.claude/skills/ai-brain-starter"'
  echo 'hdr(){ printf "%s\n" "$*"; }'
  echo 't(){ [ "$LANG_CODE" = es ] && echo "$2" || echo "$1"; }'
  awk '/^print_terminal_step\(\) \{/,/^\}/' "$BOOTSTRAP"
  echo 'LANG_CODE=en print_terminal_step'
} > "$HARNESS"
EN_OUT="$(LANG_CODE=en bash "$HARNESS")"
echo "$EN_OUT" | grep -q "TERMINAL STEP NEEDED" || fail "1: EN render missing the 'TERMINAL STEP NEEDED' sentinel"
echo "$EN_OUT" | grep -q 'bash "/home/u/.claude/skills/ai-brain-starter/bootstrap.sh"' \
  || fail "1: EN render missing the exact 'bash \$SKILL_DIR/bootstrap.sh' Terminal command"
echo "$EN_OUT" | grep -qi "expected, not an error" || fail "1: EN render must pre-frame this as expected, not an error"

ES_OUT="$(sed 's/LANG_CODE=en/LANG_CODE=es/' "$HARNESS" | bash)"
echo "$ES_OUT" | grep -q "PASO EN LA TERMINAL" || fail "2: ES render missing the 'PASO EN LA TERMINAL' sentinel"

# ── 3. an already-installed brew is sourced into PATH before the reinstall decision ──
# The pre-decision sourcing loop (for _brew in /opt/homebrew/bin/brew ...) must
# appear before the second `is_mac && ! have brew` guard that decides to
# reinstall — otherwise a Terminal-installed brew that just isn't on Claude
# Code's PATH gets needlessly reinstalled (and fails on the password).
shellenv_line="$(grep -n 'for _brew in /opt/homebrew/bin/brew' "$BOOTSTRAP" | head -1 | cut -d: -f1)"
decide_line="$(grep -n 'Homebrew is genuinely missing' "$BOOTSTRAP" | head -1 | cut -d: -f1)"
[ -n "$shellenv_line" ] || fail "3: no pre-decision brew-shellenv sourcing loop found"
[ -n "$decide_line" ] || fail "3: reinstall-decision anchor not found"
[ "$shellenv_line" -lt "$decide_line" ] \
  || fail "3: brew is not sourced into PATH before deciding to reinstall (line $shellenv_line !< $decide_line)"

# ── 4. terminal-step branch precedes the homebrew-install-failed err (ordering) ──
tty_guard_line="$(grep -n 'print_terminal_step$' "$BOOTSTRAP" | head -1 | cut -d: -f1)"
brew_fail_line="$(grep -n 'homebrew install failed' "$BOOTSTRAP" | head -1 | cut -d: -f1)"
[ -n "$tty_guard_line" ] || fail "4: print_terminal_step is never called"
[ -n "$brew_fail_line" ] || fail "4: 'homebrew install failed' err anchor not found"
[ "$tty_guard_line" -lt "$brew_fail_line" ] \
  || fail "4: the Terminal-step exit does not precede the homebrew-install-failed err — cascade not averted (line $tty_guard_line !< $brew_fail_line)"

# Guard the guard: the non-interactive condition must actually gate the exit.
grep -q '\[\[ ! -t 0 \]\]' "$BOOTSTRAP" || fail "4: missing the non-interactive ([[ ! -t 0 ]]) guard"

echo "PASS: brew-missing non-interactive degrades to one framed Terminal step (test_bootstrap_brew_terminal_step)"

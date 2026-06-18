#!/usr/bin/env bash
# Regression test: onboarding install-handoff discipline (MYC-1187 + MYC-1190).
#
# Guards four onboarding warts real install reports surfaced, against silent
# regression:
#
#   1. WRONG-SURFACE ESCAPE (MYC-1187). When the installing assistant cannot run
#      local commands (web chat / read-only / no shell+file tools) it must NOT
#      improvise "leave this session, cd ... && claude, run /setup-brain". It
#      continues Phase 1 in THIS session, or routes the user to the Claude Code
#      desktop app + the README install prompt. README assistant guide + SKILL.md
#      both carry the escape.
#
#   2. NO NANO-BANANA / GEMINI NUDGE (MYC-1187) in the bootstrap "Install complete"
#      message, on BOTH bootstrap.sh AND bootstrap.ps1 (the Windows path was missed
#      by the first fix). The nano-banana SKILL stays synced + discoverable; only
#      the proactive end-message nudge is removed.
#
#   3. CORRECT claude-seo MARKETPLACE SLUG (MYC-1187): agricidaniel-claude-seo,
#      never the stale agricidaniel-seo (which 404s for every installer).
#
#   4. INTERVIEW AUTO-RUNS AFTER INSTALL (MYC-1190). The install is step one of
#      two; the assistant must flow straight into Phase 1 in the same turn, not
#      stop at "install complete" and wait for the user to ask. The README Step-2
#      paste prompt itself demands the interview; assistant-guide step 3 forces the
#      same-turn continuation; SKILL.md bans the stop-after-install pattern.
#
# Ships with a built-in negative control: mutated fixtures MUST trip the checks,
# else the guard is dead.
#
# Self-contained. Exit 0 = pass. Exit 1 = fail with details.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# run_checks <root> — sets global CHECK_FAILS to the number of failed assertions.
run_checks() {
  local root="$1"
  local README="$root/README.md"
  local SKILL="$root/SKILL.md"
  local BOOT="$root/bootstrap.sh"
  local BOOTPS="$root/bootstrap.ps1"
  local POWER="$root/docs/POWER_TOOLS.md"
  CHECK_FAILS=0

  _has() {  # <file> <label> <literal>
    if ! grep -qF -- "$3" "$1" 2>/dev/null; then
      echo "  MISS [$2]: \"$3\"" >&2
      CHECK_FAILS=$((CHECK_FAILS + 1))
    fi
  }
  _lacks() {  # <file> <label> <literal>
    if grep -qF -- "$3" "$1" 2>/dev/null; then
      echo "  BANNED-BACK [$2]: \"$3\"" >&2
      CHECK_FAILS=$((CHECK_FAILS + 1))
    fi
  }

  # 1. Wrong-surface escape present in BOTH agent-facing docs.
  _has "$README" "README in-session handoff directive" \
    "Continue the setup interview in THIS session"
  _has "$README" "README forbids the new-session bounce" \
    "start a new session and run"
  _has "$SKILL" "SKILL.md wrong-surface row (continue here)" \
    "Continue Phase 1 HERE"

  # 2. Nano-banana / Gemini nudge gone from BOTH installers' end-message (EN + ES)...
  _lacks "$BOOT" "bootstrap.sh EN nano-banana/gemini nudge" \
    "Image generation (Nano Banana, via Gemini)"
  _lacks "$BOOT" "bootstrap.sh ES nano-banana/gemini nudge" \
    "Generación de imágenes (Nano Banana"
  _lacks "$BOOTPS" "bootstrap.ps1 EN nano-banana/gemini nudge" \
    "Nano Banana via Gemini"
  _lacks "$BOOTPS" "bootstrap.ps1 ES nano-banana/gemini nudge" \
    "Nano Banana vía Gemini"
  #    ...but the nano-banana SKILL stays synced + discoverable.
  _has "$BOOT" "nano-banana skill still synced (discoverable)" \
    "nano-banana"

  # 3. claude-seo marketplace slug correct (bootstrap + POWER_TOOLS), stale slug gone.
  _has "$BOOT" "bootstrap claude-seo slug" \
    "claude-seo@agricidaniel-claude-seo"
  _lacks "$BOOT" "bootstrap stale claude-seo slug" \
    "@agricidaniel-seo"
  _has "$POWER" "POWER_TOOLS claude-seo slug" \
    "claude-seo@agricidaniel-claude-seo"
  _lacks "$POWER" "POWER_TOOLS stale claude-seo slug" \
    "@agricidaniel-seo"

  # 4. Interview AUTO-RUNS after install — the handoff forces same-turn continuation.
  _has "$README" "README Step-2 prompt demands the interview (EN)" \
    "run the full setup interview without stopping"
  _has "$README" "README Step-2 prompt demands the interview (ES)" \
    "corré la entrevista de setup completa sin parar"
  _has "$README" "README step 3 forces continuation (step one of two)" \
    "step one of two"
  _has "$README" "README step 3 names the immediate next action" \
    "your very next message to the user is the Phase 1 language question"
  _has "$SKILL" "SKILL.md bans stop-after-install" \
    "The install is step one; the interview is the rest"
}

# ── Real check against the repo ───────────────────────────────────────────────
echo "==> onboarding handoff: wrong-surface escape + no nano-banana nudge + claude-seo slug + auto-run"
run_checks "$REPO_ROOT"
if [ "${CHECK_FAILS:-0}" -gt 0 ]; then
  echo "" >&2
  echo "$CHECK_FAILS onboarding check(s) failed. See ⚙️ agent-onboarding-doc-discipline (MYC-1187 / MYC-1190)." >&2
  exit 1
fi

# ── Negative control: mutated fixtures MUST trip the checks ───────────────────
# A guard earns trust only by failing on the thing it catches. Reintroduce each
# bug in a throwaway copy and assert the checks fire.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/docs"
# README: drop the wrong-surface directive, the auto-run forcing line, and the
# strengthened Step-2 prompt line.
grep -vF "Continue the setup interview in THIS session" "$REPO_ROOT/README.md" \
  | grep -vF "step one of two" \
  | grep -vF "run the full setup interview without stopping" > "$TMP/README.md" || true
# SKILL.md: drop the wrong-surface row and the stop-after-install row.
grep -vF "Continue Phase 1 HERE" "$REPO_ROOT/SKILL.md" \
  | grep -vF "The install is step one; the interview is the rest" > "$TMP/SKILL.md" || true
# bootstrap.sh: reintroduce the nano-banana nudge AND the stale claude-seo slug.
{
  cat "$REPO_ROOT/bootstrap.sh"
  printf '\n  Image generation (Nano Banana, via Gemini) is the one thing that cannot auto-install.\n'
  printf 'install_plugin "AgriciDaniel/claude-seo" "claude-seo@agricidaniel-seo"\n'
} > "$TMP/bootstrap.sh"
# bootstrap.ps1: reintroduce the nano-banana nudge.
{
  cat "$REPO_ROOT/bootstrap.ps1"
  printf '\nWrite-Host "Image generation (Nano Banana via Gemini) is the one thing."\n'
} > "$TMP/bootstrap.ps1"
# POWER_TOOLS unmutated (proves it is not a false-positive source).
cp "$REPO_ROOT/docs/POWER_TOOLS.md" "$TMP/docs/POWER_TOOLS.md"

run_checks "$TMP"
if [ "${CHECK_FAILS:-0}" -eq 0 ]; then
  echo "FAIL (negative control): mutated fixtures did NOT trip any check — the guard is dead." >&2
  exit 1
fi
echo "  negative control: mutated fixtures tripped $CHECK_FAILS check(s) — guard is live."

echo "PASS: wrong-surface escape (README + SKILL.md); nano-banana/Gemini nudge absent from bootstrap.sh AND bootstrap.ps1 (EN + ES) with the skill still synced; claude-seo slug = agricidaniel-claude-seo; interview auto-run forced (Step-2 prompt EN+ES, README step 3, SKILL.md stop-after-install ban)."

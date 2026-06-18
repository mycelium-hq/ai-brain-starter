#!/usr/bin/env bash
# Regression test: onboarding install-handoff discipline (MYC-1187).
#
# Three onboarding warts a real install report (2026-06-18) surfaced, each
# guarded here against silent regression:
#
#   1. WRONG-SURFACE ESCAPE. When the installing assistant cannot run local
#      commands (web chat / read-only / no shell+file tools) it must NOT
#      improvise "leave this session, cd ~/.claude/skills/... && claude, then
#      run /setup-brain". The canonical handoff is: continue Phase 1 in THIS
#      session, or — if the surface truly cannot run it — route the user to the
#      Claude Code desktop app + the README install prompt. The assistant guide
#      (README) and SKILL.md must both carry this. (Promotes the MYC-419
#      deferred "wrong-surface guidance" item; per agent-onboarding-doc-discipline.)
#
#   2. NO NANO-BANANA / GEMINI NUDGE in the bootstrap "Install complete"
#      message. Image generation is an on-demand extra most installers never
#      use; the proactive "set up a Gemini API key" nudge is noise at first
#      run. The nano-banana SKILL stays synced + discoverable (so /nano-banana
#      still works on request) — only the end-message nudge is removed.
#
#   3. CORRECT claude-seo MARKETPLACE SLUG. Upstream marketplace.json declares
#      name=agricidaniel-claude-seo; the stale slug agricidaniel-seo 404s for
#      every installer (the "FAIL: 1" in the install summary).
#
# Ships with a built-in negative control (--selftest, also run unconditionally
# at the end): mutated fixtures MUST trip the checks, else the guard is dead.
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
  _has "$SKILL" "SKILL.md banned-pattern row (continue here)" \
    "Continue Phase 1 HERE"

  # 2. Nano-banana / Gemini nudge gone from the bootstrap end-message (EN + ES)...
  _lacks "$BOOT" "bootstrap EN nano-banana/gemini nudge" \
    "Image generation (Nano Banana, via Gemini)"
  _lacks "$BOOT" "bootstrap ES nano-banana/gemini nudge" \
    "Generación de imágenes (Nano Banana"
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
}

# ── Real check against the repo ───────────────────────────────────────────────
echo "==> onboarding handoff: wrong-surface escape + no nano-banana nudge + claude-seo slug"
run_checks "$REPO_ROOT"
if [ "${CHECK_FAILS:-0}" -gt 0 ]; then
  echo "" >&2
  echo "$CHECK_FAILS onboarding check(s) failed. See ⚙️ agent-onboarding-doc-discipline (MYC-1187)." >&2
  exit 1
fi

# ── Negative control: mutated fixtures MUST trip the checks ───────────────────
# A guard earns trust only by failing on the thing it catches. Reintroduce each
# bug in a throwaway copy and assert the checks fire.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/docs"
# README: drop the in-session handoff directive line.
grep -vF "Continue the setup interview in THIS session" "$REPO_ROOT/README.md" > "$TMP/README.md" || true
# SKILL.md: drop the banned-pattern row.
grep -vF "Continue Phase 1 HERE" "$REPO_ROOT/SKILL.md" > "$TMP/SKILL.md" || true
# bootstrap.sh: reintroduce the nano-banana nudge AND the stale claude-seo slug.
{
  cat "$REPO_ROOT/bootstrap.sh"
  printf '\n  Image generation (Nano Banana, via Gemini) is the one thing that cannot auto-install.\n'
  printf 'install_plugin "AgriciDaniel/claude-seo" "claude-seo@agricidaniel-seo"\n'
} > "$TMP/bootstrap.sh"
# POWER_TOOLS unmutated (proves it is not a false-positive source).
cp "$REPO_ROOT/docs/POWER_TOOLS.md" "$TMP/docs/POWER_TOOLS.md"

run_checks "$TMP"
if [ "${CHECK_FAILS:-0}" -eq 0 ]; then
  echo "FAIL (negative control): mutated fixtures did NOT trip any check — the guard is dead." >&2
  exit 1
fi
echo "  negative control: mutated fixtures tripped $CHECK_FAILS check(s) — guard is live."

echo "PASS: wrong-surface escape present (README + SKILL.md); nano-banana/Gemini nudge absent from the bootstrap end-message (EN + ES) while the nano-banana skill stays synced; claude-seo slug = agricidaniel-claude-seo (bootstrap.sh + POWER_TOOLS.md)."

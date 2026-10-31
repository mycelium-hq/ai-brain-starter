#!/usr/bin/env bash
# Test: a close phrase with a negation just before it is not a close.
#
# Bug class: detect-closing-signal.py matched the close PHRASE and never looked
# at the words in front of it. "don't close this session, we keep going" holds
# the literal phrase "close this session", so it fired the full close cascade
# (and pre-built an empty session file) for someone who had just said the
# opposite. Two tiers did it, independently:
#
#   1. The user's own closingSignals.custom phrases. They are matched as
#      literals at the highest tier and skip every false-positive guard by
#      design, so nothing else could stop them.
#   2. The shared packs' strong tiers (high_confidence, explicit):
#      `close (this|the) session`, `wrapping up`, `/close`, "es todo por hoy"
#      fire wherever they stand in the message. With no custom list at all,
#      "don't close this session" still closed the session through these.
#
# Fix under test: before a strong-tier match counts, the clause in front of it
# (the text since the last . ! ? ; : , newline, "but" or "pero") is searched for
# a negation within a few words of the phrase. Each language pack lists its own
# negation words (templates/closing-signals/*.json "negations"); the user's
# custom phrases carry no language, so they get every loaded language's words.
#
# Every "should NOT fire" case has a "should fire" twin. The twins include the
# English sign-offs that start with "no" ("no thanks, that's all", "no I'm
# good"): in Spanish "no" is a negation, in English it is usually a reply, and
# the Spanish one must never swallow the English one.
#
# Self-contained: tmpdir fake vault, HOME redirected. Exit 0 = pass, 1 = fail.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/detect-closing-signal.py"
# HOME alone does not sandbox ~ on Windows - see lib/sandbox_home.sh.
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$REPO_ROOT/tests/integration/lib/sandbox_home.sh"
if [ ! -f "$HOOK" ]; then
  echo "ERROR: $HOOK not found" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
sandbox_home "$TMP/fake-home"

VAULT="$TMP/vault"
META="$VAULT/Meta"
mkdir -p "$META/Sessions" "$META/Decisions"

# The user's own phrases, as they would sit in CLAUDE.md.
CUSTOM_EN='closingSignals.custom: ["close this session", "lets close this session", "wrap up this session"]'
CUSTOM_ES='closingSignals.custom: ["es todo por hoy", "ya es todo", "cierra la sesión"]'
NO_CUSTOM=''

# U+2019, built from bytes so no tool or editor can rewrite it to a straight '.
CURLY="$(printf '\xe2\x80\x99')"

run_hook() {
  local prompt="$1" claude_md="$2"
  rm -f "$VAULT/CLAUDE.md"
  if [ -n "$claude_md" ]; then
    printf '%s\n' "$claude_md" > "$VAULT/CLAUDE.md"
  fi
  printf '{"prompt":%s,"session_id":"test-sid","cwd":%s}' \
    "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$prompt")" \
    "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$VAULT")" \
    | VAULT_ROOT="$VAULT" python3 "$HOOK"
}

assert_no_fire() {
  local prompt="$1" claude_md="$2" output
  output="$(run_hook "$prompt" "$claude_md")"
  if echo "$output" | grep -qE "SESSION CLOSE|POSSIBLE SESSION CLOSE"; then
    echo "FAIL [should NOT fire]: $prompt" >&2
    echo "  output: $output" >&2
    return 1
  fi
  return 0
}

assert_fires() {
  local prompt="$1" claude_md="$2" output
  output="$(run_hook "$prompt" "$claude_md")"
  if ! echo "$output" | grep -qE "SESSION CLOSE|POSSIBLE SESSION CLOSE"; then
    echo "FAIL [should fire]: $prompt" >&2
    echo "  output: $output" >&2
    return 1
  fi
  return 0
}

failed=0
no_fire() { assert_no_fire "$@" || failed=$((failed+1)); }
fires()   { assert_fires "$@"   || failed=$((failed+1)); }

# --- NEGATED, the user's own phrases (should NOT fire) ------------------------
no_fire "don't close this session, you can compact it but we keep going until we finish." "$CUSTOM_EN"
no_fire "do not close this session" "$CUSTOM_EN"
no_fire "dont close this session yet" "$CUSTOM_EN"
no_fire "never close this session" "$CUSTOM_EN"
no_fire "please don't wrap up this session" "$CUSTOM_EN"
no_fire "we are not going to close this session" "$CUSTOM_EN"
no_fire "no need to close this session" "$CUSTOM_EN"
no_fire "let's not close this session" "$CUSTOM_EN"
no_fire "I don't want to close this session" "$CUSTOM_EN"
no_fire "Don${CURLY}t close this session" "$CUSTOM_EN"
no_fire "please don't /close yet" "$CUSTOM_EN"

# --- NEGATED, shared packs only: no custom list at all (should NOT fire) ------
no_fire "don't close this session" "$NO_CUSTOM"
no_fire "we're not wrapping up yet" "$NO_CUSTOM"
no_fire "don't wrap it up" "$NO_CUSTOM"

# --- NEGATED, Spanish: the es pack and the user's own phrases (should NOT fire)
no_fire "no cerremos esta sesión" "$CUSTOM_ES"
no_fire "no es todo por hoy" "$CUSTOM_ES"
no_fire "no es todo por hoy" "$NO_CUSTOM"
no_fire "no vamos a cerrar la sesión" "$CUSTOM_ES"
no_fire "no quiero cerrar esta sesión" "$CUSTOM_ES"
no_fire "nunca cerramos la sesión sin guardar antes" "$CUSTOM_ES"

# --- STILL CLOSES: the user's own phrases -------------------------------------
fires "close this session" "$CUSTOM_EN"
fires "lets close this session" "$CUSTOM_EN"
fires "ok close this session" "$CUSTOM_EN"
fires "wrap up this session" "$CUSTOM_EN"
# A comma, a period or "but" ends a negation's reach.
fires "don't worry, close this session" "$CUSTOM_EN"
fires "we're not done but close this session" "$CUSTOM_EN"
fires "Don't close this session yet. OK, close this session now." "$CUSTOM_EN"
# "no" alone is an answer in English, and "never mind" is not a refusal.
fires "no, close this session" "$CUSTOM_EN"
fires "never mind close this session" "$CUSTOM_EN"
fires "/close" "$CUSTOM_EN"
fires "ok /close" "$CUSTOM_EN"

# --- STILL CLOSES: the shared packs, including English "no ..." sign-offs -----
fires "close this session" "$NO_CUSTOM"
fires "wrapping up" "$NO_CUSTOM"
fires "no thanks, that's all" "$NO_CUSTOM"
fires "no I'm good" "$NO_CUSTOM"

# --- STILL CLOSES: Spanish ----------------------------------------------------
fires "cerremos esta sesión" "$CUSTOM_ES"
fires "cierra la sesión" "$CUSTOM_ES"
fires "ya es todo" "$CUSTOM_ES"
fires "es todo por hoy" "$CUSTOM_ES"
fires "no, cerremos esta sesión" "$CUSTOM_ES"

if [ "$failed" -gt 0 ]; then
  echo "FAIL: $failed assertion(s) failed" >&2
  exit 1
fi
echo "PASS: a negation just before a close phrase cancels it; bare and comma-separated closes still fire"

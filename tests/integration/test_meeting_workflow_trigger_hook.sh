#!/usr/bin/env bash
# Regression test for inject-meeting-workflow-on-trigger.py
#
# Bug class: ARTIFACT-WITHOUT-AUTOMATION-WIRING. The meeting-workflow.md
# rule existed in the vault and README/POWER_TOOLS.md promised the
# "I just had a meeting" cascade fired automatically — but no
# UserPromptSubmit hook surfaced the rule on the trigger phrase. Users
# reported saying "I just had a meeting" and getting nothing back.
#
# This test asserts:
#   1. The hook is present in hooks/.
#   2. It is wired into hooks.json under UserPromptSubmit.
#   3. EN trigger phrases fire ("I just had a meeting", variants).
#   4. ES trigger phrases fire ("acabo de tener una reunión", variants).
#   5. Non-trigger meeting mentions do NOT fire (future / past-week /
#      planning / asking about a meeting — temporal-anchor discipline).
#   6. The injected payload references meeting-workflow.md so the
#      assistant actually has the cascade in context.
#   7. The bypass env var suppresses the injection.
#
# Self-contained. Exit 0 = pass. Exit 1 = fail with details.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/inject-meeting-workflow-on-trigger.py"
HOOKS_JSON="$REPO_ROOT/hooks.json"

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

# 1. Hook present
[[ -f "$HOOK" ]] || fail "hook missing at $HOOK"
[[ -x "$HOOK" ]] || chmod +x "$HOOK"

# 2. Wired into hooks.json
grep -q "inject-meeting-workflow-on-trigger.py" "$HOOKS_JSON" || \
    fail "hook not wired into hooks.json — add a UserPromptSubmit entry"

# Build a throwaway vault with a real meeting-workflow.md so the hook
# resolves a rule path (otherwise it falls back to the embedded summary,
# which is also valid but we want to verify the preferred path works).
TMP_VAULT="$(mktemp -d)"
trap 'rm -rf "$TMP_VAULT"' EXIT
mkdir -p "$TMP_VAULT/Meta/rules"
cat > "$TMP_VAULT/Meta/rules/meeting-workflow.md" <<'EOF'
---
type: rule
trigger: "I just had a meeting"
---

# Meeting workflow stub

Find the transcript. Read it. Enrich the meeting note. Update CRM.
Update to-dos. Update Decision Log. Verify backlinks. Report.
EOF
mkdir -p "$TMP_VAULT/Meta"
touch "$TMP_VAULT/Meta/Current Priorities.md"

run_hook() {
    local prompt="$1"
    local extra_env="${2:-}"
    local payload
    payload=$(python3 -c "import json,sys; print(json.dumps({'prompt': sys.argv[1]}))" "$prompt")
    if [[ -n "$extra_env" ]]; then
        eval "$extra_env" VAULT_ROOT="$TMP_VAULT" python3 "$HOOK" <<<"$payload"
    else
        VAULT_ROOT="$TMP_VAULT" python3 "$HOOK" <<<"$payload"
    fi
}

# 3. EN triggers FIRE
EN_POSITIVE=(
    "I just had a meeting with Sara"
    "i just finished a call"
    "I just wrapped up the standup"
    "I just got out of a 1:1"
    "The meeting just ended"
    "the meeting is done"
    "meeting with John just ended"
    "pull the transcript"
    "pull my meeting notes"
    "process today's meeting"
    "Diego's meeting is done"
    "done with my interview"
    "wrapped up the sync"
)
for p in "${EN_POSITIVE[@]}"; do
    out=$(run_hook "$p")
    if [[ -z "$out" ]]; then
        fail "EN trigger did NOT fire: $p"
    fi
    echo "$out" | grep -q "meeting-workflow auto-injected" || \
        fail "EN trigger fired but missing header marker: $p (output: $out)"
done

# 4. ES triggers FIRE (accent-insensitive)
ES_POSITIVE=(
    "Acabo de tener una reunión con Diego"
    "acabo de tener una reunion"
    "acabo de terminar la llamada"
    "acabo de salir de una junta"
    "la reunión ya terminó"
    "la reunion ya termino"
    "mi reunión recién acabó"
    "ya terminé la reunión"
    "ya acabé mi llamada"
    "trae las notas de la reunión"
    "saca el transcript"
    "reunión con María ya terminó"
)
for p in "${ES_POSITIVE[@]}"; do
    out=$(run_hook "$p")
    if [[ -z "$out" ]]; then
        fail "ES trigger did NOT fire: $p"
    fi
done

# 5. Negative cases — must NOT fire
NEGATIVE=(
    "I have a meeting tomorrow"
    "I had a meeting last week"
    "I'm going to a meeting later"
    "What was that meeting about?"
    "Looking forward to the meeting"
    "I need to prep for a meeting"
    "Did you join the meeting?"
    "Cancel my meeting"
    "Tengo una reunión mañana"
    "Voy a una reunión luego"
    "¿De qué se trata la reunión?"
    "Necesito prepararme para la reunión"
    "what's on my calendar"
    "build a new feature"
)
for p in "${NEGATIVE[@]}"; do
    out=$(run_hook "$p" 2>/dev/null || true)
    if [[ -n "$out" ]]; then
        fail "negative case incorrectly fired: $p (output: $out)"
    fi
done

# 6. Injected payload contains the rule body (vault path preferred)
out=$(run_hook "I just had a meeting")
echo "$out" | grep -q "meeting-workflow.md" || \
    fail "injected payload does not reference meeting-workflow.md (output: $out)"
echo "$out" | grep -q "Meeting workflow stub" || \
    fail "injected payload missing rule body from vault (output: $out)"

# 7. Bypass env var
out=$(run_hook "I just had a meeting" "MEETING_WORKFLOW_BYPASS=1")
if [[ -n "$out" ]]; then
    fail "bypass env var did not suppress injection (output: $out)"
fi

# 8. Bypass via in-prompt token
out=$(run_hook "MEETING_WORKFLOW_BYPASS=1 I just had a meeting")
if [[ -n "$out" ]]; then
    fail "in-prompt bypass token did not suppress injection (output: $out)"
fi

# 9. Empty / missing prompt -> silent exit
out=$(printf '{}' | VAULT_ROOT="$TMP_VAULT" python3 "$HOOK")
if [[ -n "$out" ]]; then
    fail "empty prompt should produce no output (output: $out)"
fi

# 10. Fallback path: no vault rule file, no template -> embedded summary still fires
EMPTY_VAULT="$(mktemp -d)"
mkdir -p "$EMPTY_VAULT/Meta"
touch "$EMPTY_VAULT/Meta/Current Priorities.md"
out=$(printf '{"prompt": "I just had a meeting"}' | \
    VAULT_ROOT="$EMPTY_VAULT" \
    HOME="$EMPTY_VAULT" \
    python3 "$HOOK")
rm -rf "$EMPTY_VAULT"
if [[ -z "$out" ]]; then
    fail "fallback summary did not fire when no rule file exists"
fi
echo "$out" | grep -q "meeting-workflow fallback" || \
    fail "fallback summary missing marker (output: $out)"

echo "PASS: inject-meeting-workflow-on-trigger.py wired + EN/ES triggers fire + negatives don't fire + bypass + fallback"

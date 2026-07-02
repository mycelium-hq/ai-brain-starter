#!/usr/bin/env bash
# ai-brain-auto-update.sh — UserPromptSubmit auto-update for the deployed
# ai-brain-starter checkout. Prints ONE Claude-Code hook JSON object on stdout
# and ALWAYS exits 0 (a UserPromptSubmit hook must never block the turn).
#
# THE REACH GUARANTEE (MYC-720): when the pull moves HEAD, this DEPLOYS the new
# hooks itself (runs scripts/install-hooks-user-level.py, bounded) instead of only
# asking the model to. The prior inline hook delegated the install step to the
# model, so a merged substrate PR silently did NOT run until someone happened to
# re-install by hand — the recurring "deployed checkout 40 -> 131 commits behind,
# nobody noticed" failure. Now: pull that moves HEAD => hooks rewired the same
# turn, by construction.
#
# Safety, all preserved from the prior inline hook and hardened:
#   - Pinnable:      ~/.claude/.ai-brain-starter-pinned present => no-op.
#   - Rate-limited:  runs at most once per ABS_UPDATE_INTERVAL_DAYS (default 6).
#   - Single-flight: atomic mkdir lock so concurrent sessions never double-run.
#   - ff-ONLY:       fetch + `merge --ff-only`. A client's DIRTY tree or DIVERGENT
#                    fork is REFUSED and surfaced for manual merge — never given a
#                    surprise merge commit (the old `git pull` could merge-commit).
#   - Bounded deploy: the install step runs under a wall-clock timeout + nice, so a
#                    hung installer can never wedge the user's prompt.
#   - Fail-open:     any unexpected error emits a valid silent JSON object.
#
# Hermetically testable via env overrides (tests/integration/test_ai_brain_auto_
# update.sh): ABS_SKILL_DIR, ABS_UPDATE_STATE_DIR, ABS_UPDATE_INTERVAL_DAYS,
# ABS_UPDATE_DEPLOY_TIMEOUT.
set +e

STATE_DIR="${ABS_UPDATE_STATE_DIR:-$HOME/.claude}"
SKILL_DIR="${ABS_SKILL_DIR:-$HOME/.claude/skills/ai-brain-starter}"
PIN="$STATE_DIR/.ai-brain-starter-pinned"
LAST="$STATE_DIR/.ai-brain-starter-last-update"
LOCK="$STATE_DIR/.ai-brain-starter-update.lock"
INTERVAL_DAYS="${ABS_UPDATE_INTERVAL_DAYS:-6}"
DEPLOY_TIMEOUT="${ABS_UPDATE_DEPLOY_TIMEOUT:-120}"

# A UserPromptSubmit hook must always print valid JSON. `silent` = the no-op form.
silent() { printf '{"continue":true,"suppressOutput":true}\n'; exit 0; }

# Emit a UserPromptSubmit additionalContext object. $1 = PLAIN message; python3
# does the JSON escaping so backticks, quotes, and newlines in the message can
# never break the JSON (the class the old hand-escaped inline blob risked).
emit_ctx() {
  MSG="$1" python3 - <<'PY' 2>/dev/null || silent
import json, os
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": os.environ["MSG"],
}}))
PY
  exit 0
}

# Portable bounded run (GNU timeout -> gtimeout -> background+poll+kill), niced.
# Returns 124 on timeout, matching GNU `timeout`.
_run_bounded() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then nice -n 19 timeout "$secs" "$@"; return $?; fi
  if command -v gtimeout >/dev/null 2>&1; then nice -n 19 gtimeout "$secs" "$@"; return $?; fi
  nice -n 19 "$@" &
  local pid=$! elapsed=0
  while (( elapsed < secs )) && kill -0 "$pid" 2>/dev/null; do sleep 1; elapsed=$((elapsed + 1)); done
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null; sleep 1; kill -KILL "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
    return 124
  fi
  wait "$pid"; return $?
}

# 0. Pinned -> no-op (the escape hatch; must win before any fetch).
[ -f "$PIN" ] && silent

# 1. Rate-limit: only once per INTERVAL_DAYS. `find -mtime +N` prints the file
#    only when it is older than N days; an ABSENT LAST means "never ran" -> run.
if [ -f "$LAST" ] && [ -z "$(find "$LAST" -mtime +"$INTERVAL_DAYS" 2>/dev/null)" ]; then
  silent
fi

# 2. Single-flight: atomic mkdir lock. A SIGKILL mid-run can't fire the trap and
#    would STRAND the lock, silently disabling updates forever — so first reclaim a
#    lock older than the run could ever take (bounded to DEPLOY_TIMEOUT seconds; 60
#    min is far beyond that). A held-and-FRESH lock is a real concurrent session.
[ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +60 2>/dev/null)" ] && rmdir "$LOCK" 2>/dev/null
mkdir "$LOCK" 2>/dev/null || silent
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
touch "$LAST" 2>/dev/null   # claim this interval up-front (matches prior behavior)

cd "$SKILL_DIR" 2>/dev/null || silent
[ -d .git ] || silent

# 3. Fetch. Network down -> surface the stuck-updater hint, never crash the turn.
if ! git fetch origin main --quiet 2>/dev/null; then
  emit_ctx "AI Brain Starter auto-update: git fetch failed (network down or repo unreachable). The checkout at ~/.claude/skills/ai-brain-starter may be behind origin/main; it will retry next session. No action needed now."
fi

HEAD_SHA="$(git rev-parse HEAD 2>/dev/null)"
ORIGIN_SHA="$(git rev-parse origin/main 2>/dev/null)"
[ -n "$HEAD_SHA" ] && [ "$HEAD_SHA" = "$ORIGIN_SHA" ] && silent   # already current

# 4. ff-ONLY. A dirty tree or a divergent fork cannot fast-forward -> surface a
#    manual-merge hint and STOP; never fabricate a merge commit on a user's fork.
#    TRACKED changes only (--untracked-files=no): untracked files never block a
#    fast-forward, and the updater's OWN runtime artifacts land in the checkout
#    (sync-skills.sh writes .sync.log; CHANGELOG/CLAUDE.md merges leave .bak-*),
#    so counting them would make the updater refuse to pull FOREVER after one run.
if [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; then
  emit_ctx "AI Brain Starter auto-update is BLOCKED: ~/.claude/skills/ai-brain-starter has local uncommitted edits to TRACKED files, so it will not auto-pull (your edits are preserved). To update: cd ~/.claude/skills/ai-brain-starter && git stash && git pull --ff-only origin main && git stash pop, or discard the local changes first."
fi
if ! git merge --ff-only origin/main --quiet 2>/dev/null; then
  emit_ctx "AI Brain Starter auto-update is BLOCKED: ~/.claude/skills/ai-brain-starter has diverged from origin/main (a local fork), so it cannot fast-forward. Your fork is preserved. To merge manually: cd ~/.claude/skills/ai-brain-starter && git pull --rebase origin main (or your preferred strategy)."
fi

CHANGES="$(git log --oneline "${HEAD_SHA}..HEAD" 2>/dev/null | head -20 | tr '\n' ';')"

# 5. Propagate skill content (backs up user customizations before overwrite).
SYNC_OUTPUT="$(bash "$SKILL_DIR/scripts/sync-skills.sh" 2>&1 | tail -20)"

# 6. THE REACH GUARANTEE: deploy the freshly-pulled hooks NOW, bounded, instead of
#    delegating the install to the model. install-hooks-user-level.py is
#    idempotent, backs up settings.json, and rolls back on a JSON parse error.
DEPLOY_NOTE="Hooks were rewired automatically (install-hooks-user-level.py ran clean)."
_run_bounded "$DEPLOY_TIMEOUT" python3 "$SKILL_DIR/scripts/install-hooks-user-level.py" --quiet --fail-on-missing >/dev/null 2>&1
DEPLOY_RC=$?
if [ "$DEPLOY_RC" -eq 124 ]; then
  DEPLOY_NOTE="WARNING: the hook re-install TIMED OUT (${DEPLOY_TIMEOUT}s) and was killed, so newly-added hooks may not be wired yet. Re-run: python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py --quiet --fail-on-missing"
elif [ "$DEPLOY_RC" -ne 0 ]; then
  DEPLOY_NOTE="WARNING: the hook re-install exited ${DEPLOY_RC}, so newly-added hooks may not be wired yet. Re-run it and surface the missing-paths report: python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py --quiet --fail-on-missing"
fi

emit_ctx "AI Brain Starter was auto-updated and hooks were redeployed. Commits: ${CHANGES} Skill sync: ${SYNC_OUTPUT} ${DEPLOY_NOTE} Any changed file was backed up to <file>.bak-YYYY-MM-DD-HHMM first, so local customizations are recoverable. Now, briefly and casually (not a changelog dump): 1) Read ~/.claude/skills/ai-brain-starter/docs/CHANGELOG.md (top entry only) and tell the user in 1-2 plain sentences what changed and why. 2) If the update added rules to the Obsidian Rules or Session Protocol sections of SKILL.md, read the user's vault CLAUDE.md and, for each new or changed rule not already there, offer to merge it: show a short diff, cite the failure mode from CHANGELOG, ask one yes/no question, and on yes back up CLAUDE.md to CLAUDE.md.bak-YYYY-MM-DD-HHMM before editing. 3) If the skill sync backed up any files, mention it so the user knows their customizations are recoverable."

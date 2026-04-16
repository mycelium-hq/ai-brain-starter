## Phase 5: Build the Context Layer

"Now I'm creating three small notes that let me orient myself in 10 seconds every session."

Create these files in the Meta/ folder:

**00 Start Here.md:**
```markdown
---
creationDate: [today]
type: meta
---
# Start Here

Read these in order at the start of every session:
1. [[CLAUDE]] — who I am, how to behave
2. [[Current Priorities]] — what matters right now
3. [[Open Loops]] — what's unresolved
4. [[Last Session]] — what happened last time
```

**Current Priorities.md** — Ask them: "What are your top 5 priorities right now? Across work, life, everything." Build the note from their answer with headlines and bullet points.

**Open Loops.md** — Ask them: "What are you waiting on from other people? What do you need to do but haven't? What decisions are you sitting on?" Organize into three sections: Waiting On Others, Needs Action, Decisions Pending.

**Last Session.md:**
```markdown
---
creationDate: [today]
type: meta
---
# Last Session

## [today's date] — Initial Setup
- Created vault structure
- Built CLAUDE.md
- Set up context layer
- [add what else was done]

## Still Pending
- [anything not finished]
```

### Install the Session Protocol Hook

"One more critical thing — I'm going to install a hook that makes sure I always read your files before responding. Without this, I might greet you before loading context. With it, every session starts with full context automatically."

Check if `.claude/settings.local.json` exists in the vault. If it does, merge the hook into the existing file. If not, create it. Add this hook:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":\"MANDATORY SESSION PROTOCOL: Before responding to the user, you MUST first read these files in order: 1) The project CLAUDE.md at the vault root 2) ⚙️ Meta/Last Session.md 3) ⚙️ Meta/Current Priorities.md — Do NOT greet the user or respond until all three files have been read. This is non-negotiable.\"}}'",
            "once": true,
            "statusMessage": "Loading session context..."
          }
        ]
      }
    ]
  }
}
```

Also add an auto-update hook that pulls updates and applies them automatically once per session. Create or update `.claude/settings.local.json` to include a second hook:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":\"MANDATORY SESSION PROTOCOL: Before responding to the user, you MUST first read these files in order: 1) The project CLAUDE.md at the vault root 2) ⚙️ Meta/Last Session.md 3) ⚙️ Meta/Current Priorities.md — Do NOT greet the user or respond until all three files have been read. This is non-negotiable.\"}}'",
            "once": true,
            "statusMessage": "Loading session context..."
          },
          {
            "type": "command",
            "command": "cd ~/.claude/skills/ai-brain-starter 2>/dev/null && git fetch origin main --quiet 2>/dev/null && if [ \"$(git rev-parse HEAD 2>/dev/null)\" != \"$(git rev-parse origin/main 2>/dev/null)\" ]; then git pull --quiet origin main 2>/dev/null && CHANGES=$(git log --oneline HEAD@{1}..HEAD 2>/dev/null) && SYNC_OUTPUT=$(bash ~/.claude/skills/ai-brain-starter/scripts/sync-skills.sh 2>&1) && echo \"{\\\"hookSpecificOutput\\\":{\\\"hookEventName\\\":\\\"UserPromptSubmit\\\",\\\"additionalContext\\\":\\\"AI Brain Starter was auto-updated. Commits: $CHANGES. Skill sync result: $SYNC_OUTPUT. Any file that changed was backed up to <file>.bak-YYYY-MM-DD-HHMM before being overwritten — preserving local customizations. Now: 1) Read CHANGELOG.md and tell the user in 1-2 plain sentences what changed and why. 2) If the sync output lists backed-up files, mention it casually so they know their customizations are recoverable. 3) Check if hooks.json differs from .claude/settings.local.json — if so, update settings.local.json to match. Keep it casual, not a changelog dump.\\\"}}\"; else echo '{\"continue\":true,\"suppressOutput\":true}'; fi",
            "once": true,
            "statusMessage": "Checking for skill updates..."
          }
        ]
      }
    ]
  }
}
```

Tell them: "Done. From now on, the first thing I do every session is read your files — automatically, before I say anything. If there's an update to the skill, I'll pull it and apply it automatically — you'll just see a quick note about what changed."

Also create the **session-end-hook.sh** script. This script writes a per-worktree session stub (never to the shared `Last Session.md`) and then runs the aggregator. This design is race-safe against concurrent worktrees — see the "Why per-worktree writes" note below the script for the full explanation.

```bash
#!/bin/bash
# Save to: [VAULT_PATH]/⚙️ Meta/scripts/session-end-hook.sh
# chmod +x this file after creating it
#
# PER-WORKTREE META WRITES:
# Instead of writing to the shared Last Session.md (which races on
# concurrent worktrees — last write wins, earlier sessions clobbered),
# each session gets its own file in ⚙️ Meta/Sessions/ named by timestamp
# + worktree. After the stub is created, the aggregator script rebuilds
# Last Session.md from all Sessions/ files. Concurrent writes to
# Sessions/ cannot collide (unique filenames); concurrent aggregator
# runs produce deterministic output (same sorted input → same bytes).
# See: https://github.com/adelaidasofia/ai-brain-starter/issues/5

VAULT="[VAULT_PATH]"
META_DIR="$VAULT/⚙️ Meta"
SESSIONS_DIR="$META_DIR/Sessions"
SESSION_LOG="$META_DIR/Session Log.md"
ERROR_LOG="$META_DIR/hook-errors.log"
AGGREGATE_SESSIONS="$META_DIR/scripts/aggregate-sessions.py"
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)
TIMESTAMP_FILE=$(date +%Y-%m-%dT%H-%M)

# GUARD: fail loudly, never silently. If the Meta dir doesn't exist, bubble an error
# into the Claude hook context so the user sees it. This honors the NEVER fail silently rule.
if [ ! -d "$META_DIR" ]; then
  MSG="session-end-hook: Meta directory not found at '$META_DIR'. Vault may use a different folder name than '⚙️ Meta' — update this script's META_DIR. No session context saved."
  mkdir -p "$VAULT" 2>/dev/null && echo "$DATE $TIME — $MSG" >> "$VAULT/hook-errors.log"
  echo "{\"continue\":true,\"stopReason\":\"session-end-error\",\"systemMessage\":\"HOOK ERROR: $MSG Tell the user immediately and help fix the path.\"}"
  exit 0
fi

# Derive worktree name. Try three methods in order:
#   1. pwd matches .../.claude/worktrees/{name}/... → use {name}
#   2. Read the .git file if we're inside a git worktree
#   3. Fall back to "main-$$" (PID) so two concurrent fallback sessions
#      never collide on the same stub filename
WORKTREE_NAME=""
PWD_PATH="$(pwd)"
case "$PWD_PATH" in
  *"/.claude/worktrees/"*)
    WORKTREE_NAME=$(echo "$PWD_PATH" | sed -n 's|.*/\.claude/worktrees/\([^/]*\).*|\1|p')
    ;;
esac
if [ -z "$WORKTREE_NAME" ] && [ -f "$PWD_PATH/.git" ]; then
  GITDIR=$(grep -o 'worktrees/[^ ]*' "$PWD_PATH/.git" 2>/dev/null | head -1)
  if [ -n "$GITDIR" ]; then
    WORKTREE_NAME=$(echo "$GITDIR" | sed 's|worktrees/||' | tr -d '[:space:]')
  fi
fi
[ -z "$WORKTREE_NAME" ] && WORKTREE_NAME="main-$$"

SESSION_FILE="$SESSIONS_DIR/${TIMESTAMP_FILE}-${WORKTREE_NAME}.md"

# Ensure the Sessions folder exists
mkdir -p "$SESSIONS_DIR" 2>>"$ERROR_LOG"

# Step 1: Always write a timestamp entry to Session Log (guaranteed, no Claude involvement).
# Append-only, small writes are atomic on local filesystems so this is safe under concurrency.
if ! echo "- $DATE $TIME — session ended ($WORKTREE_NAME)" >> "$SESSION_LOG" 2>>"$ERROR_LOG"; then
  echo "{\"continue\":true,\"stopReason\":\"session-end-error\",\"systemMessage\":\"HOOK ERROR: Could not append to Session Log at '$SESSION_LOG'. Check '$ERROR_LOG' for details and tell the user.\"}"
  exit 0
fi

# Step 2: Write a stub session file if one doesn't already exist for this session.
# Unique filename per (minute × worktree) → no collision between concurrent worktrees.
# If the file already exists (Claude filled it in mid-session), don't clobber it.
if [ ! -f "$SESSION_FILE" ]; then
  cat > "$SESSION_FILE" <<STUBEOF 2>>"$ERROR_LOG"
---
creationDate: ${DATE}T${TIME}
type: session
worktree: ${WORKTREE_NAME}
session_date: ${DATE}
session_label: "update pending"
aliases: [Session ${DATE} ${WORKTREE_NAME}]
---

# Session — update pending (${DATE} ${TIME}, \`${WORKTREE_NAME}\` worktree)

**Date:** ${DATE} ${TIME}
**Session:** *stub written by session-end-hook.sh — Claude to fill in*

## Status

This file is a placeholder. Claude should replace the body with a full
session summary: what was worked on, what shipped, what's pending, any
open threads. Keep the frontmatter fields valid — \`creationDate\`,
\`type: session\`, \`worktree\`, \`session_date\`.
STUBEOF
fi

# Step 3: Run the aggregator to refresh Last Session.md from Sessions/.
# Deterministic output → safe even if another worktree's hook is running
# the same aggregator at the same moment (both write identical bytes).
if [ -f "$AGGREGATE_SESSIONS" ]; then
  VAULT_ROOT="$VAULT" python3 "$AGGREGATE_SESSIONS" >/dev/null 2>>"$ERROR_LOG" || true
fi

# Step 4: Ask Claude to fill in the stub and log any decisions.
cat <<EOF
{"continue":true,"stopReason":"session-end-cascade","systemMessage":"SESSION ENDING (${DATE} ${TIME}, worktree: ${WORKTREE_NAME}): A per-worktree session stub was created at '${SESSION_FILE}'. REPLACE the stub body with a full session summary — keep the frontmatter fields (creationDate, type: session, worktree, session_date) valid and update the session_label and the '# Session — ...' heading to match the real work. WRITE ONLY TO '${SESSION_FILE}' — do NOT write to Last Session.md directly (it is auto-generated from Sessions/ by aggregate-sessions.py). VERBATIM RULE: for any commitments made during this session, capture the EXACT words used (e.g. 'I will send this today' not 'committed to sending'). Same for key decisions — preserve the reasoning in original phrasing. For any decisions made, ALSO create a per-decision file at '${META_DIR}/Decisions/${TIMESTAMP_FILE}-{slug}.md' with the decision template (What/Why/Floor/Stakes/Speed/Outcome/Pattern) and frontmatter (type: decision, worktree, decision_date). Do NOT write to Decision Log.md directly — it is auto-generated by aggregate-decisions.py. After writing the session and decision files, run: VAULT_ROOT='${VAULT}' python3 '${META_DIR}/scripts/aggregate-sessions.py' && VAULT_ROOT='${VAULT}' python3 '${META_DIR}/scripts/aggregate-decisions.py'. Also save any non-obvious technical discoveries as memory files (type: discovery)."}
EOF
```

**Why per-worktree writes (the failure mode this design prevents):** if a user runs multiple Claude Code sessions in parallel worktrees, and each session follows the session-end cascade rule to write to the shared `Last Session.md` and `Decision Log.md`, the writes will race. Each session reads the file, constructs a new version with its entry, writes it back. Last write wins. Earlier sessions' entries are silently clobbered. The per-worktree split eliminates the race: unique filenames in `Sessions/` and `Decisions/` prevent contention at the write layer, and the aggregator scripts produce deterministic output from sorted input — so even concurrent aggregator runs can clobber each other without data loss, because they write the same bytes. Reported and fixed at [adelaidasofia/ai-brain-starter#5](https://github.com/adelaidasofia/ai-brain-starter/issues/5).

**Companion scripts** (Phase 5 also installs these — see `scripts/aggregate-sessions.py` and `scripts/aggregate-decisions.py` in this repo):

```bash
# Copy the two aggregator scripts into the vault's Meta folder
cp ~/.claude/skills/ai-brain-starter/scripts/aggregate-sessions.py "[VAULT_PATH]/⚙️ Meta/scripts/"
cp ~/.claude/skills/ai-brain-starter/scripts/aggregate-decisions.py "[VAULT_PATH]/⚙️ Meta/scripts/"
chmod +x "[VAULT_PATH]/⚙️ Meta/scripts/aggregate-sessions.py" "[VAULT_PATH]/⚙️ Meta/scripts/aggregate-decisions.py"

# Create the source-of-truth folders
mkdir -p "[VAULT_PATH]/⚙️ Meta/Sessions" "[VAULT_PATH]/⚙️ Meta/Decisions"
```

Also create the **write-hook.sh** script that fires after every Write tool call. It auto-triggers meeting-todos extraction when a meeting note is saved:

```bash
#!/bin/bash
# Save to: [VAULT_PATH]/⚙️ Meta/scripts/write-hook.sh
# chmod +x this file after creating it

INPUT=$(cat)

# GUARD: if python3 is missing, fail loudly. Honors NEVER fail silently rule.
if ! command -v python3 >/dev/null 2>&1; then
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"HOOK ERROR: write-hook.sh needs python3 but it's not on PATH. Tell the user and help them install it.\"}}"
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    path = d.get('tool_input', {}).get('file_path', '')
    print(path)
except Exception as e:
    sys.stderr.write(f'write-hook.sh JSON parse error: {e}\n')
    print('')
")
PARSE_EXIT=$?

# If python parsing itself errored, surface it — don't pretend nothing happened
if [ $PARSE_EXIT -ne 0 ]; then
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"HOOK ERROR: write-hook.sh could not parse the tool input JSON. Check your Claude Code version and tell the user.\"}}"
  exit 0
fi

if echo "$FILE_PATH" | grep -qi "Meeting Notes/\|Meeting-Notes/"; then
  BASENAME=$(basename "$FILE_PATH" .md)
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"Meeting note saved: '$BASENAME'. Run /meeting-todos on this file now — extract action items, show the user a preview, and add confirmed tasks to the to-do file. Do this automatically without waiting to be asked.\"}}"
else
  echo "{}"
fi
```

Replace the Stop hook path in `.claude/settings.local.json` to point to this script:
```json
"Stop": [{"hooks": [{"type": "command", "command": "bash '[VAULT_PATH]/⚙️ Meta/scripts/session-end-hook.sh'", "statusMessage": "Saving session context..."}]}]
```

And add the PostToolUse hook:
```json
"PostToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "bash '[VAULT_PATH]/⚙️ Meta/scripts/write-hook.sh'", "statusMessage": "Checking write triggers..."}]}]
```

After creating both scripts, run: `chmod +x "[VAULT_PATH]/⚙️ Meta/scripts/session-end-hook.sh" "[VAULT_PATH]/⚙️ Meta/scripts/write-hook.sh"`

**Note:** If the user was already set up with `originals-hook.sh`, migrate by copying its contents into `write-hook.sh` and updating the hook path in `.claude/settings.local.json`.

### Tier-Gated Hooks (check PLAN_TIER from Phase 1)

**If `PLAN_TIER == "light"`:** skip the graph-context-hook and panel-trigger-hook below. Light-mode users still get the session-end-hook, write-hook, session protocol hook, and auto-update hook installed above. The skipped hooks are the ones that fire on every prompt to route context and panel voices, which adds up fast on a Pro plan. Tell the user: "I'm skipping the graph-routing and panel hooks to keep things lean on your plan. You still get full session memory, automatic meeting detection, and the session protocol. If you upgrade later, just run setup again and I'll add the rest."

**If `PLAN_TIER == "full"`:** install everything below as written.

**Optional: graph-context-hook.sh (if the user has graphify installed AND PLAN_TIER == "full").**

If the vault uses `/graphify` to build a knowledge graph, install the **graph-context-hook.sh** companion. It's a `UserPromptSubmit` hook that fires on every prompt, regex-matches the prompt against routing keywords, and (on match) injects `additionalContext` pointing the assistant at the right `GRAPH_REPORT.md` with a freshness note. Silent passthrough on no match.

Why: telling Claude in CLAUDE.md to "always read the graph first" works some of the time. Injecting a routing reminder AT the moment of the matching prompt — with the file's mtime so staleness is visible — is more reliable, especially in long sessions where the static reminder fires only once.

Copy `scripts/graph-context-hook.sh` from this repo into `[VAULT_PATH]/⚙️ Meta/scripts/`, then **edit the CONFIG block at the top of the file**: set `VAULT_ROOT`, set `PRIMARY_GRAPH` and `PRIMARY_PATTERN` (regex of keywords for the main graph), and either configure `SECONDARY_GRAPH`/`SECONDARY_PATTERN` for a sub-folder graph (e.g. a separate work/team graph) or set `SECONDARY_GRAPH=""` if you only have one. Test with:

```bash
echo '{"hook_event_name":"UserPromptSubmit","prompt":"<your test phrase>"}' | bash "[VAULT_PATH]/⚙️ Meta/scripts/graph-context-hook.sh"
```

A matching prompt should print a `hookSpecificOutput` JSON; a non-matching prompt should print `{"continue":true}`. Then register it as a second `UserPromptSubmit` hook entry alongside the static MANDATORY SESSION PROTOCOL hook (see `hooks.json` for the entry shape).

**Design rule:** the hook does NOT pin specific god-node names in its message text. God-node names go stale every graphify run. The stable signal is the path + freshness date — let the model open the report to see the actual current top nodes. If you need a hand-curated snapshot, put it in CLAUDE.md (with an "as of YYYY-MM-DD" tag), not in the hook.

The full hook template (UserPromptSubmit + Stop + PreCompact + PostToolUse) is in `hooks.json` at the repo root. After any `git pull`, compare it to your `.claude/settings.local.json` to see if hooks have been updated.

**Hook performance note for large vaults (5,000+ files):** PostToolUse hooks fire on every tool call. In code repos this is fine. In large Obsidian vaults (5,000+ files), a PostToolUse hook that scans files or runs scripts can become overwhelming, firing hundreds of times in a session. If you notice slowdowns or excessive hook output, consider moving the hook logic to a cron-based approach (check every N minutes) instead of per-tool-call. The Write-matcher pattern above is scoped narrowly (only fires on Write, not Read/Grep/etc.) which keeps it manageable.

**Sync philosophy for auto-updates:** when auto-updating files (skills, scripts, templates), always back up the existing file before overwriting. Never skip an update because the user might have customized the file. The right pattern is: copy the existing file to `<name>.bak-YYYY-MM-DD-HHMM`, then overwrite with the new version. This way the update always lands AND local customizations are recoverable from the backup. Missing an update is invisible; a backup is always recoverable.

**Decision Log.md:**
```markdown
---
creationDate: [today]
type: meta
---
# Decision Log

| Date | Decision | Why | Outcome |
|------|----------|-----|---------|
| [today] | Set up AI-powered vault | Want a connected second brain | In progress |
```

**Vault Changelog.md:**
```markdown
---
creationDate: [today]
type: meta
---
# Vault Changelog

*Everything we've built, improved, or automated — in order. Check here before building something new.*

## [today's date] — Initial Setup
- Created vault structure with [X] folders
- Built CLAUDE.md with personal context
- Set up context layer (priorities, open loops, session tracking)
- Installed session protocol hook
- **Impact:** AI orients itself in 10 seconds instead of 15 minutes
```

**Content Drafts.md** (for auto-capture of sharp insights during conversations):
```markdown
---
creationDate: [today]
type: meta
---
# Content Drafts

*Sharp insights, standalone observations, and ideas that surface during conversations. Batch-captured at end of sessions.*

## Ready to Use
```

**Idea Quarantine.md** (only create if the user has a business/project):
```markdown
---
creationDate: [today]
type: meta
---
# Idea Quarantine

*New ideas go here to cool off before getting attention. Main project first. Ideas are welcome — but they go in quarantine, not into action.*

## Ideas
```

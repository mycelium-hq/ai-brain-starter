---
type: rule
purpose: Session close protocol. Run before goodbye or context compaction.
trigger: User signals session end OR context compaction imminent
---

# Session close protocol

Run BEFORE goodbye or compaction. Every phase runs every session. Report zeros ("0 decisions, 0 delegations"), never skip silently.

**Skip condition:** <5 user messages, no decisions/info/learnings.

**Closing signals:** "bye", "thanks that's all", "done", "good night", "ttyl", "wrapping up", `/wrap-up`, or equivalent in any language.

## Model

Switch to a cheaper/faster model (Sonnet-class) before starting this protocol. The session close is structured, write-heavy work, scanning, filing, batch writes, running aggregators. That is not judgment-call territory. Announce the switch so the user knows what model is running the close.

## Phase 0: Timestamp

Run `date "+%Y-%m-%d %I:%M %p"`. Reuse this for ALL writes (session file, time tracking, to-do dates, session captures entries).

## Phase 1: Single-pass conversation scan

One pass through the conversation, seven output buckets. Compose everything in memory before writing anything.

**Pattern auto-detection (silent).** If your vault has a `/patterns` skill, evaluate its triggers (tool friction, user correction, dead-end recovery, discovery). If 1+ fires, surface one suggestion. Don't auto-run.

**Belief shift check.** "What does the user believe differently now?" If anything, that's the first journal seed.

**Journal seeds.** Verbatim quotes where the user revealed a belief, changed their mind, made an observation, or said something new. Never reworded. Emotional signals tagged `[emotional]`. Destination: a single Session Captures file (e.g. `Meta/Session Captures.md`) with date + context tag.

**Public-writing note candidates (if the user publishes).** Destination: a staging queue file, never published-content files directly.

**Forcing function for public writing. Execute in order before writing ANY note:**
1. Read 3 random notes from the user's published work. Full notes, not scanned.
2. Classify the draft against the user's actual format types.
3. **Structural match test.** Does the draft structurally resemble the 3 notes you just read? Sentence cadence, opening pattern, ratio of observation to personal detail, ending structure?
4. **Kill conditions (do not write the note if any are true):**
   - Starts with "I" + something that happened today ("I checked", "I shipped", "I felt")
   - Startup-blogger / LinkedIn-thought-leader tone
   - "Look at me" ego framing
   - Requires context from the session to land
   - Reads like diary instead of universal observation
5. **Filter test before filing:** Could this live in the user's published file without anyone knowing where it came from? If no, drop it.

**Why this matters.** Taste is not computable through abstract instruction. The model must pattern-match against concrete exemplars or it produces generic content-marketing prose.

**Actionable content.** Strategy ideas, product insights, pitch angles, partnership leads, writing seeds. File to where it belongs. No clear home: Session Captures under an "Ideas & Strategy" heading.

**To-dos.** Personal: a personal to-do file. Team/project: relevant project to-do file. Format: `- [ ]` under `## From [context] - YYYY-MM-DD`.

**To-do reconciliation.** Check off (`- [x]`) completed items in Current Priorities, to-do files, team files. Match by substance. Partial: leave unchecked, append progress note.

**Decision outcome backfill.** Check decision files with blank `Outcome:`. If resolved this session, fill in.

**Decision logging.** New decisions: create a dated decision file (What/Why/Stakes/Speed/Outcome placeholder).

**Delegations.** Items for others (teammates, contractors): add to team to-do with `@Name`. Draft the message, offer to send.

**Contractor task clarity gate.** If the user works with contractors or non-technical teammates, verify every task assigned this session contains: a wikilink to a playbook AND the linked doc covers 4 fields: **Source** (where input lives), **Location** (where output goes), **Shape** (what done looks like), **Channel** (how to report back). Naked tasks ("do X") get sent back for enrichment before close.

**Orphan playbook scan (prevents invisible work).** Any playbook or instructions doc created/modified this session must be referenced by a live (unchecked) task in the relevant to-do file. Orphan playbooks = invisible work: the contractor never sees them and never executes. Stop-ship defect.

**Issue tracker entries.** If any issues/PRs were filed this session in GitHub/Linear/Jira: log to a single open-issues file.

**Time tracking entry.** Format: `- HH:MMam/pm - HH:MMam/pm | Category | Brief`. Categories can be whatever the user uses (Writing, Work, Vault, Personal, Admin). Verify start < end.

## Phase 2: Batch writes

All accumulated edits written in parallel. No interleaved read-write cycles.

**Session file.** Write to `Meta/Sessions/{timestamp}-{worktree}.md`. Never write to an auto-generated "Last Session" file directly. Include: what happened, key outputs, decisions, delegations, pending items. Verbatim rule: capture commitments in exact words used.

**Per-worktree writes (race-safety).** Decisions: `Meta/Decisions/{timestamp}-{slug}.md` with frontmatter (type, worktree, decision_date, stakes, speed, outcome).

**Vault firewall.** Personal content → personal vault. Team/business content → team vault. Ambiguous defaults to personal.

**Append, never overwrite.** Wikilink people, projects, concepts. Enough context for 6 months.

**Aggregators (foreground, sequential).** Run aggregator scripts after writes complete. NO backgrounding. They take a few seconds combined. Backgrounded aggregators racing with a git commit can corrupt `.git/index`; foreground-sequential is the only way to prevent it.

```bash
VAULT_ROOT="<vault>" python3 "<vault>/Meta/scripts/aggregate-sessions.py"
VAULT_ROOT="<vault>" python3 "<vault>/Meta/scripts/aggregate-decisions.py"
```

## Phase 2b: Git snapshot (targeted, never full-tree, foreground only)

After Phase 2 writes AND aggregators complete, commit the session's changes as a local snapshot. **Run foreground only**, never use `run_in_background` for git operations in session close. Git creates `.git/index.lock` during writes; backgrounding races with anything else touching the index and can truncate it.

**Cross-session lock contention (the real cause of every "lock is in the way" failure).** Multiple agent sessions on the same machine share ONE `.git/`. When several close at once, they queue at `.git/index.lock`. The lock is a legitimate mutex, not a bug. If you encounter it:

1. **NEVER `rm -f .git/index.lock` blindly.** Run `lsof "<vault>/.git/index.lock"` first. If a process owns it, another session is mid-commit, WAIT. Only remove if no process is attached AND the lock is older than 60s (proven orphan).
2. **NEVER background a git operation** (`run_in_background: true`, trailing `&`). Background git racing with another session's git can truncate the index.
3. **NEVER `git add -A`, `git add .`, or any unscoped form.** Sweeping commits steal staged files from other sessions and bloat your commit. Each session commits ONLY its own paths, listed explicitly.

**Use the wrapper, not raw git.** Copy `~/.claude/skills/ai-brain-starter/scripts/vault-safe-commit.sh` into your vault's `Meta/scripts/` (or any path on disk). It handles lock waiting, stale-lock detection, and a vault-wide mutex. For defense-in-depth, the starter ships three optional gates you can install:

1. PreToolUse hook `~/.claude/skills/ai-brain-starter/hooks/block-raw-vault-git.py` — blocks raw mutating git (`add`/`commit`/`checkout`/`reset`/`merge`/`rebase`/`restore`/`switch`/`stash`) inside the vault before Bash runs. Copy into `~/.claude/hooks/` and register in settings.local.json. Emergency bypass: prefix the command with `GIT_VAULT_BYPASS=1`.
2. The wrapper itself acquires `/tmp/vault-commit-<hash>.lock` to serialize concurrent wrapper calls.
3. For defense-in-depth against commits that sneak past the PreToolUse hook (terminal, editor, cron), you can add a native `.git/hooks/pre-commit` that acquires the same `/tmp/vault-commit-<hash>.lock` before allowing any commit. Left as a bring-your-own snippet tailored to your vault path.

None of these are auto-installed. Install only if your vault is git-tracked AND you run multiple concurrent sessions against it.

```bash
cd "$VAULT_ROOT" && \
  bash scripts/vault-safe-commit.sh \
    "session: <worktree-slug> <date>" \
    "Meta/Sessions/<this-session-file>.md" \
    "Meta/Decisions/<any-new-decision-files>" \
    "Meta/rules/<any-edited-rule-files>" \
    "Meta/Session Captures.md" \
    "To-dos/Get to-do.md" \
    "<any-other-specific-paths-touched-this-session>"
```

Rules:
1. List every path explicitly. No wildcards that expand beyond what you edited.
2. If a path goes through a symlink to cloud storage (Google Drive, iCloud Drive, Dropbox), `git add` through the symlink fails ("beyond a symbolic link"). Cloud storage handles that vault's version history separately. Skip.
3. If the vault has no git remote, it is a local-only snapshot repo. Never attempt `git push`.
4. Worktree branches share HEAD with master once master is committed, no merge step needed. Delete the worktree branch after the session with `git worktree remove` if done.
5. If the session made NO tracked-file edits, skip this phase entirely. Don't stage speculatively.

### Recovering from index corruption

If `git add` or `git commit` fails with "index file smaller than expected" or similar corruption:

1. Working tree is safe, every file is still on disk.
2. Run `git reset` (NOT `--hard`) at vault root. Rebuilds `.git/index` from HEAD.
3. Re-stage with explicit paths (or rerun `vault-safe-commit.sh`).
4. Commit normally.

Corruption happens when `.git/index.lock` is removed during a real write. Never remove the lock unless: (a) it is 0 bytes AND (b) no `git add/commit/checkout/reset/merge/rebase` process is running. Use `lsof .git/index.lock` to verify. Or call `vault-safe-commit.sh`, it handles this automatically.

## Phase 3: Verification + propagation

**Change impact audit (conditional).** Only if session modified rules, scripts, skills, hooks, schedules, paths, CLAUDE.md. Verify: paths resolve, skills trigger, hooks fire, cross-refs valid. Fix before closing.

**Execution-session functional audit (mandatory when session shipped code/docs to a public repo users download).** Personal-data scrub + `git push` is NOT the audit. Before claiming done, verify shipped artifacts actually work for a stranger:

1. **Syntax:** `python3 -m py_compile` every new/modified `.py`. `bash -n` every new/modified `.sh`. JSON-validate every new/modified `.json`.
2. **Path resolution:** grep every absolute path in docs/templates against the actual filesystem. Every path must resolve.
3. **Orphan scan:** grep every new file under `hooks/`, `scripts/`, `templates/` against the docs that should reference it (README, install phases, bootstrap). Unreferenced = invisible to users = shipped-but-unusable.
4. **Smoke test:** invoke each new script with `--help` or minimal args. It should at least parse without crashing.
5. **Misleading copy:** search shipped docs for phrases that imply auto-installation. If the artifact isn't auto-installed, rewrite to "opt-in, install via:".
6. **Relative link check:** resolve every `](...)` relative link in modified README/docs against the filesystem.

Report: "Audit: N python OK, M bash OK, K JSON OK, P paths resolved, Q orphans found + fixed, R smoke tests passed." Never claim "everything works" without running these.

**Public repo propagation check.** If anything qualifies for a public companion repo: ASK first. Strip personal data. Update CHANGELOG if the repo has one.

## Summary format

Single message: "Filed X journal seeds, Y note candidates, Z to-dos (yours: A, delegations: B), logged N decision(s), checked off M items, filed P content items. Anything I missed?"

**DO NOT SKIP ANY PHASE.** Run before compacting.

---
creationDate: {{DATE}}
type: rule
purpose: Session close protocol — full cascade preserved, hook-orchestrated. Run before goodbye or context compaction.
trigger: User signals session end OR context compaction imminent
supersedes: session-end-cascade.md (deprecated; this file is the canonical source)
---

# Session close protocol

The session close cascade is layered across three coordinated mechanisms. **You don't need to read this file when the cascade fires** — the `detect-closing-signal.py` hook injects all paths and instructions into your context automatically. This file exists for documentation, debugging, and the rare manual run.

## Architecture

| Layer | Mechanism | Responsibility |
|---|---|---|
| 1 | `hooks/detect-closing-signal.py` (UserPromptSubmit) | Detect close signal; pre-resolve timestamp/worktree/paths; pre-build session file shell; pre-fetch decisions-with-empty-Outcome list; write marker file; inject cascade context for the model |
| 2 | The model's turn | Run Phase 0b incomplete-work check, then scan conversation and write captures to pre-built paths in one batched tool-call block. No tool-call narration. |
| 3 | `scripts/session-end-hook.sh` (Stop) | If marker exists: run `session-close-fallback.py` only when model bailed (empty body), then aggregators, targeted git snapshot, retention cleanup, marker cleanup. If no marker: cheap-path turn-end log only. |

**Skip condition.** When the user has fewer than 5 messages this session AND no captures detected, the hook injects a "trivial — skip" instruction. The model says a clean goodbye, the Stop hook still logs a timestamp.

**Closing signals.** EN/ES/PT language packs at `templates/closing-signals/*.json`. Includes explicit slash commands (`/close`, `/wrap-up`, `/bye`, `/cerrar`, `/tchau`), high-confidence natural-language closes ("bye", "thanks that's all", "good night", "ttyl", "chao", "nos vemos", "tchau", "valeu"), emoji-only farewells, and ambiguous signals ("ok", "cool", "perfect") that trigger a one-line confirmation before the cascade. False-positive guards exclude code blocks, quoted "bye", "done with X" mid-conversation transitions, and meta-questions about close signals.

**Custom signals.** Users can extend per-language via `closingSignals.custom: ["k thx", "okkk"]` in CLAUDE.md frontmatter or inline.

## Phase 0b — Incomplete-work gate (model, FIRST)

Before any writes. Surface anything that did not finish this session:

- Background tasks still running (`run_in_background: true` Bash calls).
- Tasks killed mid-run (any `TaskStop` or pipeline phase aborted).
- Pipeline phases that didn't complete (graphify stage, second-brain-mapping phase, imports/exports that errored).
- Commands that errored and were not retried.

For each, ask the user: "Finish now, or close and leave for next session?" Wait for the call. Do NOT proceed until every incomplete item is finished or explicitly deferred.

If nothing is incomplete: say "No incomplete work" and continue.

## Phase 1 — Single-pass conversation scan (model)

One pass through the conversation. All output buckets composed in memory before writing.

**Belief shift check.** Does the user end the session believing something different? If yes, that's the first journal seed.

**Journal seeds.** VERBATIM quotes where the user revealed a belief, observation, or change of mind. Tag emotional ones `[emotional]`. Never reword. Destination: `Session Captures.md`.

**Writing note candidates.** If the user has a Substack/blog setup configured in CLAUDE.md, apply kill conditions before drafting:
- No "I" + something that happened today ("I checked", "I shipped", "I felt")
- No startup-blogger / LinkedIn-thought-leader tone
- No "look at me" ego framing
- Must read as universal observation, not diary
- Must stand alone without session context
- If bilingual configured (e.g., EN+ES Substack pair), draft both.
- File to user's Content Drafts file (path defined in CLAUDE.md) or Captures under "Ideas & Strategy."

**Actionable content.** Strategy fragments, product insights, partnership leads. File to canonical location per the vault map; default to Captures.

**To-dos** (separated by canonical destination — personal vs team). Apply self-contained capture rule: every task includes a `[Context prefix in brackets]` OR a wikilink OR a direct URL OR a file path so it stands alone when surfaced out of session context.

**To-do reconciliation.** Check off (`- [x]`) completed items in Get to-do, team to-do, Current Priorities. Match by substance, not exact wording. Partial completion: leave unchecked, append progress note.

**Decision logging.** New decisions: create per-decision file in `Decisions/{timestamp}-{slug}.md` with frontmatter (`type: decision`, worktree, decision_date, floor, stakes, speed, outcome placeholder, pattern placeholder). Include the reasoning, not just the outcome.

**Decision outcome backfill.** The hook pre-fetches files in `Decisions/` with blank Outcome (listed in the injected context). If this session resolved any of those, fill in the Outcome.

**Delegations.** Items for others: add to team to-do with `@Name`. Draft the message (Slack, WhatsApp, email) the user can send in one click.

**GitHub issues.** If any filed this session: log to `Open GitHub Issues.md`.

**Time tracking entry** (if vault uses it, per CLAUDE.md). Format: `- HH:MMam/pm - HH:MMam/pm | Category | Brief`. Categories defined in the time-tracking file. Verify start < end. Infer category from conversation.

## Phase 2 — Batch writes (model, single tool-call block)

All accumulated edits written in parallel. No interleaved read-write cycles. No tool-call narration.

**Session file.** Fill the pre-built shell at the path the hook injected. Sections (`## What happened`, `## Decisions`, `## Captures`, `## To-dos filed`, `## Delegations`, `## Pending / incomplete`) are already there — just fill the bodies. Verbatim rule: capture commitments in the user's exact words.

**Per-decision files.** Create at the pre-resolved Decisions/ path with frontmatter.

**Append, never overwrite.** Wikilink people, projects, concepts. Enough context for 6 months.

**Vault firewall.** Personal to personal vault. Team/business to team vault. Ambiguous defaults to personal. Never let personal content leak into the team vault.

## Phase 3 — Final summary (model, one line)

"Filed X seeds, Y to-dos (yours: A, delegations: B), Z decisions, checked off M items. Anything I missed?"

Then say goodbye in the user's primary language. Warm, no machinery narration.

## Phase 4 — Hook finalization (automatic, runs after model's turn ends)

The Stop hook runs without your involvement:

1. **Haiku fallback.** If the session file body is still empty (you bailed), `scripts/session-close-fallback.py` calls Haiku 4.5 with the conversation transcript and fills the file. Flagged for next-session review. Requires `ANTHROPIC_API_KEY`; without it, leaves a "fallback unavailable" notice + partial-flag for `recover-last-close.py` to retry later.
2. **Aggregators.** `aggregate-sessions.py` rebuilds Last Session.md, `aggregate-decisions.py` rebuilds Decision Log.md.
3. **Targeted git snapshot.** Only if the vault is git-tracked. Stages explicit paths only (session file, decision files, captures file, aggregated views). Never `git add -A`. Waits up to 60s for any concurrent index lock. No push (vaults are typically local-only snapshot repos). **Drift scan first:** also `git status -s` the rules/, sessions/, decisions/, and captures-file paths to catch pre-existing dirty state from prior closes that never committed. Append matched paths to the explicit list. Catches edits made in a previous session whose own cascade missed them. Failure mode is silent until a worktree archive prompt threatens to discard the residue.
4. **Retention cleanup.** Stubs older than 7 days deleted; substantive sessions older than 7 days archived to `Sessions/Archive/`.
5. **Marker cleanup.** Removes `~/.claude/.closing-signal-{session_id}.json`.

## Recovery + rollback

- `python3 scripts/recover-last-close.py` — if a partial-flag exists (model bailed + no API key), retry the fallback now that the API key is available, OR open the file in `$EDITOR` for manual completion.
- `python3 scripts/recover-last-close.py --list` — list all partial flags.
- `python3 scripts/undo-last-close.py` — move the most recent session file + co-located decisions to an `.undone-{timestamp}/` archive folder, optionally revert the git commit, re-run aggregators. Always interactive unless `--yes`.

## Manual invocation (for power users)

If you want to trigger the cascade explicitly without saying "bye" out loud, type any of these and the detector treats them as explicit close commands:

- `/close`, `/wrap-up`, `/bye`, `/done`, `/finish`
- `/cerrar`, `/terminar`, `/chao`
- `/fechar`, `/encerrar`, `/tchau`

These are not registered slash commands — they are detector keywords. Typing them in any conversation fires Layer 1 the same as a natural-language close, with explicit-confidence routing (no ambiguity check).

## Configuration (CLAUDE.md frontmatter or settings)

- `closingSignals.custom: ["..."]` — extra patterns to match as explicit closes.
- `closeDetection: regex | hybrid` — `hybrid` adds a Haiku fallback for ambiguous prompts (requires `ANTHROPIC_API_KEY`).
- `sessionCloseFeedback: silent | minimal | verbose` — visibility of the cascade. Default `silent`. `minimal` adds one summary line. `verbose` shows phase-by-phase.

## Skip + opt-out

- Trivial sessions (<5 user messages, no captures) skip the cascade automatically.
- To temporarily disable detection in a session: `export CLOSING_SIGNAL_DETECTION=off` in the shell where Claude Code launched.
- To uninstall entirely: remove the UserPromptSubmit + Stop hook entries from `hooks.json` and the `hooks/detect-closing-signal.py` script.

## Errors

All hook errors fail-open (never block the user) and are logged to `~/.claude/logs/session-close-errors.log` for debugging. Common issues:

- "fallback unavailable" — `ANTHROPIC_API_KEY` not set; run `recover-last-close.py` later.
- "git index.lock held >60s" — concurrent session is mid-commit; snapshot skipped, will retry next close.
- "language pack not found" — check `templates/closing-signals/*.json` exists and `CLOSING_SIGNAL_LANGS` env var is correct.

## Telemetry (opt-in)

Set `cascadeTelemetry: true` in CLAUDE.md frontmatter to log anonymized cascade-fire rate, completion rate, and language-match distribution to `~/.claude/logs/cascade-telemetry.jsonl`. Useful for the maintainer's quarterly runbook iteration. No content captured, only structural counts.

## Why this rule exists

Prior architecture relied entirely on the model "noticing" closing signals and choosing to read this rule file before responding. Three brittle steps (notice signal → read rule → execute), any one failing silently. The new architecture moves detection to a deterministic hook (Layer 1), preserves all model-required creative work in Phase 1, and adds a Haiku backstop (Layer 3) that guarantees no silent loss even if the model bails. The full cascade — every capture from the prior 7-phase spec — is preserved.

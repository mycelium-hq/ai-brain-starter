---
name: changelog
description: What's new in AI Brain Starter — plain English, no jargon
---

# What's new

*Every time you update (`git pull` or tell Claude "update the ai-brain-starter skill"), check here to see what changed and why.*

---

## 2026-04-30 — Hooks now install at USER level (closes #6, fires universally in worktrees)

**Who this affects:** anyone whose Claude Code work happens in git worktrees (most active users do, since each `claude/<branch>` worktree is how feature work is isolated).

**The bug:** ai-brain-starter hooks were installed at project level (`<vault>/.claude/settings.json`). When Claude Code runs from inside `<vault>/.claude/worktrees/<name>/`, project-level hooks silently don't fire. UserPromptSubmit hooks specifically — the ones that detect "bye", catch malformed YAML at write time, log skill usage — would never get a chance to run. Reports of "I said bye and the cascade didn't trigger" had this as a quiet root cause even after the cascade detection itself was fixed.

**The fix is structural:** hooks now install at user level (`~/.claude/settings.json`), which fires universally regardless of cwd. The hooks themselves are unchanged — only the install path moved.

### What shipped

- **`scripts/install-hooks-user-level.py`** — idempotent installer that reads `hooks.json` (the canonical source-of-truth in this repo) and merges entries into `~/.claude/settings.json` while preserving every existing user-defined hook. Custom hooks are never touched. Backup at `~/.claude/settings.json.bak-{timestamp}-abs` before any edit. Post-write JSON validity verified; auto-rollback on parse error. Fingerprint-based matching means re-running the installer is a no-op when nothing has changed.
- **`hooks/migrate-to-user-level.py`** — SessionStart hook that detects existing project-level installs and prompts the user once to migrate. Tracks state per-vault at `~/.claude/.abs-migration-state.json` so the prompt fires at most once per vault. Easy opt-out: `migrationDeclined: true` in CLAUDE.md frontmatter.
- **`scripts/test-hooks-in-worktree.sh`** — regression test that creates a temp git repo + worktree, fires the detector hook from inside the worktree, and asserts it responds correctly. **6/6 checks pass:** main-worktree firing, child-worktree firing, worktree name derivation, installer preservation of custom hooks, installer adding ABS hooks, installer idempotency. CI-runnable.
- **`bootstrap.sh`** updated with `--install-hooks-user-level` flag (manual escape hatch) AND inline call at the end of normal install runs (so new users get user-level hooks by default without thinking about it).
- **`docs/HOOKS_INSTALL.md`** — full architecture doc covering install/migration/troubleshooting/why.
- **`hooks.json`** — added the migrate-to-user-level entry to the SessionStart chain so the migration prompt is part of the canonical install surface.

### Why this is the right fix

Two alternative fixes considered and rejected:

1. *"Detect worktrees and install hooks at the worktree level too."* Project-level config inside `.claude/worktrees/<name>/.claude/settings.json` would still be brittle and require reinstalling on every new worktree. User-level wins on simplicity.
2. *"File a Claude Code bug and wait for an upstream fix."* Issue is open ([#6](https://github.com/adelaidasofia/ai-brain-starter/issues/6)) but waiting blocks every user. The user-level install is a structural workaround that's actually cleaner — global hooks belong at global scope.

### What's preserved

The full session-close cascade, all 14 bundled skills, all the Phase 5 setup, every existing user-defined hook in `~/.claude/settings.json`, every project-level hook the user installed manually. The only change is that ai-brain-starter's specific hooks now live at user level. Project-level installs are not removed automatically — they coexist (additive migration). Once the user verifies the user-level hooks work, they can manually delete the project-level entries.

### Migration paths

- **New users via bootstrap.sh:** automatic — installer runs at end of bootstrap.
- **Existing users on a current update:** the SessionStart migration hook detects project-level installs and prompts once with the migration command.
- **Manual:** `python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py`
- **Verification:** `bash ~/.claude/skills/ai-brain-starter/scripts/test-hooks-in-worktree.sh` (6/6 expected).
- **Uninstall:** `python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py --uninstall` removes ONLY ai-brain-starter entries, preserves everything else.

**Closes [adelaidasofia/ai-brain-starter#6](https://github.com/adelaidasofia/ai-brain-starter/issues/6).**

---

## 2026-04-30 — Compounding reliability + stewardship layer (10 features in one drop)

**Who this affects:** everyone. This is a single coordinated drop that addresses every reliability gap the maintainer's panel review surfaced and closes 4 of 4 oldest open issues simultaneously.

**The shape:** these aren't 10 independent features. They're a layered architecture where each piece compounds on the previous one. Foundational reliability first (schema linter, bootstrap bundle), then telemetry, then stewardship surfaces, then periodic processes, then infrastructure.

### Layer 1 — Reliability foundations

- **Vault schema linter.** Same permanent-fix pattern that saved settings.json. New `hooks/lint-vault-frontmatter.py` is a PreToolUse hook that catches malformed YAML in Decisions/, Sessions/, and journal frontmatter before it lands. New `scripts/vault-schema-validator.py` is a standalone validator with 9-fixture self-test, runnable in CI or on-demand. Per-type schemas at `templates/schemas/{decision,session,journal}.json`. Closes the same class of bug that nuked Sergio's CRM 2026-04-27 (silent YAML parse error → empty re-marshal over real content).
- **Bootstrap reliability bundle (closes [#2](https://github.com/adelaidasofia/ai-brain-starter/issues/2), [#3](https://github.com/adelaidasofia/ai-brain-starter/issues/3), [#4](https://github.com/adelaidasofia/ai-brain-starter/issues/4) at once).** New flags: `--restore` for interactive recovery from .bak files, `--smoke-test` for end-to-end install verification, `--detect-partial` for finding half-installed components. Persistent log at `~/.claude/.bootstrap.log` with size-based rotation. Three new scripts: `bootstrap-restore.sh`, `detect-partial-installs.sh`, `post-install-smoke-test.sh`. The smoke test runs Python syntax, bash syntax, JSON validity, hook smoke tests, aggregator smoke tests, schema validator self-test, and the closing-signal fixture harness — 130+ checks in one command.

### Layer 2 — Telemetry foundation

- **Skill-usage telemetry (opt-in).** New `hooks/log-skill-usage.py` (UserPromptSubmit) detects `/skill-name` invocations and logs structured records to `~/.claude/logs/skill-usage.jsonl` AND vault `⚙️ Meta/skill-usage-log.jsonl` (matches the existing reporter schema, dual-location write so vault-aware analytics still work). Privacy-first: OFF by default, opt-in via `cascadeTelemetry: true` in CLAUDE.md frontmatter or `SKILL_USAGE_TELEMETRY=1` env var. Anonymized session IDs (SHA-256 truncated). Length bucketed, never full prompts. Local only, never sent over network. Erase any time with `rm ~/.claude/logs/skill-usage.jsonl`.

### Layer 3 — Stewardship surfaces

- **First-week check-ins (day 3 / day 7 / day 14).** New `hooks/first-week-checkin.py` is a SessionStart hook that fires once per milestone with a one-paragraph "how's it going?" prompt and 1-2 specific suggestions tailored to which skills the user has and hasn't tried (read from telemetry if opted in, generic hints otherwise). Closes the cohort dropout cliff. State tracked at `~/.claude/.ai-brain-checkin-state.json`. Easy opt-out via `firstWeekCheckin: false` in CLAUDE.md.
- **CLAUDE.md drift detection.** New `scripts/check-claude-md-drift.py` flags people in `## People` not mentioned in any session/decision/journal in the last 90 days, archived projects, broken wikilinks, duplicate headings, and `Codified YYYY-MM-DD` markers older than a year. Read-only; writes a review document to `⚙️ Meta/CLAUDE-md drift.md` for the user to act on. The drift detector is the meta-rule for the memory durability rule: it catches the case where the rule itself rotted.
- **Curatorial pass surface.** New `scripts/curate-skills-surface.py` reads usage telemetry and ranks skills, outputs a "most-used skills" badge, and optionally patches a managed region in README.md (between `<!-- top-skills:BEGIN -->` and `<!-- top-skills:END -->` markers). Once 4 weeks of data accumulate, the README re-ranks itself; until then, it stays static.

### Layer 4 — Periodic processes

- **Vault hygiene auto-pass.** New `scripts/vault-hygiene.py` walks the vault and reports broken wikilinks, empty notes, stale notes (>365 days untouched by default), duplicate concept candidates (same stem in multiple folders), and graphify staleness. Read-only; writes a summary to `⚙️ Meta/Vault Hygiene.md`. Designed to run weekly via cron OR as part of /sunday-review.
- **/sunday-review meta-skill.** New skill at `skills/sunday-review/SKILL.md`. Orchestrates `/weekly` + `/patterns` + vault-hygiene + claude-md-drift + decision-retrospective + skill-usage curatorial pass in a single ordered flow, then synthesizes one note at `📓 Journals/Reviews/Sunday Review {YYYY-MM-DD}.md` with linked drill-downs. Matuschak's panel critique fix: existing skills don't compound unless you force them to interlock once a week. This is that forcing function.
- **Decision retrospective loop.** New `scripts/decision-retrospective.py` finds Decisions/ files older than 90 days with empty Outcome and produces review-ready prompts. The `--apply-prompt` mode appends a "Retrospective candidates" section to `⚙️ Meta/Decision Retrospective.md` with one entry per stale decision, ready to fill in during /sunday-review or /monthly. Without this, Outcome fields stay empty forever and the quarterly retro never happens.

### Layer 5 — Infrastructure

- **Multi-machine vault sync helper.** New `scripts/vault-multi-machine-sync.sh` ships the missing piece for users who work from multiple machines on the same vault. Uses git as transport (vault must have a remote). Three modes: `status`, `pull`, `push`, `sync`. Targeted paths only (never `git add -A`). Refuses to run if no remote, refuses to push during concurrent index lock, fail-loud on merge conflicts. Closes the gap in the memory durability rule (which says "always also write to vault" but didn't ship the sync between machines).

### What this drop deliberately does NOT do

It does not add new content skills. The Matuschak/Jackie panel reads were correct: more shipping isn't the answer; reliability + stewardship + curatorial discipline is. Every new artifact in this drop strengthens what already exists — it does not introduce new dormant features.

### Compounding diagram

```
Schema linter + Bootstrap bundle  → reliable foundation
             ↓
   Skill-usage telemetry (opt-in) → real usage data
             ↓
   First-week check-ins, drift, curatorial → stewardship informed by data
             ↓
   Vault hygiene + Sunday review + decision retro → periodic deepening
             ↓
   Multi-machine sync                → infrastructure for compound use
```

### Existing users

The next auto-update sync wires every new hook into `hooks.json` and pulls in the new scripts. Telemetry stays OFF unless explicitly opted in. First-week check-ins compute days-since-install via the git clone date or a marker file; existing users will see the day-14 check-in fire on their next session if they're past day 14, which is intended (mid-flight stewardship).

### Issues closed

- [#2](https://github.com/adelaidasofia/ai-brain-starter/issues/2) bootstrap: --restore mode (shipped as `bootstrap.sh --restore` + `scripts/bootstrap-restore.sh`)
- [#3](https://github.com/adelaidasofia/ai-brain-starter/issues/3) bootstrap: persistent log file (shipped as `~/.claude/.bootstrap.log` with size-rotation)
- [#4](https://github.com/adelaidasofia/ai-brain-starter/issues/4) bootstrap: detect partially-installed graphify (shipped as `bootstrap.sh --detect-partial` + `scripts/detect-partial-installs.sh`)

---

## 2026-04-30 — Session close cascade rebuilt as a deterministic 3-layer pipeline

**Who this affects:** everyone. Every time you say "bye" to end a session, the new pipeline runs.

**The problem:** the prior architecture relied on the model "noticing" closing signals and choosing to read a separate cascade rule file before responding. Three brittle steps (notice → read rule → execute) any one of which could fail silently. Reports came back of users saying "bye" and nothing getting saved — captures lost.

**What changed:** the close cascade is now layered across three coordinated mechanisms.

- **Layer 1 — `hooks/detect-closing-signal.py` (UserPromptSubmit, NEW).** Detects close signals via regex against language packs (EN / ES / PT) before the model ever sees the prompt. Pre-resolves all paths. Pre-builds the session file shell with frontmatter and section headers. Pre-fetches decisions with empty Outcome. Writes a marker file. Injects the cascade context as `additionalContext` so the model receives complete instructions without reading a separate rule file. Performance budget: under 500ms.
- **Layer 2 — model's turn.** The model receives the injected context and runs only the irreducibly creative work: incomplete-work check, conversation scan for journal seeds (verbatim), writing notes, to-dos, decisions, delegations, then writes everything in a single batched tool-call block to the pre-built shell.
- **Layer 3 — `scripts/session-end-hook.sh` (Stop, UPGRADED).** Reads the marker, runs aggregators, performs a targeted git snapshot if the vault is git-tracked, sweeps retention, and crucially fires `scripts/session-close-fallback.py` if the session body is empty (model bailed) — the fallback calls Haiku 4.5 with the conversation transcript and fills the file. No silent loss.

**The full 7-phase cascade is preserved.** Every capture from the prior spec — journal seeds, Substack candidates with kill-conditions, to-do reconciliation, decision logging, decision outcome backfill, delegations with drafted messages, time tracking — runs identically. The change is where the work happens (deterministic hook vs. model's context window), not what gets captured.

**Token efficiency:** the model now receives a ~400-600 token system block with pre-resolved paths and inline cascade phases, instead of having to re-read a 3K-token rule file plus narrate phase-by-phase tool calls. Roughly 80% reduction in close-related model token spend, identical capture fidelity.

**UX change:** the cascade runs invisibly by default. The model says a clean goodbye, the captures land in the background. Set `sessionCloseFeedback: minimal` in your CLAUDE.md frontmatter to see a one-line summary at close end. Set to `verbose` for phase-by-phase output if you want to debug.

**New files:**
- `hooks/detect-closing-signal.py` — UserPromptSubmit detector
- `scripts/session-close-fallback.py` — Haiku-backed graceful degradation
- `scripts/recover-last-close.py` — recover from partial-completion flags
- `scripts/undo-last-close.py` — rollback most recent close
- `scripts/test-closing-signals.py` — fixture-based test harness (74 fixtures, CI-runnable)
- `templates/closing-signals/{en,es,pt}.json` — multilingual signal dictionaries
- `docs/SESSION_CLOSE.md` — user-facing reference for the whole system
- `templates/rules/session-close.md` — rewritten as the canonical rule (supersedes session-end-cascade.md, which is now a redirect stub)

**Modified files:**
- `scripts/session-end-hook.sh` — marker check + Haiku fallback wiring + git snapshot + retention
- `hooks.json` — UserPromptSubmit chain prepended with the detector
- `templates/generated/claude-md-template.md` — Phase 4 session-end section rewritten + new optional config block
- `SKILL.md` — routing table updated to mention session-close walkthrough in Phase 19-23 finish
- `phases/phase-19-23-finish.md` — Phase 24.5 walkthrough added (15-second verbal pointer for new users)

**Closing signals matched:**
- Explicit (no confirmation): `/close`, `/wrap-up`, `/bye`, `/done`, `/finish`, `/cerrar`, `/terminar`, `/chao`, `/fechar`, `/encerrar`, `/tchau`
- High-confidence natural language: bye, thanks that's all, good night, ttyl, cya, signing off, talk later, wrapping up, I'm done, k bye, gn (EN); chao, chau, nos vemos, hasta luego, listo gracias, eso es todo, buenas noches, me voy (ES); tchau, até logo, valeu, falou, boa noite, pronto, obrigado (PT)
- Ambiguous (asks "wrapping up?"): ok, cool, perfect, great, sounds good, dale, bueno, beleza
- Emoji-only: 👋, 🙏, ✌️, 🫡, 💤
- False-positive guards exclude code blocks, quoted "bye", "done with X" transitions, "listo para X" readiness, meta-questions like "what does ttyl mean?"

**Customization:** add per-user signals via `closingSignals.custom: ["k thx", "okkk"]` in your CLAUDE.md frontmatter. Switch on Haiku ambiguous-classifier with `closeDetection: hybrid` (needs ANTHROPIC_API_KEY).

**Recovery:** if a close fails because the model bailed and you didn't have ANTHROPIC_API_KEY set, a partial-flag is left at `~/.claude/.cascade-partial-{session_id}.json`. Run `python3 ~/.claude/skills/ai-brain-starter/scripts/recover-last-close.py` later to retry the fallback.

**Rollback:** `python3 ~/.claude/skills/ai-brain-starter/scripts/undo-last-close.py` moves the most recent session file + co-located decisions to an `.undone-{timestamp}/` archive folder, optionally reverts the git commit, and re-runs aggregators. Always interactive unless `--yes`.

**Testing:** `python3 scripts/test-closing-signals.py` runs 74 fixtures across all three languages, ambiguous cases, false positives, and adversarial inputs. Exits 0 on all-pass for CI.

**Existing users:** the next auto-update sync wires the new hook into `hooks.json` and pulls in the new scripts. Old `session-end-cascade.md` becomes a redirect stub pointing at `session-close.md`. No content is lost; nothing breaks. The model-side cascade is identical in scope; the trigger is now deterministic.

**Why it matters:** "I said bye and the cascade didn't run" was a real, recurring failure mode that lost user context. The fix is structural — make detection a deterministic hook, give the model only the work it can't be replaced for, and add a Haiku backstop so even a model bail doesn't lose captures. The system never gets worse than current state on any failure.

---

## 2026-04-28 — Claude Code config integrity guards (5-layer defense against silently corrupt settings.json)

**Who this affects:** anyone who has ever hand-edited `~/.claude/settings.json` or `.mcp.json`. No breaking change — all three guards are additive and warn-only by default.

**What changed:** Three new hooks land in `hooks/`, wired into PreToolUse and SessionStart in `hooks.json`. They form a layered defense against the most common silent failure mode in Claude Code config: a duplicate top-level key (especially a second `"permissions": {...}` block at the bottom of settings.json) that wipes the original allowlist because JSON's last-key-wins semantics are silently tolerated by `json.load()`. The user keeps re-approving the same gh/git push permissions every session, never realizing the config has been corrupt for weeks.

- `lint-claude-settings.py` — detects duplicate keys at any depth, unknown enum values for `model` and `theme`, hooks pointing at files that don't exist on disk, and bare-command permissions missing the `Bash(...)` wrapper. Runs in three modes: warn-only (default, for SessionStart drift detection), `--strict` (exit 2 on BLOCK-severity issues, for the PreToolUse blocker), and `--test` (5 self-test fixtures including duplicate-key and false-positive guard, so the linter itself can't silently rot).
- `pre-write-settings-lint.py` — PreToolUse Write|Edit blocker. If you (or Claude) try to write a config file that contains a duplicate top-level key, the write is blocked with a stderr explanation pointing at the exact issue. Edit operations are projected (current file + old/new substitution) before linting so the check matches the post-edit shape.
- `check-claude-code-version.sh` — SessionStart-cached check (24h TTL) against `gh api repos/anthropics/claude-code/releases/latest`. Warns if you're behind by 3 or more patch versions. Catches the silent-drift class of bug: Claude Code has no built-in "you're behind" notification, so users routinely miss memory-leak fixes and reliability patches that ship every couple weeks.

**Why it matters:** The duplicate-permissions bug is a real failure mode that's easy to introduce and hard to detect. JSON parsers don't complain. Claude Code doesn't complain. The only signal is "huh, why is this permission not working" weeks later. Catching it at the write boundary is cheap; debugging it cold is hours. The version check closes the same kind of gap on the upgrade axis — no nag, just a one-line surface at SessionStart if you've drifted enough that it matters.

**The defense layers:**
1. PreToolUse blocks bad writes (write boundary)
2. FileChanged (if your Claude Code version supports it) warns at write-time
3. SessionStart audits drift introduced by external editors
4. SessionStart runs the linter's self-test so guard rot fails loud
5. Wire the version-check output into your existing UserPromptSubmit hook to surface drift inline

**Files touched:** `hooks/lint-claude-settings.py` (new), `hooks/pre-write-settings-lint.py` (new), `hooks/check-claude-code-version.sh` (new), `hooks.json` (PreToolUse Write|Edit chain extended, new SessionStart block).

**Existing users:** the next sync run picks up the new hooks via your hooks.json. The new SessionStart block is gated on `[ -f ~/.claude/hooks/<file> ] && ... || true` so missing files exit silently — no breakage if a sync is incomplete.

**Requires:** `gh` CLI for the version check (silently no-ops if missing).

---

## 2026-04-25 — Framework expanded from 16 to 34 floors across templates, scripts, and phase docs

**Who this affects:** anyone setting up a new AI Brain Starter vault, or anyone whose existing vault has the older 16-floor framework wired into templates and the graphify pipeline. No breaking change for users who already manually expanded their framework — this just makes the public repo match.

**What changed:** The High-Rise framework was expanded from 16 floors to 34 by mapping ~150 named human emotions onto the building. The setup phase that creates concept notes, the Templater suggester for new journal entries, the Floor Check-In quick-reference template, and the graphify scripts that build floor edges in the knowledge graph were all still on the original 16. New users would have a vault that silently lost the 18 added floors at every layer (template → frontmatter → graph). This catches all four layers up.

**The new floors:** Disgust (1), Embarrassment (3), Resignation (6), Confusion (7), Loneliness (8), Boredom (9), Disappointment (11), Hurt (12), Frustration (14), Contempt (17), Hope (20), Trust (25), Compassion (26), Humility (27), Belonging (28), Gratitude (30), Excitement (31), Wonder (32). Tier ranges shifted: Low is now 1-18 (was 1-8), Middle is 19-24 (was 9-13), High is 25-34 (was 14-16).

**Why it matters:** Several common emotional states were collapsed into the wrong floor under the 16-schema — anger and frustration treated as one floor when they have distinct voice signatures (Anger = ALL CAPS at someone; Frustration = blocked-energy "ugh"), love and gratitude conflated when one is "I give to you" and the other is "I'm so grateful." Vault dashboards and pattern-recognition queries get sharper when the labels match the actual emotional resolution.

**Files touched:** `templates/obsidian/Journal Entry.md`, `templates/obsidian/Floor Check-In.md`, `phases/phase-10a-journaling.md` (concept-note generator + Spanish translation table + tier notes), `scripts/graphify_prep.py`, `scripts/graphify_canonicalize.py`.

---

## 2026-04-24 — New build rule: structured-signal-first audit before LLM batches

**Who this affects:** anyone building scripts, skills, or agents that iterate an LLM over a folder of vault files (classify, extract, label, score, summarize). No breaking change.

**What changed:** Build Standards Optimization Pass gains a new section 4a — *Structured-signal-first audit*. Before iterating an LLM over a folder of files, the pre-build checklist now mandates a five-minute audit of what structured signal already lives in those files (frontmatter fields like `concepts_extracted`, `themes`, `tags`, body wikilinks pointing at the concepts you're about to classify, prior extractor output). If existing signal already covers ≥60% of the judgment, the build is Python-first with the LLM as tiebreaker on the residual ambiguous tail.

**Why:** vault automation tends to leave structured signal behind on every pass. When a later build needs to do the "same kind" of classification, going straight to an LLM batch re-derives what's already on disk. A 2,000-file batch at ~10s per call is hours of runtime and meaningful API spend; a Python pass over existing wikilinks + frontmatter handles the obvious cases in seconds, with the LLM reserved for genuinely contextual judgment. The audit takes five minutes; skipping it costs orders of magnitude more.

**Files touched:** `docs/BUILD_STANDARDS.md` (new section 4a between LLM usage check and Excel financial math).

---

## 2026-04-23 — Install flow: one paste, zero commands to type

**Who this affects:** anyone installing AI Brain Starter for the first time. No breaking change for existing users, big UX improvement for new users.

**What changed:** The install is now truly one paste, end to end. The README's Step 2 is a single natural-language prompt that tells Claude to clone the repo into `~/.claude/skills/ai-brain-starter/`, run bootstrap, and walk you through every setup phase without stopping. No typing `/setup-brain`. No "open Claude Code in your vault folder" instruction. No terminal navigation. The only prerequisites remain: install git (Homebrew does this) and have a paid Claude account.

**Bootstrap now dual-mode.** `bootstrap.sh` and `bootstrap.ps1` detect whether they're running inside Claude Code (via `$CLAUDE_CODE_ENTRYPOINT`). If yes, the "Next Steps" banner says Claude will continue the setup interview automatically. If no (i.e., invoked standalone from a terminal), it tells the user to open Claude Code and paste the setup prompt. One script, two correct messages.

**Why:** the previous flow had five friction points for non-technical users (install Claude Code → open in vault path → clone repo → run bootstrap → type slash command). Every decision point is an abandonment point. The blog-post funnel aims at writers and founders who are not developers; the defining characteristic of this audience is that they don't know how to navigate a filesystem or a terminal. "Zero decisions" is the actual bar, not "low friction."

**Files touched:** `README.md` (Step 2 rewritten, "Prefer the terminal?" advanced section removed, team-join paste simplified), `bootstrap.sh` + `bootstrap.ps1` (header comments rewritten, Next-Steps branch on `$CLAUDE_CODE_ENTRYPOINT`).

---

## 2026-04-23 — To-do system: strengthened task contract + area-casing warning

**Who this affects:** anyone using the to-do template. No breaking change, two strengthenings of existing rules.

**What changed (1/2): every task stands alone — stricter contract.** The "self-contained task" rule (shipped earlier today) now requires all four of: (a) action verb + concrete object ("Draft Q3 plan outline" not "Work on Q3 plan"), (b) a context anchor (prefix, URL, wikilink, or file path), (c) an expected output named (deck page, CSV row count, Slack DM sent, PR opened), (d) how you report done (mark `[x]` + reply in thread, push to branch X, send to collaborator). Tasks like "Follow up with friend" or "Verify PDF" still fail the rule even with a wikilink because the expected output and done-reporting channel are missing.

**Why:** shipping a wikilink is necessary but not sufficient. A reader with zero context still can't tell "done" from "in progress" without a named output and a report channel. Multi-owner delegated work breaks most often at the hand-off, not the hand-out.

**What changed (2/2): `[area::]` values must be lowercase.** Dataview `GROUP BY area` is case-sensitive. `[area:: sales]` and `[area:: Sales]` render as two separate "sales" buckets in per-person views — silently. Docs now tell you to pick a fixed set of 3-8 canonical lowercase values up front and lint drift on every touch.

**Why:** caught in a real audit where team member views had ghost GROUP BY sections because different sessions used different casings. The user saw duplicate headers and couldn't tell at a glance whether it was two different workstreams or one with drift.

**Files touched:** `templates/generated/todo-system-template.md` (minimum-contract rule strengthened), `docs/TODO_SYSTEM.md` (Dataview-only projections emphasis + area-casing key principle).

---

## 2026-04-23 — To-do system: self-contained task rule

**Who this affects:** anyone using the to-do template, especially the new Four Quadrants view. No breaking change, just a new rule documented in the template.

**What changed:**

Added an explicit rule that every captured task MUST stand on its own when surfaced out of context. Every task needs at least one of: a `[Context prefix in brackets]` naming the project/entity/file, a direct URL, a wikilink to the source note, or a file path. Tasks without any of these get tagged `[needs-context]` so the user (or Claude on next triage) knows to enrich before execution.

**Why:** the Four Quadrants view and Dataview queries in general strip the surrounding session header. A task like "Verify PDF has all 9 pages" made perfect sense when written inside a "## 📋 From Workshop PDF build" capture block. A week later, rendered alone in Q1, it is gibberish. The user has to dig through session notes to remember which PDF, which workshop, which pages. That archaeology kills execution velocity, which is the whole point of a to-do system.

This rule applies when Claude is helping capture tasks during `/journal`, meeting-todos, or session close. Claude must either pull context from the transcript and inline it, or flag the task for the user to complete.

**Files touched:** `templates/generated/todo-system-template.md` (added "Self-contained task rule" paragraph in the How to Use section with four concrete anchor types and examples of what fails).

---

## 2026-04-23 — To-do system: optional weighted scoring formula

**Who this affects:** anyone using the to-do template who wants more rigor than pure P1/P2/P3 judgment. Everyone else can ignore this; the three-question prioritization framework still works unchanged, and the four-quadrant Dataview view works identically regardless of how priority was assigned.

**What changed:**

The to-do template now documents an opt-in weighted scoring formula alongside the default three-question framework. Every new task can take four numeric inputs:

- `[impact:: 1-5]` — goal alignment (weight 0.40)
- `[urgency:: 1-5]` — time consequence of delay (weight 0.30)
- `[effort:: S|M|L]` — execution cost, inverted (weight 0.15)
- `[commit:: Y|N]` — external promise bonus (weight 0.75)

A formula turns these into a score; thresholds map to P1/P2/P3 deterministically. This is especially useful if an LLM is doing your triage from the capture inbox into the prioritized queue, because deterministic scoring beats "Claude, please prioritize these tasks" on consistency.

**Why:** the pure three-question framework works for most people but has two failure modes. First, some users repeatedly mis-assign priority and want an auditable reason per task. Second, LLM-assisted triage produces inconsistent results when the criteria are purely linguistic; a formula removes that drift. This ships both modes in the same template, labeled clearly, with the formula marked optional and explicitly secondary to gut judgment.

**Important caveats (read before using):**

- **Calibration is required before trust.** The weights (0.40 / 0.30 / 0.15 / 0.75) are a sensible first guess, not evidence. Score 20 known tasks manually, compare against your gut, adjust until they agree, then use the formula.
- **When the formula is procrastination:** if after two weeks of using the scoring system your daily execution has not actually changed, the formula is plumbing without payoff. Go back to the three-question framework. The four-quadrant view works either way.
- **Overbuilding your to-do system is a real hazard.** If you are tempted to add scoring because you want more "rigor," ask first whether the rigor will change what you do today. If not, skip it.

**Files touched:** `templates/generated/todo-system-template.md` (added "Two prioritization modes" callout in the top README, added "Optional: Weighted Scoring System" section inside the Get to-do.md file template with formula, example calculation, calibration instructions, fallback rule, and Claude-assisted triage prompt), `docs/TODO_SYSTEM.md` (added a summary table under "Optional: Weighted Scoring Formula" pointing to the full template for details).

---

## 2026-04-23 — To-do system: capture inbox + Eisenhower four-quadrant view

**Who this affects:** anyone running fresh `/setup-brain` installs from now on who opts into the `✅ To-dos/` folder. Existing installs can upgrade by re-installing `templates/generated/todo-system-template.md`; the new four-quadrant Dataview block is additive and can be pasted into the top of an existing `Get to-do.md` without breaking anything.

**What changed:**

The to-do template now installs two files instead of one for the main list: `Get to-do.md` (prioritized queue) and `From Meetings.md` (raw capture inbox). Captures from journaling, meetings, and session close land in `From Meetings.md` grouped by source, then get triaged into `Get to-do.md` once a week.

At the top of `Get to-do.md`, a new "Four Quadrants" section auto-renders every open task from both files through an Eisenhower matrix: Q1 (Important + Urgent), Q2 (Important, Not Urgent), Q3 (Urgent, Less Important), Q4 (Backlog), plus a NEEDS TRIAGE quadrant for tasks without a `[priority::]` tag. Importance is read from the existing `[priority:: 1-3]` inline field; urgency is derived from `[due::]` within 7 days (or a P1 with no due date). Nothing changes about how you write tasks, the quadrants are just a new lens over the same inline fields.

`This Week.md` was also updated to pull P1s from both files so priority captures sitting in the inbox still surface during weekly planning.

**Why:** a single mixed file forced you to scroll past raw capture clutter to see what actually needed doing. The split keeps the prioritized queue clean. And a text list of P1/P2/P3 does not answer the question "what do I do right now?" as directly as a four-quadrant matrix does, which is the question you are actually asking when you open the file. Eisenhower has been the textbook answer to this for decades; rendering it through Dataview means it is always current with zero maintenance.

**Files touched:** `templates/generated/todo-system-template.md` (added File 2 `From Meetings.md`, added Four Quadrants Dataview block at top of File 1, updated `This Week.md` query to read from both files, added "Why two files" explainer, added "How the quadrants work" in the usage section), `phases/phase-02-03-plugins-folders.md` (updated `✅ To-dos/` install description to mention the two-file + four-quadrant model).

---

## 2026-04-22 — Light/full tier removed: everyone gets the full second brain

**Who this affects:** anyone running fresh `/setup-brain` installs from now on. Existing installs keep working unchanged. **Existing CLAUDE.md files that mention `PLAN_TIER` are stale references, not bugs.** See `docs/migrations/2026-04-22-light-full-removed.md` for cleanup.

**What changed:**

The "do you want light or full?" question has been removed from Phase 1. Every new install now unconditionally gets the advisory panel, knowledge graph context routing, panel-voice routing, monthly insight reports with pattern analysis, and the Instinct Engine. Previously these were gated behind `PLAN_TIER == "full"`.

**Why:** the light tier was a defensive crouch from an earlier moment when the daily-budget concern was uncertain. Real usage data and the workshop showed the full version is what people came for, and most users never figured out what they were missing in light mode. Splitting the experience added friction (one more question, one more decision the user had no good basis for making) without saving them anything they cared about. Removing the choice removes the friction.

**Files touched:** `SKILL.md` (dropped Tier column from routing table, removed PLAN_TIER variable), `phases/phase-01-welcome.md` (deleted Step 1.0b), `phases/phase-05-context-layer.md`, `phases/phase-10b-panel-roster.md`, `phases/phase-18-insights.md` (all tier gates removed), `templates/generated/obsidian-rules-template.md` (Rule 19 collapsed to single 12-category version).

---

## 2026-04-22 — Windows .ps1 files now ship with UTF-8 BOM (parser-error fix)

**Who this affects:** every Windows user who has ever run `bootstrap.ps1`, `drift-check.ps1`, or `update-check.ps1`. **Critical fix.**

**What changed:**

All three PowerShell scripts in the repo now start with the UTF-8 BOM bytes (`EF BB BF`). Without it, Windows PowerShell 5.1 (the default on Windows 10/11) reads the files as Windows-1252 and crashes on the first em dash, box-drawing character, or ⚙️ emoji it hits. The scripts contain all three. The bootstrap was the worst case (51 non-ASCII lines) and would have failed at install time for every Windows user, but the bug went unnoticed because no one was running the bootstrap on Windows during development.

**Also:** `phases/phase-18-insights.md` documents a `run-insights.ps1` template that Claude writes to Windows users' machines during setup. The template contained em dashes inside PowerShell strings AND the ⚙️ emoji in vault paths but had no BOM directive. Both have been fixed: em dashes stripped, mandatory BOM-save instruction added above the template with a verification command.

**Codified durably:** SKILL.md "Important Notes for Claude" now includes the rule "Windows .ps1 files MUST be saved as UTF-8 with BOM" so future setup runs and future maintainers see this on every read.

**Why:** flagged by a Windows user during a `git pull` who saw a parser error on line 201 of drift-check.ps1. The bash version worked, so they reported it as low-urgency. It was actually a much bigger issue: the same encoding fragility was in every PowerShell script we ship.

---

## 2026-04-22 — Setup friction fixes: no terminal, no GitHub prompt, ⌘↩ clarity

**Who this affects:** everyone running fresh `/setup-brain` installs.

**What changed:**

Three small but high-impact friction reductions surfaced by the workshop on April 21-22:

1. **No more "open a terminal."** SKILL.md now says: *"NEVER ask the user to open a terminal during setup. Claude runs all bash commands via its own tools."* Workshop attendees got stuck whenever the assistant told them to switch to Terminal — non-technical users don't know what a terminal is, where to find it, or how to switch back. Fixed everywhere this was happening.
2. **GitHub auth prompt removed entirely.** Bootstrap no longer prompts for `gh auth login`. The `gh` binary still installs (it's useful), but auth is never required and never asked about. Phase 0 docs updated to match. Connecting GitHub adds zero value to the brain setup.
3. **⌘↩ vs typing rule added to Visual Reassurance Protocol.** The single most common stall point: users see a gray tool-approval box and don't know whether to type something or press ⌘↩ (Mac) / Ctrl↩ (Windows). New rule: *"If you see a gray tool box → ⌘↩. If Claude ends with a question mark → type your answer."* Said out loud once before Phase 0 starts, repeated if the user stalls.

**Why:** the workshop showed that broken tools weren't the problem — confusion was. Three concrete clarity fixes saved more abandonment risk than any feature add would.

---

## 2026-04-22 — CI / lint workflow + /diagnose self-check

**Who this affects:** maintainers (CI) and end users debugging a setup (/diagnose).

**What changed:**

1. **GitHub Actions workflow** at `.github/workflows/lint.yml` now runs on every push and PR. It catches: bash syntax errors (`bash -n`), PowerShell parser errors (`pwsh ParseFile`), missing UTF-8 BOM on `.ps1` files (the bug class above), em dashes in `.ps1`/`.sh` (preventive), and JSON validation for `hooks.json` and any `.mcp.json`. Costs $0 on public repos.
2. **`/diagnose` self-check command** at `skills/diagnose/`. Run it anytime the user is unsure if something is working. Single command checks: CLAUDE.md exists in vault, all expected skills installed in `~/.claude/skills/`, hooks registered, `journal-index.json` exists and is fresh, vault path readable, MCPs registered. Reports green/yellow/red per check with one-line fix guidance. Wired for Mac/Linux (`scripts/diagnose.sh`) and Windows (`scripts/diagnose.ps1`).

**Why:** the Windows BOM bug sat in `bootstrap.ps1` since the file was created because nothing tested it. CI prevents the regression class. /diagnose closes the gap between "something feels off" and "here's exactly what's broken" — workshop attendees specifically asked questions in the shape of "how do I know if it's working?"

---

## 2026-04-21 — Granola: local cache export replaces API sync

**Who this affects:** anyone using Granola for meeting notes.

**What changed:**

`scripts/granola_sync.py` now reads Granola's local cache directly instead of calling the Granola API. No API key or MCP required — works on any Mac with Granola installed, on any plan (free, pro, business). Exports full timestamped transcripts as markdown to your meeting notes folder, firing automatically via a LaunchAgent whenever Granola updates its cache after a meeting.

A companion `scripts/com.granola-export.plist` is included for the LaunchAgent install (edit the two placeholder paths, then `launchctl load` it).

The Granola MCP entry has been removed from Phase 0 bootstrap and all docs — the local cache approach covers the same use case without the network dependency or plan restriction.

---

## 2026-04-21 — Phase 24: first-week handoff with recommended uses

**Who this affects:** everyone running fresh `/setup-brain` installs. Post-install only, no effect on existing setups.

**What changed:**

1. **New Phase 24** appended to the setup flow. After install completes, Claude delivers a brief, understated congratulations (Jackie-register: no exclamation marks, no "Congrats!") and points to a short companion read on recommended first-week uses: three commands and one habit.

2. **Language-conditional link.** Claude shows only the link that matches the user's `PRIMARY_LANGUAGE` from Phase 1. One block, one link. No dual-language dump at the end of install.

3. **SKILL.md updated** to 25 phases (0-24). Phase 23.5 kept its "last INSTALL phase" marker; Phase 24 is the post-install handoff, not an install step.

**Why:** the most common failure mode for a new install isn't a broken tool, it's a user who finishes setup and doesn't know where to start. A single short read with three concrete actions closes that gap.

---

## 2026-04-21 — retry-budget hook: cap Claude's failing-command loops

**Who this affects:** everyone. Optional but recommended for all setups.

**What changed:**

1. **New hook `hooks/retry-budget.py`** blocks the 4th invocation of an identical Bash command within a 30-minute window. Attempts 1-3 pass silently; attempt 4 exits with code 2 and a message asking Claude to surface the blocker to you instead of looping further.

2. **Bypass flag** `RETRY_BUDGET_BYPASS=1` prefix lets Claude legitimately re-run a command more than 3 times (polling for a cron to finish, iterating on a fix where each attempt is a real change). The bypass is explicit so Claude has to tell you it's using it.

3. **Scope guards** prevent false positives: commands under 15 characters (`ls`, `pwd`, `date`, `git status`) are exempt, and state is per-Claude-session (no leakage between parallel work).

4. **Registered in `hooks.json`** under a new PreToolUse Bash matcher, so `/setup-brain` wires it up automatically on fresh installs. Existing users can install manually via the pattern in `phases/phase-05-context-layer.md`.

5. **New rule 31 in `templates/rules/efficiency.md`** documents the behavior and when to invoke the bypass.

**Why:** without a retry ceiling, Claude will cheerfully burn 200K context looping on a failing command before surrendering — this is the single highest-cost silent failure mode we see. Three attempts is enough to cover flaky-network hiccups; the fourth is almost always a signal to stop and plan. Pattern adapted from Devin 2.0 ("ask user for help if CI does not pass after the third attempt") and Cursor 2.0 ("don't loop more than 3 times to fix linter errors").

---

## 2026-04-21 — first-run UX hardening for /second-brain-mapping

**Who this affects:** everyone, especially first-time users running `/second-brain-mapping` on a fresh vault. Reduces silent failures and makes cold-start safer.

**What changed:**

1. **Setup-vault-types precheck.** Both `/second-brain-mapping` and `scripts/second-brain-mapping.sh` now check that at least one document-type extractor is configured before doing anything. Without this, Phase 1 used to run silently and report "no extractor" for every file in your vault, a confusing first-run experience. Now you get a clear message pointing you to `/setup-vault-types` instead.

2. **`--sample [N]` mode.** New flag that picks N files per registered type (default 1), runs extraction, and shows you the actual fields that would be written, without writing anything. Use this on a cold start to verify the output looks right before committing to your whole vault. Example: `/second-brain-mapping --sample 3`.

3. **Progress heartbeat in Phase 1.** On vaults of more than a few hundred files, Phase 1 used to run silently for minutes. Now it prints a progress line every 250 files showing files-per-second and ETA. Tunable with `--progress-every N`.

4. **File-count-aware cost estimate before Phase 2.** The "Run graphify? ~100k-1M tokens" prompt is now backed by a vault-specific estimate: it counts your actual files and words, applies graphify's typical compression ratio, and shows you a dollar figure at current Sonnet pricing for both cold-start and incremental modes. Treat the number as order-of-magnitude, not a quote.

5. **Hardened graphify install path.** `/graphify` Step 1 used to silently swallow pip install errors. Now it captures install output, surfaces the last 20 lines on failure, and stops with actionable next steps (network or proxy, PEP 668, pipx fallback, Python 3.10+ check) instead of continuing with a broken interpreter.

6. **Rate-limit-aware subagent dispatch.** When many graphify subagents fail with `429 / rate_limit / overloaded_error`, the skill now surfaces a clear message about API tiers and offers three concrete options (wait and re-run, split corpus, raise tier) instead of pretending extraction succeeded.

**Why:** with more people downloading and trying ai-brain-starter cold, the first 60 seconds of a `/second-brain-mapping` run determine whether they keep going or close the terminal. Six failure modes that previously looked like "the tool froze" or "the tool is broken" now produce explicit, actionable messages.

---

## 2026-04-21 — graphify wikilink hard guards

**Who this affects:** anyone who uses `scripts/graphify_apply_wikilinks.py` to apply graph-derived wikilinks. Tightens the script against path-form wikilink leaks, mirroring the hardening just shipped in `auto-wikilink.py`.

**What changed:**

1. **Hard guard in `apply_wikilink()`** — if `link_target`, `search_term`, or `display` contains a `/`, the script strips the path prefix or refuses to apply. Prevents path-form links like `[[folder/Name]]` from ever reaching the vault.

2. **User input sanitization** — at the first-name disambiguation prompt, pasted path-form input (`👤 CRM/Diego`) is stripped to the basename before use. You can no longer accidentally write a path-form alias by pasting a full vault path.

3. **Hard guard in `create_stub()`** — `note_name` with `/` is sanitized to basename. Stops stubs from being created as orphaned subdirectory children of CRM/ or Notes/.

4. **Defense in depth in `graphify_wikilink_gaps.py`** — graph labels containing `/` are filtered out during candidate collection so the apply script never sees them.

5. **Maintenance runbook** added to the docstring — dry-run first, path-form guard behavior, FileNotFoundError handling, pairing with `graphify_wikilink_gaps.py`, and pointer to `wikilink_misfire_audit.py` for cleanup.

**Why:** the v1 `auto-wikilink.py` bug (writing `[[folder/Name]]` across thousands of files) was discoverable only after a full vault audit. The graphify apply script had the same structural vulnerability — no hard guard, no input sanitization — even though the graph rarely produces path-form labels. This patch closes that gap before it causes the same mess.

---

## 2026-04-21 — wikilink misfire audit + auto-wikilink patch

**Who this affects:** anyone who ran `auto-wikilink.py` before v2 (the v1 script wrote `[[folder/Name]]` path-form wikilinks instead of bare `[[Name]]` wikilinks — every vault that ever ran v1 has these).

**What changed:**

1. **New script: `scripts/wikilink_misfire_audit.py`** — detects and batch-fixes path-form wikilinks left by v1. Run with `--fix` to apply, `--dry-run` to preview. Generates a report at `⚙️ Meta/Reports/auto-wikilink-misfire-audit-{date}.md`. Configurable `WRONG_ALIAS_BASENAMES` set for notes whose v1 alias links were semantically wrong (strip the link, keep the display text instead of re-linking).

2. **`scripts/auto-wikilink.py` patch** — added `try/except (FileNotFoundError, OSError)` in `add_wikilinks()`. Previously a file that disappeared between the directory walk and the file read (e.g. a git-deleted stub) would crash the whole run. Now those files are silently skipped.

3. **`scripts/auto-wikilink.py` maintenance runbook** added to the docstring — correct run order (misfire audit first, then auto-wikilink), known quirks (multi-word note titles create aggressive alias matches), and `WRONG_ALIAS_BASENAMES` pointer.

**Correct cleanup sequence:**
```
python3 "⚙️ Meta/scripts/wikilink_misfire_audit.py" --fix
python3 "⚙️ Meta/scripts/auto-wikilink.py" --all --dry-run  # review first
python3 "⚙️ Meta/scripts/auto-wikilink.py" --all
```

---

## 2026-04-21 -- graphify: two silent-failure bugs fixed

**Who this affects:** anyone running `/graphify` with MiniMax pre-extract enabled, anyone running graphify stages on a vault with nested folder structure (journals, writing, notes with subfolders), or anyone who has ever looked at the `extraction_manifest.json` and found it under-counting what was actually processed.

**What changed:**

1. `scripts/graphify_minimax_preprocess.py` now walks the full shell-config fallback chain to find `MINIMAX_API_KEY` — `~/.zshenv`, `~/.zsh_secrets`, `~/.zshrc`, `~/.zprofile`, `~/.bashrc`, `~/.bash_profile`, `~/.profile`, `~/.env`. Previously it only grepped `~/.zshrc` and failed silently for users whose keys lived anywhere else.

2. `scripts/graphify_stage_finish.py` now records a manifest entry for every file sent to a stage, not just files that produced LLM-novel canonical nodes. It also unflattens staged `graphify-input/A_B_C.md` source-file references back to their original nested paths by trying each `_` → `/` combination against the real filesystem.

**Why #1:** `~/.zshrc` is an *interactive* shell config. Scripts launched by IDE agents or subprocesses run under a non-interactive shell that never sources `.zshrc`, so a key defined only there is invisible. Users commonly keep API keys in `~/.zsh_secrets` (private, sourced from `.zshenv`) or directly in `.zshenv`. The old fallback missed both of those cases. The error was silent and expensive — the script errored out mid-pipeline, the stage ran without the cheap pre-extract, and the main model burned more tokens than it should have.

**Why #2:** When you stage files for a graphify chunk, the script flattens the nested path into a single filename (`✍️ Writing/High-Rise/Floor.md` → `✍️ Writing_High-Rise_Floor.md`) so every file lives in one directory. Subagents then set `source_file` on every node they produce to this flattened staged path. After the run, `graphify_stage_finish.py` was trying to map those staged paths back to the real vault file to record a manifest entry — but it only tried the direct path, which no longer exists once staging is cleaned up. The staged path stopped resolving, `is_file()` returned False silently, and the manifest recorded zero entries despite 100% of the stage succeeding. Next coverage audit would then report every one of those files as "MISSING" and re-run them.

Separately, the manifest only pulled entries from canonical nodes/edges. Files whose content was already covered by the regex-preflight wikilink pass never produced any *new* LLM items, so they never appeared in canon and never got a manifest entry — even though the agent read them and decided they didn't need additional inference. Those files also kept showing up as "MISSING" forever.

**What you'll see:** `manifest updated: N files recorded` where N matches the number of files you actually sent to the stage. Previously it could print `0 files recorded` on a stage that processed dozens of files successfully. If the resolver can't map some source files back, you'll get a `WARN:` line naming the first five unresolved refs.

**Who should update:** everyone running graphify stages regularly. The bugs compound over time — every stage with missing manifest entries adds noise to future coverage audits and causes unnecessary re-runs.

---

## 2026-04-20 -- skill sync skips skills with their own .git

**Who this affects:** anyone who has put a bundled skill (like `humanizer`) under independent version control after installing it. Most commonly: forking a skill on GitHub and tracking your changes there.

**What changed in `scripts/sync-skills.sh`:** the sync now skips any installed skill directory that contains its own `.git` (file or directory). The same way it already skips symlinked skills.

**Why:** if you fork a skill and develop it independently, the old behavior would clobber your local commits with the bundled version on every sync. Worst-case: the overwrite would race with an in-flight Edit and corrupt a commit you were about to push to your fork. Skipping is safer; you keep responsibility for `git pull`-ing your fork on your own schedule.

**What you'll see:** when sync runs, your forked skill shows up in the SKIPPED line as `<skill>: <path> has its own git repo (independently managed)`. No files written, nothing backed up, nothing changed in your fork's working tree.

**If you want bundled-version updates anyway:** delete `.git` from the installed skill (turns it back into a plain copy), or remove the install entirely and let the bundled version reinstall fresh on next sync.

---

## 2026-04-20 -- proposal-PDF workflow (opt-in reference, not a default install)

**Who this is for:** founders and consultants who ship formal business proposals as PDFs. If you don't send PDF proposals, ignore this update — nothing auto-installed, nothing got added to your active Claude environment, nothing to remove.

**What was added to the repo as reference material (not installed anywhere on your machine):**

- `templates/obsidian-snippets/proposal-letterhead.css` — Obsidian CSS snippet (also usable with pandoc + WeasyPrint from the CLI) that transforms a plain markdown note into a letterpress-quality branded PDF on export
- `docs/PROPOSAL_PDF_WORKFLOW.md` — step-by-step guide covering install, customization, both Obsidian-UI and CLI paths, color alternatives, and recommended proposal structure

**Explicit opt-in:** To use this you have to actively copy the CSS into your vault's `.obsidian/snippets/` folder, enable the snippet in Obsidian Settings, and customize two placeholder lines. Or, for the CLI path, install pandoc + WeasyPrint via Homebrew. Nothing happens automatically, and nothing is loaded into any skill or session context.

**What the output looks like:** Georgia body typography, deep navy section headers with hairline underlines, italic letterhead on pages 2+, "N / total" page numbers, clean business-document table styling. Reads as "law firm" or "senior consulting firm" — sober, not marketing-flavored.

**When NOT to use this:** you don't send formal PDF proposals; your proposals live in Google Docs, Notion, or a design tool; your clients expect slide decks not documents; you're fine with a markdown-default PDF.

**Originated in:** A Colombian consulting engagement where the proposal had to read as senior-professional-services to a traditional industrial patriarch. The same register works for any founder shipping proposals into traditional industry contexts — construction, legal, financial services, manufacturing, government.

**To adopt:** Read `docs/PROPOSAL_PDF_WORKFLOW.md`. 15 minutes from install to first PDF. **To skip:** do nothing. This isn't on by default.

---

## 2026-04-20 -- two new team workflows: Canonical Facts and playbook-to-task wiring

**What changed:** `for-teams/team-workflows.md` gained two new sections that codify patterns every team with contractors or external-facing numeric claims will eventually need.

**Section 5 — Canonical Facts registry.** Single source of truth for every numeric claim, source, and attribution that appears in external material (pitch deck, sales one-pager, investor memo, marketing site). Each entry carries the claim, a tier-1 primary source, the year, and the URL. Files that cite numbers must trace back to the registry. Drift = stop-ship defect before anything ships.

**Section 6 — Playbook-to-task wiring.** An "Instructions for [Name]" playbook without a matching task in the team to-do file is orphan work: the contractor never sees it. Session close now scans every playbook modified this session against the team to-do file; if any is not referenced by a live task, close is blocked until a task is added or the playbook is explicitly marked reference-only.

**Why it matters:** these two patterns address the same failure mode from opposite sides. Canonical Facts prevents contradictory numbers from reaching investors. Playbook-to-task wiring prevents careful instructions from becoming invisible work. Both patterns came out of a 2026-04-20 fabrication-audit session where four conflicting market-size numbers had propagated across five investor assets, and a rebuilt pitch-deck playbook failed to reach the contractor because no task pointed at it.

**Also:** `CLAUDE.md` template gets the matching three lint rules (Canonical Facts source-of-truth, Canva URL resolution for shortlinks, playbook-to-task wiring) so Claude enforces them at write time, not just at session close.

---

## 2026-04-17 -- bootstrap now auto-removes deprecated tools on re-run

**What changed:** `bootstrap.sh` and `bootstrap.ps1` now have a "Cleanup deprecated tools" section that runs at the top of every re-run. If it finds something that's been removed from the bundled stack, it removes it automatically and tells you why. No prompts, no manual steps.

Current tools it removes if present:
- **claude-mem** — security issues (open local HTTP port, file-read surface, plaintext API keys). The built-in memory system covers everything it did.
- **notebooklm** — browser automation + Google login on every session wasn't worth it for most users. If you want it back: `git clone https://github.com/PleasePrompto/notebooklm-skill.git ~/.claude/skills/notebooklm`

**If you actively use one of these:** re-install it after the bootstrap runs. The bootstrap only removes it — it doesn't block you from having it.

**How future removals work:** when something gets removed from the default stack, the bootstrap handles the cleanup. You don't need to read release notes or run manual commands — just re-run bootstrap and it takes care of it.

---

## 2026-04-17 (session-end-cascade.md) -- foreground-only git + cross-session lock contention rules

**The problem this fixes:** If you run multiple Claude sessions on the same machine, they share one `.git/` and queue at `.git/index.lock` when closing. The old session-close protocol backgrounded aggregators (`&`) and sometimes deleted live locks (`rm -f .git/index.lock`), which in concurrent setups corrupted the git index and stalled commits for minutes. One session's session-close.md edit on 2026-04-17 lost a 10-minute window to this exact race.

**What changed:**
- Aggregators now run **foreground, sequential** — no `&`, no `run_in_background`. ~5s slower per close, eliminates the entire race class.
- Added a **polite spin-wait commit pattern**: wait for `index.lock` to clear naturally, only `lsof`-check then remove if it's been orphaned 60s+, never blindly delete.
- Hardened the existing "no `git add -A`" rule with the cross-session reasoning (sweeping commits steal staged files from other sessions).

**No action needed** — fix lives in `templates/rules/session-end-cascade.md`. Re-run the install or pull the latest to pick it up.

---

## 2026-04-17 (hooks audit) -- rotate-logs.sh gzip failure cleanup

**The problem this fixes:** If gzip failed mid-write (disk full, permission error), a partial or zero-byte `.1.gz` was left on disk. On the next rotation cycle it would shift to `.2.gz`, polluting the rotation history. The original log was always safe, but the stale partial was never cleaned up.

**What changed:**
- **`hooks/rotate-logs.sh`**: gzip step now uses `if/else`. On success, truncates the original. On failure, removes the partial `.1.gz`. One-line change, no behavior change on the happy path.

---

## 2026-04-17 (later) -- vault-git targeted-paths rule in CLAUDE.md and claude-md-template

**The problem this fixes:** Claude Code was running `git add -A` inside large Obsidian vaults during session close, walking 60K+ files, locking `.git/index.lock` for 10+ minutes, and burning context while the assistant polled for progress. Rules alone aren't enough — future sessions can ignore them.

**What changed:**

- **`CLAUDE.md`**: new "Git in large Obsidian vaults (users' vaults)" section. Instructs the assistant to never run `git add -A`, `git add .`, or unscoped `git status` in a vault. Always pass explicit file paths. Includes a fast diagnostic (`wc -l <(git ls-files)`) to detect whether you're in a large vault.
- **`templates/generated/claude-md-template.md`**: added "Git in this vault (if git-tracked)" section. Ships the rule to every new vault's `CLAUDE.md` via Phase 4 so new users get it on setup, not after an incident.
- **`scripts/auto-snapshot.sh`** (follow-up): rewrote to use targeted paths instead of `git add -A` even with the file-count guard. The guard always aborted on large vaults anyway — the rewrite makes the script actually useful.

**If you already have a large vault under git:** stage only the files you know changed. Session files, decision files, edited rules, to-do edits. Not the whole tree.

---

## 2026-04-17 -- git bloat prevention + vault health check

**The problem this fixes:** Claude Code's worktree isolation feature creates a full copy of your vault for every session. If those copies aren't cleaned up, they accumulate — 32 stale copies discovered in a live vault, totalling 46GB. On top of that, each copy left a `claude/` git branch behind, inflating `.git/objects` to 6GB. Binary files (videos, Photoshop files) committed by accident made it worse.

**What changed:**

- **`scripts/worktree-prune.sh`** (upgraded): now also deletes orphaned `claude/` branches — those whose worktree directory no longer exists. Previously only pruned stale refs. Wire this to a weekly cron or scheduled task.

- **`scripts/vault_maintenance.py`** (upgraded): added a Git Health section to the monthly maintenance report. Checks for: stale `claude/` branches (>5 is a warning), prunable worktrees, and git pack size >500MB. Reports the exact fix commands so you don't have to look them up.

- **`templates/rules/session-end-cascade.md`** (upgraded): added Phase 2b — git snapshot + cleanup. Every session close now removes the current worktree and deletes all `claude/` branches after committing. Prevents accumulation from the source.

- **`templates/rules/advisory-panel.md`** (tightened): intro, Technology & AI section, and Panel Rules compressed ~40%. No panelists removed. The `Pick when:` triggers are unchanged — just stripped the commentary between credential and trigger.

**If you already have bloat:** run the vault maintenance script to see your current state, then follow the fix commands in the report. Or run manually: `git branch | grep 'claude/' | xargs git branch -D && git worktree prune`.

---

## 2026-04-17 -- session close runs on Sonnet

**`templates/rules/session-end-cascade.md`**: added a Model section at the top. The session-close protocol should always run on Sonnet, not Opus. The close is structured, write-heavy work (scanning, filing, batch writes, running aggregators) — no judgment calls. Switching to Sonnet before Phase 0 saves real tokens without losing anything. Claude announces the switch so you know what model is running.

---

## 2026-04-17 -- maintenance hooks, MCP health check, worktree pruner, rollback guide

New scripts and hooks that save common manual recovery steps:

- **`scripts/mcp-config-check.py`** (new): health checker for your MCP config. Catches six silent-fail bugs: malformed .mcp.json, missing server paths, blank env vars, ghost config files, orphan MCP directories, and misplaced user-scoped MCPs. Run at session start or on-demand. Configurable via env vars (VAULT_ROOT, MCP_SCAN_DIRS).
- **`scripts/worktree-prune.sh`** (new): weekly git worktree pruner. Self-locates via $BASH_SOURCE so it survives vault moves. Logs to `logs/worktree-prune.log`. Wire to a cron or scheduled task.
- **`hooks/file-changed-settings.sh`** (new): FileChanged hook that validates .claude/settings.json and .mcp.json on every write. Surfaces a clear error to stderr if JSON is malformed, before a silent failure cascades into broken hooks.
- **`hooks/rotate-logs.sh`** (new): rotates hook logs at 500KB, keeps 3 gzipped generations per file. Auto-discovers *.log files in LOG_DIR. Safe to call every SessionStart. Prevents unbounded log growth on active vaults.
- **`hooks/claude-scheduled-runner.sh`** (new): headless Claude Code launcher for launchd/cron scheduled tasks. Reads the task prompt from a SKILL.md file, runs `claude -p` with a turn cap, logs to ~/Library/Logs. All paths configurable via env (VAULT_ROOT, CLAUDE_BIN, TASKS_DIR, LOG_DIR).
- **`templates/rules/rollback.md`** (new): step-by-step recovery guide when hooks, settings, or plugins break. Diagnosis-first approach (check JSON validity, scan logs, look for stuck locks) before any revert. Nuclear-last ordering.
- **`templates/rules/obsidian-reference.md`** (new): Obsidian-specific reference details. Covers the workspace.json sort-state quirk (why editing app.json doesn't change sort order), macOS APFS folder mtime behavior, and the custom-sort plugin fix.

---

## 2026-04-17 (later) -- token optimization guide + cheap model routing

New `docs/TOKEN_OPTIMIZATION.md`: a practical guide to where Claude Code burns tokens on overhead (spoiler: 5K–20K per message before you type anything) and six fixes that cut 50–70% of that cost. Covers caveman-dense Claude-facing files, a hard cap on MEMORY.md entries, disabling unused MCP servers, routing grunt work to cheap models, and a quarterly compression habit.

New `scripts/minimax.sh`: a thin bash wrapper for MiniMax M2.7 (~$0.06/M tokens, 150x cheaper than Opus). Users supply their own API key from [platform.minimax.io](https://platform.minimax.io). Good for extraction, summarization, and bulk classification — the grunt work you shouldn't pay Opus for.

`docs/MEMORY_SYSTEM.md` now has a hard 50-entry cap and a pre-add checklist (already in CLAUDE.md? skip. one-time bug fix? skip. useful in 3 sessions? if no, skip).

`templates/generated/obsidian-rules-template.md` now ships a "Token Efficiency Rules" block so every new vault starts with the compress-everything mindset baked in.

- **`docs/TOKEN_OPTIMIZATION.md`** (new): the full guide + checklist
- **`scripts/minimax.sh`** (new): generic cheap-model helper
- **`docs/POWER_TOOLS.md`**: new "Cheap model APIs" section
- **`docs/MEMORY_SYSTEM.md`**: 50-entry cap in the hygiene section
- **`templates/generated/obsidian-rules-template.md`**: Token Efficiency Rules block
- **`README.md`**: linked TOKEN_OPTIMIZATION.md in Deeper Documentation
- **Why it matters:** a large vault setup burns hundreds of thousands of tokens per session on overhead alone. These patterns pay for themselves within one session.

---

## 2026-04-17 (later) -- auto-snapshot: guard against large vaults

`scripts/auto-snapshot.sh` now checks tracked file count before running `git add -A`. If the vault has more than 5,000 tracked files (typical Obsidian vault: 10K-60K), the script logs a clear abort message and exits instead of walking the full tree. A full-tree `git add` on a large vault locks `.git/index.lock` for 10+ minutes and burns assistant context while it waits.

No behavior change for small repos (side projects, code repos). If you have a large vault, use explicit-path staging at session close instead.

- **`scripts/auto-snapshot.sh`**: added file-count guard before `git add -A`

---

## 2026-04-17 (later) -- vault-context hook: actual file injection for strategic questions

Previously, the session-protocol hook told Claude to "read Current Priorities.md before responding." That's an instruction — it can be skipped or deferred. In practice, Claude often gave generic answers without ever reading the vault.

Fix: a new `vault-context.py` hook that actually reads the files and injects their contents into context before Claude responds. No instructions to follow — the content is just there.

How it works: on every message, the hook checks for strategic keywords (plan, decision, priorities, client, revenue, strategy, etc.). If matched, it reads `⚙️ Meta/Current Priorities.md` and `⚙️ Meta/Open Loops.md` and passes them as `additionalContext`. Silent on trivial queries (rename, fix typo, etc.). Auto-detects the vault root by walking up from the working directory — no hardcoded paths, works in worktrees.

You can extend it by editing `~/.claude/hooks/vault-context.py` and adding entries to `TOPIC_MAP` — each entry maps a keyword list to a list of additional files to inject (e.g. your raise dashboard, a project brief, a client list).

- **`hooks/vault-context.py`** (new): the hook itself. Auto-detecting, keyword-triggered, silent on non-matches.
- **`hooks.json`**: added vault-context as a UserPromptSubmit hook.
- **`phases/phase-05-context-layer.md`**: added installation step with copy command and wiring instructions.
- **Why it matters:** instructions are unreliable. Injected context is not.

---

## 2026-04-17 (later) -- daily-journal: verbatim-capture rule added

When you're journaling with Claude, you type a lot of things back: answers, tangents, panel replies, corrections. Previously the skill only synthesized those into a smooth narrative, so the exact words got lost. If you later came back looking for something you'd said, it was gone.

Fix: every message you type during a journal session now gets logged word-for-word in a dedicated `### My responses to the panel (verbatim, every message I typed back in this session)` subsection inside the entry. No paraphrase. No summary. Typos preserved. The narrative stays readable; the verbatim appendix is the archive.

- **`skills/daily-journal/SKILL.md`**: new "Verbatim-capture rule (critical — no exceptions)" section near the top (after the separation rule). Updated entry template to require the verbatim subsection. Added reinforcement line in the Step 7 "Important" bullets.
- **Why it matters:** a journal that silently paraphrases you is a journal you stop trusting. The rule is stated in three places now so the model can't skip it.

---

## 2026-04-17 -- wikilink gaps: `--exclude` flag to skip vault author's own name

In personal vaults, the owner's name appears in every journal entry — as a section header, panel pullback marker, signature, or third-person reference. The gaps script was surfacing it as a high-connection "candidate" with thousands of false matches.

Fix: add `--exclude LABEL [LABEL ...]` so users can suppress their own name (or any label) permanently without touching the script.

- **`scripts/graphify_wikilink_gaps.py`**: new `--exclude` flag; excluded labels skip the `is_wikilink_candidate` check entirely. Case-insensitive match.
- **Usage:** `python3 graphify_wikilink_gaps.py --vault-root . --exclude "Jane Doe" "Jane"`

---

## 2026-04-16 (late, part 2) -- auto-wikilink: `--all` flag for vault-wide backfill

`auto-wikilink.py` previously defaulted to journals only. For a mature vault, that leaves years of writing, notes, chats, and CRM with unlinked mentions. Running it on individual folders piecemeal is tedious.

Fix: add a `--all` flag that walks the entire vault, plus a cleaner dir-exclusion model.

- **`scripts/auto-wikilink.py`**: new `--all` flag walks every `.md` file in the vault (respecting the team-vault firewall). Split `EXCLUDED_DIR_NAMES` into `EXCLUDED_TERM_DIRS` (dirs that can't be sources of canonical terms — e.g. AI Chats) and `EXCLUDED_PROCESSING_DIRS` (dirs that can't be written to — e.g. `_archive`, `.obsidian`). AI Chats now receives wikilinks but never supplies them.
- **Use pattern:** `--dry-run --all` first (prints proposed count), review sample, then drop `--dry-run` to apply. On a mature vault this typically connects 10k-50k unlinked references in one pass.
- **Still safe:** existing region-tracking, frontmatter protection, and path-form guard all unchanged. Team-vault firewall still hard-enforced.

Why this matters: an Obsidian alias lets `[[Vanessa]]` resolve to `[[Vanessa Rodriguez]]`, but it does NOT auto-convert plain text "Vanessa" mentions across your vault. `--all` closes that gap retroactively, so the graph actually reflects what you wrote.

---

## 2026-04-16 (late) -- Model routing: flip the default, add a nudge hook

Most sessions silently run the biggest model available even for trivial tasks because users set `"model": "opus"` (or `opusplan`) once and forget. The rules at the SKILL level say "route to the right model" but no mechanism enforces it — and a running Claude session can't swap its own model mid-turn.

Fix: flip the default, add a lightweight nudge.

- **`hooks/route-suggest.py`** (new): UserPromptSubmit hook. Classifies each prompt by keyword — strategy/panel/architecture → suggest `opus`; trivial edit → suggest `haiku`; extraction/tagging/boilerplate → suggest a cheap model (minimax/local). Silent when no confident match. Never auto-switches — just prints a one-line `[route nudge]` the user sees in context.
- **`templates/rules/efficiency.md`**: added Rule 30 — "Never push back with 'too long' or 'too expensive.'" Cost appeals shut down conversations; specific blockers open them. Banned phrases listed.
- **Recommended default:** set `"model": "sonnet"` in settings.json and use `/model opus` or a shell alias (e.g. `cc-deep='claude --model opusplan'`) when you actually need heavy reasoning. Opus becomes opt-in, not opt-out.

Why this matters: a dumb router with the right default beats a smart router with the wrong one. Flipping the default is one line; the nudge hook catches the 20% of prompts where the default is wrong. Together they cut token burn without adding decision fatigue.

---

## 2026-04-16 (evening) -- Dropped Calendar + Juggl from default stack

Audited the installed Obsidian plugins against actual usage. Two plugins weren't earning their spot: Calendar (dead weight once `/journal` became the entry point — nobody was clicking dates) and Juggl (zero config data, zero note references — graph exploration happens via Graphify + Smart Connections now).

- **`phases/phase-02-03-plugins-folders.md`**: removed `calendar` and `juggl` from the PLUGINS dict and from the manual-fallback walkthrough. Auto-installer now ships 6 plugins, not 8.
- **`templates/rules/obsidian-plugins.md`**: dropped the Juggl section; "Visual Graph Exploration" now points only at Neo4j Browser.
- **`templates/rules/tool-routing.md`** + **`docs/POWER_TOOLS.md`**: removed Juggl/Calendar from routing tables and power-tool catalog.
- **`skills/insights/SKILL.md`**: removed Juggl from the monthly plugin-update scan list.

Existing installs aren't auto-removed — this only affects new `/setup-brain` runs. If you want to drop them from an existing vault, delete `.obsidian/plugins/{calendar,juggl}` and remove them from `community-plugins.json`.

---

## 2026-04-16 (night) -- Windows parser bug + bootstrap cleanup

Post-consolidation audit caught three things: a PowerShell parser bug that broke every Windows bootstrap run, bun left in as dead weight, and install verbs that leaked past the phase-file firewall.

- **`bootstrap.ps1`**: `"$sub:"` in two status lines was parsed by PowerShell as a scope accessor (`$scope:name`), erroring on every bundled sub-skill. Fixed with `"${sub}:"`. Sergio (and any Windows user) would have hit this on every install.
- **`bootstrap.sh` + `.ps1`**: removed bun. It was a claude-mem runtime dep that stayed after claude-mem was dropped. Nothing currently depends on it.
- **`phases/`**: pulled remaining install verbs (brew/winget/snap/flatpak/git-clone/cp -R/mcpServers) out of phase-01, -04, -06-09, -11. Phases now defer to bootstrap for any install recovery.
- **CHANGELOG**: compressed the top three entries from 3-paragraph templates to 1-paragraph + bullets. Cleanup commits don't need the full template.

---

## 2026-04-16 (late evening) -- Single source of truth for installs: bootstrap canonical, Phase 0 thin

Install logic lived in two places (`bootstrap.sh`/`.ps1` AND `phases/phase-00-install.md`) with 80% overlap; they drifted and users on different paths got different stacks.

- **`bootstrap.sh`** and **`bootstrap.ps1`** are the ONE source of truth: fastmcp, full bundled sub-skill set (insights, deconstruct, daily-journal, repurpose-talk, nano-banana skill folder), granola + chatprd MCPs, obsidian-skills marketplace, obsidian/context7/playwright plugins, Mac Obsidian CLI symlink. `--dry-run` skips verification.
- **`phases/phase-00-install.md`** rewritten 431 → 158 lines: thin orchestrator only. Invokes the local bootstrap, then Granola login walkthrough, Obsidian CLI confirmation, nano-banana deferred install, Knowledge Graph CLAUDE.md rule template.

Every install path (curl one-liner, /setup-brain, re-run) now hits the same code. Windows parity via `.ps1` in the same commit, not deferred.

---

## 2026-04-16 (evening, later) -- Enforce compressed Claude-facing docs at tool level

Memory-level rules require active recall and get skipped; moved compression enforcement into a tool-level hook so it fires regardless.

- **`templates/hookify-rules/hookify.compress-claude-docs.local.md`** (new): warn-level hook on writes to memory files, hookify rules, vault rule files, and CLAUDE.md. Shows the rules inline at tool-use time.

---

## 2026-04-16 (evening) -- Fix duplicate note titles (filename + H1)

Scripts and templates were writing `# Title` after frontmatter; in Obsidian the filename IS the title, so every note rendered its heading twice.

- **`scripts/granola_sync.py`**: dropped the `# {title}` line; auto-imported notes now start with the `*Auto-imported...*` context line.
- **`phases/phase-06-09-tools-templates.md`**: CRM Entry and Meeting Note templates no longer include `# {{title}}` after frontmatter.
- **`templates/hookify-rules/hookify.no-duplicate-h1.local.md`** (new): opt-in warn rule catching any H1 written after frontmatter in a `.md` file.

---

## 2026-04-16 (late p.m.) -- Session close protocol: no more stubs, 7-day retention, compressed rule

**The problem:** the session-end-hook created a "stub" session file every time the hook fired, expecting Claude to fill it in. In practice most sessions end without running the full protocol (short sessions, abrupt exits, worktree subagents, compactions), so stubs piled up unused. One user had 966 of 1,046 files as empty stubs -- 92% noise, 4.2 MB of clutter in the `⚙️ Meta/Sessions/` folder.

**What changed:**

**`scripts/session-end-hook.sh`** (rewritten):
- No longer creates stub files. Claude writes the real session file directly during session close (Phase 2 of the protocol).
- Added retention cleanup on every hook invocation: stubs older than 7 days are deleted, substantive files older than 7 days are archived to `Sessions/Archive/`. Fast and idempotent -- only touches files past the cutoff.
- Cross-platform date math (BSD `date -v-7d` on macOS, GNU `date -d '7 days ago'` on Linux).
- Step 4 prompt trimmed: points Claude at the session-close rule file instead of restating the entire protocol inline in a JSON blob.

**`templates/rules/session-end-cascade.md`** (rewritten, same filename for install compatibility):
- Went from 7 lanes / 192 lines to 4 phases / 84 lines. No information lost -- just compressed per the "caveman prose" rule (machine instructions, not human-facing).
- Phase 0: run `date` once, reuse the timestamp everywhere (session file, time tracking, to-do dates).
- Phase 1: single-pass conversation scan fills all output buckets in memory before writing anything.
- Phase 2: batch writes in parallel, aggregators run in background.
- Phase 3: conditional change-impact audit and repo propagation.

**`phases/phase-05-context-layer.md`**: the inline hook template embedded in the phase doc was updated to match the new scripts/ version (no stubs, retention cleanup, compressed Step 4 prompt).

**`phases/phase-04-claude-md.md`**: the CLAUDE.md session-end section was updated from "7-lane capture cascade" to "4-phase session close protocol" to match the new rule file.

**Why this matters for you:**
- Your `⚙️ Meta/Sessions/` folder will stop filling up with empty placeholders.
- The folder self-cleans: anything older than 7 days either goes away (stubs) or moves to `Archive/` (substantive). You get a week of rolling context, nothing more.
- Session close runs faster (single-pass scan, parallel writes, background aggregators).

**Upgrade notes:**
- If you already have hundreds of stub files, delete them: `grep -rl 'session_label: "update pending"' "$VAULT/⚙️ Meta/Sessions/" | xargs rm` (one user went from 1,046 files / 4.2 MB to 83 files / 476 KB).
- The new hook is backward-compatible with existing substantive session files; they'll sit untouched until they pass the 7-day cutoff, then move to `Archive/`.

---

## 2026-04-16 (p.m.) -- Removed claude-mem from bundled stack (security)

Dropped claude-mem from the default install after a security audit surfaced: (1) unauthenticated local HTTP API on port 37777; (2) arbitrary file-read via the `smart_unfold` / `smart_outline` MCP tools; (3) API keys stored plaintext at `~/.supermemory-claude/credentials.json`; (4) a `UserPromptSubmit` hook injecting content into every session (persistent prompt-injection surface); (5) deprecated `glob@11.1.0` transitive dep flagged for ReDoS; (6) PreToolUse:Read hook truncating Read output to line 1 (we had shipped a local patch around this).

Fresh installs no longer register the `thedotmack` marketplace, enable `claude-mem@thedotmack`, install `bun` as a claude-mem runtime, or run `npx claude-mem install`. Existing installs that already had it are NOT auto-uninstalled (bootstrap is additive). To remove manually: `claude plugin uninstall claude-mem@thedotmack` + drop the `thedotmack` entry from `extraKnownMarketplaces` in `~/.claude/settings.json`.

What replaces it for most users: the auto-memory system at `~/.claude/projects/.../memory/` (typed markdown files, durable, human-readable) plus graphify for cross-session knowledge. That combo covers `mem-search` / `knowledge-agent` use cases without the attack surface. For AST-aware code search (the one unique capability), install `ast-grep` as a standalone CLI if a specific project needs it.

Removed from: bootstrap.sh, bootstrap.ps1 (if present), README.md, docs/POWER_TOOLS.md, phases/phase-00-install.md, phases/phase-01-welcome.md, phases/phase-06-09-tools-templates.md, scripts/patch-claude-mem-read-hook.sh (deleted).

---

## 2026-04-16 (p.m.) -- Removed notebooklm from bundled stack

Dropped the notebooklm skill from the default install. Not part of the daily workflow for most users; the overhead (Chromium browser automation, Google auth dance, first-run setup) wasn't paying off. If you want it, clone directly: `git clone https://github.com/PleasePrompto/notebooklm-skill.git ~/.claude/skills/notebooklm`. Existing installs are untouched (bootstrap never overwrites the folder).

Removed from: bootstrap.sh, bootstrap.ps1, README.md, docs/POWER_TOOLS.md, phases/phase-00-install.md, phases/phase-06-09-tools-templates.md, scripts/vault-repo-drift-check.sh, skills/notebooklm/.

---

## 2026-04-16 (p.m.) -- Session close rule: compressed + restructured

**templates/rules/session-end-cascade.md** (rewrite, 191 → 85 lines):
- Renamed "11-lane capture cascade" to "Session close protocol" and restructured into Phase 0 (single timestamp) / Phase 1 (single-pass scan with output buckets) / Phase 2 (batch writes) / Phase 3 (verify + propagate). Same semantics, dense caveman prose.
- Added explicit "Report zeros, never skip silently" directive and a templated summary format so every session ends with the same shape.
- Backgrounded both aggregators in Phase 2 (parallel `&`) for faster wall time.
- Added Phase 0 timestamp discipline: one `date` call per session, reuse everywhere.
- Added 7-day retention policy (session files archived or stubbed, prevents unbounded growth).
- Kept the `gh issue create` heredoc under Phase 3 so end users have the actual command, using `<owner/repo>` placeholder.
- Tightened skip condition: <5 user messages with no decisions/info/learnings.

## 2026-04-16 (p.m.) -- Hookify template README: correct upstream URL

**templates/hookify-rules/README.md**:
- Fixed two links that pointed to `github.com/anthropics/claude-code/tree/main/plugins/hookify`. The hookify plugin actually lives in a separate repo: `github.com/anthropics/claude-plugins-official/tree/main/plugins/hookify`. Both references updated.
- Discovered while filing an upstream PR to fix a CLAUDE_PLUGIN_ROOT fallback bug in hookify itself: [anthropics/claude-plugins-official#1441](https://github.com/anthropics/claude-plugins-official/pull/1441).

## 2026-04-16 (p.m.) -- Claude Performance Self-Improvement System

**scripts/claude_performance_digest.py** (new):
- Weekly digest script that reads Claude Code JSONL session data from ~/.claude/projects/ and computes six effectiveness metrics: activity distribution (Coding/Exploration/Debugging/Delegation/Planning/Conversation), one-shot edit rate, agent spawn analysis, model mix (Opus/Sonnet/Haiku), per-project allocation, and hookify firings.
- Six diagnostic rules with configurable thresholds. When triggered, writes prescriptive to-dos to "Claude To-dos.md" for investigation items, and for four specific rule types (VERBOSE AGENTS, MODEL ROUTING, LOW ONE-SHOT RATE, EXPLORATION OVERHEAD) writes permanent behavioral rules to ~/.claude/CLAUDE.md so future sessions read them at start.
- Stdlib only, stream-parses JSONL, idempotent to-do appending. Self-locates via __file__. Configurable PROJECT_LABELS dict for clean display labels.
- Usage: python3 scripts/claude_performance_digest.py [--days N] [--dry-run] [--no-report]

## 2026-04-16 -- Plugin hook fix + graphify encoding hardening (Lessons #95-99)

**scripts/fix-plugin-hooks.sh** (new):
- Claude Code does not reliably expand `${CLAUDE_PLUGIN_ROOT}` in plugin hooks.json. When the variable is unset, hook commands resolve to a nonexistent path, error, and Claude Code defaults to BLOCK for PreToolUse -- silently denying all Write/Edit operations. Run this script after any plugin install to replace all `${CLAUDE_PLUGIN_ROOT}` references with absolute paths. Safe to re-run.

**graphify_stage_finish.py** -- encoding hardening (Lesson #98):
- All `write_text()` calls now use `encoding="utf-8"`. Without it, emoji characters in node labels (e.g. folder names like `📋 Strategy`) can be silently mangled on some systems. Affected calls: raw JSON, canon JSON, graph.json (already had `ensure_ascii=False`, now also has explicit encoding), GRAPH_REPORT.md, and extraction_manifest.json.

**graphify_stage_select.py** -- SKIP_PARTS expanded (Lesson #89):
- Added `⚙️ Meta` and `🗄 Archive` to the skip set. Without these, vault meta folders (templates, GRAPH_REPORT.md, runbook files) would appear as eligible extraction candidates, inflating file counts and wasting LLM tokens.

**What NOT to do (Lesson #99)**:
- Never write `graph.json` directly from a NetworkX object (`nx.node_link_data()`). The `hyperedges` key lives outside the NetworkX model and is silently dropped. Always use `graphify_stage_finish.py --num-chunks 0` for recluster/report-only runs -- it reads `merged_graph` as a dict and preserves hyperedges through the full pipeline.

---

## 2026-04-16 -- Graphify pipeline hardening: layout auto-detect, mtime manifest, dual-SHA, cache pruner

Four improvements to the graphify staged-rollout scripts, plus a new utility:

**graphify_stage_select.py** (rewrite):
- Layout auto-detect (Lesson #87): detects personal vs. multi-vault (team) layout at startup. Personal vault keeps cache + chunks under graphify-out/. Team layout splits cache at vault root, chunks under corpus subfolder. Prints layout name for clarity.
- SKIP_PARTS filter (Lesson #89): excludes Archive/, _review_alternate_drafts/, and iCloud/GDrive conflict copies ("foo 2.md") from file listing. Prevents non-content files from entering the extraction pipeline.
- Mtime-manifest short-circuit (Lesson #93): reads extraction_manifest.json and skips files whose mtime is within 5 seconds of their last LLM extraction. Falls back to SHA check when the manifest doesn't cover a file. Cuts re-run times dramatically on large vaults.
- Dual-SHA cache lookup (Lesson #94): tries both relative-to-vault and absolute path variants when checking the SHA cache. The graphify library uses relative paths internally, older scripts used absolute. This prevents false cache misses after upgrades.
- Now accepts multiple corpus folders in a single run and supports --max-files-per-chunk (default 45) to prevent schema collapse on large batches.

**graphify_stage_finish.py** (rewrite):
- Layout auto-detect with --corpus-folder and --cache-dir args. Auto-detects corpus folder by scanning vault children. Uses detected base path for raw/canon output, graph path, and report path.
- Manifest writer (Lesson #93): after cache save, writes extraction_manifest.json with per-file entries (llm_time, sha, node_count, stage). This is the write side of the mtime short-circuit that select.py reads.
- Fixed cache_dir in Step 5b to use args.cache_dir instead of hardcoded path.
- Added import hashlib (required for manifest SHA computation).

**graphify_prune_stale_cache.py** (new):
- Deletes cache entries whose SHA256 key no longer matches any current file. Run monthly or after vault restructuring. Honors the same SKIP_PARTS and dual-SHA logic as select.py.

**patch-claude-mem-read-hook.sh** (new):
- Disables the claude-mem PreToolUse:Read hook that replaces file content with a one-line summary. Idempotent, creates timestamped backup before patching. Run after any claude-mem plugin update.

---

## 2026-04-16 -- Bug fixes: pip, graph edge key, directed graphs, and skill guardrails

Porting improvements that surfaced from production use:

**graphify/SKILL.md** -- Three fixes:
- `pip install` changed to `"$PYTHON" -m pip install` (with bare-pip fallback). Prevents the case where the system `pip` installs to a different Python than the one graphify actually runs under, causing "module not found" on first run.
- Added `--directed` flag to the usage table. Builds a `DiGraph` that preserves edge direction (source to target) instead of the default undirected `Graph`. Useful for code dependency graphs, citation networks, or any corpus where direction matters.
- Added `--whisper-model` flag to the usage table. Lets you pass a larger model (`small`, `medium`, `large`) when transcribing audio/video files for higher accuracy at the cost of speed.

**meeting-todos/SKILL.md** -- Added guardrail to the description: "Do NOT use for general task management, journaling, or pulling full meeting transcripts (use the meeting workflow for that)." Prevents Claude from triggering this skill when someone asks to journal or pull a full transcript.

**patterns/SKILL.md** -- Added guardrail: "Do NOT use for weekly/monthly journal reviews (use insights), daily journaling (use daily-journal), or one-off decisions (use deconstruct)." Clarifies the skill's scope so Claude routes correctly instead of running `/patterns` on a prompt that belongs in `/journal` or `/weekly`.

---

## 2026-04-15 -- To-do system template

New template: `templates/generated/todo-system-template.md`. A complete prioritized task management system for Obsidian with Dataview integration.

**What it includes:**
- **Main to-do file** with P1/P2/P3 priority tiers, Dataview inline fields (`[area::]`, `[priority::]`, `[due::]`), and a Done Archive section
- **This Week view** that auto-pulls all P1 items via Dataview (never needs manual refresh)
- **Waiting On tracker** with sections for delegations, external blockers, and "blocked on self" items
- **Team variant** with per-person views, `[owner::]` field, and sprint progress queries

**System rules baked in:**
- Lint rule: every task must have `[area::]` and `[priority::]` or Claude adds them on contact
- Stale item decay: open items older than 14 days with no due date get flagged during weekly reviews
- Overdue rule: past-due items auto-surface and must be re-dated or dropped
- Priority assignment framework: three questions (hard deadline? someone blocked? moves top goal?)

**Integration:** Added as a conditional folder in Phase 2-3 (only created if the user wants in-vault task management). Personal to-do Dataview queries added to the query library.

Born from the maintainer's own vault restructure: the "organize by when I thought of it" pattern always decays into a mess. Priority tiers with inline fields and auto-refreshing views don't.

---

## 2026-04-15 -- Graph query MCP + conditional graph loading + Minimax routing + session length flag

Four optimizations for high-volume, multi-account Claude setups:

**Graph query MCP** (`scripts/mcps/graph-query-server.py`): FastMCP server that loads your vault graph (NetworkX node-link JSON) at startup and exposes surgical tools: `search_nodes`, `get_neighbors`, `find_path`, `query_subgraph`, `get_community_members`. Replaces reading the full GRAPH_REPORT.md (~3K tokens) every time you ask a question. Load graph once, query it many times. Supports two vaults via `scope` param ('primary'/'secondary'). Requires two env vars: `GRAPH_JSON_PATH` and `SECOND_GRAPH_JSON_PATH`. Install via `fastmcp` (pip) and add to `.mcp.json`.

**Conditional graph loading** (`templates/generated/claude-md-template.md`): Session Protocol step 1 changed from "always load both graphs" to "load only when the first message is topic-relevant." Keyword hook (`graph-context-hook.sh`) catches natural-language queries (not just exact nouns) so casual questions like "what's my pattern with money?" or "my pitch needs work" trigger graph loading automatically. Saves 6K+ tokens on sessions that don't touch the graph.

**Explicit Minimax routing list** (`templates/rules/efficiency.md`, rule 28): Five operation types always route to the cheap model without asking: (a) structured extraction from raw text, (b) bulk tagging/classifying, (c) boilerplate from template, (d) single-doc summary under 5K tokens with no voice requirement, (e) pre-extraction for graphify/weekly/insights pipelines. Removes the hesitation loop where Claude second-guesses whether to route.

**Session length flag** (`templates/rules/efficiency.md`, rule 29): At 30 exchanges, surface a reminder to run `/compact`. Long sessions degrade in the back half. Early compaction keeps the context clean.

---



## 2026-04-14 -- Advisory panel: Colombia localization section + named-only rule

Two additions to the advisory panel template:

- **New "Colombia: Life & Business" section** with 8 named, integrity-verified voices covering corporate culture (Carlos Raul Yepes), brand building (Catalina Escobar), cultural identity (Hector Abad Faciolince), business law (Francisco Reyes Villamizar), women in business (Sylvia Escovar), relationships/gender (Florence Thomas), bicultural identity (Patricia Engel), and holistic wellness (Dr. Jorge Carvajal Posada). Every person was researched for integrity before inclusion.
- **Rule #8: Named panelists only.** Claude must never invent archetypes or unnamed experts. Every panel voice must be a named person from the roster. If none fit, say so and offer to add one. Prevents fabricated "a hospitality GM" or "a marketplace founder" style voices.

## 2026-04-14 -- Doc compression rule + memory durability enforcement

Two new efficiency rules that make the whole setup more reliable:

- **Rule #25: Compress all Claude-facing docs.** Every file Claude reads (rules, runbooks, SKILL.md, CLAUDE.md, templates) must fit in a single Read call (<10k tokens). Dense prose, no filler. If a file exceeds the limit, split it. This prevents the Read tool from silently truncating important instructions.
- **Rule #26: Memory durability.** Never store something only in Claude's project memory. Memory is tied to one account on one machine. Every memory must also be written to a vault file in the same response. The vault is the source of truth across all accounts and computers.

Both rules in `templates/rules/efficiency.md`.

## 2026-04-14 -- MCP Build Runbook + 13 build lessons

New `docs/MCP_BUILD_RUNBOOK.md` — the full protocol for building MCP servers and managed agents on top of this vault setup. Distilled from a single build session that shipped 13 agents.

What's in it:
- **Optimization Pass** (mandatory before every build): kills over-engineered stacks before you write code. Saved multiple Next.js + Postgres + Railway setups that were meant for one internal user.
- **13 lessons** from real builds: symlink handling in macOS vaults, dict access safety, lazy Anthropic client pattern, datetime.utcnow() deprecation fix, financial math goes in Excel not Python/LLM, and more.
- **Self-test protocol**: every agent must pass a no-API-key self-test before it's done.
- **GitHub publishing checklist**: strip personal data, standard files, README requirements.
- **Which agents are worth publishing**: decision table for when to open-source vs keep private.

The lazy client pattern and symlink rules alone will save most people 30-60 minutes per build.

## 2026-04-14 -- ChatPRD and RescueTime MCP setup docs + RescueTime server script

Two new MCP integrations documented and ready to use:

- **ChatPRD MCP** — HTTP MCP at `https://app.chatprd.ai/mcp`. Add to your vault `.mcp.json`, authenticate once via OAuth, and Claude can create/read/search PRDs directly from Claude Code. Setup snippet in `docs/POWER_TOOLS.md`.
- **RescueTime MCP** — Custom FastMCP server at `scripts/mcps/rescuetime-server.py`. Gives Claude read access to your productivity data (pulse, top apps, category breakdown, trends). Pairs with the session-end time tracking lane so `/weekly` reviews can merge app-level data (RescueTime) with purpose-level logs (session end cascade). Setup instructions in `docs/POWER_TOOLS.md`.
- **Tool routing template updated** — added RescueTime row so the routing table is complete for anyone who sets it up.

Important: never commit your RescueTime API key or ChatPRD tokens. Keep secrets in the `env` block of your vault `.mcp.json` and make sure that file is gitignored.

---



## 2026-04-14 -- custom-sort auto-activates on install (no manual toggle needed)

- **Fix:** custom-sort plugin now writes `data.json` with `suspended: false` during Phase 2 setup. Previously the plugin installed silently disabled (Obsidian's default is `suspended: true`) and required a manual ribbon-click to activate. First-time users had no idea why their folders weren't sorting. This is now handled automatically.

---



## 2026-04-14 -- Journal organization by month + insights save path fix

- **New script: `scripts/organize-journals.py`** — organizes a flat Journals folder into month subfolders ("January 2026", "February 2026", etc.) based on the `creationDate` field in each entry's YAML frontmatter. Also moves any existing `Monthly Summaries/` and `Weekly Insights/` subfolders into their matching month folders and removes the empty parent folders. Run once to reorganize, or after any bulk import. Usage: `python3 scripts/organize-journals.py --vault-root "/path/to/vault"`.
- **Insights skill save path updated** — `/weekly` and `/monthly` reports now save directly inside the appropriate month folder (e.g. `Journals/April 2026/Apr. 7-13, 2026 Weekly.md`) instead of a separate `Weekly Insights/` or `Monthly Insights/` root subfolder. Keeps all content for a given month together in one place.

---



## 2026-04-14 -- Recursive folder sorting by most recently modified

- **New plugin: Custom File Explorer sorting** (`custom-sort` by SebastianMC). Phase 2 now installs this automatically. It sorts every folder in your vault by the most recently modified note *inside* it, recursively. This means if you edit a file deep inside a subfolder, that folder and all its parents bubble to the top of the file explorer — not just the file itself. Fixes the limitation where Obsidian's built-in sort only used the folder's own filesystem mtime (which macOS doesn't update recursively).
- **New file: `sortspec.md`** at vault root. Auto-generated during setup. Contains the `> advanced recursive modified` rule for all folders. You can customize per-folder rules here if needed.

---



## 2026-04-14 -- Optional time tracking lane in session-end cascade

- **New Lane 8 (optional): Time tracking.** If you add a "Time tracking" preference to your CLAUDE.md, Claude will auto-log what you worked on at the end of each session, categorized by type (Writing, Business, Vault, Personal, Admin, etc.). No manual tagging needed: Claude infers the category from conversation context. Pairs well with productivity APIs like RescueTime for a combined "what app" + "what purpose" view during weekly reviews. Opt-in: does nothing unless you enable it.
- Session-end cascade is now 9 lanes (was 8). Lane 9 is the former Lane 8 (change impact audit).

---



## 2026-04-14 -- Customer discovery meeting template + to-do system guidance

- **New template: `templates/meeting-prep-discovery.md`** -- A Mom Test-based customer discovery meeting prep template. Includes: 3-point agenda to send the client, role assignments (lead/relationship owner/listener), 30-question bank organized by block (their world, pain points, how they buy, competitive landscape, expansion), meeting structure with time blocks, case study outline draft, and post-meeting action items. Generic and ready to use for any B2B client meeting. Based on Rob Fitzpatrick's "The Mom Test" framework.
- **To-do system tip: external tracker callout** -- When team members use an external task tracker (Linear, Jira, Asana) for certain work (e.g., engineering), don't duplicate those tasks in the vault. Instead, add a callout in the vault to-do file noting where those tasks live. Prevents sync drift and double maintenance.

---

## 2026-04-15 -- Advisory panel: Technology & AI section

Five new panelists covering the AI/automation gap most knowledge workers have in their advisory roster:

- **Ethan Mollick** (Wharton/Co-Intelligence) — practical AI integration, what to delegate vs. own
- **Tiago Forte** (Building a Second Brain) — PKM, vault architecture, knowledge compounding
- **Andy Matuschak** (evergreen notes, tools for thought) — stress-tests whether systems actually change thinking over time
- **Andrej Karpathy** (Tesla AI, OpenAI) — technical AI sanity-checks, capability assumptions
- **Tim Ferriss** (4-Hour Workweek) — ruthless elimination, delegation, systems over heroics

Pick when: AI workflow decisions, vault/system design, automation choices, delegation triage.

---

## 2026-04-14 -- Cowork project guide + floor voice verification

- **New doc: `docs/COWORK_PROJECTS.md`** — Guide for creating project-scoped CLAUDE.md files when using Cowork projects. Includes template, architecture diagram, and tips from real usage (iterate with Cowork feedback, split tool routing, don't over-duplicate). Solves the common problem where a Cowork project scoped to a subfolder doesn't inherit root vault context.
- **Writing voice as floor verification** — New section in SKILL.md (under "Emotional floor tagging") that teaches Claude to cross-check floor assignments against writing style, not just content. Includes a voice signature table for all 16 floors and cross-floor heuristics (entry length, bilingual code-switching, body vocabulary). Template is calibrated per-user after ~100 entries.

---

## 2026-04-13 -- Naming conventions + journal integration

- **Insight report naming:** Weekly reports now use human-readable dates (e.g., "Apr. 7-13, 2026 Weekly.md") instead of ISO week numbers. Monthly uses "Apr. 2026 Monthly.md".
- **Journal / Session Captures integration:** Daily journal skill now checks the Session Captures staging file before starting the interview, surfaces accumulated seeds, and deletes them after use.
- **Journal index note:** Users with emoji folder names (e.g., "Journals" vs. "Journals") must pass `--journal-dir` and `--meta-dir` explicitly to `build-journal-index.py`, or update the defaults in the script to match their vault structure.

---

## April 13, 2026 (forty-second session -- LLM accuracy guardrails)

Five new efficiency rules that prevent Claude from guessing when a tool gives the right answer instantly:

- **Rule #10: Never count in-context.** Use `wc` for words/chars/lines. LLMs tokenize subwords, not characters, so counting by reading is architecturally unreliable.
- **Rule #11: Never do math in-context.** Use `python3 -c` or `bc` for any arithmetic. Anthropic's own docs say to verify with specialized software. There's an open bug for this (anthropics/claude-code#9421).
- **Rule #12: Verify wikilinks exist.** Check with `obsidian unresolved` or Glob before creating `[[links]]`. Never link to non-existent notes without flagging it.
- **Rule #13: Use IANA timezones.** Never hardcode UTC offsets or use ambiguous abbreviations (EST/EDT). Use `python3` with `zoneinfo` for conversions. DST differences between cities make offsets unreliable.
- **Rule #14: Check file size before reading.** Run `wc -l` first. Under 2000 lines: read whole. Over 2000: use offset/limit. Over 5000: question whether you need the whole file.

---

## April 13, 2026 (forty-first session -- always check system clock)

- **Efficiency rule #9: Always check the system clock.** Claude's internal sense of time is unreliable, and the system prompt only provides a rough date (no time). New rule: always run `date` in bash before writing any timestamp. Applies to journal entries, meeting notes, file headers, session captures, and to-do dates. Use `date "+%Y-%m-%d %I:%M %p"` for human-readable format.

---

## April 13, 2026 (fortieth session -- optimize-on-repeat + change impact audit)

Two process improvements ported from production use:

- **Efficiency rule #8: Optimize on repeat.** Expanded beyond "recurring processes get a runbook." Now: before running a repeated task, review what happened last time. After running, note what could be better and fix it immediately (update the runbook, fix the script, add a rule, file the bug). The key addition is "don't just note it and move on." Document deduplication misses, schema violations, hung steps, parallelization opportunities, caching gaps, new tools, and pattern drift.

- **Session close Lane 8: Change impact audit.** When a session modifies rules, scripts, skills, hooks, schedules, integrations, or paths, verify nothing broke before closing. Six checks: (1) paths resolve, (2) skills still trigger, (3) hooks still fire, (4) schedules still run, (5) cross-file references valid, (6) integrations connect. Catches silent breakage from renamed paths, moved files, or updated configs.

---

## April 13, 2026 (thirty-ninth session -- Session-close capture system)

- **Session close protocol:** 8-lane automatic capture at end of every session (journal seeds, writing notes, actionable content, to-dos, delegations, decisions, belief shifts, change impact audit). Nothing valuable stays trapped in chat transcripts.
- **Session Captures staging file:** template added for journal seed accumulation across sessions. Journal skill pulls from it and deletes used items.
- **Decision archive lifecycle:** active decisions in Decisions/ move to Decisions/Archive/ after Outcome + Pattern are filled in during weekly/monthly retrospectives.
- **Decision retrospective:** added to weekly/monthly insights skill (section 5b2) to close the loop on past decisions.

---

## April 13, 2026 (thirty-eighth session -- Obsidian sort order)

Phase 2 plugin installer now configures `fileSortOrder: "byModifiedTime"` in `.obsidian/app.json` during setup. Files and folders sort by most recently modified (newest first) out of the box. Uses `setdefault` so it won't overwrite if the user already set a preference.

## April 13, 2026 (thirty-seventh session -- new skill + panel automation)

Added **1 new skill** and **1 automation script**:

- **repurpose-talk** (`/repurpose-talk`) -- turns a speaking engagement into 10-30 content pieces. Extracts key insights, stories, and one-liners, then generates LinkedIn posts, short-form notes, article seeds, and a video clip plan with timestamps. Includes a 2-week posting calendar and cross-pollination checks (business angles, investor soundbites, CRM follow-ups). Supports bilingual output. Trigger: `/repurpose-talk` or "I just gave a talk."
- **panel-trigger-hook.sh** -- a UserPromptSubmit hook that detects decision language in prompts ("should I", "weighing", "torn between", "pros and cons", etc.) and injects an advisory panel reminder so Claude pulls 3-5 relevant voices with mandatory dissent. Silent passthrough on non-decision prompts. Install by adding to settings.local.json hooks. Solves the problem of advisory panels only firing when explicitly invoked -- this makes them proactive.

## April 13, 2026 (thirty-sixth session -- 5 new skills)

Added **5 skills** that were missing from the repo:

- **daily-journal** -- conversational journaling with floor detection, behavior accountability, and advisory panel dialogue. Interviews you, identifies your emotional floor, runs checks (gym, sleep, scrolling), consults 90+ advisory voices, and saves a properly formatted entry. Includes idea quarantine and to-do extraction.
- **humanizer** (v2.7.0) -- removes AI writing patterns from text using Wikipedia's 29-pattern library. Pre-flight doc-type detection, voice calibration against your own writing, Spanish/bilingual support, 4-tier ROI-ranked pattern ordering, and adaptive pass strength.
- **insights** (/weekly, /monthly) -- generates insight reports from journal entries with floor trends, life coach flags, therapist observations, 60+ panel voices, first-principles audit, skill usage snapshots, and Obsidian ecosystem checks.
- **nano-banana** -- image generation via Google Gemini 3 Pro Image. Text-to-image, editing, multi-image composition (up to 14 images), iterative refinement, and search-grounded generation.
- **notebooklm** -- query Google NotebookLM notebooks from Claude Code for source-grounded, citation-backed answers. Browser automation, library management, persistent auth.

All skills were sanitized: personal paths replaced with `[VAULT_PATH]`, names removed, personal context genericized. Panel rosters preserved (they're public figures and the framework is universal).

---

## April 13, 2026 (thirty-fifth session -- proactive compaction rule)

Added efficiency rule #7: **compact proactively at ~50% context usage.** Long sessions (graph pipelines, weekly reviews, multi-step cascades) degrade quality when context fills silently. The rule is simple: if you've done 3+ major tasks, compact before the next one. The PreCompact hook already preserves state, so compaction is safe.

---

## April 13, 2026 (thirty-fourth session -- patterns auto-detection)

The `/patterns` skill (Instinct Engine) now has **session-end auto-detection triggers** inspired by Hermes Agent's skill generation heuristics. Instead of only running when you manually invoke `/patterns`, Claude now silently evaluates four triggers at the end of every session:

1. **High tool-call friction** (5+ calls for routine work, suggesting a missing shortcut)
2. **User correction** (approach was wrong, may echo a recurring pattern worth codifying)
3. **Dead-end recovery** (backtracked before finding the right path, worth preserving)
4. **Non-trivial discovery** (undocumented finding that should become a rule)

If any trigger fires, Claude suggests running `/patterns` but never auto-runs it. You can say "yes" (full scan), "just save it" (quick capture), or "no" (skip).

---

## April 13, 2026 (thirty-third session -- vault maintenance automation)

Three additions that keep your vault clean automatically so it doesn't become a junk drawer over time:

1. **Vault maintenance script.** New `scripts/vault_maintenance.py` runs a monthly hygiene scan checking 7 categories: inbox overdue files, naming issues (too-long or lowercase-starting filenames), stray binaries outside designated folders, backup file accumulation, empty folders, oversized folders (500+ files), and graphify backup count. Writes a Markdown report to your Meta folder. Fully configurable via CLI flags.

2. **Graphify backup rotation script.** New `scripts/rotate_graphify_backups.py` keeps only the N most recent graph.json backups (default 3) and deletes the rest. Also cleans .bak files older than N days. Prevents the 50-backup pileup that can consume hundreds of MB.

3. **Inbox zero pattern.** New Rule 23 in `templates/rules/obsidian.md`: create an Inbox/ folder as a quick-capture landing zone with a 7-day max residency rule. The maintenance scan flags overdue items. Prevents notes from piling up in random folders.

4. **Maintenance docs.** New `docs/MAINTENANCE.md` with setup instructions, CLI usage, and three recommended scheduled task patterns (monthly scan, quarterly audit, weekly backup rotation) with cron expressions.

All scripts require `--vault-root` (no hardcoded paths), auto-detect emoji-prefixed Meta folders, and work in any vault.

---

## April 13, 2026 (thirty-second session -- Obsidian plugin integration + skill tracking)

Five additions that connect your vault to Obsidian's plugin ecosystem and help you understand which skills you actually use:

1. **Skill usage tracking.** New hook + script (`skill-usage-tracker.sh`) that logs every `/skill` invocation to a JSONL file. Companion report script (`skill-usage-report.py`) generates a Markdown usage report with per-skill counts, daily/weekly trends, and peak-time analysis. Add it to your `/monthly` routine to spot which skills earn their keep and which you forgot exist.

2. **Obsidian plugin integration guide.** New template `templates/rules/obsidian-plugins.md` covering three plugins that extend what Claude Code can do with your vault: Local REST API (open notes, search, run commands over HTTP), Smart Connections (semantic search that finds conceptually related notes even without shared links), and Juggl/Neo4j (visual graph exploration). Includes a search routing table so you know when to use which tool.

3. **Open-in-Obsidian rule.** Rule 22 in `templates/rules/obsidian.md`: after creating or significantly editing a file, auto-open it in Obsidian via the Local REST API so you don't have to hunt for it. Skips bulk operations.

4. **Neo4j export script.** `scripts/graph-to-neo4j.py` converts your graphify `graph.json` into Neo4j-compatible CSVs and a Cypher import script. For power users who want Cypher queries over their knowledge graph.

5. **PostToolUse Skill hook.** Added to `hooks.json` so the skill tracker fires automatically. Existing hooks unchanged.

All scripts auto-detect vault root from `$VAULT_ROOT` env var or their own file location, so they work in any vault without editing paths.

---

## April 13, 2026 (thirty-first session -- to-do system with Dataview views)

New documentation and templates for a complete to-do system that scales from solo use to small teams.

**What's new:**

- **`docs/TODO_SYSTEM.md`** -- full architecture guide for an inline-field to-do system. Covers: Dataview inline fields (`[owner::] [area::] [priority::]`), a three-question prioritization framework, view file templates (per-person, by-area, sprint progress, overdue, due-this-week, waiting-on), a "This Week" focusing lens (max 7 items, ONE Thing pattern), a Done Archive for completed tasks, and a lint rule so Claude auto-fixes missing fields. All templates are generic with placeholder names and paths.

- **`templates/dataview-queries.md`** -- added 6 to-do system queries: filter by person + priority, group by area, overdue items, due this week, waiting-on (delegated), and sprint progress. These complement the existing journal, CRM, and decision-log queries.

**How to use it:** Read `docs/TODO_SYSTEM.md`, adapt the folder paths and team member names to your vault, create the view files from the templates, and add inline fields to your existing tasks (a script approach is recommended for 100+ tasks). Add the lint rule to your CLAUDE.md so fields stay complete over time.

---

## April 13, 2026 (thirtieth session -- obsidian hygiene rules)

New file: `templates/rules/obsidian.md` -- 21 rules for wikilink hygiene, naming conventions, and import safety. Born from a vault-wide audit that found and fixed 3,548 issues across a 5,900-file vault. The four most impactful rules (discovered during the audit):

- **Never wikilink inside URLs.** Auto-linking scripts that insert `[[wikilinks]]` into URLs break both the URL and the link. 205 instances found and fixed.
- **No em dashes in filenames.** Em dashes (`---`) break Obsidian anchor links and TOC slugs. Use ` - ` instead. 46 files renamed.
- **Heading links use wikilink syntax.** Markdown anchors `[text](#slug)` silently break in Obsidian with emojis or special characters. Use `[[#Heading|display]]`.
- **No Roam artifacts.** `[[//database-path/...]]` references from Roam exports never resolve. Clean on import.

Drop this file into your vault's rules folder and reference it from your root CLAUDE.md.

---

## April 13, 2026 (twenty-ninth session -- graphify multi-vault pipeline)

Three new graphify scripts that make the knowledge graph pipeline work across multiple vaults:

1. **`graphify_stage_finish.py`** -- the end-to-end finish script that combines chunk results, canonicalizes, merges into the existing graph, reclusters, regenerates the report, and saves the cache. Now accepts `--vault-root`, `--report-title`, and `--report-path` so it works for any vault (personal, team, or project) without hardcoded paths.

2. **`graphify_canonicalize.py`** -- merges nodes that refer to the same concept but were given different IDs across files (e.g., 74 separate "Love" nodes from different journals collapse to 1). Also strips invalid file_type values agents invent and normalizes folder-prefix wikilink labels.

3. **`graphify_stage_select.py`** -- walks a corpus folder, applies filters (500-word minimum, skip AI-generated content), checks the cache for real LLM extractions vs. preflight stubs, and bin-packs the uncached files into word-balanced chunks ready for parallel dispatch.

All three auto-detect your vault root from their own script location, so they work anywhere without editing paths.

---

## April 13, 2026 (twenty-eighth session -- context optimization)

Three fixes that prevent your vault from slowing down over time:

1. **Session aggregator bug fix.** The script that builds Last Session.md had a bug where old content got duplicated on every run. Over time this could balloon the file to hundreds of KB, making it unreadable. Fixed: old content now gets stripped properly, and there's a 15KB safety cap so it can never snowball again.

2. **Smarter session-start hook.** The hook used to tell Claude to re-read your CLAUDE.md file, but it's already loaded automatically. That was wasting tokens. Now it just tells Claude to read Last Session + Current Priorities, and load rules files only when needed for the specific task.

3. **New: context-audit.py script.** Run `python3 "⚙️ Meta/scripts/context-audit.py"` to check your vault's health: file sizes, aggregator integrity, stale memories, zombie worktrees, rules completeness. All checks should show green. Run it anytime things feel slow, or add it to your /monthly routine.

---

## April 13, 2026 (twenty-seventh session -- /deconstruct first-principles skill)

New skill: `/deconstruct` strips away assumptions you don't realize you're making and rebuilds your thinking from scratch. Modeled on Aristotle's first-principles method.

**What changed:**

- **New skill: `skills/deconstruct/SKILL.md`** — a 4-phase analysis framework. Phase 1 surfaces hidden assumptions and classifies their origin (convention, imitation, precedent, fear, or unexamined default). Phase 2 finds what's true independent of all that. Phase 3 rebuilds 3 approaches from scratch. Phase 4 identifies the single high-leverage move.
- **Two modes:** Full mode (all 4 phases) for big decisions. Fast mode (Phase 1 + Phase 4 only) for daily use when auto-triggered.
- **Three auto-trigger integration points:** (1) Panel trigger for convention-following language during journaling ("best practice," "that's how it's done"). (2) Decision-log gate that auto-offers deconstruct when stakes are high. (3) Weekly retrospective audit that flags high-stakes decisions made without a first-principles check.
- **Fear-to-journal bridge:** When an assumption is classified as fear-origin, the skill explicitly flags it as an emotional problem, not an analytical one: "This isn't an analysis problem. It's a journal entry. What are you actually afraid of?"

**Why this matters:** Most thinking tools help you think better within your current frame. This one questions the frame itself. The auto-triggers mean you don't have to remember to use it; it catches convention-following and high-stakes moments automatically.

---

## April 12, 2026 (twenty-sixth session — modular CLAUDE.md + aggregator tightening)

Two problems: CLAUDE.md and Last Session.md both grew past the 10,000-token read limit, which meant Claude needed multiple reads at session start and could miss important rules.

**What changed:**

- **CLAUDE.md split into modular rule files.** Three large protocol blocks — session-start checks (~200 lines), session-end cascade (~120 lines), and meeting workflow (~55 lines) — were extracted into standalone files in `⚙️ Meta/rules/`. CLAUDE.md now has concise trigger pointers that tell Claude *when* to load each protocol and *where* to find it. The pointers explicitly say "the summary below is NOT sufficient — you MUST read the full file." This keeps CLAUDE.md under 10K tokens while preserving every detail of every protocol.
- **New rule template files** in `templates/rules/`: `session-start-checks.md` and `session-end-cascade.md` — the universal (non-personal) versions of the extracted protocols. These get installed into your vault's `⚙️ Meta/rules/` directory during setup.
- **Session aggregator tightened.** Default changed from top 3 sessions to top 2. New `--max-lines` flag (default: 60) truncates verbose session entries with a pointer to the full file in `Sessions/`. Legacy pre-split content archived to `Sessions/legacy-pre-split.md` instead of bloating the aggregated view. Result: Last Session.md dropped from ~25K tokens to ~4K tokens.
- **Old inline rule templates preserved.** The old `session-start-update-check.md` and `session-end-capture.md` templates still exist for backwards compatibility. New installs will use the modular rule files instead.

**Net result:** both mandatory session-start files now load in a single read call. No protocol details were lost — they just moved from "always loaded" to "loaded when triggered."

---

## April 11, 2026 (twenty-fifth session — graphify runbook hardening)

Hardened `skills/graphify/RUNBOOK.md` with a top-of-file STOP-READ gate, a PRE-FLIGHT CHECKLIST, two new standing rules, and four new lessons (#37–#40) — all from a real session that started with "run graphify on more of the vault" and turned into 30+ minutes of wasted work because the runbook got skimmed instead of read.

### Part 1 — The STOP-READ gate and PRE-FLIGHT CHECKLIST

The runbook now opens with a big red directive telling Claude to read the whole file in full before touching any graphify work. If the file exceeds the Read tool's 10k-token cap (which it does), Claude is instructed to chunk the read with `offset` + `limit` — never to fall back to Grep sampling or `head_limit`, because those are search tools, not reading tools, and they leave you confident you've "covered it" while missing most of the content.

Right after the gate is a 7-step **PRE-FLIGHT CHECKLIST** that catches the five most destructive antipatterns before they cost time:

1. Read this whole file
2. Check for stale graphify processes from other sessions
3. Force-warm the target folder if your vault is on a sync service (iCloud, Google Drive, OneDrive, Dropbox) — cold reads can be 1000x slower and look exactly like a hang
4. Never call `check_semantic_cache` on large corpora — re-hashing blocks for minutes
5. Prioritize concept-dense corpora (Books/Notes/Writing) over episodic ones (Journals/Daily Logs) — roughly 3x more concepts per token
6. Verify the cwd matches the target vault root
7. Run the stage-selection script to size the job before dispatching — NOT on capped slices though, see Lesson #38

### Part 2 — Two new standing rules

**Active lesson capture.** Any optimization or gotcha gets written up the moment it surfaces, not saved for end-of-session. If you wait, the specifics (exact numbers, exact error messages) degrade into vague pattern-matching and the lesson loses most of its value. Ten seconds to write now beats ten minutes of re-derivation next week.

**Validation hypotheses on every batch/dispatch doc.** Every handoff doc for a graphify batch must include a "What this run is testing" table with numbered hypotheses, quantitative predictions, measurement methods, and explicit kill criteria. This turns every stage into a live experiment for the lessons it depends on. You already pay the tokens — recording the measured result against a pre-registered prediction is free signal. Without it, lessons stay anecdotal ("cap-7 worked last time") and drift silently. With it, every stage either strengthens the lesson with N more data points or explicitly overturns it when a kill criterion triggers.

### Part 3 — Four new lessons (#37–#40)

- **#37** — Read-tool 10k cap handling: use `offset`+`limit` chunking, never Grep sampling
- **#38** — Don't run the full-corpus sizer for capped slices. Write a targeted picker that sorts by metadata (filename date, `st_size`, `st_mtime`) without reading contents, then reads only the top `cap × 1.6–2.0` candidates in a 16-thread pool for a 6–8x speedup over sequential. Includes filter-attrition math: journals lose ~70% to `<500w OR already-cached`, writing loses ~40%, so overshoot constants are corpus-specific.
- **#39** — Scan for content-level near-duplicate drafts in `Writing/` and `Drafts/` folders BEFORE chunking. `graphify_prep.py` only catches byte-identical duplicates; files that share 99% of their content but differ in formatting or wikilink conventions slip through. A single 57k-word draft triplicated across three folders costs ~430K tokens to redundantly extract. A 10-second title-similarity scan before dispatch catches it.
- **#40** — Merge discipline: normalize wikilinks + tags + whitespace before line-level comparison, then preserve every unique line in a "Recovered from earlier drafts" appendix at the bottom of the merged file. Never silent-drop content. Back up all originals to `/tmp` before overwriting or deleting anything.

### Why this matters for non-technical users

These four lessons are the difference between a `/graphify` run that costs 30 minutes and one that costs 3 hours. For someone who has never written a Python script and whose vault is on iCloud or Google Drive, the cold-read gotcha (Lesson #17) combined with the skimmed-runbook pathology (now blocked by the new top-gate) was the most common "it hung, I don't know what happened" outcome. The gate + checklist force a diagnostic path before any action, and the new lessons give Claude explicit fallbacks for the three most common failure modes.

**What you should do:** nothing. Next time you run `/graphify`, Claude will read the hardened runbook first and apply the new pre-flight checklist automatically. You'll notice faster runs and fewer "why is this hanging?" moments. If you want to see the new lessons, open `skills/graphify/RUNBOOK.md` and scroll to the "Session-start discipline and read-tool patterns" subsection (Lessons #37–#40) and the two "Standing rule" blocks at the top of "Lessons learned."

---

## April 11, 2026 (twenty-fourth session — CHANGELOG rotation)

Rotated 28 older session entries (April 8 → April 11 sessions 1–18) out of `CHANGELOG.md` and into a new `CHANGELOG_archive_2026Q1.md`. The live changelog now carries only the most recent ~5 sessions, which is what almost every post-pull update check actually needs to read.

**Why:** the live `CHANGELOG.md` had grown to 1,313 lines. Every `git pull` triggers Claude to read it and translate "what's new" into plain English for the user, so every line is a real token cost on every pull. The full release history is preserved in the archive file — nothing is lost. To read it: open `CHANGELOG_archive_2026Q1.md` next to this file.

**What you should do:** nothing. The next pull will show you this rotation entry and that's it. If you want the full history, the archive file is right next to the live one.

---

## April 11, 2026 (twenty-third session — non-technical onboarding overhaul + automatic file drift detection)

This is two things shipped together because they share the same theme: **make a non-technical user's first install (and every subsequent pull) work without them ever having to ask "why doesn't this work?"**

### Part 1 — Non-technical onboarding overhaul (14 fixes)

Audited the full first-install experience for someone who has never opened a terminal and doesn't know what Obsidian, Claude Code, Python, Node, or an API key is. Found 14 friction points where the setup assumed the user knew something they don't, or made them do a manual step that the bootstrap could just do for them. All 14 are fixed in this release.

**Auto-installs added — you no longer have to download anything yourself:**

- **Obsidian** — auto-installed by the bootstrap (Mac via `brew install --cask obsidian`, Windows via `winget install Obsidian.Obsidian`, Linux via snap → flatpak → AppImage download fallback). Previously the README mentioned Obsidian as a "prerequisite" with a one-line bullet, the bootstrap didn't touch it, and you'd hit a wall mid-setup when /setup-brain asked "do you have Obsidian?" You no longer have to think about it.
- **Claude Code itself** — auto-installed by the bootstrap via `npm install -g @anthropic-ai/claude-code`. Previously listed as a prerequisite with no install step. Now installed automatically once Node is present, on every OS.
- **winget on older Windows 10** — bootstrap.ps1 used to abort hard with "winget is required, install App Installer from the Microsoft Store and re-run." That sentence is opaque to a non-technical user. Now the bootstrap auto-downloads and installs App Installer from Microsoft's official URL (`aka.ms/getwinget`) before doing anything else, with a fallback to direct MSI installs of Python, Node, and Obsidian if winget can't be installed at all.
- **Obsidian community plugins** (Dataview, Templater, Tasks) — Phase 2 of `/setup-brain` used to walk you through ~36 manual clicks across the Obsidian Community Plugins UI to install three plugins one at a time. Now Phase 2 runs a Python helper that downloads each plugin's latest release directly from GitHub, drops it into your vault's `.obsidian/plugins/` folder, and writes `.obsidian/community-plugins.json` to enable them. Manual UI walkthrough is still there as a fallback for any plugin that fails to auto-install.

**Onboarding-flow clarity:**

- **README install section rewritten end-to-end.** Step 1 (open your terminal — with concrete instructions for Mac, Windows, Linux including the critical "PowerShell, NOT cmd.exe" warning), Step 2 (paste the install command and watch it run), Step 3 (type `claude` then `/setup-brain`). The "Prerequisites" section is gone — replaced with one line that says "all you need is a Mac, Windows, or Linux computer; the bootstrap installs everything else." Manual `git clone` install path removed since it's confusing to non-technical readers.
- **`/setup-brain` Phase 0 progress messaging.** Used to go silent for 2-3 minutes while installing tools, which makes non-technical users think the setup has frozen. Now Claude says "Setting up the tools you'll need — give me a moment" before starting, and gives a one-line `tool ready ✓` confirmation as each tool finishes.
- **`/setup-brain` Phase 1 step 6 — Obsidian question rewritten.** Used to ask "Do you have Obsidian installed? If not, go to obsidian.md and download it. I'll wait." Now detects whether Obsidian is already installed (which it always should be after the bootstrap) and skips the question. If somehow it's missing, the skill auto-installs it instead of asking.
- **Homebrew password prompt warning.** Bootstrap now prints a multi-line `⚠️ HEADS UP` block before installing Homebrew, telling you the password prompt is coming, that you won't see characters as you type, and to NOT close the window. Reduces "is this thing frozen?" anxiety.
- **`gh auth login` framing.** Previously asked you to log in to GitHub with developer-jargon defaults ("GitHub.com → HTTPS → Login with web browser"). Now framed as OPTIONAL with explicit "if you don't have a GitHub account, press Ctrl+C to skip — everything else still works." The implicit pressure to log in is gone.
- **Granola post-install authorization step.** Bootstrap registers the Granola MCP server but used to never tell you that the MCP only works AFTER you've signed into the Granola Mac/web app at least once. Now the install message says explicitly "I just wired up Granola — one more step on YOUR side: log in to the Granola app once before the connection works. Want me to walk you through it?" If you say "I don't use Granola," the bootstrap removes the dead MCP entry instead of leaving it stranded.
- **Nano-banana / Gemini API key deferred.** Phase 0 used to mention setting up nano-banana with a `GEMINI_API_KEY` env var as part of the main setup. That's a 5-minute side quest involving API jargon for a feature most users don't need on day 1. Now the install is deferred entirely — nano-banana only gets installed when you explicitly ask for image generation, and Claude walks you through the API key setup interactively at that point with concrete clicks instead of CLI commands.

### Part 2 — Automatic file drift detection (`drift-check.sh` + `drift-check.ps1`)

`update-check.sh` only knows whether you're behind on commits. It does NOT know whether files that were already installed in a prior release have since drifted from the repo's version. That happens when a previous sync only partially landed, when you hand-edit a script in your vault, when a `git stash` recovery leaves files mixed, or when a manual cherry-pick missed something. Until now the only way to find stale files was to manually ask Claude "compare everything" — which defeats the whole point of automatic updates.

**New script: `scripts/drift-check.sh` (and `drift-check.ps1` for Windows).** Runs at session start alongside `update-check.sh`, on the same once-per-day cooldown. Read-only — never modifies anything. Detects three kinds of drift:

1. **Installed skills** — files under `~/.claude/skills/<skill>/` that differ from the repo's `skills/<skill>/<rel-path>`.
2. **Vault scripts** — files under `$VAULT/⚙️ Meta/scripts/<basename>` that differ from `<starter>/scripts/<basename>`. Curated list of scripts the starter installs into vaults during /setup-brain.
3. **Vault CLAUDE.md rule blocks** — for each `templates/rules/*.md`, finds its top-level heading inside `$VAULT/CLAUDE.md` and diffs the block underneath. Tolerates trailing `---` separators (a CLAUDE.md formatting convention, not part of any rule).

**`session-start-update-check.md` rule extended with the drift-handling UX.** When drift is found, Claude walks you through it one file at a time: reads both files, shows you a `diff -u` of the changes, asks {update / skip / **skip permanently** / update all / stop}, **backs up before every single change** (no exceptions, even on "update all"), and for `vault-rule` drift, replaces only the targeted block via Edit (never the whole CLAUDE.md file). Files annotated with `note: hand-edited CONFIG block` (currently just `graph-context-hook.sh`) are never overwritten wholesale — they get cherry-pick treatment with a manual ask instead.

**Permanent ignore registry: `~/.claude/.ai-brain-starter-drift-check-ignore`.** Files like `graph-context-hook.sh` ship as a generic template in the repo and get hand-customized in your vault during /setup-brain. Drift on those files is permanent-by-design — having drift-check nag about them every session is noise. The ignore file is a plain-text per-user registry: one entry per line, supports literal paths and shell-glob patterns, `#` for comments. When you pick "skip permanently" during the walkthrough, Claude appends the file to this registry for you. If you change your mind, open the file in any text editor and delete the line. Defensive normalization (BOM, CRLF, thematic-break separators) prevents false-positive drift on benign formatting differences too.

**Why human-in-the-loop instead of auto-update:** because the drifted file might be a hand-edit you intentionally made (e.g. customizing `graph-context-hook.sh` with your vault paths and routing keywords), and an auto-replace would silently destroy your work. Backup-before-every-change is non-negotiable.

### What you do

Nothing — both parts apply automatically on the next bootstrap re-run or `git pull`. The drift check honors a once-per-day cooldown so it won't double-prompt during a single day.

If you want to verify drift detection right now: `bash ~/.claude/skills/ai-brain-starter/scripts/drift-check.sh --vault "<your vault path>" --force` (or the `.ps1` equivalent on Windows).

---

## April 11, 2026 (twenty-second session — update-check summary skips the corporate-event rule bullet)

Small tone-only change to `templates/rules/session-start-update-check.md`.

The session-start update check reads new CHANGELOG entries after a `git pull` and translates them into plain-English bullets for you. One of those bullets kept describing the corporate-event Onde suggestion rule (Phase 16 rule 15, added April 10) in persuasive language — framing the rule as a thing that "suggests it as a sales opportunity" or similar. That framing misses the point of the rule, which is opt-out, inline-disclosed on first fire, and scoped tightly to corporate events you're already planning. Describing it in promotional terms in the post-pull summary made it read like the starter was marketing at you, which is exactly what the rule is designed *not* to do.

The fix is the smallest possible: an "Opinionated skip list" in the update-check template that explicitly tells Claude to leave the corporate-event rule out of the update summary entirely. You'll discover the rule the first time it fires, with the full inline disclosure ("Onde was built by the same person who made this starter skill") right there at fire-time. That's where the honesty lives — not in a release-notes bullet two days earlier.

**Nothing changes about the rule itself.** It still auto-installs, still fires on the 12 corporate-event categories, still opts out permanently the moment you decline, still carries the inline disclosure on every fire. The only change is that future pulls won't announce it in a persuasive bullet in the update summary.

### What you do

Nothing. The template edit applies the next time the update-check runs. If you want to apply it right now without waiting for the next session start: pull the repo and the new template takes effect.

---

## April 11, 2026 (twenty-first session — concurrent-worktree race fix for session-end cascade)

### The bug this fixes

If you run multiple Claude Code sessions at the same time in different worktrees (which you'll do if you're using the parallel-worktrees workflow for different tasks), and each session follows the session-end cascade rule — they all race on `⚙️ Meta/Last Session.md` and `⚙️ Meta/Decision Log.md`. Each session reads the file, adds its entry, writes it back. Last write wins. **Earlier sessions' entries are silently clobbered.**

This isn't a bug in any one session. It's a structural race condition in the cascade rule itself. If you've been using this setup with parallel worktrees for any length of time, some of your session summaries and decisions have quietly disappeared without you knowing.

I caught it live on 2026-04-11 — four concurrent worktrees wrote to the meta files in one evening; at least two decisions and one session summary were overwritten before the fix shipped. Reported and tracked in [#5](https://github.com/adelaidasofia/ai-brain-starter/issues/5).

### What changed

**New folder structure (created automatically on update via the session-end hook):**

```
⚙️ Meta/
  Sessions/
    2026-04-11T22-30-my-worktree.md          # one file per session, unique filename
    2026-04-11T17-18-other-worktree.md
  Decisions/
    2026-04-11T22-30-daily-journal-redesign.md  # one file per decision, unique filename
    2026-04-11T22-30-per-worktree-meta-writes.md
  Last Session.md         # auto-generated from Sessions/ by aggregate-sessions.py
  Decision Log.md         # auto-generated from Decisions/ by aggregate-decisions.py
```

Concurrent worktrees write to *different files*, so there is no contention. The shared `Last Session.md` and `Decision Log.md` are rebuilt by aggregator scripts that produce deterministic output from sorted input — so even two concurrent aggregator runs write identical bytes. The race is structurally eliminated, not papered over with locks or retries.

**Two new scripts** (installed to your vault's `⚙️ Meta/scripts/`):

- `aggregate-sessions.py` — rebuilds `Last Session.md` by reading `Sessions/*.md`, sorting by filename descending, concatenating the top N (default 3). Filters out stub files (unfilled placeholders) so orphaned session-end hook writes don't pollute the view.
- `aggregate-decisions.py` — same for `Decisions/` → `Decision Log.md`, showing all decisions newest-first.

Both scripts read the vault path from `$VAULT_ROOT` so you don't need to edit them for your setup — the bootstrap sets the env var for you, and the hook passes it on every run.

**Updated `session-end-hook.sh`** — now detects your worktree name (three fallback methods: pwd parse → `.git` file read → PID-based unique fallback), writes a session stub to `Sessions/{timestamp}-{worktree}.md`, and runs the aggregator as the final step. The hook never writes to `Last Session.md` directly.

**Updated session-end capture rule** — tells Claude to write session content to a per-worktree file (not the shared view) and to create per-decision files (not append to `Decision Log.md`). Runs the aggregators after each write. The destination table in the rule was updated to reflect the new paths.

**Backwards-compatible migration.** Your existing `Last Session.md` and `Decision Log.md` are NOT touched on first run. The aggregator preserves all pre-split historical content below a `## Legacy (pre-split) historical entries` / `## Legacy (pre-split) historical decisions` header. Nothing gets deleted. You can roll back by deleting `Sessions/` and `Decisions/` and restoring from the `.bak-pre-aggregator-*` backups if anything goes wrong.

**Idempotency.** The aggregators are byte-stable across runs — three consecutive runs produce identical MD5 hashes. Safe to run as many times as you want, including concurrently.

### What you do (nothing, unless you want to)

The update auto-installs the new scripts and updates the hook. The next time you end a session, the hook will create your first entry in `Sessions/` and rebuild `Last Session.md` as the aggregator view. If you want to manually trigger a rebuild before then: `VAULT_ROOT="<your vault path>" python3 "<vault>/⚙️ Meta/scripts/aggregate-sessions.py"`.

If you've been running parallel worktrees and want to know what you may have lost, check `⚙️ Meta/Session Log.md` (the always-append log) for timestamps of ended sessions without matching entries in `Last Session.md`. That's your missing-content list.

---

## April 11, 2026 (twentieth session — daily journal panel becomes a live participant, with real pushback)

If you've been using `/journal` for a while, you've probably noticed the advisory panel at the end of each entry mostly cheers you on. Warm, supportive, agreeable. The problem: on good days that means *no real signal*, and on days when you're rationalizing something, it means the panel *helps you* rationalize it. The whole point of having an advisory panel is that it pushes back when you need it — and the old setup couldn't, because it ran after you'd already decided how the story goes.

This update restructures the journal skill so the panel works the way a real advisory board works.

### What's different

**1. The panel can now interrupt you mid-journal.** A new "Standing Rules" section in the journal skill has a trigger table — if you say hedge words ("I guess," "I don't know why"), drop a vague "I should" without a date, mention a new side idea during a hard stretch, brush past a missed habit, avoid naming a hard conversation, etc. — the relevant advisor pulls in with one sentence, in character, then hands the conversation back. You don't wait until the end for the panel's reaction.

**2. At least one panelist must dissent on every entry.** Especially on good days. Rationalizations slip through most easily on high-floor entries, and the old "1–2 sentences per advisor, keep it tight" format couldn't force disagreement. The new rule is simple: if all 3–5 panelists agree, you have not looked hard enough. Dissent is required, not optional.

**3. Panel dialogue, not parallel bullets.** Step 5 now stages an actual in-character exchange where panelists can challenge each other and you, ask you questions back, and push on what you avoided. Not a stack of isolated advisor quotes.

**4. Omission pass.** Before the panel weighs in, the skill checks: *what did the user NOT say tonight that a panelist would notice?* A commitment from yesterday that vanished. A meeting tomorrow with no prep. A person they were upset with who's suddenly absent from the entry. A body signal they skipped. If an omission exists, one panelist names it in Step 5.

**5. Strict voice separation in the saved entry.** This is the biggest long-term change. Every new journal entry now has two clearly-labeled sections separated by horizontal rules:
   - `## Journal — [your name]'s voice` — your original thought only, your words, your voice. Panel lines never appear here.
   - `## Panel dialogue (synthetic — not [your name]'s original thought)` — the AI-generated panel exchange, below a ⚠️ disclaimer.

Why this matters: when you reread your journals in 6 months or 6 years, you'll be able to tell at a glance which sentences were *you* thinking and which were AI commentary. Without this separation, the two voices bleed together and the journal archive loses its value as a record of how you actually think. This was the single biggest long-term failure mode of AI-assisted journaling and it's now structurally impossible in the generated skill.

**6. Panel dissents auto-log to a cross-context Panel Feedback Log.** If Step 5 produced a dissent or omission flag, the skill automatically appends it to your Panel Feedback Log (the same file that catches feedback from real human meetings). Patterns surface over time — if three different daily entries all got the same dissent, that's a real pattern to act on.

**7. Full advisory roster expanded.** The panel now includes more specialized voices: female-physiology experts (Stacy Sims, Lara Briden), pelvic-floor and embodiment (Carrie Pagliano, Bonnie Bainbridge Cohen), LGBTQ+ relational voices (Alexandra Solomon, queer polarity archetypes), cross-border tax and family office archetypes, and "archetype" slots (Curious Friend, Buddhist Monk, Stoic Philosopher, CBT Therapist, Existential Psychotherapist, Inner Child Therapist) for when no specific real person fits.

**8. Roster customization during setup.** When you run the setup flow, you'll now be offered the chance to customize the advisory panel — add or remove voices, swap in specific people from your own life (a mentor, a grandparent, a coach). Whatever you say gets baked into the generated skill so your daily journal uses *your* panel, not a generic one.

### Why

This came from noticing a real pattern: on two consecutive entries, the panel gave four affirming voices in a row and not a single piece of pushback. Nothing challenged the user's framing. On a day when the user rationalized a non-obvious decision, the panel agreed with the rationalization. That's not what an advisory board is for. The redesign fixes it at the structural level — dissent is required, the panel can interrupt mid-interview, the original voice is walled off from commentary, and patterns of pushback get logged across sessions so they don't evaporate.

If you're already set up, the next time you run `/journal` the skill file will still be the old version until you tell me to regenerate it. Ask: *"regenerate my daily-journal skill with the latest panel behavior"* and I'll rebuild it using the new template, preserving your existing floor framework, habit tracking, and customizations.

---

## April 11, 2026 (nineteenth session — bootstrap best practices for advanced users with custom skills + forks)

Session 18 added the basic safety guarantees. This session adds the protections specifically aimed at advanced users — people who have their own forks of bundled skills, their own custom CLAUDE.md rules, their own divergent ai-brain-starter clone, or any other heavy customization. The bar: **never silently overwrite anyone's hard work, regardless of how complex their setup is.**

### What's now protected for advanced users

Four new protection layers in both `bootstrap.sh` and `bootstrap.ps1`:

#### 1. Forked sub-skill detection

If you have your own `.git/` directory inside `~/.claude/skills/graphify/` (or `meeting-todos/`, or `patterns/`) — meaning you cloned your own customized version of one of the bundled skills — the bootstrap **detects this and skips that skill entirely.** It won't sync the upstream version over yours. You manage updates to your fork yourself.

The signal is the presence of `.git/` inside the skill folder. The bootstrap logs:

```
graphify has its own .git/ directory — detected as YOUR FORK, skipping entirely
  Your fork is preserved untouched. You manage updates to it yourself.
```

#### 2. Symlinked sub-skill detection

If `~/.claude/skills/graphify` (or another bundled skill) is a **symlink** instead of a regular folder — meaning you've pointed it at a shared location, a development checkout elsewhere, or a Dropbox/Drive path — the bootstrap detects the symlink and refuses to write through it. The target may be a shared resource you don't want surprised by this script.

```
graphify is a SYMLINK to /Users/you/code/graphify-fork — bootstrap will NOT write through it
  If you want bootstrap to update this skill, replace the symlink with a regular folder.
```

#### 3. Divergent ai-brain-starter clone detection

If your local `~/.claude/skills/ai-brain-starter` clone has commits that **aren't** on `origin/main` AND `origin/main` has commits that **aren't** on your clone (a true divergence — you've made your own commits that diverge from upstream), the bootstrap **refuses to pull** and tells you exactly how many commits diverge in each direction:

```
DIVERGENT FORK DETECTED at ~/.claude/skills/ai-brain-starter
  Your local clone has 3 commit(s) NOT on origin/main
  AND origin/main has 7 commit(s) NOT on your clone
  Refusing to pull. Your fork is preserved unchanged.
  To merge manually: cd ~/.claude/skills/ai-brain-starter && git pull --rebase
```

The bootstrap also handles two related cases more gracefully:

- **Local commits, no upstream changes** (you're ahead but not divergent): leaves your clone alone, doesn't pull
- **Behind upstream with no local commits**: stashes any uncommitted changes, then fast-forwards

#### 4. Explicit-disable preservation for `claude-mem@thedotmack`

Previously the bootstrap unconditionally set `enabledPlugins["claude-mem@thedotmack"] = True`. If an advanced user had explicitly set it to `False` (because they intentionally disabled the plugin), the bootstrap would silently re-enable it on the next run.

Now the bootstrap only sets the key if it's **absent**. If the user has it set to `False`, the bootstrap respects that choice and prints:

```
NOTE: respecting your explicit disable of claude-mem@thedotmack — leaving it off
```

### `--dry-run` mode

Both bootstrap scripts now accept a `--dry-run` flag (PowerShell: `-DryRun`) that previews **every action** the bootstrap would take, without making any changes. No files written, no installs run, no git operations performed. Just a transcript of "what would happen if you ran this for real."

```bash
bash bootstrap.sh --dry-run
```

```powershell
iex "& { $(irm https://raw.githubusercontent.com/adelaidasofia/ai-brain-starter/main/bootstrap.ps1) } -DryRun"
```

The output looks like:
```
[dry-run] would: git fetch --quiet origin
[dry-run] would: git pull --quiet (fast-forward 53 commit(s))
[dry-run] would sync graphify skill from <repo> to <dest> (with backup-before-overwrite)
[dry-run] would back up: ~/.claude/settings.json → ~/.claude/settings.json.bak-2026-04-11-1530
[dry-run] would: register thedotmack marketplace + enable claude-mem@thedotmack (if not explicitly disabled)
```

This is the right way for an advanced user to inspect the bootstrap before running it on a heavily customized setup.

### Final change summary

Both scripts now end with a structured **change summary** that lists everything that happened (or would happen, in dry-run mode):

```
━━━ Change summary ━━━

  Installed (new):
    + ai-brain-starter clone

  Updated:
    ↑ ai-brain-starter clone (pulled 53 commit(s))
    ↑ graphify skill (12 new, 4 updated, 4 backed up)

  Skipped (your customizations preserved):
    ⊘ meeting-todos skill (your own fork — has .git)
    ⊘ patterns skill (symlink to /Users/you/code/patterns-fork)

  Backups created (recoverable):
    ↳ /Users/you/.claude/settings.json.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/SKILL.md.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/scripts/run.py.bak-2026-04-11-1530
    ↳ /Users/you/.claude/skills/graphify/scripts/util.py.bak-2026-04-11-1530

  To restore any backup: mv <file>.bak-YYYY-MM-DD-HHMM <file>
```

After every run, the user knows exactly what changed, what was preserved, and how to undo anything they didn't expect.

### Best practices we now follow

For an installer that touches user-customized files, the relevant best practices are:

| Best practice | Status |
|---|---|
| Idempotence (re-run safe) | ✅ |
| Backup before overwrite | ✅ |
| Respect explicit user choices (e.g. disabled plugins) | ✅ |
| Detect forks of bundled components and skip them | ✅ |
| Detect symlinks before writing through | ✅ |
| Detect divergent histories before pulling | ✅ |
| `--dry-run` preview mode | ✅ |
| Final summary of every change | ✅ |
| Detailed error messages | ✅ |
| Verification block at end | ✅ |
| Custom skills outside bundled set untouched | ✅ |
| User vault never touched | ✅ |
| Recoverable from any unexpected change | ✅ |

The remaining gaps are nice-to-haves: a `--restore` mode that auto-restores from the most recent `.bak` files (not strictly needed since the file paths are obvious), atomic operations across the whole script (would require a temp directory + final swap, significant refactor), and a logging file (right now the summary is stdout only — could also write to `~/.claude/.bootstrap.log` for forensics).

### What this means for an advanced user

If you've built a heavy custom setup — your own forks of bundled skills, your own divergent ai-brain-starter, your own custom plugins, your own MCP servers, your own hand-tuned settings — running the bootstrap on top of it will:

1. **Detect everything you've customized** (forks via `.git`, symlinks via attributes, divergent clones via `git rev-list`, explicit-false plugins via JSON inspection)
2. **Skip those entirely** (not "back them up and overwrite", actually skip)
3. **Tell you in the summary exactly what was preserved and why**
4. **Update only the things that aren't customized** (and back those up too, just in case)

The bar: an advanced user with five custom forks should be able to run the bootstrap and have nothing they care about touched. The summary should confirm "5 custom things preserved, 0 things you customized were modified."

Run with `--dry-run` first if you're at all unsure. The dry run is the answer to "but what if it does something I don't expect?" — it shows you exactly what would happen with zero side effects.

---

## Older entries

For sessions 1–18 (April 8–11, 2026), see [`CHANGELOG_archive_2026Q1.md`](CHANGELOG_archive_2026Q1.md). Rotated on 2026-04-11 to keep the live changelog focused on the most recent ~5 sessions.

## [Unreleased]

### Added
- `docs/RELEASES.md` entry for Claude Code v2.1.118: `/usage` command, `type: "mcp_tool"` hooks, agent frontmatter hooks/MCPs in main-thread, `Bash(find:*)` permission change.

### Changed
- `templates/rules/advisory-panel.md` Rule 1: confidence scoring is now internal only. Panel filters by lens-fit score (0-100) but NEVER prints the number in output. No `[confidence: N]`, no `(72)`, no score annotations. Background filter, not visible ink.

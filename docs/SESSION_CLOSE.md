# Session close — how the cascade works

When you finish a Claude Code session, a multi-step capture cascade saves your decisions, journal seeds, to-dos, time tracking, and a rebuilt session/decision log. This doc explains what runs, when, and how to control it.

## TL;DR

- **Just say "bye" (or any natural close in EN / ES / PT) and the cascade fires automatically.** No slash command needed.
- **Power-user shortcut:** type `/close`, `/wrap-up`, `/bye`, `/cerrar`, or `/tchau` to be explicit. They are detector keywords, not registered commands.
- **The cascade is silent by default.** The model says a clean goodbye and writes captures invisibly. To see a one-line summary at close, set `sessionCloseFeedback: minimal` in your CLAUDE.md frontmatter.
- **Trivial sessions skip.** Fewer than 5 user messages with no captures = clean goodbye, no protocol.
- **Nothing is ever silently lost.** If the model bails mid-cascade and you have `ANTHROPIC_API_KEY` set, a Haiku fallback fills the session file from the transcript. Without an API key, a partial-flag is left for `recover-last-close.py`.
- **Undo:** `python3 ~/.claude/skills/ai-brain-starter/scripts/undo-last-close.py` rolls back the most recent close (interactive).

## Layered architecture

The close cascade lives in three coordinated layers. Each layer is independent and fails open — if any layer breaks, the next one degrades gracefully rather than blocking you.

### Layer 1 — UserPromptSubmit hook (`hooks/detect-closing-signal.py`)

Fires on every user message, before the model sees the prompt. Responsibilities:

1. **Detect close signals** via regex against language packs (`templates/closing-signals/{en,es,pt}.json`).
2. **Apply false-positive guards** — code blocks, quoted "bye", "done with X" mid-conversation transitions, meta-questions.
3. **Optional Haiku second look** for ambiguous prompts ("ok", "cool") if `closeDetection: hybrid` is set.
4. **Pre-resolve all paths** — timestamp, worktree, vault root, session file, decisions dir, captures file.
5. **Pre-build the session file shell** — frontmatter + section headers, ready for the model to fill.
6. **Pre-fetch decisions with empty Outcome** — so the model can backfill any that this session resolved.
7. **Write a marker file** at `~/.claude/.closing-signal-{session_id}.json` for the Stop hook to detect.
8. **Inject the cascade context** as `additionalContext` so the model receives complete instructions without reading a separate rule file.

Performance budget: under 500ms.

### Layer 2 — Model's turn

The model receives the injected context and runs the creative phases:

1. **Phase 0b — incomplete-work gate.** Surface any background tasks still running, killed mid-run, or pipeline phases that didn't complete. Wait for the user's call ("finish now, or defer?").
2. **Phase 1 — single-pass conversation scan** for: belief shifts, journal seeds (verbatim), writing notes, actionable content, to-dos, decisions, delegations, time tracking entry.
3. **Phase 2 — batch writes** to the pre-built shell + per-decision files.
4. **Phase 3 — final summary** in one line + warm goodbye.

The model never re-runs the deterministic work the hook already did.

### Layer 3 — Stop hook (`scripts/session-end-hook.sh`)

Fires after the model's turn ends. If the marker file exists:

1. **Haiku fallback** — if the session file body is still empty (model bailed), `scripts/session-close-fallback.py` calls Haiku 4.5 with the conversation transcript and fills the file. Flagged for next-session review.
2. **Aggregators** — `aggregate-sessions.py` rebuilds Last Session.md, `aggregate-decisions.py` rebuilds Decision Log.md.
3. **Targeted git snapshot** — only if vault is git-tracked. Stages explicit paths only (session file, decision files, captures, aggregated views). Never `git add -A`. Waits up to 60s for any concurrent index lock. No push.
4. **Retention cleanup** — stubs older than 7 days deleted; substantive sessions older than 7 days archived.
5. **Marker cleanup** — removes the closing-signal marker.

If no marker exists (normal turn), only the cheap-path runs (timestamp log + retention sweep).

## Configuration

Add any of these to the YAML frontmatter at the top of your CLAUDE.md:

```yaml
---
closingSignals.custom: ["k done", "okkk", "i'm out for real"]
closeDetection: regex                # or "hybrid" — adds Haiku fallback for ambiguous closes; needs ANTHROPIC_API_KEY
sessionCloseFeedback: silent         # or "minimal" (one summary line) or "verbose" (phase-by-phase)
cascadeTelemetry: false              # opt in to anonymized cascade-fire / completion-rate logging
---
```

## Closing signals (what gets matched)

Three confidence levels:

**Explicit** (always fires the cascade with no confirmation):
- `/close`, `/wrap-up`, `/bye`, `/done`, `/finish`
- `/cerrar`, `/terminar`, `/chao`
- `/fechar`, `/encerrar`, `/tchau`

**High-confidence natural language** (fires the cascade):
- EN: bye, thanks that's all, good night, ttyl, cya, signing off, talk to you later, wrapping up, that's all for today, I'm done, k bye, k thx, gn
- ES: chao, chau, nos vemos, hasta luego, hasta mañana, listo gracias, eso es todo, buenas noches, me voy
- PT: tchau, até logo, valeu, falou, boa noite, pronto, obrigado

**Ambiguous** (asks "wrapping up, or keeping going?" before firing):
- EN: ok, cool, great, perfect, sounds good
- ES: dale, bueno, perfecto, genial
- PT: beleza, legal, ótimo

**Emoji-only**:
- 👋, 🙏, ✌️, 🫡, 💤

**False-positive guards** (do NOT fire):
- "what does ttyl mean?" (meta-question)
- `say bye to feature X` (idiom)
- "ok now do Y" (transition, not close)
- "done with auth, lets move on" (subtask completion)
- "listo para empezar" (readiness, not close)
- Code blocks containing close keywords
- Quoted close keywords ("bye" in quotes)

## Recovery + rollback

| Situation | Command |
|---|---|
| Last close failed because model bailed + no API key was set | `python3 scripts/recover-last-close.py` (auto) |
| Want to manually fill in a partial session file | `python3 scripts/recover-last-close.py --manual` |
| List all partial-completion flags | `python3 scripts/recover-last-close.py --list` |
| Rollback most recent close (move files to `.undone/` archive) | `python3 scripts/undo-last-close.py` |
| Rollback specific worktree | `python3 scripts/undo-last-close.py --worktree NAME` |
| Preview rollback without changes | `python3 scripts/undo-last-close.py --dry-run` |

## Testing the detector

If you change a language pack or add custom signals, run the fixture test harness:

```bash
python3 scripts/test-closing-signals.py
python3 scripts/test-closing-signals.py --verbose
python3 scripts/test-closing-signals.py --fixture en-bye
```

The harness ships with 74 fixtures across all three languages, ambiguous cases, false positives, and adversarial inputs. CI-runnable: exits 0 on all-pass, 1 on any failure.

## Adding custom close signals

Two paths:

**Per-user (in CLAUDE.md):**
```yaml
---
closingSignals.custom: ["k thx bai", "im out for real"]
---
```

These match as **explicit** confidence (no ambiguity check, fires immediately).

**Per-language pack (PR-worthy):** edit `templates/closing-signals/{lang}.json`, add to the appropriate level (`explicit`, `high_confidence`, `ambiguous`, `emoji_only`), run the test harness with new fixtures, open a PR.

To add a new language entirely, create `templates/closing-signals/{lang}.json` following the schema of `en.json` and add `{lang}` to `CLOSING_SIGNAL_LANGS` env var.

## Disabling the cascade

**Temporarily (this shell session only):**
```bash
export CLOSING_SIGNAL_DETECTION=off
```

**Permanently:** remove the UserPromptSubmit hook entry and the Stop hook entry from `hooks.json`. The cascade then falls back to model-side rule reading from `templates/rules/session-close.md` (the prior architecture).

## Debugging

All hook errors are logged to `~/.claude/logs/session-close-errors.log`. Common ones:

- `aggregate-sessions failed` — check `⚙️ Meta/Sessions/` for malformed frontmatter; the aggregator skips bad files but logs them.
- `aggregate-decisions failed` — same, for `⚙️ Meta/Decisions/`.
- `git index.lock held >60s` — concurrent session was mid-commit; snapshot was skipped. Will retry next close.
- `language pack not found` — check `templates/closing-signals/` is intact and `CLOSING_SIGNAL_LANGS` env var is correct.
- `fallback exited non-zero` — `session-close-fallback.py` had an issue; check `ANTHROPIC_API_KEY` is set and the SDK is installed.

For verbose tracing during a session, set `CLOSING_SIGNAL_DEBUG=1` and watch stderr.

## Why this exists

The prior architecture relied entirely on the model "noticing" closing signals and choosing to read the cascade rule file before responding. Three brittle steps (notice signal → read rule → execute the cascade), any one of which could fail silently. Reports came back of users saying "bye" and the cascade not firing — captures lost.

This architecture moves detection to a deterministic hook (Layer 1), preserves all model-required creative work in Phase 1, and adds a Haiku backstop (Layer 3) that guarantees no silent loss even if the model bails. The full cascade — every capture from the prior 7-phase spec — is preserved.

## Schema reference

### Closing-signal marker (`~/.claude/.closing-signal-{session_id}.json`)

```json
{
  "timestamp": "2026-04-30 14:23",
  "timestamp_file": "2026-04-30T14-23",
  "matched_signal": "^(ok(ay)?[,.\\s]+)?bye\\b",
  "confidence": "high_confidence",
  "language_packs": ["en", "es", "pt"],
  "worktree": "main",
  "vault_root": "/Users/.../My Vault",
  "meta_dir": "/Users/.../My Vault/⚙️ Meta",
  "session_file": "/Users/.../⚙️ Meta/Sessions/2026-04-30T14-23-main.md",
  "user_msg_count": 23,
  "is_trivial": false,
  "is_ambiguous": false,
  "elapsed_ms": 4
}
```

### Partial-completion flag (`~/.claude/.cascade-partial-{session_id}.json`)

```json
{
  "session_id": "abc-123",
  "session_file": "/Users/.../Sessions/2026-04-30T14-23-main.md",
  "reason": "session body empty + fallback unavailable"
}
```

### Pre-built session file shell

```yaml
---
creationDate: 2026-04-30 14:23
type: session
worktree: main
session_date: 2026-04-30
session_label: "update pending"
---

# Session — 2026-04-30 14:23

## What happened
## Decisions
## Captures
## To-dos filed
## Delegations
## Pending / incomplete
```

The model fills bodies under each header. The `session_label` flips from `"update pending"` to a real label once the body is non-empty (or to `"fallback (haiku)"` / `"fallback (no-api-key)"` if the Stop hook had to backfill).

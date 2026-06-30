---
status: accepted
date: 2026-06-30
---

# 0006 - Measure the LIVE settings.json injection, not just the shipped template

## Context

[ADR 0005](0005-cache-position-injected-context.md) moved the substrate's stable
UserPromptSubmit (UPS) injectors to SessionStart and added **axis D** to the footprint
gate: `--measure --execute` runs each UPS substrate hook with a neutral prompt and sums
the `additionalContext` tokens it emits every message. After the move, the substrate's
own UPS injectors measure **0**.

But axis D measures the **shipped `hooks.json` template** - it resolves each command to a
`skills/ai-brain-starter/(hooks|scripts)/X.py` file in *this repo* and runs that file. The
per-message injection an install **actually pays** does not live in the template. It lives
in each install's `~/.claude/settings.json`, which:

1. is where the installer **merges** `hooks.json` (the template is a subset of it), and
2. **also holds the user's OWN + customized injectors** - a CONTEXT.md auto-loader, a
   per-message version check, an umbrella-map loader, any hand-wired UPS hook.

A stable, prompt-independent injector wired there re-injects its full block on **every
message** - the exact recurring-token waste ADR 0005 fixed for the substrate's own hooks -
and the template-only axis D is **blind to it**, because:

- The command points at `~/.claude/hooks/X.py` or an absolute path, not the substrate
  path → it doesn't match the substrate signature, so axis D never resolves or runs it.
- The injector is **non-`.py`** (a `bash '…/x.sh'` vault-script, or an inline-bash
  `echo '{…additionalContext…}'`) → axis D only executes `.py` substrate files.
- The injector is on **PreToolUse / PostToolUse** (a stable block emitted on every `Write`
  or `Bash`) → axis D only looks at `UserPromptSubmit`.

ADR 0005 named this gap explicitly and put it out of scope: *"Founder-personal `~/.claude`
UPS injectors (e.g. a CONTEXT.md auto-loader) exhibit the same class but are NOT in this
public substrate - out of scope here."* This ADR closes it.

## Decision

Add `scripts/footprint-sla-check.py --measure-live [--execute]` - axis D against the LIVE
`~/.claude/settings.json` (override with `--settings`).

1. **Execute the LITERAL wired command, not a resolved repo file.** Each hook is run the
   way Claude Code runs it: the command string via `/bin/bash -c`, the event payload on
   stdin, stdout parsed for `hookSpecificOutput.additionalContext` (and, for UPS, raw
   non-JSON stdout, which the harness also injects). Running the literal command is the
   single change that makes **unowned**, **non-`.py`** (vault-script / inline-bash), and
   **per-tool** (PreToolUse / PostToolUse) injectors all measurable uniformly - the three
   forms the resolve-a-repo-file path skips.

2. **Scope = the recurring events** (`UserPromptSubmit`, `PreToolUse`, `PostToolUse`), in a
   **sandboxed HOME** (`HOME` + `CLAUDE_PROJECT_DIR` redirected to a throwaway dir, per-hook
   timeout). SessionStart is deliberately **excluded**: it is the relocate *target* (fires
   once per session-segment → cached prefix), not a per-message cost, and executing its
   fleet (skill sync, backups, git) would be heavy and side-effectful.

3. **Tag owned vs unowned** from a single source of truth - `is_abs_owned` imported from
   `install-hooks-user-level.py` (the same `ABS_FINGERPRINTS` / `ABS_OWNED_BASENAMES` that
   decide what the installer may relocate), with a path-heuristic fallback that names
   itself. An unowned stable injector is the user's to fix; the report says so.

4. **Surface a relocate hint.** Any UPS hook that emits a stable block on a neutral prompt
   is flagged *"belongs on SessionStart (cached prefix), not UserPromptSubmit"*; a per-tool
   injector is flagged *"move the stable part to SessionStart, or gate it to emit only when
   relevant."*

5. **Advisory, never a gate; the LOGIC is gated by `--selftest`.** `--measure-live` prints
   numbers and exits 0 (a missing settings.json → graceful note + 0; a clean CI box has
   none). The raw numbers are install/runner-dependent, so they are never a CI pass/fail.
   What CI *does* gate is the measurement **logic**: `--selftest` builds a synthetic
   settings.json with one of each injector form and asserts an unconditional `.py` injector
   scores high, a conditional one scores 0, a **non-`.py` inline-bash** injector is
   measured, a **per-tool** injector is measured, an **unowned** injector is measured, a
   JSON no-op scores 0, and the ownership tag loads from its single source of truth.
   `tests/integration/test_footprint_sla.sh` §7 locks the same at the integration level.

### Why a CLI mode and not an auto-firing SessionStart advisory

The issue offered "a `--measure` mode **or** a SessionStart advisory." A SessionStart hook
that executed the whole live fleet every session would itself be a per-session footprint
regression - the precise thing this epic fights (`SLOW-INSTALL-FROM-LAZY-PLUMBING`), and it
would execute the user's hooks unprompted. So the live measurement is an **opt-in CLI
mode** a maintainer runs deliberately, discoverable from `--measure --execute`'s output. No
new always-on hook ships; the always-on footprint stays at zero new cold starts.

### Why executing the user's own hooks is acceptable here

`--execute` runs the install's real wired hooks - but they are the *same* hooks that
already fire on every turn, run **once each** with a **neutral** payload in a **sandboxed
HOME**, strictly less than one normal turn of activity. The maintainer opts in. A
well-behaved conditional hook short-circuits on the neutral payload and does nothing.

## Consequences

- A maintainer/install can see the per-message injected-token cost of their **actual**
  settings.json - owned and unowned, `.py` and non-`.py`, UPS and per-tool - with concrete
  relocate-to-SessionStart hints. The ADR 0005 out-of-scope gap is closed.
- The number is advisory and install-specific; it is not added to `footprint-budgets.json`
  (a cross-install ceiling there would be meaningless). The deterministic template gate
  (ADR 0004 / 0005) is unchanged and still the CI ratchet.
- Reversal would re-blind the audit to the per-message cost an install actually pays - the
  cost that compounds at scale and earns the "this slowed my Mac" reputation.
- A future install-time or commercial-substrate check could consume a machine-readable
  variant (a `--json` shape for `--measure-live` is straightforward to add when a consumer
  needs it) to surface stable per-message injectors during onboarding, without ever
  blocking on the flaky raw number.

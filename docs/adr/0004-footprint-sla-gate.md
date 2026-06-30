---
status: accepted
date: 2026-06-30
---

## Context

The substrate's `hooks.json` is what every install runs — a free self-install and a paid commercial install built on this substrate are the same fleet ([HOOK_FLEET_RESOURCE_GOVERNANCE.md](../HOOK_FLEET_RESOURCE_GOVERNANCE.md)). Every wired hook is a cold `python3` start, so the felt cost of a hot event is interpreter-startup × fan-out: a `Write` fans out to several cold starts, `SessionStart` to more. A footprint audit of the live fleet found ~14 cold starts on `SessionStart`, 7 on a `Write`, 6 per message on `UserPromptSubmit`. Nothing stopped that count from re-growing every time a hook was added. Bug class: SLOW-INSTALL-FROM-LAZY-PLUMBING — the install slowly slows the machine, and a "this slowed my Mac" reputation kills the funnel.

The same audit corrected two intuitions that shape the gate:

1. **Hooks for one event run concurrently in Claude Code**, so felt wall-clock latency is `MAX(hook)`, not `SUM(hook)`. The summed "~1.5 s per turn" figure was wrong; the real per-event felt latency is the single slowest hook (tens of ms). The fan-out still costs real CPU/battery (N cold spawns) and reliability (one slow hook stalls the whole event to its timeout), but it is **not a wall-clock-latency emergency**.
2. **A wall-clock-ms gate is flaky on a shared CI runner.** A gate that fails on timing noise teaches bypass (admin-merge, `--no-verify`), which then masks real failures ([over-strict-verification-teaches-bypass](../../templates/rules/), Reliability Manifesto pillar 2: guardrails are deterministic Python checks, not judged signals).

We need a gate that bounds the footprint durably without flaking, and that ships green on the current fleet (an auto-managed gate must never ship known-red).

## Decision

`scripts/footprint-sla-check.py --gate` is a CI release gate, wired into `scripts/ci.sh` via `tests/integration/test_footprint_sla.sh`. It splits axes into **hard** (deterministic, block merge) and **advisory** (reported, never block):

**Hard axes — parse committed source, no timing, no hook execution:**
- **Per-event / per-tool substrate cold-start fan-out** vs `footprint-budgets.json`. This is the CPU/battery + reliability axis. Per-message events exclude `once: true` entries (they fire once per session, not per turn), so `UserPromptSubmit` is gated on its steady per-message count. `PreToolUse` / `PostToolUse` are matcher-gated, so fan-out is computed per tool (`Write`, `Bash`, …). Only commands that resolve to a shipped `skills/ai-brain-starter/(hooks|scripts)/X.py` are counted — `[ -f ~/.claude/hooks/… ]`-guarded maintainer hooks no-op on a fresh install and are excluded.
- **Default-on background daemon count** — a coarse structural tripwire that the default install path (`bootstrap.sh`) wires 0 launchd/cron daemons (daemons are opt-in). Trips if a change makes one default-on.

**Advisory axes — printed by `--measure --execute`, never gated:**
- Per-hook cold-start time (median vs the `python3 -c pass` floor) and per-event felt = `MAX(hook)`. Flaky on shared runners → reported, with the correct MAX semantics, so the latency story is visible without being a flaky gate.
- Per-message injected bytes from the `UserPromptSubmit` context-injectors — the recurring-token axis (MYC-2359). Install-specific (a clean CI box has no vault) → reported.

**Budgets ratchet.** `footprint-budgets.json` is `measured + headroom` (default 2), regenerated with `--update-budgets`. The gate ships green on today's fleet, bites on growth, and records `_baseline_measured` for transparency. As Stage 2 (precise triggers + async) reduces the fan-out, the budgets tighten — the gate is a ratchet, not a one-time cleanup.

**Fail-loud.** `--gate` / `--selftest` exit 2 on any internal error (missing/unparseable `hooks.json` or budgets) so a broken gate can never read as a silent green. `--selftest` is the built-in negative control: a 30-hook synthetic fan-out trips the gate, a default-on daemon trips it, a within-budget fleet passes, and a missing budgets file fails loud.

This gate does **not** duplicate `audit-sessionstart-boundedness.py` (MYC-571): that gate governs each hook's work shape (no unbounded corpus walk); this one governs the fleet's fan-out + footprint. Two concerns, two gates.

## Why

- The fan-out **count** is the honest deterministic proxy for the CPU/battery cost the audit actually found, and it is exactly the thing that silently re-grows. Gating the count prevents re-bloat with zero CI flakiness — you cannot wire a new cold-start hook without the gate forcing the conversation (optimize, or raise the budget with a rationale).
- Gating wall-clock ms would have flaked on the runner and taught bypass, then masked the real signal. Measuring it as `MAX` and reporting it keeps the latency story honest without that failure mode.
- Setting budgets at `measured + headroom` is what lets the gate ship green today (never a known-red auto-managed gate) while still biting on real growth.

## Consequences

- Adding a hook that pushes a hot event past budget turns CI red; the author must either move work off the hot path (Stage 2) or raise the budget in the same PR with a one-line rationale. That is the intended ratchet.
- The dispatcher (the heavy structural fix, MYC-2362) is now conditional on this gate staying red after the cheap fixes land — sequence-then-gate, not build-the-cathedral-first.
- The advisory timing/token axes need `--execute` and a populated vault to be meaningful; CI never executes hooks, so the gate stays fast and side-effect-free.
- Tightening the budgets as fan-out drops is a one-command change (`--update-budgets`), reviewable as a diff of `footprint-budgets.json`.
- Reversal would mean letting the hook fan-out grow ungoverned again — re-opening SLOW-INSTALL-FROM-LAZY-PLUMBING.

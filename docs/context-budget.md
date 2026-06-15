# Context budget: governing the always-loaded text layer

`token-economics.md` measures what you *install* (plugins, MCP servers). This doc
measures what you *always load*: the text injected into every session, on every
turn, forever — your `CLAUDE.md` files, `MEMORY.md`, and `CONTEXT.md`.

That layer is the most expensive context in the system, and the one with no natural
guard. Plugin load is measured; MEMORY.md has a cliff guard; but the `CLAUDE.md`
kernel itself just grows — every rule codified inline with full rationale, every
"codified 2026-..." retro pasted in whole — until a new session opens already 15–20%
full before you've typed anything. Discipline ("keep it terse") without measurement
drifts. This is the same `ARTIFACT-WITHOUT-MEASUREMENT` class as token economics.

## The guard

`hooks/context-budget-measure.py` runs at SessionStart and:

- **measures** the always-loaded files it can find — global `~/.claude/CLAUDE.md`,
  the project's `CLAUDE.md`, `MEMORY.md`, the project's `CONTEXT.md` — and reports
  the total in bytes + estimated tokens;
- **warns on a hard per-file ceiling** (default: global `CLAUDE.md` over 40 KB ≈ 10K
  tokens). The kernel pays this every turn; rationale belongs in linked rule files,
  the kernel stays one-line pointers;
- **warns on total growth past a stored baseline** (drift detection), and
- **silently ratchets the baseline down** when the layer shrinks — so a deliberate
  slim becomes the new floor and future growth is what surfaces.

It is a measure-and-warn ratchet, not a framework: fail-open (never crash-blocks a
session start), frequency-capped (warns at most once/day), silent when healthy.

## Using it

```bash
# See the table any time:
python3 ~/.claude/hooks/context-budget-measure.py --report

# Acknowledge an intentional growth as the new baseline floor:
python3 ~/.claude/hooks/context-budget-measure.py --accept

# Prove it fires/stays-silent correctly (positive + negative control):
python3 ~/.claude/hooks/context-budget-measure.py --self-test
```

Tuning (env): `CONTEXT_BUDGET_GLOBAL_CEILING` (bytes, default 40000),
`CONTEXT_BUDGET_TOL_BYTES` / `CONTEXT_BUDGET_TOL_FRAC` (growth tolerance).
Bypass for one session: `CONTEXT_BUDGET_BYPASS=1`.

## Keeping the kernel lean

When the ceiling fires, the fix is almost never "delete a rule" — it's **move the
rationale out of the always-on file and leave a one-line pointer**:

- A `CLAUDE.md` rule with multi-paragraph "why" + an incident retelling → compress to
  the rule + a pointer to the rule file that holds the detail. The detail is still
  there; you just stop paying for it every turn.
- `MEMORY.md` is a *curated, capped index*, not a catalog. One line per memory; the
  full note lives in its own file.
- If you compile shared rules into the kernel (a team brain), tier them: a one-line
  digest always-on, the full body retrieval-only.

The measurer tells you *when* the layer has grown; these moves are *how* you bring it
back under the floor without losing anything.

# Token economics — measure at install, scope by frequency

Plugins, MCP servers, and `SessionStart` hooks all add **always-on** context cost to every session. Each new install incrementally eats your context budget, even when the new capability is rarely used. This document codifies the discipline for keeping that load lean **without losing capability**.

## The bug class

**`ARTIFACT-WITHOUT-MEASUREMENT`.** Installing something without measuring its always-on cost.

A real measurement from one user's environment:

- Total always-on plugin load: **~19,000 tokens per session** (about 10% of a 200K context).
- Two domain-bundle plugins (a marketing pack + an SEO pack) accounted for **~10,000** of that — roughly half.
- Both were used less than once a week. Disabling them with a one-command re-enable saved ~10K per session with **zero capability loss**.

The pattern repeats: tools accumulate, indexes inflate, capability is mostly there but the cost is silent. The fix is not "use fewer plugins." The fix is **measure at install**, **decide by frequency**, **document the choice**, and **never lose capability** in the trade.

## The hard rule

Every install gets:

1. **Measurement first.** Run `claude plugin details <name>` before `claude plugin install <name>`. Note the "Always-on" line.
2. **Apply the decision tree** (below).
3. **Document the choice.** A short note in your install/audit memory: which scoping, why, and the re-enable command if disabled.
4. **Quality stays the bar.** Disabling is only legitimate if capability stays available (per-session enable, keyword-triggered reminder, vault skill that wraps the most-used capability, etc.).

## Decision tree

```
always-on cost?
├── ≤500 tok                   → install globally (cheap, no scoping needed)
└── >500 tok
    ├── used ≥ weekly          → install globally (cost amortizes against use)
    └── used < weekly
        ├── high-friction       → install globally + keyword-trigger reminder
        └── normal              → install disabled + document the re-enable command
```

`500` is a starting threshold; tune for your context budget. On a 200K window, 500 tokens per plugin × 50 plugins is 25K — meaningful. On a 1M window, the same load is noise.

## Skills vs MCPs vs hooks

Each component type has different cost behavior:

- **Skill metadata** (name + description) loads always-on; **skill bodies** load only when the skill fires. An idle skill is ~100 tokens of index. A fired skill is index + body. Domain bundles with 40+ skills can hit 5K+ tokens of always-on index for capability you may not touch this session.
- **MCP server tool schemas** are often deferred in Claude Code (loaded on search rather than always-on) — the harness-level win that makes MCP servers feasible at scale. The deferred-tool **name list** still contributes a smaller per-session cost, so unused MCP servers in `.mcp.json` should be pruned.
- **`SessionStart` hooks** inject context at every session start. Measure the injection size before adding a new hook. Cache long-running checks (24h TTL pattern works well): `echo "$msg" > ~/.claude/.<my-hook>-cache` and skip the network call when the cache is fresh.

## Measuring

This repo ships `scripts/measure-plugin-load.py`. It runs `claude plugin details` over every installed plugin in parallel, parses the always-on cost, and flags plugins above a threshold.

```bash
# Show a sorted table + flag plugins >500 tok always-on
python3 scripts/measure-plugin-load.py --threshold 500

# Write a Markdown report to a file (good for quarterly review):
python3 scripts/measure-plugin-load.py --report plugin-token-report.md

# JSON output for downstream tooling:
python3 scripts/measure-plugin-load.py --json
```

The output ranks plugins by always-on cost and flags candidates exceeding the threshold for the decision tree above.

## Periodic review

- **Quarterly**, or whenever sessions feel heavy: re-run the measurement script. Catches drift — plugins that grew, new installs that bumped the total without anyone noticing.
- **Every install**: measure first, decide, document.
- **`/usage` in Claude Code 2.1.149+**: per-category breakdown for skills, subagents, plugins, and per-MCP-server cost. Use it to cross-check the script's numbers.

## Quality floor — the non-negotiable

This rule reduces **token load**, never **capability**. Disabled plugins are one command away from being enabled, and you'll have written that command in your install memory.

The point is that big domain bundles — marketing, SEO, error tracking, fuzzing, language servers you only use in one codebase — shouldn't pay rent in every session when you use them once a month.

If your decision tree starts cutting capability you actually use weekly, you've gone too far. Re-enable. Find a smaller lever:

- A hookify keyword-trigger that surfaces the disabled plugin when domain keywords appear in your prompt.
- A vault skill that wraps the most-used capability from the disabled bundle.
- A different, lighter bundle from a different marketplace.

## Companion artifacts

- `scripts/measure-plugin-load.py` — the measurement tool. Generic; works for any user with the `claude` CLI installed.
- `docs/installing-new-skills.md` (your own install playbook) — extend it so the token-cost measurement is **Decision 0** in your install flow.
- A note in your CLAUDE.md or AGENTS.md pointing future sessions at this discipline.

## Bug class registered

**`ARTIFACT-WITHOUT-MEASUREMENT`.** The fix is the measurement step, not the disable. Disabling is just what the measurement reveals; the discipline is making the cost visible at install time, every time.

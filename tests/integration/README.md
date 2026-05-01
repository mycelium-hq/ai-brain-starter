---
type: integration-tests
last_verified: 2026-04-30
freshness_days: 90
---

# End-to-end catalect integration tests

Each step in `test_e2e_pipeline.py` exercises a contract between two or
more pieces shipped today, not just one piece in isolation. The test is
the verification artifact for "the 5 catalect primitives compose
correctly," not a smoke test of any single script.

## Run

```bash
python3 tests/integration/test_e2e_pipeline.py
```

Stdlib + PyYAML only. No pytest, no fixtures folder, no mocks. The
script provisions a fresh `/tmp/abs-integration-vault/`, runs the 11
checks, and tears the vault down on exit.

Exit codes:

- `0`: all 11 steps passed.
- `1`: first failure printed to stderr with the step name and the
  exact assertion that broke.

## What the 11 steps prove

| Step | Catalect primitive validated | Contract under test |
|---|---|---|
| 1 + 2 | Ingestion | Synthetic Slack-shaped markdown with frontmatter and the trigger keyword `pricing exception` lands at `External Inputs/Slack/<channel>/<date>.md`. |
| 3 | Synthesizer (`synth-thread-to-sop`) | Reading an ingested thread produces a typed-memory file under `Meta/Exceptions/` with the cross-type frontmatter contract: `type`, `memory_class`, `sha8`, `last_verified`, `freshness_days`, `provenance`, `entity_ids.slack`, `exception_summary`. |
| 4 | Aggregator (`resolver-build.py`) | The resolver walks `Meta/Decisions|Workflows|Exceptions|Facts/`, parses frontmatter, and emits `Meta/RESOLVER.md` whose body references the new rule by `sha8`. |
| 5 | Bi-temporal freshness (fresh case) | A typed-memory entry whose `last_verified` was just set is reported as `active`, not `stale`. `stale-rule-check.py` exits 0. |
| 6 | Bi-temporal freshness (stale case) | Backdating `last_verified` 200 days flips the same entry to `stale`. `stale-rule-check.py` exits 2 and the entry shows in stdout. |
| 7 | Cascade (`proposed-update-drafter`) | When a rule changes, every downstream `[[wikilink]]` reference gets a `proposed-update:BEGIN ... END` banner injected once, idempotently. |
| 8 | Validator (positive path) | A valid `SKILL.md` whose frontmatter conforms to `templates/schemas/skill.json` passes the `validate-skill-frontmatter.py` PreToolUse hook with `permissionDecision: allow`. |
| 9 | Validator (negative path) | A `SKILL.md` missing the schema-required `type` and `name` fields is rejected at the write boundary. The hook either denies or exits non-zero. |
| 10 | Closed-loop promotion | Three episodic Learning files with overlapping `error_excerpt` 5-grams cluster into a single `Meta/Promotion-Candidates/<sha8>.md` with `status: candidate` and `memory_class: procedural`. |
| 11 | Ground-truth wiki maintainer | Adding a `topic:` field to a typed-memory entry causes `ground-truth-wiki-maintain.py` to produce `Meta/Wiki/<topic>.md` with `auto_generated: true` and a section per matched type. |

## Why this matters

Each shipped piece has its own smoke test, but smoke tests do not catch
contract drift between primitives. A skill validator that passes a
schema change in isolation can still break the synthesizer if the
synthesizer writes a field the schema no longer accepts. A resolver
that builds happily on its own can still emit broken links if the
synthesizer's `sha8` derivation drifts. The 11 steps wire those
contracts together end-to-end.

## Adding a step

Add a `step_N_<name>` function. Each step must:

- Call into a shipped script via `subprocess.run`, never reimplement
  its logic in the test.
- Use `assert`-style checks. Any failure routes through `fail(step,
  detail)` so stderr names the step and the breakage.
- Be idempotent over the temporary vault: do not assume any other step's
  state beyond what the prior step explicitly produced.

## Cleanup

The script tears the vault down inside a `finally` block, so an early
failure still removes `/tmp/abs-integration-vault/`. If a manual run
leaves a stale vault behind, remove it with `rm -rf
/tmp/abs-integration-vault`.

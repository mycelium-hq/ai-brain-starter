---
name: hook-fleet-resource-governance
description: The SessionStart hook fleet this repo ships is what EVERY install runs (free self-install and paid commercial installs alike). Its resource-governance invariant + provenance + how it's verified.
---

# Hook-fleet resource governance

## Why this doc exists

This repo's `hooks.json` is the source of truth for the Claude Code SessionStart
hook fleet. That fleet is what runs on **every** install — a free self-install
and a paid commercial install built on this substrate are the **same fleet**.
There is no separate "paid" hook fleet.

A SessionStart hook fires once per Claude Code session. A machine running many
concurrent sessions runs every SessionStart hook many times at once. So a single
SessionStart hook that does heavy or unbounded work is a per-session multiplier:
under N concurrent sessions it becomes N concurrent heavy jobs.

On 2026-06-05 that exact shape hard-froze a machine (load 36, total freeze): the
corpus-walk secret scan ran on SessionStart, its cooldown was stamped *after* the
slow scan, and four concurrent sessions each launched their own full-corpus walk.
The fix was twofold and both halves live here: the scan moved **off** SessionStart
(scheduled job + cached-findings surfacer), and a stuck-hook reaper now ships **on**
SessionStart. This doc records the invariant so it can't silently regress.

## Provenance — what an install actually wires

```
bootstrap.sh
   └─ git clone (idempotent) ai-brain-starter@main → ~/.claude/skills/ai-brain-starter/
        └─ scripts/install-hooks-user-level.py
              └─ reads the canonical root hooks.json
                    └─ merges its SessionStart block into ~/.claude/settings.json
```

- The clone tracks **`main`** (it refuses to pull over a locally diverged clone,
  but it does not pin an old tag). A fresh install gets current `main`.
- `install-hooks-user-level.py` is idempotent and additive: it never removes a
  user's own hooks, only merges the ai-brain-starter set.
- **Native desktop / commercial products that wrap this substrate do not vendor
  or re-wire this fleet.** Where they spawn the Claude CLI for their own agent
  loop they run it with SessionStart/SessionEnd hooks disabled, and where they
  need vault-safety logic they re-implement it natively rather than shelling out
  to these Python hooks. So the only thing that wires this SessionStart fleet onto
  any machine — free or paid — is the path above.

Net: "is the paid install's hook fleet hardened?" reduces to "is `ai-brain-starter@main`
hardened?" — and the rest of this doc is the answer.

## The invariant

1. **No unbounded or corpus-scale work on SessionStart.** A SessionStart hook
   reads small, bounded state (a marker file, one directory level, a bounded
   subprocess with a timeout). Anything that walks a large corpus, syncs over the
   network, or otherwise scales with the user's data belongs on a **scheduled job**
   or a **cached-findings surfacer**, never the synchronous cold-start path.
2. **The protective reaper ships on SessionStart.** `remediate-runaway-procs.py`
   (CLASS-2 stuck-hook reaper) is the backstop that kills a wedged `~/.claude/hooks`
   process; it must be present in every install.

## Audit — the shipped SessionStart set

Every hook in the canonical `hooks.json` SessionStart block, and why each is
bounded (read against this repo at the time of writing — re-run the verification
below to confirm on any later revision):

| Hook | Work it does | Bound |
|---|---|---|
| `lint-claude-settings.py` (+ `--test`) | parse + lint one JSON file | single small file |
| `check-claude-code-version.sh` | read one cached version string | cached, no walk |
| `first-week-checkin.py` | read an install-date marker | marker read + budget guard |
| `migrate-to-user-level.py` | one-shot settings migration check | idempotent, no walk |
| `surface-orphan-claude-branches.py` | `git for-each-ref` + one `iterdir` | bounded git op + 1 dir level |
| `surface-stranded-session-artifacts.py` | `iterdir` of `.claude/worktrees/` | 1 dir level + subprocess `timeout=15` |
| `surface-orphan-worktree-snapshots.py` | `rglob` under the small snapshots dir | snapshot tree only, results capped |
| `worktree-footprint-signal.py` | `iterdir` of the worktree dir | 1 dir level |
| `surface-backup-status.py` | `iterdir` of repo root + `git` | 1 dir level + subprocess `timeout=30` |
| `enforce-worktree-cap.py` | count worktrees vs cap | bounded count + budget guard |
| `remediate-runaway-procs.py` | scan `~/.claude/hooks` procs, reap wedged ones | dual age/CPU gate, no FS walk |

None walks the user's vault corpus or `~/.claude/projects` transcripts.

**Deliberately NOT on SessionStart** (the two "heavy / concurrent" classes the
freeze taught us to keep off the cold-start path):

- `scan-prior-sessions-for-secrets.py` — corpus-walk secret scan. Runs as a
  scheduled job; SessionStart only reads its cached findings. (Hardened anyway —
  single-instance lock, stamp-at-start cooldown, incremental, `os.nice`, wall
  budget, per-file cap — so even a manual re-add can't pile up.)
- `health-auto-sync.py` — network wearable sync. Opt-in power-user file; the
  default chain syncs once per day on `/journal` Stop, not per session.

## How it's enforced (regression guards, all in `scripts/ci.sh`)

- `tests/integration/test_sessionstart_freeze_class_excluded.sh` — asserts the
  canonical `hooks.json` SessionStart set **excludes** the corpus-walk scan and
  **includes** the reaper. Ships with negative controls that re-add the scan /
  drop the reaper and confirm the guard trips.
- `tests/integration/test_scan_prior_single_instance.sh` — a second concurrent
  scan run backs off (no pile-up), even if the scan is invoked directly.
- `tests/integration/test_remediate_runaway_procs.sh` — the reaper's pos/neg
  controls (reaps a wedged hook proc; never reaps self or a non-python proc).
- `services/health-mcp/tests/test_v05_hooks.py` — asserts `health-auto-sync.py`
  stays out of the default SessionStart block.

## Verify on a fresh install

The repo being hardened is not the same as a fresh install landing the hardened
wiring. To prove it on any revision, install into a throwaway `$HOME` and assert
the SessionStart wiring:

```bash
FRESH="$(mktemp -d)"; mkdir -p "$FRESH/.claude"
HOME="$FRESH" python3 scripts/install-hooks-user-level.py \
  --hooks-source "$PWD/hooks.json" --quiet

python3 - "$FRESH/.claude/settings.json" <<'PY'
import json, sys
ss = json.dumps(json.load(open(sys.argv[1])).get("hooks", {}).get("SessionStart", []))
assert "remediate-runaway-procs.py" in ss,            "reaper must be wired"
assert "scan-prior-sessions-for-secrets.py" not in ss, "corpus scan must stay off SessionStart"
assert "health-auto-sync.py" not in ss,                "network sync must stay off SessionStart"
print("fresh-install SessionStart wiring OK")
PY
```

Expected: `fresh-install SessionStart wiring OK`.

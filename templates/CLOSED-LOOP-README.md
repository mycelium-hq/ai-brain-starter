# Closed-loop learning architecture

This file documents the closed-loop learning primitives that ship with the
starter: the memory-class typology, the agent-during-execution Learnings
hook, the background consolidation script, and the human-in-the-loop
promotion gate.

The architecture is one Read away from being legible. Read this file in
full once and you have the full mental model.

## The four-stage loop

1. **Capture during execution.** A PostToolUse hook
   (`hooks/post-tool-use-learnings.py`) watches every Bash, Edit, Write, and
   Agent tool call. When the call fails or the result contains an explicit
   `<learning>...</learning>` annotation, the hook writes one episodic
   memory file to `<vault-root>/Meta/Learnings/<YYYY-MM-DD>-<sha8>.md`.
   This is the "what just happened" sink. The agent never has to remember to
   write to it; the harness does it automatically.

2. **Episodic memory accumulates.** Each Learning carries
   `type: learning`, `memory_class: episodic`, a captured-at timestamp, the
   source tool, an excerpt of the error (if any), and provenance pointing
   back to the originating Claude session. Files are append-only. The hook
   is idempotent (sha8 derived from tool-call-id + timestamp), so a re-run
   of the same tool call does not produce duplicate Learning files.

3. **Background consolidation surfaces patterns.** A consolidation script
   (`scripts/promote-episodic-to-procedural.py`) walks the Learnings folder
   and groups files by source tool, then by 5-gram overlap on the error
   excerpt (Jaccard similarity threshold 0.30). When a cluster reaches
   `--min-occurrences` (default 3), the script drafts a procedural-memory
   candidate at `<vault-root>/Meta/Promotion-Candidates/<sha8>.md`. The
   candidate carries `status: candidate` and lists the source episodic
   files in its frontmatter.

4. **Human review promotes the candidate.** The reviewer reads the
   candidate, decides whether the pattern is real, and either:
   - reshapes it to fit the `exception` schema and moves it to
     `Meta/Exceptions/`, or
   - reshapes it to fit the `workflow` schema and moves it to
     `Meta/Workflows/`, or
   - deletes the candidate as a false positive.

   The script never promotes directly. The gate is intentional: closed-loop
   learning without human review tends to amplify noise. The gate is also
   cheap: a candidate is one file, the reviewer scans it in ~30 seconds.

## Memory class typology

The closed-loop architecture sits on top of a typology that classifies every
typed-memory entry as either `episodic` or `procedural`.

`episodic` memory pins down what happened on a specific day or in a specific
moment. Journal entries, session logs, decisions, observed outcomes, and
Learnings all qualify. Replaying the entry later does not generate a new
instance; it retrieves the one that already exists. Episodic entries are
typically write-once at capture time and read-many during retrospection.

`procedural` memory captures repeatable, time-stable knowledge. Facts,
workflows, exceptions, and relationships qualify. The agent can pull a
procedural entry once and apply it across many runs. Procedural entries
evolve over time: a `freshness_days` window tells consumers when to
re-verify the entry, and the `last_verified` field records the most recent
confirmation.

| Schema | Default `memory_class` |
|---|---|
| `journal` | `episodic` |
| `session` | `episodic` |
| `decision` | `episodic` |
| `outcome` | `episodic` |
| `fact` | `procedural` |
| `workflow` | `procedural` |
| `exception` | `procedural` |
| `relationship` | `procedural` |

The typology is the substrate the consolidation pass needs. Without it, the
script cannot tell which entries are evidence (episodic) and which are
candidates for stable retrieval (procedural). With it, the promotion path
is unambiguous: episodic clusters become procedural candidates, never the
other way around.

## Files in this loop

```
hooks/post-tool-use-learnings.py
    PostToolUse hook. Writes one episodic Learning file per failed tool call
    or per <learning> annotation. Idempotent. Stdlib + PyYAML.

scripts/promote-episodic-to-procedural.py
    CLI consolidation script. Walks Meta/Learnings/, clusters by similarity,
    drafts procedural candidates at Meta/Promotion-Candidates/. Never
    promotes directly. State file at .promote-state.json + --quiet make it
    cron-friendly. Stdlib + PyYAML.

scripts/demote-stale-procedural.py
    CLI decay script. Walks Meta/Workflows/, Meta/Exceptions/, Meta/Facts/.
    Surfaces stale procedural rules (past multiplier x freshness_days, with
    empty outcome or unset pattern) as demotion candidates at
    Meta/Demotion-Candidates/. Never auto-deletes. Stdlib + PyYAML.

templates/schemas/*.json
    All eight typed-memory schemas now carry `memory_class` and
    `entity_ids`. Schemas remain permissive: the new fields are optional and
    documented defaults only apply when the writer leaves them blank.

templates/schemas/README.md
    Cross-type contract documentation. Includes the memory-class typology
    and the entity-ids cross-source linking conventions.
```

## Wiring the hook

The hook lives at `hooks/post-tool-use-learnings.py`. To register it, add
this stanza to `~/.claude/settings.json` or the project-local
`.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Edit|Write|Task",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/ai-brain-starter/hooks/post-tool-use-learnings.py"
          }
        ]
      }
    ]
  }
}
```

The hook reads JSON from stdin (the harness's PostToolUse contract), detects
failure or `<learning>` annotation, and writes the Learning file. On any
internal error, it emits a passthrough so it never blocks the calling agent.

## Running the consolidation script

```
python3 scripts/promote-episodic-to-procedural.py \
    --vault-root /path/to/vault \
    --min-occurrences 3 \
    --dry-run
```

`--dry-run` prints what would be written without touching the filesystem.
Drop the flag to actually draft candidates. The script is safe to re-run; if
a candidate already exists at the target path, the script skips it.

### Cron / scheduled runs

The script keeps a state file at `<vault-root>/.promote-state.json`
recording the last-run timestamp and the count of Learning files seen. On
re-invocation, if the file count has not changed since the last run, the
script exits early without doing any clustering work. Pair this with the
`--quiet` flag and the script becomes a no-op on idle vaults: zero output,
zero cost.

One-line cron pattern (every 6 hours):

```
0 */6 * * * cd /path/to/vault && python3 \
    /path/to/ai-brain-starter/scripts/promote-episodic-to-procedural.py \
    --vault-root /path/to/vault --quiet
```

The state file lives at the vault root, so add it to `.gitignore` if the
vault is a git repo. Use `--force` to ignore the state file and re-scan
every Learning file (useful when the clustering parameters change).

### Confidence-weighted promotion

When every entry in a cluster carries `confidence >= --auto-confidence`
(default 0.85) AND the cluster spans at least `--auto-span-days` days
(default 7) between earliest and latest capture, the candidate is written
with `status: ready-for-auto-promote` instead of `status: candidate`. Both
statuses still require human review before the procedural memory goes live;
the difference is triage speed. A reviewer scanning a backlog can clear
`ready-for-auto-promote` candidates faster because they already cleared
the high-confidence bar.

Confidence semantics:
- `confidence` lives on each Learning file's frontmatter as a float in
  `[0.0, 1.0]`. The PostToolUse hook sets it from the captured signal
  (an explicit `<learning confidence="0.92">...` annotation, or a default
  if the hook had no better signal).
- The threshold is intentionally high (0.85) so that auto-ready candidates
  are conservative. A single low-confidence entry in the cluster downgrades
  the whole candidate to `status: candidate`.
- The span requirement (default 7 days) prevents a single bad afternoon
  of repeated failures from minting a high-confidence candidate. Real
  recurring patterns show up across days, not minutes.

A reasonable cadence is every 6 hours, run from cron or a launchd plist or
the session-close cascade. The state file means most invocations are
no-ops, so the cadence cost is negligible.

## Decay: the demotion path

The promotion path turns episodic captures into procedural candidates. The
decay path catches procedural rules that have gone stale.
`scripts/demote-stale-procedural.py` walks `Meta/Workflows/`,
`Meta/Exceptions/`, and `Meta/Facts/`. For each entry it computes
`(today - last_verified)`. When that value exceeds
`--multiplier x freshness_days` (default multiplier 2) AND the entry shows
signs of never having been confirmed working (empty `outcome`, no `pattern`
field set), the script writes a demotion candidate to
`<vault-root>/Meta/Demotion-Candidates/<sha8>.md`.

The candidate frontmatter records:
- `type` matching the source type (`workflow`, `exception`, or `fact`)
- `memory_class: procedural`
- `status: demotion-candidate`
- `source_procedural_file` (path relative to the vault root)
- `reason` (one of `stale-no-outcome`, `stale-no-pattern`)
- `days_since_verified` (integer)

Operator workflow:
1. Read the candidate. Decide whether the rule is still alive.
2. If alive: open the source file, set `last_verified` to today, optionally
   fill in `outcome` or `pattern`. Delete the candidate.
3. If decayed: change the source's `status` to `archived` (or move it to
   an archive folder). Delete the candidate.

The script never auto-deletes a source file. Human review is the only
demotion gate, mirroring the promotion side.

```
python3 scripts/demote-stale-procedural.py \
    --vault-root /path/to/vault \
    --multiplier 2 \
    --dry-run
```

## Entity IDs cross-source linking

Every schema also accepts an `entity_ids` field: an object mapping
short canonical source-system names to IDs (`{"slack": "C0123ABCD",
"github_pr": "owner/repo#42", "linear": "TEAM-123"}`). The field exists so a
single typed-memory entry can be joined to its representations in other
tools without a separate join table. The consolidation script does not yet
use this field, but a future deduper or graph builder will: entries that
share `entity_ids.github_pr` are very likely about the same workstream.

## Why this architecture

The vault-as-ground-truth principle says the agent never trusts what it
remembers between sessions. Every claim the agent makes must trace to a file
the company controls. The closed loop turns that principle into a substrate
that compounds: the agent's failures become episodic records, the records
cluster into recognizable patterns, the patterns get human-reviewed into
procedural memory, and the next agent reads the procedural memory before
re-running the same task. Over time the procedural surface grows, the
failure rate falls, and the agent's reliability becomes a function of the
vault rather than the model's training-time priors. The corpus gets richer
every week. The model itself does not get smarter; the substrate does.

The human review gate is the load-bearing piece. Without it, the loop
amplifies noise (transient errors, environmental flakes, one-off network
hiccups) into spurious procedural rules. With it, the loop captures the
real, recurring failure modes and converts them into stable knowledge the
agent can apply on the next run.

## Daemon mode (added 2026-05-02)

The hourly `cron` entry that runs `promote-episodic-to-procedural.py` has
up to 1 hour of latency. For operators who tune the loop in real time and
want the resolver to see new procedural rules within seconds of capture,
the repo now ships a long-running daemon at
`scripts/closed-loop-daemon.py`.

The daemon watches `<vault>/⚙️ Meta/Learnings/` (path configurable via
`--meta-dir-name`). On every new `.md` file it runs the same promote
script with `--quiet`. Two backends:

1. **`watchdog`-based** (default if installed): inotify on Linux, FSEvents
   on macOS. Latency = milliseconds. Install: `pip install watchdog`.
2. **Stat-poll fallback** (zero deps): polls every 30 seconds. Latency =
   up to 30s. Force this with `--use-polling`.

Crash protection: a single-instance pidfile at
`<vault>/⚙️ Meta/.closed-loop-daemon.pid`. Restarting the daemon while
the previous PID is still alive errors out with exit 3, so launchd
respawns and pidfile races stay safe.

### macOS launchd install

A launchd plist template ships at
`templates/launchd/com.abs.closed-loop-daemon.plist.template`. The script
`scripts/install-closed-loop-daemon.sh /abs/path/to/vault` substitutes
operator paths, drops the plist into `~/Library/LaunchAgents/`, loads
it, and starts the agent. Logs land at
`~/.local/state/ai-brain-starter/closed-loop-daemon.{out,err}.log`.

```bash
./scripts/install-closed-loop-daemon.sh /Users/me/Desktop/MyVault
```

Stop with:

```bash
launchctl unload ~/Library/LaunchAgents/com.abs.closed-loop-daemon.plist
```

### Linux systemd

For Linux operators: write a systemd user unit pointing at
`closed-loop-daemon.py`. The polling backend works without `watchdog`,
but installing it gives inotify latency.

### When to use which

- Default to the **hourly cron** entry. It is zero-config, runs without
  a long-lived process, and the 1-hour latency is acceptable for most
  operators who batch their Claude Code sessions.
- Switch to the **daemon** when you tune the loop in real time and want
  the resolver to surface new rules within seconds of capture.
- Run **both** if you want belt-and-suspenders: the daemon catches
  real-time captures, and the cron sweeps anything the daemon missed
  (e.g. files created while the daemon was offline).

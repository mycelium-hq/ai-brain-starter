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
    promotes directly. Stdlib + PyYAML.

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

A reasonable cadence is once a day, run from cron or a launchd plist or
the session-close cascade. Daily is enough because the failure cluster has
to reach `--min-occurrences` to surface, and that takes several days of
real usage in practice.

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
the company controls. The closed loop turns that principle into a
self-improving substrate: the agent's failures become episodic records, the
records cluster into recognizable patterns, the patterns get human-reviewed
into procedural memory, and the next agent reads the procedural memory
before re-running the same task. Over time the procedural surface grows,
the failure rate falls, and the agent's reliability becomes a function of
the vault rather than the model's training-time priors.

The human review gate is the load-bearing piece. Without it, the loop
amplifies noise (transient errors, environmental flakes, one-off network
hiccups) into spurious procedural rules. With it, the loop captures the
real, recurring failure modes and converts them into stable knowledge the
agent can apply on the next run.

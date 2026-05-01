# _shared

Shared module for `ingest-*` and `synth-*` skills. Stdlib + PyYAML only.

Extracted per Build Standards #5 (cross-artifact shared code) once 6 skills had grown duplicated YAML, ISO time, slug, frontmatter, and vault-write logic.

## When to use

If you are building a skill that:
- Writes a typed-memory file (`workflow`, `decision`, `exception`) under `<vault>/Meta/<TypeFolder>/<sha8>.md`, OR
- Writes an external-input file under `<vault>/External Inputs/<Source>/<scope>/<YYYY-MM-DD>.md`, OR
- Needs YAML escaping, ISO timestamp parsing, slug helpers, body truncation, or sha8 idempotency keys

import from `_shared.connector_utils` instead of reimplementing.

## Six core helpers (the ones the spec required)

| Helper | What it does |
|---|---|
| `sha8(text)` | 8-char SHA-1 hex digest. Stable across runs. Used as idempotency keys for synth-* outputs. |
| `read_existing_or_none(path)` | Returns parsed frontmatter dict, or None if file missing/empty/malformed. Used to detect `hand_edited: true`. |
| `write_typed_memory(vault_root, type, content, frontmatter, idempotency_key)` | Writes one of `Meta/Workflows/<sha8>.md`, `Meta/Decisions/<sha8>.md`, `Meta/Exceptions/<sha8>.md`. Returns the path. |
| `normalize_for_vault(items, source_type, scope_id)` | Generic per-item markdown block renderer. Skills with rich source-specific rendering keep their own. |
| `entity_ids_for(source_type, ids)` | Builds the `entity_ids` dict for external-input frontmatter. |
| `write_external_input(vault_root, source, scope, date, items, ...)` | Generic write to `<vault>/External Inputs/<source>/<scope>/<date>.md`. Skills today use their own to control frontmatter shape; this helper is the contract for future skills. |

## Secondary helpers (extracted from the 6 skills)

YAML: `yaml_escape`, `yaml_int_array`, `yaml_str_array`, `render_frontmatter`, `split_frontmatter`

ISO time: `parse_iso`, `to_local_str`, `to_local_date`, `to_local_sortkey`, `now_iso`, `today_iso`, `date_range_strs`

Body / text: `excerpt`, `fence_text`, `truncate_body`

Slugs: `slugify`, `slugify_unicode`, `slug_repo`

## Import pattern

```python
import sys
from pathlib import Path

# Skills live two levels up from _shared.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from connector_utils import sha8, yaml_escape, to_local_str, excerpt
```

The two-line `sys.path` shim works whether the skill is run as `python3 skills/<name>/ingest.py` from repo root or installed into `~/.claude/skills/<name>/` (the symlinked end-user location).

## What lives where

- This module: pure utilities, no I/O beyond `write_typed_memory` and `write_external_input`. No network calls. No external pip deps beyond PyYAML.
- Source-specific normalizers (PR rendering, Notion props, Linear state transitions): live in the per-skill `ingest.py` / `synth.py` so each skill keeps fidelity.
- CLI argparse, payload validation, exit codes: live in the per-skill `ingest.py` / `synth.py`. The shared module never owns the CLI.

## Why not `from _shared import ...`

`_shared/` is a sibling to each skill, not a parent. Python's package resolution does not walk siblings. The two-line `sys.path` shim is the supported pattern across all 6 skills today.

## Versioning

This module is internal to ai-brain-starter. Breaking changes are fine. Skills that import from it ship in the same repo and update together.

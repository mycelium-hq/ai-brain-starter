Shared language for the public substrate codebase. Read at session start before drafting skills, hooks, install steps, or template content. This file is for substrate maintainers and contributors. End-user vault content lives downstream.

## Language

**Substrate**:
This repo. The public, MIT-licensed pattern set teaching how to build an AI-augmented Obsidian vault. NOT a hosted product. NOT a runtime. Users install via `bash <(curl ...)` then run their own.
*Avoid*: "the brain" (collides with downstream user vaults), "the platform" (we are not a platform).

**End-user vault**:
The Obsidian vault a user creates by installing the substrate. Lives at `~/Documents/<vault-name>/` or wherever they pick. NOT this repo. The substrate ships templates that get copied INTO the end-user vault at install time.
*Avoid*: "the vault" without qualifier (could mean substrate vs end-user).

**Skill**:
A unit of capability under `skills/<name>/`. Each skill has at least a `SKILL.md` describing trigger conditions and how. May include `scripts/`, reference markdown files, optional templates.
*Avoid*: "command" (collides with slash-command), "module" (too generic).

**Hook**:
A Claude Code hook script under `hooks/<name>.{py,sh}`. Wired via `~/.claude/settings.json` to PreToolUse, PostToolUse, SessionStart, etc. Substrate hooks must use ABSOLUTE paths in the wired settings (`${CLAUDE_PLUGIN_ROOT}` does not reliably expand at install time).

**Phase-00**:
The install bootstrap (`install.sh` + `BOOTSTRAP.md`). Runs once per machine. Accepts `EMAIL` + `NAME` env vars, POSTs to `/api/install/quick-mint`, writes a marker file, continues install. Ships a `[ai-brain-starter:NEEDS_EMAIL]` sentinel when no env is set so Claude Code can ask the two questions in chat.

**Marker file**:
Per-vault file written at install time. Marks the vault as substrate-installed. Future installs read the marker and skip the bootstrap.

**Closed-loop memory**:
The episodic-to-procedural memory architecture (`Meta/Learnings/`, `Meta/Promotion-Candidates/`, `Meta/Workflows/`, `Meta/Exceptions/`, `Meta/Facts/`, `Meta/Decisions/`). Episodic captures get clustered by `promote-episodic-to-procedural.py` into candidates. Human review promotes to procedural. README at `templates/CLOSED-LOOP-README.md`.
*Avoid*: "memory" alone (loaded with meaning); say "closed-loop memory" or specific subfolder.

**Episodic vs procedural**:
- **Episodic**: raw captures of an event ("error excerpt landed in `Meta/Learnings/`")
- **Procedural**: synthesized rule promoted from episodic ("hookify rule + memory entry promoted from 3 episodic captures")

**Type registry**:
The set of vault document types the substrate knows how to extract metadata from. Lives at `extractors/` + `schemas.yaml`. The `setup-vault-types` skill is the wizard that picks which types are active for a given install.

**TYPE_ALIASES**:
Map in `extractors/dispatcher.py`. Normalizes `contact -> person`, `location -> travel`, `organization -> company` so insight-engine analytics route to the correct bucket. Bug class: insight engine missing alias normalization makes contact-type files invisible.

**Extractor**:
Per-type metadata writer. Reads a markdown file's body + frontmatter, writes structured fields back to frontmatter. Each `type:` value in frontmatter has at most one extractor.

**Bare `Meta/` vs `⚙️ Meta/`**:
Two intentional folders, not a path bug. `⚙️ Meta/` = human-readable rules + decisions + sessions (vault-author-curated). `Meta/` (no emoji) = closed-loop machine memory (substrate-managed). Operational sinks under `Meta/` are gitignored as of 2026-05-08.
*Avoid*: collapsing them. Scripts that want `⚙️ Meta` must use `_meta_resolver.find_meta_dir()` which prefers the variant containing a known subfolder.

**caveman_lint.py**:
Public diff-checker for personal-data scrub. Greps for known personal tokens before any commit lands on a downstream maintainer's fork. ZERO findings required to push. Substrate maintainers wire their own token list in their fork.

**Auto-sync helper pattern**:
The pattern of pulling upstream changes at SessionStart and pushing local changes at SessionEnd. Backup-before-overwrite. Personal-data scrub gate is non-negotiable on every public push. Substrate ships the helper template at `scripts/sync-skills.template.sh`; downstream forks adapt it.

**Two clones (recommended downstream)**:
Substrate maintainers run TWO clones per machine: one for editing (`~/dev/ai-brain-starter`) and one as the end-user install (`~/.claude/skills/ai-brain-starter`, auto-updated, NEVER hand-edit the symlinked one).

## Relationships

- **Substrate** ships **Skills**, **Hooks**, **Templates**, **Extractors**, scripts
- **Phase-00** is what turns a fresh install into a working **End-user vault**
- **Closed-loop memory** is a substrate-shipped pattern; the **End-user vault** uses it
- **Type registry** + **Extractors** drive metadata extraction; **TYPE_ALIASES** routes the buckets
- **Auto-sync helper pattern** is shipped as a template; downstream forks wire their own scrub gate

## Open-core boundary

The substrate is the public teaching pattern. Anything that would constitute a hosted runtime, paid workflow content, or per-tenant audit analytics belongs in a separate downstream repo, NOT in the substrate. The substrate teaches the pattern; downstream products carry the moat. This boundary is enforced by hookify rules in maintainer forks (`warn-public-repo-create`, `warn-mit-on-content-repo`).

## Flagged ambiguities

- **"the brain"**: substrate (this repo) vs end-user vault vs any downstream runtime. Always say which
- **"memory"**: closed-loop memory architecture vs Claude Code's `~/.claude/projects/<proj>/memory/` vs in-conversation memory. Say which
- **"hook"**: Claude Code hook (substrate-shipped) vs hookify rule (end-user-configured). Say which
- **"vault"**: end-user vault vs substrate test vault (CI). Say which

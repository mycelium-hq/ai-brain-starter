# Love language context hook

When you name someone in your prompt and they have a `## [[5 Love Languages]]` section in their CRM card, the assistant gets that section as additional context before it responds. The point: the assistant matches how you express care to how the person actually receives it — not the channel you'd default to.

## What it does

`hooks/inject-love-language-context.py` runs on every `UserPromptSubmit`. If the prompt contains the name (or alias, or globally-unique first name) of any CRM person who has codified love language data, the hook injects that data as `additionalContext`.

Example: you say *"I'm calling Sam later, what should I say"*. The hook reads `👤 CRM/Sam.md`, finds the love language section, and injects it. The assistant then drafts a reply using Sam's primary channel — words of affirmation, quality time, acts of service, physical touch, or receiving gifts — instead of guessing.

The hook is silent when:
- The prompt names nobody who has a love-language section
- The vault root isn't detectable
- The CRM folder doesn't exist
- The environment variable `LOVE_LANGUAGE_HOOK_DISABLE=1` is set

## How to add love language data

Two options. The hook reads both formats.

### Option 1: H2 section (clean)

In any CRM card under `👤 CRM/` (or `CRM/`):

```markdown
## [[5 Love Languages]]
- Quality time — 35%
- Words of affirmation — 25%
- Physical touch — 20%
- Acts of service — 15%
- Receiving gifts — 5%
*Source: their quiz result on 2025-04-12*
```

### Option 2: Roam-template indented bullet (legacy)

If you imported your CRM from Roam, you might already have this structure:

```markdown
  * [[5 Love Languages]]
    * Quality time — 35%
    * Words of affirmation — 25%
    * Physical touch — 20%
    * Acts of service — 15%
    * Receiving gifts — 5%
```

Both work. Hook stops at the next heading or the next sibling top-level bullet.

## Name matching

The hook matches three forms (case- and accent-insensitive):

1. **Filename** without `.md`: `Sam Rivera.md` → matches "Sam Rivera"
2. **Frontmatter aliases**: any string in the `aliases:` list. Phone numbers (starting with `+`) and single characters are skipped.
3. **First name** ONLY if globally unique across the CRM. If two cards have the first name "Daniel", neither matches on "Daniel" alone — you'd need the full name or an alias. This prevents wrong-person false matches.

Example: a card at `👤 CRM/María José Hernández.md` with `aliases: [Majo]` matches "María José Hernández", "Maria Jose Hernandez", "Majo", and "María" — but only "María" if no other card has that first name.

## Index cache

Performance: scanning every CRM file on every prompt would slow things down. The hook caches the index at `~/.claude/.love-language-index.json`. Cache invalidates when:

- The newest `.md` mtime in the CRM folder is newer than the cache's build time
- The cache is more than 1 day old
- The CRM folder path changes (e.g., you renamed your CRM folder)

Force a rebuild by deleting the cache file: `rm ~/.claude/.love-language-index.json`.

## Vault root detection

In order:

1. `VAULT_ROOT` environment variable
2. Walk up from `cwd` looking for any `CRM/` or `👤 CRM/` folder
3. Walk up from `cwd` looking for `⚙️ Meta/Current Priorities.md`

Override the CRM folder name with `CRM_DIR_NAME=YourCrmFolderName`.

## Installation

If you ran `bootstrap.sh` or `install-hooks-user-level.py` after this hook landed, you're already set up. Verify with:

```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py --verify
```

To add to an existing install without re-running the full installer:

```bash
python3 ~/.claude/skills/ai-brain-starter/scripts/install-hooks-user-level.py
```

The installer is idempotent — it skips entries it already added.

## Cap

The hook injects at most 5 people per prompt. If you name 8 friends in one message, the first 5 (by encounter order) get their love languages surfaced. Cap is hardcoded as `MAX_INJECTED_PEOPLE` in the source file — change it if your prompts routinely name large groups.

## What the assistant should do with the data

The companion behavior — i.e., *using* the injected data in drafts instead of just acknowledging it — isn't enforced by this hook. It depends on the assistant being told to apply love language data when it's present. Add a CLAUDE.md rule or memory entry like:

> When the `[love-language-context]` block appears in the prompt, treat that data as a binding spec for HOW to express care toward the named person — gifts, replies, apologies, planning. Match the channel of care they actually receive love through, not the one you'd default to. Don't restate the data back; apply it.

Adapt the rule to your voice.

## Why this exists

The 5 Love Languages framework (Gary Chapman, 1992) maps how people express and receive love through five channels: words of affirmation, acts of service, receiving gifts, quality time, physical touch. Mismatch between giving and receiving channels is the most common silent root cause of feeling unloved in relationships. Most CRMs treat people as static identities; this hook treats people as channels of care and shapes the assistant's relational output accordingly.

## Bypass

Set `LOVE_LANGUAGE_HOOK_DISABLE=1` in the environment to suppress the hook for one session. The hook silently no-ops; no error, no message.

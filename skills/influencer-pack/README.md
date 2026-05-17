# Influencer Pack

A creator-economy vertical pack for the ai-brain-starter substrate. The pack ships typed-memory categories, platform connectors, the idea engine, retention defaults, and decision-audit patterns so a creator can install a working second-brain on day one instead of inventing the vocabulary from scratch.

## What the pack covers

- **Audience side:** segments, recurring questions, DM history with intent classification, comment streams.
- **Content side:** every Reel + Story + post + newsletter + podcast + video tagged with metrics, voice-fit, and revenue attribution. Cross-platform.
- **Business side:** brand collabs (inbound and outbound), creator revenue across sponsorship + subscription + product + course + speaking + affiliate, voice fingerprint extracted from approved content.

## Required companion skills

The pack assumes these substrate skills are also installed in `~/.claude/skills/`. Without them, the creator-facing skills cannot reach their source content:

- `ingest-youtube` (bundled in this repo at `skills/ingest-youtube/`): pulls YouTube transcripts into the typed-memory layer. The `/repurposing-engine` and `/voice-fingerprint-update` skills both read from this output.
- `humanizer` (https://github.com/adelaidasofia/humanizer): voice-fingerprint pass on AI-generated content drafts before publish.
- `graphify` (bundled in this repo at `skills/graphify/`): knowledge graph extraction across the typed-memory layer.
- `ingest-slack` (bundled in this repo at `skills/ingest-slack/`): pulls creator community channels and agency Slack workspaces into the same vault.

The pack init step verifies these are present and prompts the operator to install any that are missing before continuing.

## What gets installed

| Layer | Where it lands |
|---|---|
| 12 typed-memory categories | `schema/typed-memory-categories.md` |
| 16 platform connector specs | `connectors/<platform>.md` |
| Idea engine (the content-generation spine) | `idea-engine/<file>.md` |
| Retention defaults | `retention/defaults.md` |
| Decision-audit patterns | `decision-audit/<pattern>.md` |

See `SKILL.md` for the full init flow, the creator-facing skill bundle, and the dependency chain.

## How this pack relates to the other vertical packs

The influencer pack is one of three avatar-tuned vertical packs that share the substrate:

- `vertical-legal/` for law firms and in-house legal teams.
- `vertical-finance/` for CFO orgs, internal audit, and finance ops.
- `vertical-healthcare/` for clinical workflows.
- `influencer-pack/` (this one) for creators and personal-brand operators.

A future build will add `operator-pack/` (SMB brick-and-mortar) and `founder-pack/` (SaaS founder + small team). All packs share the same substrate primitives; what changes is the schema vocabulary, the connector list, and the retention defaults.

## License

MIT, same as the rest of ai-brain-starter. The schema and the idea-engine mechanism are open-core. Calibrated workflow content — tuned generation prompts, per-language filter corpora — and paid-product mechanics live in the runtime layer, not in this repo.

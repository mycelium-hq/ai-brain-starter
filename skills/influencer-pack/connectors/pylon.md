# Connector: Pylon / Front

Pylon and Front are shared-inbox tools for handling brand-collab outreach, agency relationships, and high-volume DM/email triage. Most creators do not need either until they pass roughly 50K engaged followers; the connector ships in the pack but is opt-in during init.

## API surface

- Pylon: https://www.usepylon.com/. API at https://docs.pylonapp.com/. OAuth 2.0 + per-account API tokens.
- Front: https://front.com/. API at https://dev.frontapp.com/. OAuth 2.0.
- Auth: tool-specific. Substrate stores credentials in operator-scoped secret store.

## Resources mapped to typed-memory categories

| Asset | Substrate category | Sync direction |
|---|---|---|
| Brand-deal inquiry threads (email or DM routed into the shared inbox) | `dm-conversation` with `subtype: brand-collab-inbound` and `priority: high` | bidirectional |
| Internal notes on a thread (assistant-to-creator collab notes) | `dm-conversation` enrichment with `internal_notes: <list>` | bidirectional |
| Templated reply variants (for common brand pitches) | `content-source` with `subtype: reply-template` | manual maintenance |
| Account routing rules (brand A to creator's manager, brand B to direct) | configuration only, not stored as typed-memory | manual maintenance |

## Operator workflow

1. Brand outreach lands in the shared inbox via email or platform DM forwarding rules.
2. Pylon or Front classifies inbound by routing rule (priority, brand category, regional contact).
3. Connector polls the inbox every 15 minutes and ingests new threads into `dm-conversation` records.
4. `/dm-closer` skill drafts a reply using a templated variant matching the brand category.
5. Reply gets sent through Pylon/Front (which routes back to the originating channel) after creator approval.

## When to install

The pack init step prompts the creator with this rule of thumb: install Pylon or Front when (a) the creator's brand-deal pipeline exceeds 5 active conversations at once OR (b) the creator has hired an assistant or manager who needs visibility into the inbox. Below those thresholds, the platform-native DMs are sufficient and the extra tool is overhead.

## Privacy + retention

- Brand-deal inquiry content is sensitive (NDAs, pre-launch material, internal pricing). Retention defaults to 1 year unless the creator extends.
- Internal notes between the creator and their team contain candid assessments of brand counterparties. Treat as confidential; never cross-reference into public-facing surfaces.

## Alternatives the pack supports interchangeably

- Help Scout
- Missive
- Hiver (Gmail-native)
- HubSpot Inbox

Same workflow: shared inbox poll, ingest as `dm-conversation` with high priority, reply via templated variants, internal-note layer for team coordination.

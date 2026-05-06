# Connector: iManage

iManage Work is the dominant document management system at AmLaw 200 firms. This connector specs the API surface, auth model, sync cadence, and write-back rules.

## API surface

- Base URL: per-firm; iManage Work cloud uses `https://cloudimanage.com/work/api/v2/` for many tenants. Self-hosted deployments use the firm's own URL.
- Documentation: https://help.imanage.com (developer portal access required; contact iManage).
- Auth: OAuth 2.0; per-firm registration required.

## Resources mapped to typed-memory categories

| iManage resource | Substrate category | Sync direction |
|---|---|---|
| Workspaces | matter | inbound only |
| Folders | hierarchy hint | inbound only |
| Documents | privilege-tagged-doc | inbound only |
| Document profiles (custom metadata) | privilege-tagged-doc frontmatter enrichment | inbound only |
| Audit logs | audit trail enrichment for `decision-audit/privilege-handling.md` | inbound only |

This connector is read-only. iManage is the firm's document source of truth.

## Auth setup

1. Firm administrator registers an OAuth application via the iManage developer portal (contact iManage support; registration is not self-service).
2. Substrate stores the client ID, client secret, and per-firm tenant URL in the firm-scoped secret store.
3. Each user authorizes once via OAuth authorization code flow; tokens refresh automatically.

## Sync cadence

- Workspaces: daily.
- Documents: every 4 hours metadata; on-demand body fetch when referenced.
- Audit logs: every 6 hours.

## Privilege handling

iManage has native privilege controls (Need-to-Know walls, Ethical Walls, attorney-client privilege protections via security profiles). The connector reads the privilege markers from iManage and stamps them onto the substrate's `privilege-tagged-doc` frontmatter.

If a document is behind a wall the user does not have access to, the connector does not pull metadata for it; the wall is preserved.

## Document profile mapping

iManage document profiles vary widely by firm. The connector reads the profile schema at install time and stages a draft mapping for the firm administrator to confirm. The default mapping covers:

```yaml
document_profile_map:
  matter_number: matter_id
  client_number: client_id
  document_type: doc_type
  author: created_by
  custodian: storage_owner
  security: privilege_basis
```

Any profile field that does not map goes into `extra_attributes` as a sub-dict.

## Rate limits

iManage API rate limits depend on the firm's licensing tier. The connector defaults to conservative cadences and lets the firm tune via config. 429s back off with exponential retry; chronic 429s pause sync and notify the administrator.

## Failure modes

- Token expiry: re-authorize per user.
- Wall access revoked: connector pauses for the affected workspace or document, notifies the administrator.
- Profile schema drift: drift logged, sync continues for unaffected profiles.
- Self-hosted iManage with custom auth: the connector falls back to per-firm-configured auth flow; this is a custom install path, not the default.

## What this connector does NOT do

- Document authoring (read-only).
- Cross-firm collaboration (Work 10's collaborative spaces are out of scope for v1).
- Records management beyond the audit log (iManage Records Management is a separate product; out of scope for v1).

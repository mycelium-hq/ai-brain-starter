# Connector: NetDocuments

NetDocuments is a leading cloud document management system for mid-market and large firms. This connector specs the API surface, auth model, sync cadence, and write-back rules.

## API surface

- Base URL: `https://vault.netvoyage.com/v1/`
- Documentation: https://www.netdocuments.com/api-documentation
- Auth: OAuth 2.0; per-firm registration required.
- Secondary surface: ndOffice REST API for desktop integration; not used by this connector (we operate against the cloud surface).

## Resources mapped to typed-memory categories

| NetDocuments resource | Substrate category | Sync direction |
|---|---|---|
| Workspaces | matter | inbound only |
| Documents | privilege-tagged-doc | inbound only |
| Profile attributes (custom fields) | privilege-tagged-doc frontmatter enrichment | inbound only |
| Folders | hierarchy hint for matter and document organization | inbound only |
| Activity log | audit trail enrichment for `decision-audit/privilege-handling.md` | inbound only |

This connector is read-only. The firm's NetDocuments tenant is the source of truth for documents; the substrate mirrors metadata and references for query, not authoring.

## Auth setup

1. Firm administrator registers an OAuth application via NetDocuments support (registration is not self-service; contact NetDocuments).
2. Substrate stores the client ID, client secret, and per-firm cabinet ID in the firm-scoped secret store.
3. Each user authorizes once via OAuth authorization code flow; tokens refresh automatically.

## Sync cadence

- Workspaces (matters): daily.
- Documents: every 4 hours metadata; on-demand body fetch when referenced.
- Activity log: every 6 hours.

NetDocuments rate limits favor lower-frequency syncs. The connector defaults to conservative cadences and lets the firm tighten if the rate limit allows.

## Privilege handling

NetDocuments has native privilege controls (Ethical Walls, Attorney-Client Privilege protections). The connector reads the privilege markers from NetDocuments and stamps them onto the substrate's `privilege-tagged-doc` frontmatter. If a document is behind an Ethical Wall the user does not have access to, the connector does not pull metadata for it; the wall remains the firewall.

The connector never bypasses NetDocuments access controls. If the firm needs to query across walls for governance purposes, that is a governance use case that runs against the NetDocuments admin API directly, not through this connector.

## Profile attribute mapping

NetDocuments profile attributes are mapped into substrate frontmatter via a per-firm config:

```yaml
profile_attribute_map:
  matter_number: matter_id
  client_id: client_id
  document_type: doc_type
  privilege_tag: privilege_basis
```

If the firm has profile attributes that do not map cleanly, they go into `extra_attributes` as a sub-dict and remain queryable but unenforced.

## Rate limits

NetDocuments API is rate-limited per cabinet. The connector backs off on 429 with exponential retry; chronic 429s pause sync and notify the administrator.

## Failure modes

- Token expiry: re-authorize per user.
- Cabinet access revoked: connector pauses for that cabinet, notifies the administrator.
- Profile attribute schema drift: drift logged, sync continues for unaffected attributes.

## What this connector does NOT do

- Document authoring (read-only).
- Trust account or matter financial data (NetDocuments does not surface this; use the practice-management connector).
- Cross-firm sharing (collaboration spaces are out of scope for v1).

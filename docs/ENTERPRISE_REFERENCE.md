# Enterprise Reference Architecture

For teams larger than 50, regulated industries, or any organization where the CTO / CISO / VP Eng owns the install decision. The personal and small-team patterns shipped in `for-teams/` cover Google Drive / Dropbox / iCloud as the collaboration substrate. Enterprise installs do not.

This doc names the architecture an enterprise install needs. It is not a one-size install. Every engagement resolves the open questions against the client's existing infrastructure. The doc exists so the architecture is concrete before procurement asks.

## Who this is for

- 50+ person organization, OR
- Regulated industry (finance, healthcare, legal, defense, government) where the consumer-cloud-sync pattern fails an InfoSec review on principle, OR
- Multi-team install where role-based access matters, OR
- Any install where data residency is a contract term

If none of those apply, use the patterns in `for-teams/`. Drive / Dropbox / iCloud are correct defaults below the enterprise line.

## What changes from the team pattern

The four problems `for-teams/why-teams-are-different.md` names (concurrent editing, permissions, meeting routing, institutional memory) all still apply. Enterprise adds five more.

| Concern | Team pattern | Enterprise pattern |
|---|---|---|
| Vault hosting | Google Drive / Dropbox folder | Client-owned git repo on their infrastructure (GitHub Enterprise, GitLab self-hosted, Azure DevOps, Bitbucket Server, on-prem) |
| Identity | Google account or Dropbox account | Client IdP via SAML 2.0 or OIDC (Okta, Auth0, Azure AD, Ping, OneLogin) |
| Sub-vault permissions | Folder-level Drive ACLs | Git submodule with branch-protection + CODEOWNERS; per-team read/write enforced by the git host |
| MCP server location | Operator's local laptop | Client VPC (private subnet, no public ingress) with mutual TLS to client agents |
| Audit logging | Git commit history | Append-only audit log per Claude session: who, what file, what tool call, what time, what client agent. Streamed to client SIEM (Splunk, Datadog, Sumo) |
| Data residency | Wherever Drive lives | Pinned region per contract (EU, US, APAC, public-sector cloud) |
| Backup + DR | Drive's history | Client-owned backup with tested restore; RPO + RTO defined in MSA |
| Update cadence | Operator pushes when ready | Client-owned change window, signed releases, rollback path |
| Vendor risk | Trust the operator | SOC 2 Type II + standard MSA + DPA + BAA where applicable |

Each of these is a contract term in an enterprise MSA. The reference architecture below is the technical answer to each.

## Reference architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Client identity provider (Okta / Auth0 / Azure AD)          │
│  SAML 2.0 / OIDC                                             │
└────────────┬─────────────────────────────────────────────────┘
             │ assertions
             ▼
┌──────────────────────────────────────────────────────────────┐
│  Client git host (GitHub Enterprise / GitLab self-hosted)    │
│  ─ Master vault: <client-org>-vault                          │
│  ─ Sub-vaults as submodules with CODEOWNERS per team         │
│  ─ Branch protection on main; PRs required                   │
│  ─ Signed commits enforced                                   │
│  ─ Webhooks to audit log on every push                       │
└────────────┬─────────────────────────────────────────────────┘
             │ clone/pull
             ▼
┌──────────────────────────────────────────────────────────────┐
│  User workstation (per team member)                          │
│  ─ Claude Code reads vault from local clone                  │
│  ─ Hooks + skills versioned in vault, no untracked drift     │
│  ─ Pre-commit hook: scrub before push                        │
└────────────┬─────────────────────────────────────────────────┘
             │ MCP tool calls
             ▼
┌──────────────────────────────────────────────────────────────┐
│  Client VPC                                                  │
│  ─ MCP servers run in private subnet                         │
│  ─ Mutual TLS between agent and MCP                          │
│  ─ All connector credentials live in client KMS / vault      │
│  ─ No public ingress; agent reaches MCP via VPN or PrivateLink│
└────────────┬─────────────────────────────────────────────────┘
             │ append-only events
             ▼
┌──────────────────────────────────────────────────────────────┐
│  Client SIEM (Splunk / Datadog / Sumo / Elastic)             │
│  ─ Per-session audit: user, file, tool, timestamp            │
│  ─ Retention per contract; client-owned                      │
└──────────────────────────────────────────────────────────────┘
```

## Per-component spec

### Vault hosting

The vault is a git repo on the client's infrastructure. Acceptable hosts:

- GitHub Enterprise (Cloud or Server)
- GitLab Self-Managed
- Azure DevOps
- Bitbucket Data Center
- On-prem git (Gitea, Gogs) with mirroring to a client-managed cold storage

Consumer git hosts (github.com Free / Personal, GitLab.com SaaS Free) are NOT acceptable for tier-5 installs. The git host must support:

- SAML / OIDC SSO
- Branch protection
- CODEOWNERS enforcement
- Required signed commits
- Webhooks to internal SIEM

### Identity

SSO via the client's IdP. No personal Google / Microsoft accounts. Required claims:

- `sub`: stable user identifier
- `email`: routable address for audit + notification
- `groups`: team membership for sub-vault access
- `mfa_authenticated`: assertion that MFA was satisfied

Map IdP groups to git CODEOWNERS via a sync job. Sub-vault read/write follows from git host enforcement, not from a separate ACL system.

### Sub-vault permissions

Each sub-vault is a git submodule pinned to a SHA. Permissions are enforced by the git host via CODEOWNERS:

```
# CODEOWNERS at master vault root
/finance-vault/         @org/finance-team
/legal-vault/           @org/legal-team
/strategy-vault/        @org/founders
/engineering-vault/     @org/eng-team
/shared-resources/      @org/all
```

Sub-vault submodules can be configured as read-only for users outside the owner group. Cross-vault references use git submodule paths, not symlinks (symlinks don't survive checkout on Windows or in CI).

### MCP server location

MCP servers (calendar, CRM, document store, internal-data) run in the client's VPC, not on operator workstations. Ingress is restricted:

- VPN / PrivateLink / Direct Connect for agent → MCP traffic
- No public DNS records for MCP endpoints
- Mutual TLS with client CA-signed certs
- Connector credentials in client KMS (AWS KMS, Azure Key Vault, GCP Secret Manager, HashiCorp Vault)

Operator workstations connect via the client's VPN to reach MCP. Operator MCP servers (those running on the operator's local machine) are NOT in the architecture for tier-5. Every MCP must be operable by the client without operator presence.

### Audit logging

Every Claude session writes an append-only audit event per tool call:

```json
{
  "session_id": "<uuid>",
  "user_sub": "<idp-sub>",
  "ts": "2026-05-15T14:22:00Z",
  "tool": "Read",
  "args": {"file_path": "/finance-vault/q1-forecast.md"},
  "outcome": "success",
  "vault_repo": "<org>/master-vault@<sha>"
}
```

Streamed to the client SIEM. Retention per contract (typically 7 years for SOX-relevant scopes, 6 years HIPAA, longer per state bar).

The audit log is the source of truth for a privilege incident, a HIPAA breach investigation, or a SOX 404 control test. It MUST be tamper-evident (append-only, signed batches).

### Data residency

Vault content stays in the contracted region. Operationally:

- Git repo region pinned (GitHub Enterprise Server in client region; GitLab Self-Managed in client VPC)
- MCP servers in client VPC, region pinned
- Audit log in client SIEM, region pinned
- Anthropic API region selection (EU residency available; US-only for some models, check current availability per contract)

If the client requires the model to NOT cross regions, a self-hosted model (Llama, Mistral, DBRX) can substitute via the same MCP architecture. Quality differences require evaluation per task; see eval-gates-in-ci pattern.

### Backup + DR

Vault git host: client's backup policy. RPO / RTO defined in MSA.

MCP servers: stateless or backed by client database; client owns backup.

Operator artifacts (skills, hooks, configs): versioned in vault repo; recovered via `git checkout`.

### Update cadence

Substrate updates (this repo, ai-brain-starter) follow a release channel. Client subscribes to one of:

- `main`: rolling, no SLA, for evaluation
- `stable`: monthly, regression-tested, recommended
- `lts`: quarterly, deeper regression suite, for regulated installs

Client-owned change window. Signed releases. Rollback to previous tag is one `git revert`.

### Vendor risk

Mycelium furnishes:

- SOC 2 Type II report (annual)
- Standard MSA + DPA
- BAA where PHI is in scope (healthcare installs)
- Sub-processor list with notification
- Penetration test summary

Operator (the consultant doing the install) is bound by NDA + role-based access; gets read access to the necessary vault subset only, no production data, no privileged credentials.

## Open questions per engagement

These are the questions every Executive Suite engagement resolves in the discovery phase. Answers drive the implementation:

- Which git host? (GitHub Enterprise Cloud, GitHub Enterprise Server, GitLab Self-Managed, Azure DevOps, Bitbucket Data Center, on-prem)
- Which IdP and which protocol? (SAML 2.0 vs OIDC; group-claim format)
- Which cloud for MCP servers? (AWS, Azure, GCP, OCI, on-prem)
- Which KMS for credentials? (AWS KMS, Azure Key Vault, GCP Secret Manager, HashiCorp Vault, CyberArk)
- Which SIEM for audit logs? (Splunk, Datadog, Sumo Logic, Elastic, Chronicle, Sentinel)
- Which compliance regimes apply? (SOC 2, HIPAA, GDPR, PCI-DSS, FedRAMP, ITAR, ISO 27001)
- Data residency: which region(s)?
- Sub-processor approval: standard list or per-vendor approval needed?
- Model selection: Anthropic-hosted, self-hosted (Llama / Mistral / DBRX), or hybrid?

## Discovery deliverables

Each Executive Suite engagement begins with a discovery session that produces:

1. Architecture diagram pinned to client's actual infrastructure (this doc's diagram instantiated)
2. Per-component vendor selection signed off by client CISO
3. RACI for build vs run (operator vs client teams)
4. SLA terms, escalation path, support matrix
5. Acceptance test plan: how the client confirms the install works against their compliance requirements
6. Rollout plan: pilot team first, then expansion

Discovery is the work that earns the install fee. Without it, the install is unreliable and the client's procurement team has no defensible artifact.

## What this doc is not

- A pre-built install. Each engagement is bespoke against client infrastructure.
- A guarantee of compatibility. Some compliance regimes (FedRAMP High, certain government cloud requirements) require additional controls not in this reference.
- A substitute for the client's own InfoSec review. The client's security team owns the final architecture decision.

## Use of this doc

For procurement: hand to the client's CTO / CISO during evaluation. Demonstrates that the architecture is concrete and that the engagement is bounded.

For the operator: walk through with the client during discovery. Each open question gets an answer before contract signature.

For substrate maintainers: this is the public reference. Specific connector implementations, audit-log code, and per-vendor connector specs live in the private runtime, not here.

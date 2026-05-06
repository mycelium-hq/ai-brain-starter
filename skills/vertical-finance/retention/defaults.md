# Retention defaults: finance vertical

Defaults map to SOX 404 evidence retention, SEC 17a-4 broker-dealer rules, IRS general business records, and the most common per-jurisdiction variations. They are starting points; verify against your audit firm and counsel before going live.

## Default table

| Category | Trigger | Default retention | Basis |
|---|---|---|---|
| sox-control | control retired | 7 years from retirement | Sarbanes-Oxley Section 802 |
| audit-evidence | linked record retention | matches linked record + 7 years floor | Sarbanes-Oxley Section 802 |
| journal-entry | posting date | 7 years from fiscal year end of posting | Sarbanes-Oxley Section 802, IRS 26 CFR 1.6001 |
| board-pack-decision | meeting date | 7 years from meeting date | Sarbanes-Oxley Section 103, exchange listing rules |
| internal-audit-finding | finding closure | 7 years from closure | Sarbanes-Oxley Section 802 |
| deal | actual close date | 7 years from close | Sarbanes-Oxley Section 802, M&A indemnity windows |
| counterparty | last linked deal close | 7 years from last close | KYC and AML retention |
| vendor | last transaction | 7 years from last transaction | IRS 26 CFR 1.6001, vendor master integrity |
| expense-policy | superseded date | 7 years from supersession | Sarbanes-Oxley Section 802 |

## SEC 17a-4 (broker-dealer)

If the firm is a broker-dealer, the SEC 17a-4 rules apply additionally:

- 6 years total retention with first 2 years easily accessible (rule revised 2022, replacing the prior 3-and-3 split).
- WORM (write-once-read-many) or audit-trail-protected storage required for electronic records.
- Designated third-party access required.

The connector marks broker-dealer evidence with a separate `broker_dealer: true` flag on the audit-evidence record so the storage layer can route to a 17a-4-compliant tier.

## J-SOX and other foreign equivalents

| Jurisdiction | Rule | Variation |
|---|---|---|
| Japan | Financial Instruments and Exchange Act (J-SOX) | 7 years; aligns with Sarbanes-Oxley defaults |
| EU member states | varies by country, generally 10 years for tax records | 10 years on tax-relevant records (longer than SOX baseline) |
| United Kingdom | Companies Act 2006 + FCA SYSC | 6 years on company records; 5 years on FCA-regulated records |
| Canada | Income Tax Act + CPA Canada Handbook | 6 years on tax records, 7 years on audit evidence |
| Singapore | MAS Notice 626 | 5 years on customer due diligence; 5 years on transaction records |

When the firm operates across jurisdictions, the longest applicable retention wins. The substrate enforces the maximum.

## Litigation and regulatory hold

A litigation hold or regulatory inquiry suspends the retention clock for the records in scope. The substrate's hold mechanism flags affected records as `hold: true` with a `hold_reason` and `hold_initiated_date`; the cleanup job that enforces retention skips held records.

## Override mechanism

A firm can override any default by writing a `retention-policy` document with `overrides_default: true`. Overrides apply only within the local install.

## What is NOT in this table

- Tax provision workpapers beyond journal-entry retention (out of scope for v1).
- Treasury cash-positioning evidence beyond audit-evidence (out of scope for v1).
- Compensation committee minutes (use board-pack-decision plus the access-control layer).
- ESG and sustainability evidence (out of scope for v1).

## Provenance

Sarbanes-Oxley Section 802 (audit work paper retention) is codified at 18 U.S.C. § 1520. SEC 17a-4 is at 17 CFR 240.17a-4. IRS general business records at 26 CFR 1.6001. J-SOX in the Financial Instruments and Exchange Act of Japan, Article 24-4-4. Verify against your audit firm and counsel before go-live; we ship defaults, the firm owns compliance.

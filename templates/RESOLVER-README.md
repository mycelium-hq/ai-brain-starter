---
type: doc
title: Bi-Temporal Resolver
last_updated: 2026-04-30
---

# Bi-Temporal Resolver

The catalect Bi-Temporal Resolver is the layer that sits on top of the typed-memory schemas and answers two questions cheaply: which rule applies to this query, and is that rule still fresh. It is composed of three components plus the rendered index file.

## The four files

1. `scripts/resolver-build.py` is the aggregator. It walks `Meta/Decisions/`, `Meta/Workflows/`, `Meta/Exceptions/`, `Meta/Facts/` inside the configured vault root, parses YAML frontmatter on every `.md` file, derives a status per row, and emits `Meta/RESOLVER.md`. CLI: `--vault-root PATH --out PATH --dry-run`.
2. `scripts/stale-rule-check.py` is the detector. It computes `(today - last_verified)` for every typed-memory entry and reports anything past `freshness_days`. Exit code 2 when stale rules surface, 0 when clean. CLI: `--vault-root PATH --threshold-days N --json`.
3. `scripts/proposed-update-drafter.py` is the downstream surfacer. Given a changed source file, it greps the vault for wikilink and path references, then prepends an idempotent proposed-update HTML comment block at the top of each downstream file. CLI: `--vault-root PATH --changed-file PATH --dry-run`.
4. `templates/RESOLVER.md.template` is the single-Read-readable reference for what the rendered index looks like. The aggregator reproduces this shape; the template documents it for humans.

## The bi-temporal data model

Every rule carries two clocks.

- Validity-time is `last_verified` (or, for decisions, `decision_date`). It answers when the rule was last confirmed to describe the world. A rule whose `last_verified` is older than `freshness_days` is `stale`, even if the file was edited yesterday.
- Transaction-time is the git commit time of the source file. It answers when the rule was written into the vault. The aggregator does not currently surface transaction-time directly because the validity clock is what governs trust.

The `under-review` status fires on a different signal: a decision whose `outcome` is filled in but whose `pattern` is still empty. That is the bridge between resolution and lesson-learned.

## How the resolver layer composes with the schemas

The schemas in `templates/schemas/` define the YAML frontmatter contract for each typed-memory primitive. The cross-type contract fields (`provenance`, `confidence`, `freshness_days`, `last_verified`, `source_count`) are the substrate the resolver reads. In particular, the resolver depends on `last_verified` and `freshness_days` for the stale check, and on `outcome`/`pattern` for the under-review signal.

The resolver does not validate frontmatter; that is the job of `vault-schema-validator.py`. The resolver assumes the validator has already failed loud on malformed YAML. The contract is: validator at write time, resolver at read time.

## Operational use

Rerun `resolver-build.py` after any rule change so `Meta/RESOLVER.md` reflects the current pipeline. Wire `stale-rule-check.py` into the session-close cascade so stale rules surface before they rot. Call `proposed-update-drafter.py` whenever a high-confidence rule changes, so every downstream consumer is forced to either confirm or correct the reference before the staleness clock starts running. The three scripts together turn a bag of typed-memory files into a routable, time-aware policy index.

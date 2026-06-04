---
status: accepted
date: 2026-06-03
---

## Context

[ADR-0002](0002-no-email-gate.md) de-gated the *install*: the bootstrap no longer refuses to run without an email, and the setup interview makes exactly one optional ask at the end (Phase 24.4).

A later hook quietly reversed that at *runtime*. `scripts/email-gate-hook.py` was wired as a `UserPromptSubmit` hook that fired on every prompt of every session. When the marker file `~/.claude/.ai-brain-starter-email-on-file` was missing, after three prompts it injected a block ending with *"DO NOT proceed with the user's original request until they have either captured (form OR in-chat) or explicitly declined,"* and walked the user through fetching and pasting a token. It re-armed every four hours, forever, in every session — including journaling.

Two failures made it worse than a one-time ask:

1. The marker was only written when a token minted successfully. A network hiccup, or a user who declined, left no marker — so the nag never stopped. Declining was never recorded anywhere.
2. The hook installer (`install-hooks-user-level.py`) only ever *adds or replaces* ai-brain-starter hooks from the template. It never *removes* one. So deleting the hook from the template would have fixed new installs only; every existing user would keep it wired in their `~/.claude/settings.json` and keep being nagged.

Real users hit this. Someone who had already given their email was asked again, repeatedly, mid-journaling, and pointed at a token.

## Decision

There is no runtime email gate. The email is asked at exactly two moments, both optional, declinable, and token-free:

1. **First-time install** — the setup interview, Phase 24.4. Unchanged.
2. **After a `git pull` that lands a new version, when there is still no email on file** — `scripts/post-update-email-ask.py`. At most once, then a 14-day cooldown, and only when the installed clone's git HEAD actually changed. The very first run only records HEAD and stays silent (first-install is Phase 24.4's job).

Supporting changes:

- `scripts/email-gate-hook.py` is deleted. `hooks.json` wires `post-update-email-ask.py` in its place.
- The installer gains an `ABS_RETIRED_FINGERPRINTS` list and a `retire_stale_hooks()` step that actively removes a retired hook from a user's `settings.json` on the next install / auto-update. This is what un-nags existing users — not just new installs.
- The marker is now a three-state "settled" flag. Its *existence* means "never ask again." Its *content* is a 32-char hex token (opted in), `recorded` (opted in but the server returned no token), or `declined` (said no). Phase 24.4 and the post-update hook both write it on every resolved outcome, so the question settles permanently.
- Consumers that need the token (the journal's first-journal telemetry) validate the hex shape before using it, so a `declined` / `recorded` marker never fires a funnel call.
- `/diagnose` is no longer an email-capture surface; a missing marker is never a finding.
- No surface ever tells a user to fetch or paste a token.

## Why

- A runtime gate that blocks the user's actual request to extract contact info is the same mistake ADR-0002 rejected at the install boundary, just moved one layer in. Capture belongs at or after the moment of value, never as a recurring toll on every session.
- "Asked over and over, even while journaling" is the single worst experience a free, local, open-source tool can give. It reads as adware. The fix is not a gentler nag schedule; it is removing the recurring ask entirely and keeping only the two honest moments.
- Recording a decline is not optional. Without it, "no" is indistinguishable from "not yet," and the only safe default a gate can pick is to ask again — which is the bug.
- A hook installer that can add but not remove is a one-way ratchet: every future hook removal silently strands on every existing machine. `retire_stale_hooks()` makes deletions propagate, which is a prerequisite for ever safely retiring *any* hook.

## Consequences

- Existing users stop being nagged on their next auto-update (the retire step runs when the installer re-runs), not just on a fresh install.
- The post-update ask reaches paste-clone users (who never ran the setup interview) the next time the repo updates, rather than after three prompts of their first session. Fewer asks, later, higher intent — consistent with ADR-0002's funnel philosophy.
- Telemetry that depended on the every-session gate to mint a marker no longer fires for users who never opt in. That was already the intended trade in ADR-0002.
- Retiring any future hook is now a two-line change (add its fingerprint + basename to `ABS_RETIRED_*`) that propagates to all installs.
- Reversal would require re-introducing a recurring runtime ask — re-litigating both this ADR and ADR-0002.

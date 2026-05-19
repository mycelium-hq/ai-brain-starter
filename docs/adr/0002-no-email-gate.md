---
status: accepted
date: 2026-05-18
---

## Context

The install used to gate on email. `bootstrap` minted an install token from a user-supplied email and `exit 3`'d (refused to install anything) when no email or token was present. That email also fed the maintainer's lead funnel: every install produced a captured address.

This made signup a hard wall in front of a free, MIT-licensed, open-source tool. A non-technical user trying it on a friend's recommendation hit "give us your email" before experiencing any value. Walling free value behind a contact-capture is the most expensive mistake a lead magnet can make: it maximizes raw capture but minimizes both conversion and lead quality. A coerced address from someone who never saw the product is a weak lead.

## Decision

The install does not gate on email.

1. `bootstrap.sh` / `bootstrap.ps1`: the signup block is non-blocking. It runs only when an email or token was already provided (the web-form path, or `EMAIL=`/`NAME=` env vars). With nothing provided it is skipped and the install proceeds in full. Token-validation failures warn and continue tokenless; they never abort the install. The `exit 3` / `NEEDS_EMAIL` sentinel paths are removed.
2. The setup interview makes exactly one email ask, at the end (Phase 24.4), after the value has been delivered. It is optional and freely declinable, and it is named up front in the README so it is never a surprise.
3. On opt-in, the signup posts with a `post_install` stage so the lead is recorded without sending a now-pointless install-link email.

## Why

- A free tool's job is to deliver value; capture belongs at or after the moment of value, never before it. The pre-install wall inverted that.
- Lead quality beats lead volume for a low-volume, high-value funnel. An optional ask at the value moment yields fewer addresses, but they belong to people who finished the install, used the tool, and chose to stay in touch.
- "Sunk cost" framing — let the user invest, then spring the ask so they feel they cannot decline — was explicitly rejected. It is manipulative and reads as one. The ask is honest and declinable, tied to a real reason to say yes (update notes plus a free workflow audit), not to pressure.
- The web-form signup path is untouched, so users who prefer to sign up first still can.

## Consequences

- Raw signup volume drops; captured leads are higher-intent. This is the intended trade.
- The token is no longer load-bearing for the install. It still mints on the web-form path and on opt-in (idempotent by email), and recap pre-population still works whenever a token exists.
- `bootstrap` telemetry that depended on a token (`/api/install/started`, `/api/install/complete`) does not fire for tokenless installs; the separate anonymous plugin-install ping still counts installs.
- A CI check (`no-remote-pipe-install`, added the same week) keeps the install instructions from regressing to `curl | bash`; this decision keeps them from regressing to a hard email gate.
- Reversal would require deciding that raw capture volume outweighs both conversion and lead quality — a different funnel philosophy than the one this records.

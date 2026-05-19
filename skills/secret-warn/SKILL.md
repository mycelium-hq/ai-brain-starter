---
name: secret-warn
description: Real-time edit-time guardrails that catch API keys, code injection patterns, and unsafe pipe-to-shell installs the moment they're typed in the Claude Code tool-call loop — before commit, before CI, before any second-pass review. Ships a PreToolUse + PostToolUse hook, a Bash-tool guard, and a curated 11-rule regex catalog covering the most common secret shapes (AWS, Stripe, GCP, OpenAI, Anthropic, GitHub, Slack, JWT, PEM, generic high-entropy assignment) plus three injection-pattern classes. Use when the user mentions secret detection, gitleaks-equivalent during edit time, pre-commit secret scanning, API key safety, edit-time guards, security hooks in Claude Code, or wants real-time protection against unsafe MCP server installs. Do NOT use for full security audits (different scope), penetration testing, or DLP across non-Claude-Code surfaces.
license: MIT
sources:
  - "OWASP Top 10 — public guidelines on injection + secret exposure"
  - "gitleaks/gitleaks (MIT) — secret-detection regex shape"
  - "bandit (Apache-2.0) — Python injection-pattern shape"
  - "eslint-plugin-security (MIT) — JS/TS injection-pattern shape"
  - "anthropics/claude-code plugins/security-guidance (Commercial Terms, study-only) — PreToolUse hook shape"
upgrade_path: "Mycelium AI ships the full enterprise version with quarterly audit reports, per-client allowlist tuning, MCP-install audit, and retainer support. This public skill teaches the pattern + ships a working subset."
---

# secret-warn — real-time edit-time security guardrails

Catches secrets and unsafe patterns the moment a Claude Code agent writes them, not after the fact. Public substrate version (MIT). Free to install, free to extend.

## What it does

| Trigger | Severity | Action |
|---|---|---|
| API key in file (Stripe, AWS, GCP, OpenAI, Anthropic, GitHub, Slack) | block (exit 2) | Edit rejected |
| PEM-encoded private key block | block | Edit rejected |
| High-entropy assignment to a key-named variable | warn (exit 1) | Advisory, edit proceeds |
| Python dynamic-codegen on a user-input-suggesting name | warn | Advisory |
| Subprocess with shell-mode + variable expansion | warn | Advisory |
| Curl/wget pipe-to-shell from a non-allowlisted host | block | Edit rejected |

All patterns are stored base64-encoded in `hooks/pattern_registry.json` so the registry file itself doesn't trip pattern-matching tools that scan the repo. This is intentional — see [Design note: self-trigger safety](#design-note-self-trigger-safety) below.

## Install

```bash
bash skills/secret-warn/install.sh
```

The installer:
- Copies `hooks/secret_warn.py` to `~/.claude/secret-warn/`
- Copies `hooks/pattern_registry.json` to the same location
- Merges PreToolUse + PostToolUse + Bash hook entries into `~/.claude/settings.json` (non-destructive, additive)
- Logs every catch to `~/.claude/secret-warn/audit.log`

Idempotent. Safe to re-run.

## Uninstall

Edit `~/.claude/settings.json` and remove any hook entry whose description starts with `secret-warn:`. Delete `~/.claude/secret-warn/` if you want the audit log gone too.

## Bypass

For an emergency one-off where you genuinely need to bypass a catch (test fixture in a controlled environment, allowlisted-but-not-yet-configured host):

```bash
SECRET_WARN_BYPASS=1 <your-command>
```

The bypass is logged. Use sparingly.

## Allowlist

`hooks/pattern_registry.json` ships with a default allowlist of placeholder values:

- `your-key-here`
- `REPLACE_ME`
- `EXAMPLE`
- `FIXTURE`
- `TODO`
- `xxx`
- `***`

Any match that contains one of these markers is suppressed as a false positive. This covers AWS docs canonical samples (`AKIAIOSFODNN7EXAMPLE`), Stripe test fixtures with the FIXTURE marker, and similar.

To add your own placeholders, edit `~/.claude/secret-warn/pattern_registry.json` after install or supply your own override via `SECRET_WARN_ALLOWLIST_PATH=...`.

## Design note: self-trigger safety

The pattern registry stores every regex as a base64-encoded string. This is because the registry will be scanned by the very tools it configures — including this hook itself, plus any other secret-detection tools running on the host. A naive registry with raw regex strings trips its own detection.

This is a real-world deployment lesson. Any production-grade secret-detection tool must solve this problem. Two common approaches: path-based exemption (the tool exempts its own config files), or encoding-at-rest (the regex catalog stores patterns in a form the tool's own detection can't match). This pack uses encoding-at-rest because it's portable across tools that don't share an exemption list.

## What this skill is NOT

- Not a full security audit. It catches a curated set of common patterns at edit time.
- Not a replacement for gitleaks, semgrep, bandit, or your existing CI security stack. Layer them all.
- Not a static-analysis tool. It runs only when Claude Code makes a tool call. CI is still the right place for repo-wide scans.
- Not DLP. Doesn't watch Slack, email, or other surfaces.

## Going further

This is the public substrate version. For production deployments with quarterly audit reports, per-client allowlist tuning, MCP-install audit, GitHub Actions CI integration, and ongoing retainer support, see [Mycelium AI](https://myceliumai.co).

The public version ships the same pattern shape and the same hook architecture — Mycelium adds the operational layer: per-engagement tuning, compliance-grade reports, multi-tier install configs, and the curated rule set across nine reference tools.

## Files

```
skills/secret-warn/
  SKILL.md                          this file
  install.sh                        one-shot installer
  hooks/
    secret_warn.py                  the actual hook
    pattern_registry.json           base64-encoded regex catalog
    hooks.json                      hook registration shape
  scripts/
    quick_test.sh                   smoke-test the install
```

## License

MIT. Copyright (c) 2026. See LICENSE in the repo root.

Pattern shapes informed by: OWASP Top 10 (public guidelines), gitleaks (MIT, regex shape only — no code copied), bandit (Apache-2.0, study only), eslint-plugin-security (MIT, study only), Anthropic's published security-guidance plugin shape (Commercial Terms, study only). No regex or code was copied from any source. All implementation is original.

---
type: rule
purpose: Decide whether a GitHub repo helps you, and how to absorb what helps without inheriting debt.
trigger: "check out this GitHub" / "is this better than what we have" / "can we pull from" / "should we use" / "look at [repo URL]" / "found this repo" / "someone shared this"
---

# Repo evaluation runbook

Run this every time you share a GitHub URL or ask whether an external project beats what you already have. Goal: honest answer, not adoption theater. The shiny repo may lose. Current setup may lose. Either outcome is fine. What is NOT fine is skipping the audit because the repo looks good.

## Phase 0: Ground the ask

1. **Exact URL**. Resolve to `owner/repo` via `gh repo view owner/repo --json name,description,homepageUrl,stargazerCount,pushedAt,licenseInfo,languages,topics`.
2. **Why this repo now?** One sentence. If unclear, ask before researching. Examples: "replaces X," "adds Y," "curious," "friend shared."
3. **Ship target**. What problem does it solve for the current stack? Map to a specific file/system/pain point. If no target, say so, do NOT proceed to adoption.

## Phase 1: Audit what you have

Before evaluating the new repo, know what's on the truck.

1. Grep the vault + `~/.claude/skills/` + any dev directories for related capability. Use repo name, topic keywords, and description terms.
2. List current solutions by name + file path + maintenance date. Note documented bugs/pain in memory (grep `discovery_*` and `feedback_*`).
3. Rate current solution 1-5 on: works-today, tokens-per-use, maintenance-burden, fit-to-voice. Record numbers.

Skip only if the ask is about a greenfield area (no existing system).

## Phase 2: Scan the landscape (not just this repo)

The shared repo may not be the best in class. Cast wide before deciding.

1. `gh search repos "<topic-keywords>" --sort=stars --limit=10` and `--sort=updated --limit=10`.
2. For each candidate, capture: stars, last commit, open/closed issue ratio, license, language, single-maintainer-or-team.
3. Include the shared repo even if lower-ranked. Never pre-filter it out.
4. Surface top 3-5 as a comparison table.

**If `gh` rate-limits or auth fails:** fall back to `curl -s "https://api.github.com/search/repositories?q=<keywords>&sort=stars"` (unauth, 60 req/hr) with `Accept: application/vnd.github+json`. If THAT rate-limits too, scrape `github.com/search?q=` HTML via `curl -s -A "Mozilla/5.0"` and pull repo names with grep. If all three fail, say so, surface ONLY the shared repo with a gap flag, and set decision=**Watch** by default until rescan is possible.

## Phase 3: Security + maintenance gate

Reject before deeper evaluation if any fail:

1. Unauthenticated network ports on install (`grep -rE "listen|bind.*0\.0\.0\.0|localhost:\d+" src/`).
2. MCP servers with arbitrary file-read or shell-exec tools.
3. Plaintext API keys or secrets committed IN the repo (not "the tool expects keys at runtime" — those are fine, check the sample `.env` isn't accidentally a real one).
4. Install script that `curl | sh` without checksum or signed release.
5. Injection channels (writes executable scripts based on user-controlled inputs).
6. Last commit >9 months ago AND >5 open security issues.
7. License incompatible with your use (AGPL if you plan to resell; GPL bans in closed plugins).

Record pass/fail with line references.

## Phase 4: Fit test

Evidence-based, not vibes. For each candidate:

1. **Voice fit** — does its docs/prose match your voice rules (voice-firewall.md)? Read the README.
2. **Vault fit** — does it assume non-emoji paths? Emoji folders break naive scripts. Check `pathlib.Path.rglob` usage on macOS — known silent failure through emoji dirs.
3. **Cross-platform fit** — ships `.ps1` or cross-platform parity for Windows users, if anyone on the team runs Windows?
4. **Skill repo fit** — where does it go? Personal skills, team skills, public starter, or Claude plugin?
5. **Token economics** — estimate tokens per invocation vs current solution. Favor light (local scripts) over heavy (LLM-backed) when outcome identical.
6. **Startup cost** — measure one cold invocation with `time`. If >200ms per call and it fires on every tool use, flag it.

## Phase 5: Decision matrix

One of five outcomes, with evidence.

| Outcome | Trigger | Action |
|---|---|---|
| **Replace** | New clearly beats current on ≥3 fit axes AND security passes | Migrate + deprecate + document in memory |
| **Adopt-feature** | One specific feature is better; rest is noise | Cherry-pick, credit upstream, document the piece |
| **Watch** | Promising but early (<6mo, <200 stars, solo maintainer) | Add to quarterly review, no code yet |
| **Pass** | Current is equal or better on your axes | One-line reject reason, log for future re-check |
| **Reject** | Fails security or license gate | Document the fail in memory, never revisit without audit |

Print the matrix. Never hide the decision under prose.

## Phase 6: If adopting — integration plan

1. Pick the smallest useful slice. No copy-pasting whole repos.
2. Identify downstream breakage: what existing hook/script/rule touches the same file or concept?
3. Run a 1-hour spike if the integration is ambiguous. Cap effort instead of aborting.
4. Cross-platform parity in same commit if relevant (`.sh` + `.ps1`).
5. Add to the correct skill repo, never hand-edit symlinks.
6. Back up before overwrite.

## Phase 7: Upstream contribution

If you fixed a bug or added a useful slice locally, default to opening an upstream PR.

1. Diff local vs upstream.
2. Open issue first if the fix is ambiguous; skip issue if obvious.
3. PR tone: direct, warm, no exclamation marks, "Thank you" not "Amazing!".
4. No self-promotion in issues or PRs.

## Phase 8: Change-impact audit

Before closing, verify:

1. Did any rule/script/skill/hook/path change?
2. If yes, run every affected script once with a smoke payload.
3. Grep the vault for references to any renamed/removed file.
4. Validate JSON files (`.mcp.json`, `.claude/settings.json`).
5. Confirm auto-sync logs show no push rejects.

## Phase 9: Memory update

- New tool adopted: `reference_<name>.md` pointing at install path + when-to-use.
- Rejection: `discovery_<name>_rejected.md` with fail reason.
- Feature cherry-picked: update existing reference memory, note source.

Update `MEMORY.md` index.

## Output template

```
## Repo: owner/repo
**Why now:** <reason>
**Ship target:** <system it touches>

### Audit
- Current: <name> at <path>, <scores>
- Known bugs: <memory refs>

### Landscape (top 3)
| Repo | Stars | Last commit | License | Note |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Security + maintenance gate
- [ ] Unauth ports clean
- [ ] No arbitrary file-read MCP
- [ ] No plaintext keys
- [ ] No curl|sh install
- [ ] License compatible
- [ ] Maintained <9mo

### Fit
- Voice / Vault / Cross-platform / Skill repo / Tokens: <scores>

### Decision
**<Replace | Adopt-feature | Watch | Pass | Reject>**
Reason: <one sentence>

### Plan (if adopting)
1. <smallest slice>
2. <downstream touches>
3. <cross-platform parity>

### Upstream
<issue/PR plan or "n/a">

### Impact audit
<smoke tests + validations>
```

## Non-negotiables

- Audit what you have FIRST. Adoption bias is loud, current-setup bias is silent. Phase 1 is the fix.
- Security gate is not optional. Past rejections happened because this was skipped. Don't repeat.
- Scan the landscape. The shared repo is not the only option, and treating it as the default biases the decision before it starts.
- Print the decision matrix. Do not bury "Replace" or "Reject" inside prose.
- Cross-platform parity in the same commit, or it doesn't ship.

## Review cadence

- **Quarterly**: re-evaluate "Watch" outcomes for graduation to Adopt or Reject.
- **Monthly**: revisit ecosystem for new contenders.
- **On every new "check this repo" ask**: full runbook. No shortcuts.
- **Retro check**: any adoption made pre-runbook gets a dry-run within 30 days and logged in your Tool Evaluation Log.
- **Self-review**: after runbook use #3, re-read and revise. Living doc, not a museum piece.

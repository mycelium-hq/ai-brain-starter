#!/usr/bin/env python3
"""SessionStart hook: surface Dependabot PR backlog across personal GitHub repos.

Panel codification 2026-05-19 (Howard Marks dissent on the Camilo-aftermath
Dependabot triage): "13 PRs queued, plus 4 stash branches in the same repo,
plus an open security alert — the bottleneck isn't 'which PR to ship,' it's
that the queue exists at all." The structural fix is a weekly clear-the-queue
ritual; this watchdog is the surface that makes the backlog visible at
SessionStart so it can't sit unnoticed.

Threshold: any repo with > 5 open Dependabot PRs OR any Dependabot PR > 14
days old. Silent below threshold. Tiered MANUAL_ONLY repos (per
gh-harden-repos.sh Layer 5: `private-memory-repo`, `private-concierge-repo`)
get a special call-out since they don't auto-merge.

Bypass: SURFACE_DEPENDABOT_BACKLOG_BYPASS=1
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys

OWNER = "github-username"
MANUAL_ONLY_REPOS = {"private-memory-repo", "private-concierge-repo"}
PR_COUNT_THRESHOLD = 5
PR_AGE_DAYS_THRESHOLD = 14
TIMEOUT_S = 30


def fetch_repos() -> list[str]:
    """Return list of repo names under OWNER. Limited to 100 (well above
    the user's current ~40)."""
    try:
        out = subprocess.run(
            ["gh", "repo", "list", OWNER, "--limit", "100", "--json", "name"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return []
    return [r["name"] for r in data if isinstance(r, dict) and "name" in r]


def fetch_dependabot_prs(repo: str) -> list[dict]:
    """Open Dependabot PRs for one repo. Returns list of {number, createdAt}."""
    try:
        out = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                f"{OWNER}/{repo}",
                "--state",
                "open",
                "--author",
                "app/dependabot",
                "--limit",
                "50",
                "--json",
                "number,createdAt",
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return []


def age_days(iso_ts: str) -> int:
    """Days between createdAt (ISO 8601 with Z) and now."""
    try:
        ts = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - ts).days


def main() -> int:
    if os.environ.get("SURFACE_DEPENDABOT_BACKLOG_BYPASS"):
        return 0

    # SessionStart payload arrives on stdin (JSON). Drain so we don't block.
    try:
        sys.stdin.read()
    except Exception:
        pass

    repos = fetch_repos()
    if not repos:
        return 0

    findings: list[tuple[str, int, int, bool]] = []
    # tuple: (repo, total_prs, oldest_age_days, is_manual_only)
    for repo in repos:
        prs = fetch_dependabot_prs(repo)
        if not prs:
            continue
        count = len(prs)
        oldest = max((age_days(p.get("createdAt", "")) for p in prs), default=0)
        flagged = count > PR_COUNT_THRESHOLD or oldest > PR_AGE_DAYS_THRESHOLD
        if flagged:
            findings.append((repo, count, oldest, repo in MANUAL_ONLY_REPOS))

    if not findings:
        return 0

    lines = ["⚠️  Dependabot backlog: clear-the-queue ritual is overdue", ""]
    for repo, count, oldest, manual in sorted(
        findings, key=lambda t: (-t[1], -t[2])
    ):
        tier = " [MANUAL_ONLY]" if manual else ""
        lines.append(
            f"  - {OWNER}/{repo}{tier}: {count} open PR(s), oldest {oldest}d"
        )
        lines.append(
            f"    review: gh pr list --repo {OWNER}/{repo} --author app/dependabot"
        )
    lines.extend(
        [
            "",
            f"Thresholds: > {PR_COUNT_THRESHOLD} open PRs OR any PR > {PR_AGE_DAYS_THRESHOLD}d old.",
            "Codified 2026-05-19 (Howard Marks panel dissent on Camilo-aftermath",
            "triage). The queue itself is the smell, not any individual merge.",
            "Bypass: SURFACE_DEPENDABOT_BACKLOG_BYPASS=1",
        ]
    )

    print(json.dumps({"systemMessage": "\n".join(lines)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

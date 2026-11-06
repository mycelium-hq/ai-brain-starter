#!/usr/bin/env python3
"""SessionStart hook: show open critical and high Dependabot alerts.

Why alerts and not pull requests: Dependabot cannot always open a fix PR. A
crate pinned to a git revision, or a dependency held back by another package's
version range, gets an alert and no PR (or a PR that closes itself). A
PR-count watchdog reads that as "nothing to do" while critical alerts sit open
for days. Alerts are the signal; PRs are only one way of acting on it.

Who is checked: the signed-in `gh` user's own repositories (one GraphQL call)
and every organization they belong to (one REST call per org, the org-wide
alerts endpoint). Nothing is hardcoded, so this works for any install.

What it says:
  * open critical/high alerts exist  -> one systemMessage naming the repos
  * zero alerts and every call worked -> silent
  * a call failed (not signed in, no access to an org's alerts, timeout,
    bad JSON)                         -> says "skipped" for what it could not
                                         read. Never silent, so a failure can
                                         never look like a clean pass.
  * `gh` is not installed             -> silent. There is no GitHub tooling to
                                         check with, and nagging every session
                                         of a user who does not use GitHub is
                                         noise, not a finding.

Cost: many sessions start at once on a busy machine, so a successful result is
cached for CACHE_MINUTES and reused. A skipped result is not cached, so the
next session tries again.

Bypass: SURFACE_DEPENDABOT_BACKLOG_BYPASS=1
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CALL_TIMEOUT_S = 10
TOTAL_DEADLINE_S = 25
MAX_ORGS = 30
CACHE_MINUTES = 30
MAX_REPOS_SHOWN = 8
SEVERITIES = ("critical", "high")

USER_REPOS_QUERY = (
    "query{viewer{repositories(first:100,ownerAffiliations:OWNER,isArchived:false)"
    "{nodes{nameWithOwner vulnerabilityAlerts(first:100,states:OPEN)"
    "{nodes{securityVulnerability{severity}}}}}}}"
)


def cache_path() -> Path:
    override = os.environ.get("DEPENDABOT_ALERTS_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "state" / "dependabot-alerts-cache.json"


class GhError(Exception):
    """gh could not answer: a reason a person can read."""


def gh_json(args: list[str], deadline: float):
    remaining = deadline - time.monotonic()
    if remaining <= 1:
        raise GhError("ran out of time")
    try:
        out = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(CALL_TIMEOUT_S, remaining),
        )
    except subprocess.TimeoutExpired:
        raise GhError("timed out")
    except OSError as exc:
        raise GhError(f"could not run gh ({exc.__class__.__name__})")
    if out.returncode != 0:
        first = (out.stderr or out.stdout or "").strip().splitlines()
        raise GhError(first[0][:120] if first else f"gh exited {out.returncode}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        raise GhError("gh returned something that is not JSON")


def user_repo_counts(deadline: float) -> dict[str, dict[str, int]]:
    data = gh_json(["api", "graphql", "-f", f"query={USER_REPOS_QUERY}"], deadline)
    try:
        nodes = data["data"]["viewer"]["repositories"]["nodes"]
    except (KeyError, TypeError):
        raise GhError("unexpected answer from GitHub")
    counts: dict[str, dict[str, int]] = {}
    for repo in nodes or []:
        for alert in ((repo or {}).get("vulnerabilityAlerts") or {}).get("nodes") or []:
            sev = str(((alert or {}).get("securityVulnerability") or {}).get("severity", "")).lower()
            if sev in SEVERITIES:
                bucket = counts.setdefault(repo["nameWithOwner"], {s: 0 for s in SEVERITIES})
                bucket[sev] += 1
    return counts


def org_counts(org: str, deadline: float) -> dict[str, dict[str, int]]:
    data = gh_json(
        [
            "api",
            f"orgs/{org}/dependabot/alerts?state=open&severity=critical,high&per_page=100",
        ],
        deadline,
    )
    if not isinstance(data, list):
        raise GhError("unexpected answer from GitHub")
    counts: dict[str, dict[str, int]] = {}
    for alert in data:
        if not isinstance(alert, dict):
            continue
        sev = str((alert.get("security_advisory") or {}).get("severity", "")).lower()
        repo = (alert.get("repository") or {}).get("full_name")
        if repo and sev in SEVERITIES:
            bucket = counts.setdefault(repo, {s: 0 for s in SEVERITIES})
            bucket[sev] += 1
    return counts


def build_message(counts: dict[str, dict[str, int]], skipped: list[str]) -> str:
    lines: list[str] = []
    if counts:
        total = {s: sum(c[s] for c in counts.values()) for s in SEVERITIES}
        lines.append(
            f"Open Dependabot alerts: {total['critical']} critical, {total['high']} high."
        )
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1]["critical"], -kv[1]["high"], kv[0]))
        for repo, c in ranked[:MAX_REPOS_SHOWN]:
            lines.append(
                f"  - {repo}: {c['critical']} critical, {c['high']} high. "
                f"https://github.com/{repo}/security/dependabot"
            )
        if len(ranked) > MAX_REPOS_SHOWN:
            lines.append(f"  - and {len(ranked) - MAX_REPOS_SHOWN} more repos")
        lines.append("Fix the ones that reach your app, or dismiss them with a written reason.")
    if skipped:
        lines.append("Dependabot alert check skipped for: " + "; ".join(skipped) + ".")
    return "\n".join(lines)


def read_cache() -> str | None:
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
        if time.time() - float(data["at"]) < CACHE_MINUTES * 60:
            return str(data["message"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def write_cache(message: str) -> None:
    path = cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"at": time.time(), "message": message}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def check() -> str:
    """The message to show ("" = nothing to say)."""
    deadline = time.monotonic() + TOTAL_DEADLINE_S
    counts: dict[str, dict[str, int]] = {}
    skipped: list[str] = []

    try:
        login = gh_json(["api", "user"], deadline).get("login")
    except (GhError, AttributeError) as exc:
        return build_message({}, [f"GitHub sign-in ({exc or 'no login'}). Run: gh auth status"])

    def org_list() -> list[str]:
        data = gh_json(["api", "user/orgs?per_page=100"], deadline)
        if not isinstance(data, list):
            raise GhError("unexpected answer from GitHub")
        return [o.get("login") for o in data if isinstance(o, dict) and o.get("login")]

    # The repo-wide GraphQL call is the slow one (~4s), so everything after the
    # sign-in check runs side by side.
    with ThreadPoolExecutor(max_workers=8) as pool:
        own = pool.submit(user_repo_counts, deadline)
        org_names = pool.submit(org_list)
        try:
            orgs = org_names.result()
        except GhError as exc:
            orgs = []
            skipped.append(f"organization list ({exc})")
        if len(orgs) > MAX_ORGS:
            skipped.append(f"{len(orgs) - MAX_ORGS} organizations past the first {MAX_ORGS}")
        per_org = [(org, pool.submit(org_counts, org, deadline)) for org in orgs[:MAX_ORGS]]
        try:
            counts.update(own.result())
        except GhError as exc:
            skipped.append(f"{login}'s repos ({exc})")
        for org, fut in per_org:
            try:
                found = fut.result()
            except GhError as exc:
                skipped.append(f"{org} ({exc})")
                continue
            counts.update(found)
            if sum(sum(c.values()) for c in found.values()) >= 100:
                skipped.append(f"{org} alerts past the first 100")

    message = build_message(counts, skipped)
    if not skipped:
        write_cache(message)
    return message


def main() -> int:
    if os.environ.get("SURFACE_DEPENDABOT_BACKLOG_BYPASS"):
        return 0
    try:
        sys.stdin.read()
    except Exception:
        pass
    if shutil.which("gh") is None:
        return 0
    message = read_cache()
    if message is None:
        message = check()
    if message:
        print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
  * more alerts or repos than one page
    holds                             -> the totals say "at least" and name
                                         what was not read.
  * `gh` is not installed             -> silent. There is no GitHub tooling to
                                         check with, and nagging every session
                                         of a user who does not use GitHub is
                                         noise, not a finding. If a gh sign-in
                                         exists but gh is not on this session's
                                         PATH (or a usual install path), it
                                         says "skipped".
  * anything unexpected crashes       -> "skipped", never silence.

Cost: many sessions start at once on a busy machine, so a clean result is
cached for CACHE_MINUTES and reused. A result that skipped or cut something off
is cached for SKIP_CACHE_MINUTES, so it retries soon without re-querying on
every session.

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
# A result that skipped something is kept for less time, so the check retries
# soon, but a member without access to an org is not re-queried every session.
SKIP_CACHE_MINUTES = 10
MAX_REPOS_SHOWN = 8
SEVERITIES = ("critical", "high")

USER_REPOS_QUERY = (
    "query{viewer{repositories(first:100,ownerAffiliations:OWNER,isArchived:false)"
    "{totalCount nodes{nameWithOwner vulnerabilityAlerts(first:100,states:OPEN)"
    "{totalCount nodes{securityVulnerability{severity}}}}}}}"
)
# Where gh usually lives when a GUI-launched session's PATH does not include it.
GH_FALLBACK_PATHS = ("/opt/homebrew/bin/gh", "/usr/local/bin/gh", "/usr/bin/gh")
GH = "gh"


def find_gh() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    fallbacks = os.environ.get("DEPENDABOT_GH_FALLBACK_PATHS")  # tests only
    for candidate in fallbacks.split(os.pathsep) if fallbacks is not None else GH_FALLBACK_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def gh_configured() -> bool:
    """A gh sign-in exists on this machine, even if the binary was not found."""
    base = os.environ.get("GH_CONFIG_DIR") or os.path.join(Path.home(), ".config", "gh")
    return os.path.isfile(os.path.join(base, "hosts.yml"))


def cache_path() -> Path:
    override = os.environ.get("DEPENDABOT_ALERTS_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "state" / "dependabot-alerts-cache.json"


class GhError(Exception):
    """gh could not answer: a reason a person can read."""


def reason(exc: BaseException) -> str:
    """Why one source could not be read, in words a person can use."""
    if isinstance(exc, GhError):
        return str(exc)
    return f"unexpected answer ({exc.__class__.__name__})"


def gh_json(args: list[str], deadline: float):
    remaining = deadline - time.monotonic()
    if remaining <= 1:
        raise GhError("ran out of time")
    try:
        out = subprocess.run(
            [GH, *args],
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


def user_repo_counts(deadline: float) -> tuple[dict[str, dict[str, int]], list[str]]:
    """Counts for the user's own repos, plus what could not be read in one page."""
    data = gh_json(["api", "graphql", "-f", f"query={USER_REPOS_QUERY}"], deadline)
    try:
        repos = data["data"]["viewer"]["repositories"]
        nodes = repos["nodes"]
    except (KeyError, TypeError):
        raise GhError("unexpected answer from GitHub")
    partial: list[str] = []
    if int(repos.get("totalCount") or 0) > len(nodes or []):
        partial.append(f"your repos past the first {len(nodes or [])}")
    counts: dict[str, dict[str, int]] = {}
    for repo in nodes or []:
        alerts = (repo or {}).get("vulnerabilityAlerts") or {}
        if int(alerts.get("totalCount") or 0) > len(alerts.get("nodes") or []):
            partial.append(f"{repo['nameWithOwner']} alerts past the first 100")
        for alert in alerts.get("nodes") or []:
            sev = str(((alert or {}).get("securityVulnerability") or {}).get("severity", "")).lower()
            if sev in SEVERITIES:
                bucket = counts.setdefault(repo["nameWithOwner"], {s: 0 for s in SEVERITIES})
                bucket[sev] += 1
    return counts, partial


def org_counts(org: str, deadline: float) -> tuple[dict[str, dict[str, int]], bool]:
    """Counts for one org, and whether the single page may have cut some off."""
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
    return counts, len(data) >= 100


def build_message(
    counts: dict[str, dict[str, int]], skipped: list[str], partial: list[str] | None = None
) -> str:
    lines: list[str] = []
    partial = partial or []
    if counts:
        total = {s: sum(c[s] for c in counts.values()) for s in SEVERITIES}
        at_least = "at least " if partial else ""
        lines.append(
            f"Open Dependabot alerts: {at_least}{total['critical']} critical, "
            f"{at_least}{total['high']} high."
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
    if partial:
        lines.append("Some alerts were not read (only one page per source): " + "; ".join(partial) + ".")
    if skipped:
        lines.append("Dependabot alert check skipped for: " + "; ".join(skipped) + ".")
    return "\n".join(lines)


def read_cache() -> str | None:
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
        age = time.time() - float(data["at"])
        if 0 <= age < float(data["minutes"]) * 60:
            return str(data["message"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def write_cache(message: str, minutes: int) -> None:
    path = cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps({"at": time.time(), "minutes": minutes, "message": message}),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except OSError:
        pass


def check() -> str:
    """The message to show ("" = nothing to say)."""
    deadline = time.monotonic() + TOTAL_DEADLINE_S
    counts: dict[str, dict[str, int]] = {}
    skipped: list[str] = []
    partial: list[str] = []

    try:
        login = gh_json(["api", "user"], deadline).get("login")
    except (GhError, AttributeError) as exc:
        message = build_message({}, [f"GitHub sign-in ({exc or 'no login'}). Run: gh auth status"])
        write_cache(message, SKIP_CACHE_MINUTES)
        return message

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
        except Exception as exc:  # one bad source must not drop the others
            orgs = []
            skipped.append(f"organization list ({reason(exc)})")
        if len(orgs) > MAX_ORGS:
            skipped.append(f"{len(orgs) - MAX_ORGS} organizations past the first {MAX_ORGS}")
        per_org = [(org, pool.submit(org_counts, org, deadline)) for org in orgs[:MAX_ORGS]]
        try:
            own_counts, own_partial = own.result()
            counts.update(own_counts)
            partial.extend(own_partial)
        except Exception as exc:
            skipped.append(f"{login}'s repos ({reason(exc)})")
        for org, fut in per_org:
            try:
                found, truncated = fut.result()
            except Exception as exc:
                skipped.append(f"{org} ({reason(exc)})")
                continue
            counts.update(found)
            if truncated:
                partial.append(f"{org} alerts past the first 100")

    message = build_message(counts, skipped, partial)
    write_cache(message, SKIP_CACHE_MINUTES if (skipped or partial) else CACHE_MINUTES)
    return message


def main() -> int:
    if os.environ.get("SURFACE_DEPENDABOT_BACKLOG_BYPASS"):
        return 0
    try:
        sys.stdin.read()
    except Exception:
        pass
    global GH
    try:
        gh = find_gh()
        if gh is None:
            # No gh anywhere: this person does not use GitHub tooling, so there
            # is nothing to check. If a gh sign-in exists, gh is installed
            # somewhere this session cannot see, and silence would read as clean.
            if gh_configured():
                message = "Dependabot alert check skipped for: gh is signed in but not on this session's PATH."
            else:
                return 0
        else:
            GH = gh
            message = read_cache()
            if message is None:
                message = check()
    except Exception as exc:  # never let a crash look like zero alerts
        message = f"Dependabot alert check skipped for: unexpected error ({exc.__class__.__name__})."
        write_cache(message, SKIP_CACHE_MINUTES)
    if message:
        print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

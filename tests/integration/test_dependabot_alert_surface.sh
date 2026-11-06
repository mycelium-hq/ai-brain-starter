#!/usr/bin/env bash
# Test: surface-dependabot-backlog.py, the SessionStart surface for open
# critical/high Dependabot alerts (tickets#5988).
#
# What a person depends on:
#   1. open critical/high alerts are shown, naming the repo (org repos AND the
#      user's own repos)
#   2. zero alerts is silent
#   3. anything that could not be read says "skipped" or "not read", never
#      silent: an org without access, not signed in, a crash, more than one
#      page, gh installed but off PATH
#   4. no gh at all (no GitHub tooling) is silent
#   5. a cached result is reused, and a skipped one is never cached as clean
#
# A fake `gh` on PATH answers from FAKE_GH_MODE. No network. Exit 0 = pass.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/surface-dependabot-backlog.py"
PY="$(command -v "${PYTHON:-python3}")"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/nobin" "$TMP/ghconf"

cat > "$TMP/bin/gh" <<'FAKE'
#!/usr/bin/env python3
import json, os, sys
mode = os.environ.get("FAKE_GH_MODE", "")
args = sys.argv[1:]
def out(obj):
    print(json.dumps(obj)); sys.exit(0)
def fail(msg):
    sys.stderr.write(msg + "\n"); sys.exit(1)
if args[:2] == ["api", "user"]:
    if mode == "signed-out":
        fail("gh: To get started with GitHub CLI, please run:  gh auth login")
    out({"login": "example-user"})
if args[:2] == ["api", "graphql"]:
    if mode == "crash":
        out({"data": {"viewer": {"repositories": {"totalCount": "many", "nodes": 7}}}})
    alerts = []
    total_alerts = 0
    if mode in ("own-alerts", "truncated"):
        alerts = [{"securityVulnerability": {"severity": "CRITICAL"}},
                  {"securityVulnerability": {"severity": "MODERATE"}}]
        total_alerts = 150 if mode == "truncated" else 2
    out({"data": {"viewer": {"repositories": {
        "totalCount": 1,
        "nodes": [{"nameWithOwner": "example-user/notes",
                   "vulnerabilityAlerts": {"totalCount": total_alerts, "nodes": alerts}}]}}}})
if args[:2] == ["api", "user/orgs?per_page=100"]:
    out([{"login": "example-org"}, {"login": "locked-org"}] if mode == "forbidden" else [{"login": "example-org"}])
if len(args) >= 2 and args[1].startswith("orgs/locked-org/"):
    fail("gh: Resource not accessible by integration (HTTP 403)")
if len(args) >= 2 and args[1].startswith("orgs/example-org/dependabot/alerts"):
    if mode in ("clean", "own-alerts", "truncated"):
        out([])
    adv = lambda s: {"security_advisory": {"severity": s},
                     "repository": {"full_name": "example-org/app"}}
    out([adv("critical"), adv("critical"), adv("high")])
fail("fake gh: unexpected call " + " ".join(args))
FAKE
chmod +x "$TMP/bin/gh"

fails=0
run() { # <mode> [cache-name]
  FAKE_GH_MODE="$1" PATH="$TMP/bin:$PATH" DEPENDABOT_ALERTS_CACHE="$TMP/cache-${2:-$1}.json" \
    DEPENDABOT_GH_FALLBACK_PATHS="" "$PY" "$HOOK" < /dev/null
}
run_without_gh() { # <gh-config-dir>
  PATH="$TMP/nobin" GH_CONFIG_DIR="$1" DEPENDABOT_GH_FALLBACK_PATHS="" \
    DEPENDABOT_ALERTS_CACHE="$TMP/cache-nogh.json" "$PY" "$HOOK" < /dev/null
}
expect_has() { # <name> <output> <needle>
  if printf '%s' "$2" | grep -qF -- "$3"; then echo "PASS: $1"
  else echo "FAIL: $1 -- missing '$3' in: $2"; fails=$((fails + 1)); fi
}
expect_empty() { # <name> <output>
  if [ -z "$2" ]; then echo "PASS: $1"
  else echo "FAIL: $1 -- printed: $2"; fails=$((fails + 1)); fi
}

out="$(run alerts)"
expect_has "org alerts shown with counts" "$out" "example-org/app: 2 critical, 1 high"
expect_has "alerts link to the repo's alert page" "$out" "github.com/example-org/app/security/dependabot"

out="$(run own-alerts)"
expect_has "the user's own repo alerts are shown" "$out" "example-user/notes: 1 critical, 0 high"

expect_empty "zero alerts is silent" "$(run clean)"

out="$(run forbidden)"
expect_has "unreadable org says skipped" "$out" "skipped for: locked-org"
expect_has "readable org still shown beside a skip" "$out" "example-org/app: 2 critical"

expect_has "signed out says skipped" "$(run signed-out)" "skipped for: GitHub sign-in"

out="$(run truncated)"
expect_has "more than one page says not read" "$out" "example-user/notes alerts past the first 100"
expect_has "a truncated total is a lower bound" "$out" "at least 1 critical"

expect_has "a crash says skipped, not silence" "$(run crash)" "skipped for: unexpected error"

expect_empty "no gh and no gh sign-in is silent" "$(run_without_gh "$TMP/ghconf")"
touch "$TMP/ghconf/hosts.yml"
expect_has "gh signed in but off PATH says skipped" "$(run_without_gh "$TMP/ghconf")" "not on this session's PATH"

# Cache: a clean result is reused (the fake now answers with alerts, the cache
# still says clean), and a skipped result is cached as skipped, never as clean.
run clean shared >/dev/null
expect_empty "a cached clean result is reused" "$(run alerts shared)"
run forbidden skipcache >/dev/null
expect_has "a cached skip stays a skip" "$(run clean skipcache)" "skipped for: locked-org"

if [ "$fails" -ne 0 ]; then echo "$fails failure(s)"; exit 1; fi
echo "ALL PASS"

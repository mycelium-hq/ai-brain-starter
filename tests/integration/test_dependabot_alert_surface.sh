#!/usr/bin/env bash
# Test: surface-dependabot-backlog.py, the SessionStart surface for open
# critical/high Dependabot alerts (tickets#5988).
#
# What a person depends on:
#   1. open critical/high alerts are shown, naming the repo
#   2. zero alerts is silent
#   3. an org whose alerts cannot be read says "skipped", never silent
#   4. not signed in to gh says "skipped", never silent
#
# A fake `gh` on PATH answers from FAKE_GH_MODE. No network. Exit 0 = pass.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/surface-dependabot-backlog.py"
PY="${PYTHON:-python3}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

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
    out({"data": {"viewer": {"repositories": {"nodes": [
        {"nameWithOwner": "example-user/notes", "vulnerabilityAlerts": {"nodes": []}}]}}}})
if args[:2] == ["api", "user/orgs?per_page=100"]:
    out([{"login": "example-org"}, {"login": "locked-org"}] if mode == "forbidden" else [{"login": "example-org"}])
if len(args) >= 2 and args[1].startswith("orgs/locked-org/"):
    fail("gh: Resource not accessible by integration (HTTP 403)")
if len(args) >= 2 and args[1].startswith("orgs/example-org/dependabot/alerts"):
    if mode == "clean":
        out([])
    adv = lambda s: {"security_advisory": {"severity": s},
                     "repository": {"full_name": "example-org/app"}}
    out([adv("critical"), adv("critical"), adv("high")])
fail("fake gh: unexpected call " + " ".join(args))
FAKE
chmod +x "$TMP/bin/gh"

fails=0
run() { # <mode>
  FAKE_GH_MODE="$1" PATH="$TMP/bin:$PATH" DEPENDABOT_ALERTS_CACHE="$TMP/cache-$1.json" \
    "$PY" "$HOOK" < /dev/null
}
expect_has() { # <name> <output> <needle>
  if printf '%s' "$2" | grep -qF -- "$3"; then echo "PASS: $1"
  else echo "FAIL: $1 -- missing '$3' in: $2"; fails=$((fails + 1)); fi
}

out="$(run alerts)"
expect_has "alerts shown with counts" "$out" "example-org/app: 2 critical, 1 high"
expect_has "alerts link to the repo's alert page" "$out" "github.com/example-org/app/security/dependabot"

out="$(run clean)"
if [ -z "$out" ]; then echo "PASS: zero alerts is silent"
else echo "FAIL: zero alerts printed: $out"; fails=$((fails + 1)); fi

out="$(run forbidden)"
expect_has "unreadable org says skipped" "$out" "skipped for: locked-org"
expect_has "readable org still shown beside a skip" "$out" "example-org/app: 2 critical"

out="$(run signed-out)"
expect_has "signed out says skipped" "$out" "skipped for: GitHub sign-in"

# Negative control: a failed run must not be cached as a pass.
if [ -e "$TMP/cache-forbidden.json" ] || [ -e "$TMP/cache-signed-out.json" ]; then
  echo "FAIL: a skipped result was cached"; fails=$((fails + 1))
else echo "PASS: skipped results are not cached"; fi

if [ "$fails" -ne 0 ]; then echo "$fails failure(s)"; exit 1; fi
echo "ALL PASS"

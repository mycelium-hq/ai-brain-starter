#!/usr/bin/env bash
# Quick smoke test for secret-warn. Runs a clean case, a placeholder case,
# and a real-shape case to verify install. Does NOT touch real settings.json.

set -euo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../hooks" && pwd)/secret_warn.py"
TMP="$(mktemp -d -t secret-warn-test-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

export SECRET_WARN_ROOT="$TMP"
export SECRET_WARN_ALLOWLIST_PATH="/nonexistent"

run() {
  local label="$1" b64="$2" expected="$3"
  local payload
  payload=$(python3 -c "
import base64, json, sys
content = base64.b64decode(sys.argv[1]).decode()
print(json.dumps({'tool_name': 'Write', 'tool_input': {'file_path': '/tmp/x', 'content': content}}))
" "$b64")
  set +e
  echo "$payload" | python3 "$HOOK" > /dev/null 2>&1
  local actual=$?
  set -e
  if [ "$actual" = "$expected" ]; then
    echo "  PASS  $label  (exit=$actual)"
  else
    echo "  FAIL  $label  (expected=$expected, got=$actual)"
    return 1
  fi
}

echo "secret-warn smoke test"
echo ""

# Clean content
run "clean python" "cHJpbnQoImhlbGxvIikK" 0

# Placeholder allowlist (AWS docs canonical EXAMPLE)
run "placeholder allowlist" "QVdTX0FDQ0VTU19LRVlfSUQ9QUtJQUlPU0ZPRE5ON0VYQU1QTEU=" 0

# Real-shape fabricated AWS key (no marker)
run "real-shape aws key" "QVdTX0FDQ0VTU19LRVlfSUQ9QUtJQVFSU1RVVldYWVowMTIzNDU=" 2

echo ""
echo "secret-warn quick test passed"

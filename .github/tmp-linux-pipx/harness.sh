#!/usr/bin/env bash
# TEMPORARY, not for merge (tickets#6171): run bootstrap.sh's REAL pipx section
# on a desktop-like Linux (python3 without pip or venv, no pipx) and check that
# pipx lands and can install a real tool. CODE=before runs the pre-fix
# bootstrap.sh (30218f9) and expects the bug: no working pipx.
set -euo pipefail
CODE="$1"; WHO="$2"
SRC="$GITHUB_WORKSPACE/bootstrap.sh"
if [ "$CODE" = before ]; then
  curl -fsSL "https://raw.githubusercontent.com/mycelium-hq/ai-brain-starter/30218f9af34229c08d76204fdd090f2b6cacb8cd/bootstrap.sh" -o /tmp/before.sh
  SRC=/tmp/before.sh
fi

# Same extraction as tests/integration/test_bootstrap_userspace_fallback.sh.
extract_fn() {
  local name="$1" src="$2" oneliner
  oneliner="$(grep -E "^${name}\(\)[ ]*\{.*\}[ ]*\$" "$src" 2>/dev/null | head -1 || true)"
  if [ -n "$oneliner" ]; then printf '%s\n' "$oneliner"
  else awk "/^${name}\\(\\)[ ]*\\{/,/^}\$/" "$src"
  fi
}

H=/tmp/harness-run.sh
{
  echo 'set -euo pipefail'
  echo 'FAILED=(); LANG_CODE=en; DRY_RUN=0'
  echo 'BOOTSTRAP_LOG="$HOME/.bootstrap.log"; : > "$BOOTSTRAP_LOG"'
  echo 'SKILL_DIR="$HOME/.claude/skills/ai-brain-starter"'
  echo 'GAPS_FILE="$HOME/.claude/.ai-brain-starter-install-gaps.jsonl"'
  echo 't() { [ "$LANG_CODE" = es ] && echo "$2" || echo "$1"; }'
  grep -E '^(NODE_FALLBACK_VERSION|PY_FALLBACK_VERSION|PY_FALLBACK_TAG)=' "$SRC"
  for fn in log ok warn err soft_err hdr dry is_mac is_linux have have_sudo quiet_retry note_gap \
            pick_python user_space_platform add_user_path_entry fetch_tarball \
            fetch_python_userspace install_python_userspace install_pipx_userspace; do
    extract_fn "$fn" "$SRC"
  done
  echo 'PY=python3; pick_python || true'
  echo 'echo "PY=$PY"'
  awk '/^if ! have pipx && \[\[ \$DRY_RUN -eq 1 \]\]; then$/,/^have pipx && ok/' "$SRC"
  awk '/^if ! have graphify && \[\[ \$DRY_RUN -eq 1 \]\]; then$/,/^have graphify && ok/' "$SRC"
  awk '/^if ! have fastmcp && \[\[ \$DRY_RUN -eq 1 \]\]; then$/,/^have fastmcp && ok/' "$SRC"
  echo 'echo "GAPS:"; cat "$GAPS_FILE" 2>/dev/null || echo "(none)"'
} > "$H"
chmod 755 "$H"
grep -q 'Installing pipx' "$H" || { echo "harness: pipx section not extracted"; exit 1; }
echo "harness lines: $(grep -c '' "$H")"

run_as() {
  if [ "$WHO" = root ]; then bash -c "$1"; else su - student -c "$1"; fi
}

echo "== run the pipx section as $WHO ($CODE)"
run_as "bash $H" || echo "(section exited non-zero; the verdict below is what landed)"

echo "== verdict"
CHECK='export PATH="$HOME/.local/bin:$PATH"; hash -r; command -v pipx && command -v graphify && command -v fastmcp && pipx --version && fastmcp --version'
if [ "$CODE" = before ]; then
  if run_as "$CHECK"; then echo "UNEXPECTED: pre-fix code produced a working pipx"; exit 1; fi
  echo "REPRODUCED: the pre-fix code leaves no working pipx"
else
  run_as "$CHECK"
  run_as 'echo "python3 is $(command -v python3)"; test "$(command -v python3)" = /usr/bin/python3' \
    || { echo "FAIL: the distro python3 is no longer the user's python3"; exit 1; }
  echo "OK: pipx, graphify and fastmcp landed; python3 is still the distro's"
fi

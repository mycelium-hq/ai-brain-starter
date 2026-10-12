#!/usr/bin/env bash
# test_discoverability_partition.sh — the MYC-766 ours/theirs gap partition for
# hooks/verify-discoverability-on-close.py.
#
# Bug class (MYC-766, 2026-06-10): the hook used to hard-block the close on ANY
# gap the discoverability-verifier returned — including gaps on artifacts a
# SIBLING session (or a pre-existing commit) authored. In a many-concurrent-
# session workflow that false-blocked unrelated sessions' closes, and the only
# escape was the bypass env var, which then masked the closing session's OWN
# real gaps (over-strict-verification-teaches-bypass).
#
# The fix partitions the verifier's gaps by whether THIS session's transcript
# authored the artifact (Write/Edit/MultiEdit/NotebookEdit file_path, or a
# write-style Bash command naming it):
#   - OURS   (session-authored) -> HARD-BLOCK (exit 2)
#   - THEIRS (sibling/pre-existing) -> SOFT note on stderr, NEVER block (exit 0)
#
# Self-contained: a stub verifier (injected via DISCOVERABILITY_VERIFIER_PATH)
# emits a controlled gap list read from $STUB_GAPS_FILE, so the test is
# independent of any live vault state. Exit 0 = pass.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/verify-discoverability-on-close.py"
if [ ! -f "$HOOK" ]; then
  echo "ERROR: $HOOK not found" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
VAULT="$TMP/vault"; mkdir -p "$VAULT"

# Stub verifier: ignores its args, prints whatever JSON sits in $STUB_GAPS_FILE.
STUB="$TMP/stub-verifier.py"
cat > "$STUB" <<'PY'
import os, sys
p = os.environ.get("STUB_GAPS_FILE", "")
sys.stdout.write(open(p).read() if p and os.path.exists(p) else '{"gaps": []}')
PY

# A gap whose artifact resolves (repo=vault) to $VAULT/<rel>.
gap_json() {  # rel suggestion
  python3 -c "import json,sys; print(json.dumps({'artifact':{'repo':'vault','path':sys.argv[1],'kind':'skill','commit':'abc','name':sys.argv[1]},'suggestion':sys.argv[2]}))" "$1" "$2"
}

# run_hook CLOSING_TEXT WROTE_ABS GAPS_JSON_ARRAY [EXTRA_ENV=v ...] -> exit code
run_hook() {
  local text="$1" wrote="$2" gaps="$3"; shift 3
  local tpath="$TMP/transcript.jsonl"
  # Transcript: an assistant text message (the closing claim) + a tool_use that
  # WROTE $wrote (empty string = wrote nothing this session), + a Bash tool_use
  # running $TRANSCRIPT_BASH when that is exported (unset = no Bash call).
  python3 -c "
import json,os,sys
text, wrote = sys.argv[1], sys.argv[2]
recs = [{'type':'assistant','message':{'content':[{'type':'text','text':text}]}}]
if wrote:
    recs.append({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Write','input':{'file_path':wrote}}]}})
bash = os.environ.get('TRANSCRIPT_BASH', '')
if bash:
    recs.append({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash','input':{'command':bash}}]}})
with open(sys.argv[3],'w',encoding='utf-8') as f:
    for r in recs: f.write(json.dumps(r)+'\n')
" "$text" "$wrote" "$tpath"
  printf '{"gaps": %s}' "$gaps" > "$TMP/gaps.json"
  local stdin_json
  # cwd = the test vault: the hook resolves its vault from the payload's cwd first,
  # so without it a vault-shaped directory the test is RUN from outranks VAULT_ROOT.
  stdin_json=$(python3 -c "import json,sys; print(json.dumps({'transcript_path':sys.argv[1],'cwd':sys.argv[2]}))" "$tpath" "$VAULT")
  set +e
  printf '%s' "$stdin_json" | env -u DISCOVERABILITY_VERIFIER_BYPASS \
    VAULT_ROOT="$VAULT" \
    DISCOVERABILITY_VERIFIER_PATH="$STUB" \
    STUB_GAPS_FILE="$TMP/gaps.json" "$@" \
    python3 "$HOOK" >"$TMP/out.txt" 2>"$TMP/err.txt"
  local rc=$?
  set -e
  echo "$rc"
}

assert_rc() {  # label expected actual
  if [ "$2" != "$3" ]; then
    echo "FAIL: $1 — expected exit $2, got $3" >&2
    echo "  --- stderr ---" >&2; sed 's/^/  /' "$TMP/err.txt" >&2
    exit 1
  fi
  echo "PASS: $1 (exit $3)"
}

CLOSING="Closing the session now and writing the artifact."
OURS_ABS="$VAULT/skills/ours.md"
GAP_OURS="$(gap_json "skills/ours.md" "ln -sfn <dir> ~/.claude/skills/ours")"
GAP_THEIRS="$(gap_json "skills/sibling.md" "sibling session must wire this")"

# 1. Sibling-only gap (NOT authored this session) -> soft note, never block.
#    This is the MYC-766 discriminator: the pre-fix hook hard-blocked here.
rc=$(run_hook "$CLOSING" "" "[$GAP_THEIRS]")
assert_rc "sibling-only gap soft-notes, never blocks" 0 "$rc"
if ! grep -qi "non-blocking" "$TMP/err.txt"; then
  echo "FAIL: expected a non-blocking soft note for the sibling gap" >&2
  sed 's/^/  /' "$TMP/err.txt" >&2; exit 1
fi
echo "PASS: sibling gap surfaces a soft note"

# 2. Session-authored gap -> HARD-BLOCK.
rc=$(run_hook "$CLOSING" "$OURS_ABS" "[$GAP_OURS]")
assert_rc "session-authored gap hard-blocks" 2 "$rc"
if ! grep -q "BLOCKED by verify-discoverability-on-close" "$TMP/err.txt"; then
  echo "FAIL: expected the BLOCKED diagnostic for the session-authored gap" >&2
  sed 's/^/  /' "$TMP/err.txt" >&2; exit 1
fi
echo "PASS: block emits the diagnostic message"

# 3. Both gaps -> blocks (ours present), still soft-notes theirs.
rc=$(run_hook "$CLOSING" "$OURS_ABS" "[$GAP_OURS,$GAP_THEIRS]")
assert_rc "ours+theirs blocks on ours" 2 "$rc"

# 4. No gaps -> allows close.
rc=$(run_hook "$CLOSING" "" "[]")
assert_rc "no gaps allows close" 0 "$rc"

# 5. Not a closing claim -> skipped (verifier never consulted).
rc=$(run_hook "Here is the analysis you asked for." "$OURS_ABS" "[$GAP_OURS]")
assert_rc "non-closing claim skipped" 0 "$rc"

# 6. Bypass -> skipped even with an authored gap.
rc=$(run_hook "$CLOSING" "$OURS_ABS" "[$GAP_OURS]" DISCOVERABILITY_VERIFIER_BYPASS=1)
assert_rc "DISCOVERABILITY_VERIFIER_BYPASS skips" 0 "$rc"

# 7. A heredoc that only READS a sibling's artifact is not authorship. Bare `<<`
#    used to count as a write hint, so this session was hard-blocked on someone
#    else's gap for having looked at it (READ-CLASSIFIED-AS-AUTHORSHIP).
export TRANSCRIPT_BASH="python3 - <<'PY'
print(open('$VAULT/skills/sibling.md').read())
PY"
rc=$(run_hook "$CLOSING" "" "[$GAP_THEIRS]")
unset TRANSCRIPT_BASH
assert_rc "read-only heredoc naming a sibling artifact soft-notes, never blocks" 0 "$rc"

# 8. A heredoc'd script that WRITES our artifact is still authorship.
export TRANSCRIPT_BASH="python3 - <<'PY'
from pathlib import Path
Path('$VAULT/skills/ours.md').write_text('x')
PY"
rc=$(run_hook "$CLOSING" "" "[$GAP_OURS]")
unset TRANSCRIPT_BASH
assert_rc "heredoc that writes our artifact still hard-blocks" 2 "$rc"

# 9-15. The command is read structurally: redirect and tee targets on its own
#    lines, file-writing calls in a script body, a patch it applies. Each of these
#    was mis-read by one regex over the whole text (MYC-5434 review): the first four
#    are writes a no-`<<` regex lost, the last three are reads it still took for writes.
bash_case() {  # label expected-rc gap command
  export TRANSCRIPT_BASH="$4"
  local rc
  rc=$(run_hook "$CLOSING" "" "[$3]")
  unset TRANSCRIPT_BASH
  assert_rc "$1" "$2" "$rc"
}
bash_case "cat >ours.md <<EOF (no space before the target) blocks" 2 "$GAP_OURS" "cat >$VAULT/skills/ours.md <<'EOF'
x
EOF"
bash_case "cat <<EOF >\"ours.md\" (redirect after the heredoc opener) blocks" 2 "$GAP_OURS" "cat <<'EOF' >\"$VAULT/skills/ours.md\"
x
EOF"
bash_case "a heredoc'd json.dump(..., open(ours, 'w')) blocks" 2 "$GAP_OURS" "python3 - <<'PY'
import json
json.dump({}, open('$VAULT/skills/ours.md', 'w'))
PY"
bash_case "git apply <<EOF of a patch to ours.md blocks" 2 "$GAP_OURS" "git apply <<'EOF'
--- a/skills/ours.md
+++ b/skills/ours.md
@@ -1 +1 @@
-a
+b
EOF"
bash_case "a heredoc that sys.stdout.write()s a sibling's file soft-notes" 0 "$GAP_THEIRS" "python3 - <<'PY'
import sys
sys.stdout.write(open('$VAULT/skills/sibling.md').read())
PY"
bash_case "a '>' comparison inside a heredoc body is not a redirect" 0 "$GAP_THEIRS" "python3 - <<'PY'
for l in open('$VAULT/skills/sibling.md'):
    if len(l) > 80:
        print(l)
PY"
bash_case "a heredoc reading a sibling, output redirected elsewhere, soft-notes" 0 "$GAP_THEIRS" "python3 - <<'PY' > /tmp/scan.txt
print(open('$VAULT/skills/sibling.md').read())
PY"

# 16-21. Second review round. Writes the bare-<< regex caught and a target-only
#    reader would lose (a variable target, a heredoc fed to a shell, a target passed
#    as an argument, a path built with os.path.join), and reads that only print to
#    stderr or only dry-run a patch.
bash_case "cat > \"\$F\" with F set to our artifact blocks" 2 "$GAP_OURS" "F=\"$VAULT/skills/ours.md\"; cat > \"\$F\" <<'EOF'
x
EOF"
bash_case "a heredoc fed to bash that redirects into our artifact blocks" 2 "$GAP_OURS" "bash <<'EOF'
echo x > $VAULT/skills/ours.md
EOF"
bash_case "a heredoc'd script writing to the path in its argv blocks" 2 "$GAP_OURS" "python3 - \"$VAULT/skills/ours.md\" <<'PY'
import sys
open(sys.argv[1], 'w').write('x')
PY"
bash_case "a heredoc'd yaml.safe_dump into open(os.path.join(...), 'w') blocks" 2 "$GAP_OURS" "python3 - <<'PY'
import os, yaml
with open(os.path.join('$VAULT/skills', 'ours.md'), 'w') as f:
    yaml.safe_dump({}, f)
PY"
bash_case "a heredoc that prints a sibling's file to stderr soft-notes" 0 "$GAP_THEIRS" "python3 - <<'PY'
import sys
print(open('$VAULT/skills/sibling.md').read(), file=sys.stderr)
PY"
bash_case "git apply --check (a dry run) of a sibling's patch soft-notes" 0 "$GAP_THEIRS" "git apply --check <<'EOF'
--- a/skills/sibling.md
+++ b/skills/sibling.md
@@ -1 +1 @@
-a
+b
EOF"

# 22-25. Third review round. A variable target counts only through a value the
#    same command assigns; open(..., 'w') is never matched past the call's end; a
#    heredoc is shell commands only when its opener runs a shell or pipes into one.
bash_case "a read of a sibling logged to \"\$OUT\" (set elsewhere) soft-notes" 0 "$GAP_THEIRS" "cat $VAULT/skills/sibling.md > \"\$OUT\""
bash_case "print(open(sibling).read().replace('a', 'x')) soft-notes" 0 "$GAP_THEIRS" "python3 -c \"print(open('$VAULT/skills/sibling.md').read().replace('a', 'x'))\""
bash_case "a heredoc into bash-tips.md that only SHOWS a redirect soft-notes" 0 "$GAP_THEIRS" "cat > $VAULT/notes/bash-tips.md <<'EOF'
Read $VAULT/skills/sibling.md first, then: echo \"\$x\" > \"\$out\"
EOF"
bash_case "cat <<EOF | bash that redirects into our artifact blocks" 2 "$GAP_OURS" "cat <<'EOF' | bash
echo x > $VAULT/skills/ours.md
EOF"

echo
echo "All assertions passed. verify-discoverability-on-close partition (MYC-766) holds."

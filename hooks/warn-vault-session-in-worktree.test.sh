#!/usr/bin/env bash
# Negative-control test for warn-vault-session-in-worktree.py (MYC-575 tripwire).
#
# A guard earns trust only by failing on the thing it catches. This proves:
#   Channel A (payload cwd inside the worktree — terminal launch + tool-time payloads):
#     1. FIRES   on a VAULT worktree cwd (main root has .obsidian/)        <- the catch
#     2. SILENT  on a plain vault cwd (no worktree segment)
#     3. SILENT  on a CODE-repo worktree cwd (no .obsidian/ at main root)  <- no over-fire
#     4. SILENT  under VAULT_WORKTREE_WARN_BYPASS=1
#   Channel B (Desktop mode — cwd is the MAIN ROOT, worktree id in transcript_path):
#     5. FIRES   cwd=vault main root + transcript_path carries the marker  <- the catch
#     6. SILENT  cwd=code-repo main root + marker present (no .obsidian/)   <- no over-fire
#     7. SILENT  plain vault session (transcript_path has NO marker)
#   Channel C (process-cwd ground truth — payload-INDEPENDENT, ZERO subprocess; the
#   2026-06-17 melt repro). MYC-1176: os.getcwd() carries the worktree segment, so a
#   string match replaces the per-call `git rev-parse` that taxed every plain session:
#     8. FIRES   payload cwd=MAIN + NO marker, but the PROCESS runs in a real git
#                worktree -> os.getcwd() reveals the truth A+B both missed   <- THE FIX
#     9. SILENT  same shape but a CODE repo (no .obsidian/ at main root) <- no over-fire
#    10. SILENT  process in the real MAIN vault checkout (not a worktree) <- no over-fire
#   Dedup (warn once per worktree slug, not every turn/tool):
#    11. FIRES   first call for a slug
#    12. SILENT  second call for the same slug (sentinel written)
#   MYC-1176 (zero-cost on the plain path + PreToolUse skip + instrumentation):
#    13. SILENT  PreToolUse skips Channel C (Channel A is authoritative at tool time)
#    14. FIRES   PreToolUse: Channel A still catches a worktree PAYLOAD cwd
#    15. ZERO git subprocess on a plain (99%) session  <- THE FIX (git-shim trace)
#    16. worktree catch still FIRES via string-match with ZERO git
#    17. guard-fire telemetry emitted on the WARN path (log_fire)
#    18. ZERO telemetry on the silent/plain path (off the hot path)
#
# Exit 0 = all pass. Non-zero = regression (or git fixture setup failed — loud, never skipped).
set -u
HOOK="$(cd "$(dirname "$0")" && pwd)/warn-vault-session-in-worktree.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0

# --- path fixtures (Channels A/B: no real git needed) ---
mkdir -p "$TMP/vaultmain/.obsidian" "$TMP/vaultmain/.claude/worktrees/slug"
mkdir -p "$TMP/devrepo/.claude/worktrees/slug"   # NO .obsidian -> code repo
mkdir -p "$TMP/neutral"                          # non-git proc-cwd so Channel C stays quiet
WT_TRANSCRIPT="/Users/x/.claude/projects/-Users-x-vaultmain--claude-worktrees-slug/abc.jsonl"
PLAIN_TRANSCRIPT="/Users/x/.claude/projects/-Users-x-vaultmain/abc.jsonl"

# --- real git fixtures (Channel C: needs an actual linked worktree) ---
mkgitwt() { # $1=root  ($2=obsidian => create .obsidian)  -> creates <root>/.claude/worktrees/wt
  git init -q "$1"
  [ "${2:-}" = "obsidian" ] && mkdir -p "$1/.obsidian"
  git -C "$1" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  git -C "$1" worktree add -q "$1/.claude/worktrees/wt" HEAD 2>/dev/null
  [ -e "$1/.claude/worktrees/wt/.git" ] || { echo "SETUP-FAIL: could not create git worktree at $1/.claude/worktrees/wt"; fail=1; }
}
mkgitwt "$TMP/gitvault" obsidian
mkgitwt "$TMP/gitcode"  ""

run() { # $1=payload-cwd  $2=extra-env  $3=transcript(opt)  $4=process-cwd(opt, default neutral)
  local payload pcwd
  pcwd="${4:-$TMP/neutral}"
  if [ -n "${3:-}" ]; then payload="{\"cwd\":\"$1\",\"transcript_path\":\"$3\"}"
  else payload="{\"cwd\":\"$1\"}"; fi
  # NODEDUP on so detection asserts are not silenced by a prior fire of the same slug;
  # STATE_DIR isolated from the real ~/tmp sentinels. cd sets os.getcwd() for Channel C.
  ( cd "$pcwd" && printf '%s' "$payload" \
      | env VAULT_WORKTREE_WARN_NODEDUP=1 VAULT_WORKTREE_WARN_STATE_DIR="$TMP/state" $2 python3 "$HOOK" )
}

assert_fires() { # $1=label $2=stdout
  if printf '%s' "$2" | grep -q "vault-worktree"; then echo "PASS: $1 (fired)"
  else echo "FAIL: $1 — expected FIRE, got: $2"; fail=1; fi
}
assert_silent() { # $1=label $2=stdout
  if printf '%s' "$2" | grep -q "suppressOutput"; then echo "PASS: $1 (silent)"
  else echo "FAIL: $1 — expected SILENT, got: $2"; fail=1; fi
}

# --- Channel A: payload cwd inside the worktree ---
assert_fires  "A1 vault worktree cwd"      "$(run "$TMP/vaultmain/.claude/worktrees/slug" "")"
assert_silent "A2 plain vault cwd"         "$(run "$TMP/vaultmain" "")"
assert_silent "A3 code-repo worktree cwd"  "$(run "$TMP/devrepo/.claude/worktrees/slug" "")"
assert_silent "A4 bypass set"              "$(run "$TMP/vaultmain/.claude/worktrees/slug" "VAULT_WORKTREE_WARN_BYPASS=1")"

# --- Channel B: Desktop mode, cwd=MAIN ROOT, worktree id only in transcript_path ---
assert_fires  "B5 vault main + marker"     "$(run "$TMP/vaultmain" "" "$WT_TRANSCRIPT")"
assert_silent "B6 code main + marker"      "$(run "$TMP/devrepo" "" "$WT_TRANSCRIPT")"
assert_silent "B7 plain vault, no marker"  "$(run "$TMP/vaultmain" "" "$PLAIN_TRANSCRIPT")"

# --- Channel C: git ground truth (the 2026-06-17 melt repro: payload=main, NO marker) ---
assert_fires  "C8 vault: payload=main+no-marker, PROCESS in real git worktree" \
              "$(run "$TMP/gitvault" "" "" "$TMP/gitvault/.claude/worktrees/wt")"
assert_silent "C9 code-repo: same shape, no .obsidian"   \
              "$(run "$TMP/gitcode" "" "" "$TMP/gitcode/.claude/worktrees/wt")"
assert_silent "C10 process in real MAIN vault (not a worktree)" \
              "$(run "$TMP/gitvault" "" "" "$TMP/gitvault")"

# --- Dedup: warn once per slug (NODEDUP off, isolated state dir) ---
DSTATE="$TMP/dedupstate"; mkdir -p "$DSTATE"
ded() { ( cd "$TMP/gitvault/.claude/worktrees/wt" && printf '{"cwd":"%s"}' "$TMP/gitvault" \
            | env VAULT_WORKTREE_WARN_STATE_DIR="$DSTATE" python3 "$HOOK" ); }
assert_fires  "D11 dedup first call"   "$(ded)"
assert_silent "D12 dedup second call"  "$(ded)"

# --- MYC-1176: Channel C skipped at PreToolUse (Channel A is authoritative there) ---
# 13. proc in a worktree + payload=main + event=PreToolUse -> C must NOT run -> silent.
#     (A real PreToolUse payload carries the worktree cwd, so A catches; this artificial
#      proc=worktree/payload=main shape is still covered at UPS + SessionStart.)
out_pre_skip="$( cd "$TMP/gitvault/.claude/worktrees/wt" && printf '{"cwd":"%s","hook_event_name":"PreToolUse"}' "$TMP/gitvault" \
    | env VAULT_WORKTREE_WARN_NODEDUP=1 VAULT_WORKTREE_WARN_STATE_DIR="$TMP/state" python3 "$HOOK" )"
assert_silent "C13 PreToolUse skips Channel C (proc=worktree, payload=main)" "$out_pre_skip"
# 14. Channel A still catches a worktree PAYLOAD cwd at PreToolUse (the real tool-time shape).
out_pre_a="$( printf '{"cwd":"%s","hook_event_name":"PreToolUse"}' "$TMP/vaultmain/.claude/worktrees/slug" \
    | env VAULT_WORKTREE_WARN_NODEDUP=1 VAULT_WORKTREE_WARN_STATE_DIR="$TMP/state" python3 "$HOOK" )"
assert_fires  "C14 PreToolUse: Channel A still catches worktree payload cwd" "$out_pre_a"

# --- MYC-1176 THE FIX: ZERO git subprocess on the hot path (git-shim trace) ---
# A `git` shim records every invocation; the plain 99% session must spawn NONE.
REALGIT="$(command -v git)"
mkdir -p "$TMP/shim"
cat > "$TMP/shim/git" <<EOF
#!/usr/bin/env bash
echo "git \$*" >> "$TMP/gitcalls"
exec "$REALGIT" "\$@"
EOF
chmod +x "$TMP/shim/git"
mkdir -p "$TMP/plainvault/.obsidian"   # a plain vault: .obsidian present, NO .claude/worktrees
: > "$TMP/gitcalls"
# 15. plain session (payload=main, proc=main, no marker, UPS) -> SILENT + ZERO git.
out_plain="$( cd "$TMP/plainvault" && printf '{"cwd":"%s","hook_event_name":"UserPromptSubmit"}' "$TMP/plainvault" \
    | env PATH="$TMP/shim:$PATH" VAULT_WORKTREE_WARN_NODEDUP=1 VAULT_WORKTREE_WARN_STATE_DIR="$TMP/state" python3 "$HOOK" )"
assert_silent "C15 plain vault session (the 99% case)" "$out_plain"
if [ -s "$TMP/gitcalls" ]; then echo "FAIL: C15 plain session spawned git ($(tr '\n' ';' <"$TMP/gitcalls"))"; fail=1
else echo "PASS: C15 plain session spawned ZERO git subprocess (MYC-1176)"; fi
# 16. the worktree CATCH path is ALSO git-free now (Channel C is a pure string match).
: > "$TMP/gitcalls"
out_wtcatch="$( cd "$TMP/gitvault/.claude/worktrees/wt" && printf '{"cwd":"%s","hook_event_name":"UserPromptSubmit"}' "$TMP/gitvault" \
    | env PATH="$TMP/shim:$PATH" VAULT_WORKTREE_WARN_NODEDUP=1 VAULT_WORKTREE_WARN_STATE_DIR="$TMP/state" python3 "$HOOK" )"
assert_fires "C16 worktree catch still FIRES with zero git" "$out_wtcatch"
if [ -s "$TMP/gitcalls" ]; then echo "FAIL: C16 worktree-catch path spawned git ($(tr '\n' ';' <"$TMP/gitcalls"))"; fail=1
else echo "PASS: C16 worktree catch fires via string-match, ZERO git"; fi

# --- MYC-1176 item 6: guard-fire telemetry on the WARN path, never the silent path ---
TFIRE="$TMP/fires.jsonl"; : > "$TFIRE"
# 17. a FIRE emits a guard-fire record (name + status=warned) to GUARD_FIRES_LOG.
out_t1="$( printf '{"cwd":"%s","hook_event_name":"UserPromptSubmit"}' "$TMP/vaultmain/.claude/worktrees/slug" \
    | env VAULT_WORKTREE_WARN_NODEDUP=1 VAULT_WORKTREE_WARN_STATE_DIR="$TMP/state" GUARD_FIRES_LOG="$TFIRE" python3 "$HOOK" )"
assert_fires "T17 warn path emits" "$out_t1"
if grep -q "warn-vault-session-in-worktree" "$TFIRE" && grep -q "warned" "$TFIRE"; then
  echo "PASS: T17 telemetry recorded a guard-fire on the WARN path (item 6)"
else echo "FAIL: T17 no guard-fire on warn path — got: $(cat "$TFIRE")"; fail=1; fi
# 18. a SILENT/plain run writes NOTHING (telemetry stays off the hot path).
: > "$TFIRE"
out_t2="$( cd "$TMP/plainvault" && printf '{"cwd":"%s","hook_event_name":"UserPromptSubmit"}' "$TMP/plainvault" \
    | env VAULT_WORKTREE_WARN_NODEDUP=1 VAULT_WORKTREE_WARN_STATE_DIR="$TMP/state" GUARD_FIRES_LOG="$TFIRE" python3 "$HOOK" )"
assert_silent "T18 silent path stays silent" "$out_t2"
if [ -s "$TFIRE" ]; then echo "FAIL: T18 telemetry fired on the silent/plain path: $(cat "$TFIRE")"; fail=1
else echo "PASS: T18 ZERO telemetry on the silent/plain path (off the hot path)"; fi

if [ "$fail" -eq 0 ]; then echo "ALL GREEN"; else echo "HAS FAILURES"; fi
exit $fail

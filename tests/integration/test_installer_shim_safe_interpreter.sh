#!/usr/bin/env bash
# CI lock: the installer bakes a shim-safe ABSOLUTE interpreter into hook
# commands, so a refuse-shim can't turn the vault's bare-python3 hooks into
# silent no-ops.
#
# The trailofbits `modern-python` plugin prepends a PATH shim for
# `python3`/`python` (SessionStart, via CLAUDE_ENV_FILE) that prints
# "ERROR: use uv run python3" and exit-1s on every bare invocation. Every
# ai-brain-starter hook command used to call bare `python3 X 2>/dev/null ||
# echo ...`, so with the shim active the ENTIRE hook layer — session close, the
# write-time secret guard, context loaders, aggregators — silently no-opped.
# hooks.json now uses a [PYTHON] token that install-hooks-user-level.py resolves
# to an absolute real interpreter (_posix_python), bypassing PATH entirely.
#
# Asserts, by running the REAL installer with a fake refuse-shim FIRST on PATH:
#   0. NEGATIVE CONTROL: bare `python3` under that PATH genuinely refuses.
#   1. NO ABS-owned hook command invokes bare `python3`/`python`.
#   2. The baked interpreter is absolute and is NOT the shim.
#   3. END-TO-END: that interpreter executes under the hostile PATH.
#   4. A virtualenv python first on PATH is skipped for one outside it.
#   4b. A virtualenv python with nothing else on PATH falls back to its base.
#   5. An install made under a virtualenv is repaired by a re-run from outside it.
#
# Stdlib python3 + bash only. No network, no git. Tmpdir removed on exit.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALLER="$REPO_ROOT/scripts/install-hooks-user-level.py"
# HOME alone does not sandbox the installer on Windows — see lib/sandbox_home.sh.
# shellcheck source=tests/integration/lib/sandbox_home.sh
. "$SCRIPT_DIR/lib/sandbox_home.sh"

PASS=0; FAIL=0
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
ok()  { PASS=$((PASS + 1)); echo "PASS  $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL  $1 :: $2"; }

# A real interpreter to LAUNCH the installer with (absolute, never the shim) —
# bare `python3` would hit the shim we are about to put on PATH.
LAUNCH_PY=""
for c in /opt/homebrew/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
  [ -x "$c" ] && "$c" -c 'import sys' >/dev/null 2>&1 && { LAUNCH_PY="$c"; break; }
done
[ -z "$LAUNCH_PY" ] && LAUNCH_PY="$(command -v python3 || true)"
[ -z "$LAUNCH_PY" ] && { echo "SKIP: no real python3 to launch installer"; exit 0; }

# Fake refuse-shim mimicking trailofbits modern-python, under a */hooks/shims
# dir so it looks exactly like the real one to the resolver's skip logic.
SHIM="$TMP/plugins/trailofbits/modern-python/1.5.0/hooks/shims"
mkdir -p "$SHIM"
cat > "$SHIM/python3" <<'SH'
#!/usr/bin/env bash
echo "ERROR: Use \`uv run python3\` instead" >&2
exit 1
SH
cp "$SHIM/python3" "$SHIM/python"
chmod +x "$SHIM/python3" "$SHIM/python"
HOSTILE_PATH="$SHIM:$PATH"

mkdir -p "$TMP/.claude"
echo '{}' > "$TMP/.claude/settings.json"
SETTINGS="$TMP/.claude/settings.json"

# Run the REAL installer with the shim FIRST on PATH. It must resolve [PYTHON]
# to a real interpreter that skips the shim.
run_sandboxed "$TMP" env -u CLAUDECODE PATH="$HOSTILE_PATH" \
  "$LAUNCH_PY" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1

echo "=== 0. NEGATIVE CONTROL: fake shim genuinely refuses bare python3 ==="
if env -u CLAUDECODE PATH="$HOSTILE_PATH" bash -c 'python3 -c "print(1)"' >/dev/null 2>&1; then
  bad "shim refuses" "fake shim did NOT refuse — test setup is broken"
else
  ok "fake shim refuses bare python3"
fi

echo "=== 1. no ABS-owned hook command invokes bare python3/python ==="
bare="$("$LAUNCH_PY" - "$SETTINGS" <<'PY'
import json, sys, re
h = json.load(open(sys.argv[1])).get("hooks", {})
viol = []
for ev, blocks in h.items():
    for blk in blocks:
        for e in blk.get("hooks", []):
            cmd = e.get("command", "")
            if "ai-brain-starter" not in cmd:
                continue
            # First token of any pipeline/list segment being bare python3/python
            # means an un-substituted interpreter that the shim would intercept.
            for seg in re.split(r"\|\||&&|[|;&]", cmd):
                toks = seg.strip().split()
                if toks and toks[0] in ("python3", "python"):
                    viol.append(cmd[:70])
                    break
print("\n".join(viol))
PY
)"
if [ -z "$bare" ]; then ok "no bare python3 in ABS-owned commands"; else bad "bare python3 present" "$bare"; fi

# Every distinct absolute interpreter baked into an ABS-owned hook command.
baked_interps() {
  "$LAUNCH_PY" - "$1" <<'PY'
import json, re, sys
h = json.load(open(sys.argv[1])).get("hooks", {})
found = []
for blocks in h.values():
    for blk in blocks:
        for e in blk.get("hooks", []):
            cmd = e.get("command", "")
            if "ai-brain-starter" not in cmd:
                continue
            for tok in cmd.split():
                # python3.14 as well as python3: an interpreter baked under its
                # versioned name must not read as "nothing was baked".
                if tok.startswith("/") and re.fullmatch(r"python[0-9.]*", tok.rsplit("/", 1)[-1]) \
                        and tok not in found:
                    found.append(tok)
print("\n".join(found))
PY
}

# How many hook scripts the installer's own post-install check reports missing, with
# HOME pointed at a directory that holds none of them. The check finds a script from
# the `python3 <path>` text of a command, so a command it cannot read adds nothing.
missing_hook_scripts() {  # missing_hook_scripts HOME_DIR SETTINGS_FILE
  run_sandboxed "$1" "$LAUNCH_PY" - "$INSTALLER" "$2" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("ih", sys.argv[1])
ih = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ih)
missing, _optional = ih.verify_paths_on_disk(json.load(open(sys.argv[2])))
print(len(missing))
PY
}

echo "=== 2. baked interpreter is absolute + not a shim ==="
INTERP=$(baked_interps "$SETTINGS" | head -1)
echo "   interpreter: ${INTERP:-<none>}"
case "${INTERP:-}" in
  */hooks/shims/*) bad "interp not shim" "$INTERP is a shim" ;;
  /*/python[0-9.]*) ok "absolute non-shim interpreter" ;;
  *) bad "interp absolute" "got [${INTERP:-<none>}]" ;;
esac

echo "=== 3. baked interpreter executes under the hostile PATH ==="
if [ -n "${INTERP:-}" ] && \
   [ "$(env -u CLAUDECODE PATH="$HOSTILE_PATH" "$INTERP" -c 'print(42)' 2>/dev/null)" = "42" ]; then
  ok "baked interpreter runs under shim-first PATH"
else
  bad "interp runs" "interpreter did not execute under hostile PATH"
fi

# A project virtualenv gets deleted or rebuilt. A hook pinned to its python then
# fails to start, and a PreToolUse gate that fails to start lets the call through.
echo "=== 4. a virtualenv python first on PATH is skipped for one outside it ==="
VENV="$TMP/proj/.venv"
"$LAUNCH_PY" -m venv --without-pip "$VENV" >/dev/null 2>&1
# CPython reports the resolved spelling of a path (macOS: /private/var/... where
# mktemp returned /var/...), so a check that names the venv has to match both.
VENV_REAL="$(cd "$VENV" 2>/dev/null && pwd -P)"
if [ "$("$VENV/bin/python3" -c 'import sys; print(sys.prefix != sys.base_prefix)' 2>/dev/null)" = "True" ]; then
  ok "fixture is a real virtualenv that runs (it would qualify on PATH alone)"
  H2="$TMP/venv-home"
  mkdir -p "$H2/.claude"
  echo '{}' > "$H2/.claude/settings.json"
  run_sandboxed "$H2" env -u CLAUDECODE PATH="$VENV/bin:$PATH" \
    "$VENV/bin/python3" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1
  VINTERPS="$(baked_interps "$H2/.claude/settings.json")"
  echo "   interpreters: ${VINTERPS:-<none>}"
  case "$VINTERPS" in
    "") bad "venv skipped" "no absolute interpreter was baked in" ;;
    *"$VENV"/*|*"$VENV_REAL"/*) bad "venv skipped" "the virtualenv python was baked in" ;;
    *) ok "virtualenv python skipped for one outside it" ;;
  esac
else
  bad "venv fixture" "could not create a working virtualenv with $LAUNCH_PY"
fi

# Section 4 never reaches the installer's fallback: $PATH still holds real pythons
# after the venv, so the PATH search finds one first. Here the venv is all there is, so
# the installer has only the python it is itself running under, and that one is inside
# the venv. It has to name the interpreter the venv was built from, for a venv that
# links to it (--symlinks) and for one that holds a copy (--copies, which links to
# nothing and used to end up as a bare python3).
echo "=== 4b. a virtualenv python with nothing else on PATH falls back to its base ==="
# What the post-install check reports for the ordinary install of section 2.
ORDINARY_MISSING="$(missing_hook_scripts "$TMP" "$SETTINGS")"
for MODE in symlinks copies; do
  VB="$TMP/proj-$MODE/.venv"
  if ! "$LAUNCH_PY" -m venv --without-pip "--$MODE" "$VB" >/dev/null 2>&1 \
     || [ "$("$VB/bin/python3" -c 'import sys; print(sys.prefix != sys.base_prefix)' 2>/dev/null)" != "True" ]; then
    bad "venv fixture ($MODE)" "could not create a working --$MODE virtualenv with $LAUNCH_PY"
    continue
  fi
  VB_REAL="$(cd "$VB" && pwd -P)"
  BASE_HOME="$(sed -n 's/^home *= *//p' "$VB/pyvenv.cfg" | head -1)"
  H4B="$TMP/venv-home-$MODE"
  mkdir -p "$H4B/.claude"
  echo '{}' > "$H4B/.claude/settings.json"
  run_sandboxed "$H4B" env -u CLAUDECODE PATH="$VB/bin" \
    "$VB/bin/python3" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1
  FB="$(baked_interps "$H4B/.claude/settings.json" | head -1)"
  echo "   $MODE: ${FB:-<none>} (the venv's home: ${BASE_HOME:-<none>})"
  case "$FB" in
    "") bad "fallback ($MODE)" "no absolute interpreter was baked in (bare python3?)" ;;
    "$VB"/*|"$VB_REAL"/*) bad "fallback ($MODE)" "the virtualenv python was baked in" ;;
    *)
      # What the venv's own pyvenv.cfg names: a stable spelling, and one whose
      # basename the installer's post-install path check recognises.
      WANT=""
      for n in python3 python; do
        if [ -f "$BASE_HOME/$n" ] && [ -x "$BASE_HOME/$n" ]; then WANT="$BASE_HOME/$n"; break; fi
      done
      if [ "$("$FB" -c 'print(42)' 2>/dev/null)" != "42" ]; then
        bad "fallback ($MODE)" "$FB does not run"
      elif [ -n "$WANT" ] && [ "$FB" != "$WANT" ]; then
        bad "fallback ($MODE)" "baked $FB, but the venv's pyvenv.cfg names $WANT"
      else
        ok "fallback ($MODE): the interpreter the venv was built from, and it runs"
      fi
      SEEN="$(missing_hook_scripts "$H4B" "$H4B/.claude/settings.json")"
      if [ "${ORDINARY_MISSING:-0}" -gt 0 ] && [ "$SEEN" = "$ORDINARY_MISSING" ]; then
        ok "fallback ($MODE): the post-install check reads the commands as it does an ordinary install ($SEEN missing hook scripts reported)"
      else
        bad "fallback ($MODE)" "the post-install check reports $SEEN missing hook scripts, an ordinary install gives ${ORDINARY_MISSING:-none}, so a missing script would go unreported"
      fi
      ;;
  esac
done

# An installer without the skip above pinned every [PYTHON] hook to the virtualenv's
# python. Once the project is gone the way to repair that install is to run the
# installer again from outside any virtualenv. is_same_command() read a command that
# carries neither an ABS fingerprint nor an owned script name as literal text,
# interpreter included, so for those the re-run added a second copy and left the dead
# one in place.
echo "=== 5. a re-run from outside a virtualenv repairs an install made under one ==="
PROJ5="$TMP/proj-deleted"
VENV5="$PROJ5/.venv"
"$LAUNCH_PY" -m venv --without-pip "$VENV5" >/dev/null 2>&1
VENV5_REAL="$(cd "$VENV5" && pwd -P)"
CLEAN_PATH="$(dirname "$LAUNCH_PY"):/usr/bin:/bin"
H5="$TMP/pinned-home"
mkdir -p "$H5/.claude"
S5="$H5/.claude/settings.json"
FRESH="$TMP/fresh-settings.json"

# Prints "<commands in A> <commands in B> <commands in A naming a virtualenv> <same|different>".
hook_report() {  # hook_report A_SETTINGS B_SETTINGS VENV_SPELLING...
  "$LAUNCH_PY" - "$@" <<'PY'
import json, sys
def cmds(path):
    hooks = json.load(open(path)).get("hooks", {})
    return [h.get("command", "") for groups in hooks.values()
            for g in groups for h in g.get("hooks", [])]
a, b, venvs = cmds(sys.argv[1]), cmds(sys.argv[2]), sys.argv[3:]
pinned = sum(1 for c in a if any(v in c for v in venvs))
print(len(a), len(b), pinned, "same" if sorted(a) == sorted(b) else "different")
PY
}

# What a fresh install looks like from this PATH. Taken in this same home, because
# some commands carry the home directory and two homes would never compare equal.
echo '{}' > "$S5"
run_sandboxed "$H5" env -u CLAUDECODE PATH="$CLEAN_PATH" \
  "$LAUNCH_PY" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1
cp "$S5" "$FRESH"
# ABS_POSIX_PYTHON is the installer's test override. It writes the virtualenv python
# into every command the way PATH resolution did before the skip.
echo '{}' > "$S5"
run_sandboxed "$H5" env -u CLAUDECODE PATH="$CLEAN_PATH" ABS_POSIX_PYTHON="$VENV5/bin/python3" \
  "$LAUNCH_PY" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1
# shellcheck disable=SC2046
set -- $(hook_report "$S5" "$FRESH" "$VENV5" "$VENV5_REAL")
BEFORE_CMDS=${1:-0}; FRESH_CMDS=${2:-0}; BEFORE_PINNED=${3:-0}
if [ "$BEFORE_PINNED" -gt 0 ]; then
  ok "setup: the install made under the virtualenv pins $BEFORE_PINNED of $BEFORE_CMDS commands to it"
else
  bad "setup" "no command names the virtualenv, so the repair below would prove nothing"
fi

rm -rf "$PROJ5"
run_sandboxed "$H5" env -u CLAUDECODE PATH="$CLEAN_PATH" \
  "$LAUNCH_PY" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1
# shellcheck disable=SC2046
set -- $(hook_report "$S5" "$FRESH" "$VENV5" "$VENV5_REAL")
AFTER_CMDS=${1:-0}; AFTER_PINNED=${3:-1}; AFTER_SAME=${4:-different}
echo "   after the re-run: $AFTER_CMDS commands, $AFTER_PINNED naming the deleted virtualenv (a fresh install has $FRESH_CMDS)"
if [ "$AFTER_PINNED" -eq 0 ]; then ok "no command still names the deleted virtualenv"
else bad "repair" "$AFTER_PINNED command(s) still name the deleted virtualenv"; fi
if [ "$AFTER_CMDS" -eq "$FRESH_CMDS" ]; then ok "the re-run left as many commands as a fresh install (none added twice)"
else bad "duplicates" "$AFTER_CMDS commands after the re-run, a fresh install has $FRESH_CMDS"; fi
if [ "$AFTER_SAME" = "same" ]; then ok "the repaired settings hold exactly the commands of a fresh install"
else bad "repair" "the repaired settings differ from a fresh install"; fi

# The same property for every [PYTHON] command hooks.json ships, whatever the
# interpreter is spelled as.
"$LAUNCH_PY" - "$INSTALLER" "$REPO_ROOT/hooks.json" <<'PY'
import importlib.util, json, sys

spec = importlib.util.spec_from_file_location("ih", sys.argv[1])
ih = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ih)
template = json.load(open(sys.argv[2]))["hooks"]
spellings = ["python3", "python", "/usr/bin/python3", "/opt/homebrew/bin/python3.14",
             "/tmp/proj/.venv/bin/python3"]
checked, failures = 0, []
for event, groups in template.items():
    for group in groups:
        for hook in group.get("hooks", []):
            cmd = hook.get("command", "")
            if "[PYTHON]" not in cmd:
                continue
            checked += 1
            pinned = cmd.replace("[PYTHON]", spellings[-1])
            for spelling in spellings[:-1]:
                if not ih.is_same_command(pinned, cmd.replace("[PYTHON]", spelling)):
                    failures.append((event, spelling, cmd[:90]))
                    break
if checked == 0:
    failures.append(("hooks.json", "", "no [PYTHON] command found, so nothing was checked"))
for event, spelling, cmd in failures:
    print(f"   DIFFERENT {event} [{spelling}] {cmd}")
print(f"   checked {checked} [PYTHON] commands, {len(failures)} read as a different hook")
sys.exit(1 if failures else 0)
PY
if [ $? -eq 0 ]; then ok "every [PYTHON] command reads as the same hook under any interpreter spelling"
else bad "interpreter spelling" "a [PYTHON] command reads as a different hook when only its interpreter differs"; fi

# And the pairs that must stay different hooks.
"$LAUNCH_PY" - "$INSTALLER" <<'PY'
import importlib.util, sys

spec = importlib.util.spec_from_file_location("ih", sys.argv[1])
ih = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ih)
same = ih.is_same_command
checks = [
    ("another script", same("/a/python3 ~/.claude/hooks/x.py 2>/dev/null || true",
                            "/b/python3 ~/.claude/hooks/y.py 2>/dev/null || true")),
    ("other arguments", same("/a/python3 ~/.claude/hooks/x.py --test",
                             "/b/python3 ~/.claude/hooks/x.py")),
    ("another interpreter", same("/a/python3 ~/.claude/hooks/x.py", "/a/node ~/.claude/hooks/x.py")),
    ("a user's own hook", same("/a/python3 ~/.claude/hooks/x.py", "echo mine")),
]
equal = [name for name, is_same in checks if is_same]
for name in equal:
    print(f"   read as the same hook: {name}")
sys.exit(1 if equal else 0)
PY
if [ $? -eq 0 ]; then ok "a different script, argument list, interpreter or user hook still reads as a different hook"
else bad "over-matching" "two different hooks read as one"; fi

echo
echo "=== summary: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]

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
#   4b. A virtualenv python with nothing else on PATH falls back to its base, or to
#       what its python resolves to when the venv records that base under a path
#       with a space in it.
#   5. An install made under a virtualenv is repaired by a re-run from outside it.
#   5b. So is one whose dead copies sit AFTER the live ones, and the installer's own
#       check names a hook whose python is gone (and leaves a user's own hook alone).
#   Then: the interpreter check reads each place a command names its python; every
#       [PYTHON] command, and a command of each shape that no owned name decides,
#       reads as the same hook under any spelling, a free-threaded python3.14t included.
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

# A venv whose pyvenv.cfg records its base interpreter under a path with a space in it.
# A hook command runs its interpreter unquoted, so that path cannot be written into one.
# The fallback has to go on to the next interpreter it can name, the one the venv's python
# resolves to, instead of ending at a bare python3: that is the spelling a refuse-shim or
# a pyenv shim intercepts.
VSP="$TMP/proj-spaced/.venv"
SPACED_BIN="$TMP/a base python/bin"
if ! "$LAUNCH_PY" -m venv --without-pip --symlinks "$VSP" >/dev/null 2>&1; then
  bad "venv fixture (spaced home)" "could not create a working --symlinks virtualenv with $LAUNCH_PY"
else
  VSP_REAL="$(cd "$VSP" && pwd -P)"
  VSP_TARGET="$("$LAUNCH_PY" -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$VSP/bin/python3")"
  mkdir -p "$SPACED_BIN" && ln -s "$VSP_TARGET" "$SPACED_BIN/python3"
  sed "s|^home *=.*|home = $SPACED_BIN|" "$VSP/pyvenv.cfg" > "$VSP/pyvenv.cfg.new" \
    && mv "$VSP/pyvenv.cfg.new" "$VSP/pyvenv.cfg"
  if [ "$("$VSP/bin/python3" -c 'import sys; print(sys.prefix != sys.base_prefix)' 2>/dev/null)" != "True" ]; then
    echo "SKIP: fallback (spaced home) needs a venv python that still starts once its recorded home is moved"
  else
    case "$VSP_TARGET" in
      *" "*) echo "SKIP: fallback (spaced home): the venv's python itself resolves to a path with a space ($VSP_TARGET)" ;;
      *)
        H4C="$TMP/venv-home-spaced"
        mkdir -p "$H4C/.claude"
        echo '{}' > "$H4C/.claude/settings.json"
        run_sandboxed "$H4C" env -u CLAUDECODE PATH="$VSP/bin" \
          "$VSP/bin/python3" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1
        FC="$(baked_interps "$H4C/.claude/settings.json" | head -1)"
        echo "   spaced home: ${FC:-<none>} (recorded home: $SPACED_BIN)"
        case "$FC" in
          "") bad "fallback (spaced home)" "no absolute interpreter was baked in (bare python3?)" ;;
          "$VSP"/*|"$VSP_REAL"/*) bad "fallback (spaced home)" "the virtualenv python was baked in" ;;
          *)
            if [ "$("$FC" -c 'print(42)' 2>/dev/null)" = "42" ]; then
              ok "fallback (spaced home): a path the commands can carry, outside the venv, and it runs"
            else
              bad "fallback (spaced home)" "$FC does not run"
            fi
            ;;
        esac
        ;;
    esac
  fi
fi

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

# The history above is the one where every line was replaced. The common one is
# different: an install from a terminal, then a later update that fires inside a session
# launched under a virtualenv. An installer without the skip rewrote the lines it
# recognised in place and appended a second copy of the rest AFTER the live ones. When the
# virtualenv goes, those copies name nothing, and an update has to remove them, not add a
# working one beside them. The installer's own check has to say so while they are there:
# it used to read the script a command runs and never the interpreter in front of it, so
# that state printed OK.
echo "=== 5b. a stale copy left after the live one is removed, and the check names it ==="
PROJ5B="$TMP/proj-deleted-2"
VENV5B="$PROJ5B/.venv"
"$LAUNCH_PY" -m venv --without-pip "$VENV5B" >/dev/null 2>&1
VENV5B_REAL="$(cd "$VENV5B" && pwd -P)"
H5B="$TMP/stale-after-live-home"
S5B="$H5B/.claude/settings.json"
mkdir -p "$H5B/.claude/skills"
# The hooks have to find their scripts, or the check fails for that and a failure for the
# interpreter proves nothing.
ln -s "$REPO_ROOT" "$H5B/.claude/skills/ai-brain-starter"
echo '{}' > "$S5B"
run_sandboxed "$H5B" env -u CLAUDECODE PATH="$CLEAN_PATH" \
  "$LAUNCH_PY" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1
LIVE5B="$TMP/live-5b.json"
cp "$S5B" "$LIVE5B"
LIVE_INTERP="$(baked_interps "$LIVE5B" | head -1)"

# Builds the damaged settings from the live ones, the way that installer left them: a
# command the match saw by owned script name is rewritten in place, any other gets a pinned
# copy appended to the first group with its matcher. The user's own hooks go in as well,
# between the live and the stale copies; none is a copy of a hook the installer ships under
# the matcher it ships it under, so none of them may change.
DAMAGED5B="$TMP/damaged-5b.json"
EXPECTED5B="$TMP/expected-5b.json"
USERHOOKS5B="$TMP/user-hooks-5b.json"
"$LAUNCH_PY" - "$INSTALLER" "$LIVE5B" "$LIVE_INTERP" "$VENV5B/bin/python3" "$DAMAGED5B" "$EXPECTED5B" "$USERHOOKS5B" <<'PY'
import copy, importlib.util, json, sys

spec = importlib.util.spec_from_file_location("ih", sys.argv[1])
ih = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ih)
live_path, live, pinned, damaged_path, expected_path, user_path = sys.argv[2:8]
settings = json.load(open(live_path))

def hooks_of(doc):
    return [(event, group.get("matcher"), hook) for event, groups in doc["hooks"].items()
            for group in groups for hook in group["hooks"]]

shipped = next(h["command"] for event, matcher, h in hooks_of(settings)
               if event == "SessionStart" and matcher is None and live in h["command"]
               and not ih.is_abs_owned(h["command"]))
user_hooks = [
    ("SessionStart", None, {"type": "command", "timeout": 7,
                            "command": "'/Users/Some User/hooks/mine.py' --flag \"a b\""}),
    ("SessionStart", None, {"type": "command",
                            "command": "/gone/user-env/bin/python3 ~/mine/own-hook.py 2>/dev/null || true"}),
    # one the installer wired once and the template no longer ships: an update cannot
    # repair it, so a check that failed on it could never be cleared by running one
    ("SessionStart", None, {"type": "command",
                            "command": "/gone/user-env/bin/python3 "
                                       "~/.claude/skills/ai-brain-starter/hooks/dropped-from-the-template.py "
                                       "2>/dev/null || true"}),
    ("SessionStart", None, {"type": "command",
                            "command": "python3 ~/.claude/hooks/surface-backup-status.py"}),
    # a shipped command under a matcher the installer does not ship it under
    ("SessionStart", "startup", {"type": "command", "command": shipped.replace(live, "/usr/bin/python3")}),
    ("PreToolUse", "Bash", {"type": "command", "command": 'py -3 "C:\\Users\\x\\hooks\\mine.py"'}),
]

def put_user_hooks(doc):
    for event, matcher, hook in user_hooks:
        groups = doc["hooks"].setdefault(event, [])
        group = next((g for g in groups if g.get("matcher") == matcher), None)
        if group is None:
            group = {"hooks": []}
            if matcher is not None:
                group["matcher"] = matcher
            groups.append(group)
        group["hooks"].insert(1, copy.deepcopy(hook))

damaged, appended = copy.deepcopy(settings), []
for event, groups in damaged["hooks"].items():
    for group in groups:
        for hook in group["hooks"]:
            cmd = hook.get("command", "")
            if live not in cmd:
                continue
            if ih.is_abs_owned(cmd):
                hook["command"] = cmd.replace(live, pinned)
            else:
                appended.append((event, group.get("matcher"), dict(hook, command=cmd.replace(live, pinned))))
for event, matcher, hook in appended:
    next(g for g in damaged["hooks"][event] if g.get("matcher") == matcher)["hooks"].append(hook)
expected = copy.deepcopy(settings)
put_user_hooks(damaged)
put_user_hooks(expected)
json.dump(damaged, open(damaged_path, "w"), indent=2)
json.dump(expected, open(expected_path, "w"), indent=2)
json.dump([[e, m, h] for e, m, h in user_hooks], open(user_path, "w"))
print(f"   {len(appended)} pinned copies appended after the live ones, {len(user_hooks)} user hooks added")
PY
cp "$DAMAGED5B" "$S5B"
rm -rf "$PROJ5B"

# The installer's own check, with every hook script in place, so only the interpreter can fail it.
interpreter_reports() {  # interpreter_reports HOME_DIR SETTINGS_FILE INTERPRETER
  run_sandboxed "$1" "$LAUNCH_PY" - "$INSTALLER" "$2" "$3" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("ih", sys.argv[1])
ih = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ih)
required, optional = ih.verify_paths_on_disk(json.load(open(sys.argv[2])))
print(sum(1 for _event, path, _cmd in required + optional if path == sys.argv[3]))
PY
}
# shellcheck disable=SC2046
set -- $(hook_report "$S5B" "$EXPECTED5B" "$VENV5B" "$VENV5B_REAL")
DAMAGED_CMDS=${1:-0}; EXPECTED_CMDS=${2:-0}; DAMAGED_PINNED=${3:-0}
if [ "$DAMAGED_PINNED" -gt 0 ] && [ "$DAMAGED_CMDS" -gt "$EXPECTED_CMDS" ]; then
  ok "setup: $DAMAGED_PINNED of $DAMAGED_CMDS commands name the deleted virtualenv, and $((DAMAGED_CMDS - EXPECTED_CMDS)) are copies added after the live ones"
else
  bad "setup" "$DAMAGED_PINNED pinned, $DAMAGED_CMDS commands against $EXPECTED_CMDS expected: not the history this section is about"
fi
VERIFY_OUT="$(run_sandboxed "$H5B" env -u CLAUDECODE PATH="$CLEAN_PATH" \
  "$LAUNCH_PY" "$INSTALLER" --settings "$S5B" --verify-only --fail-on-missing 2>&1)"
VERIFY_RC=$?
if [ "$VERIFY_RC" -ne 0 ] && printf '%s' "$VERIFY_OUT" | grep -qF "$VENV5B/bin/python3"; then
  ok "the installer's check fails and names the interpreter that is gone"
else
  bad "dead interpreter" "exit $VERIFY_RC; the check did not name $VENV5B/bin/python3: $(printf '%s' "$VERIFY_OUT" | tail -3 | tr '\n' ' ')"
fi
SEEN5B="$(interpreter_reports "$H5B" "$S5B" "$VENV5B/bin/python3")"
if [ "$SEEN5B" -eq "$DAMAGED_PINNED" ]; then
  ok "it reports each of the $DAMAGED_PINNED hooks that name the deleted virtualenv, owned or not"
else
  bad "dead interpreter" "it reports $SEEN5B hooks, $DAMAGED_PINNED name the deleted virtualenv"
fi
if printf '%s' "$VERIFY_OUT" | grep -qF "/gone/user-env/bin/python3"; then
  bad "hooks no update rewrites" "the check judged a hook of the user's own, or one the template no longer ships"
else
  ok "a hook no update rewrites (the user's own, or one the template dropped) is not judged for its interpreter"
fi

run_sandboxed "$H5B" env -u CLAUDECODE PATH="$CLEAN_PATH" \
  "$LAUNCH_PY" "$INSTALLER" --hooks-source "$REPO_ROOT/hooks.json" --quiet >/dev/null 2>&1
# shellcheck disable=SC2046
set -- $(hook_report "$S5B" "$EXPECTED5B" "$VENV5B" "$VENV5B_REAL")
HEALED_CMDS=${1:-0}; HEALED_PINNED=${3:-1}; HEALED_SAME=${4:-different}
echo "   after the update: $HEALED_CMDS commands, $HEALED_PINNED naming the deleted virtualenv (a fresh install has $EXPECTED_CMDS, counting the user's own)"
if [ "$HEALED_PINNED" -eq 0 ]; then ok "no command still names the deleted virtualenv"
else bad "stale copies" "$HEALED_PINNED command(s) still name the deleted virtualenv"; fi
if [ "$HEALED_CMDS" -eq "$EXPECTED_CMDS" ]; then ok "the update left as many commands as a fresh install plus the user's own"
else bad "stale copies" "$HEALED_CMDS commands after the update, a fresh install plus the user's own has $EXPECTED_CMDS"; fi
if [ "$HEALED_SAME" = "same" ]; then ok "the settings hold exactly the commands of a fresh install plus the user's own"
else bad "stale copies" "the settings differ from a fresh install plus the user's own"; fi
HEALED_OUT="$(run_sandboxed "$H5B" env -u CLAUDECODE PATH="$CLEAN_PATH" \
  "$LAUNCH_PY" "$INSTALLER" --settings "$S5B" --verify-only --fail-on-missing 2>&1)"
HEALED_RC=$?
if [ "$HEALED_RC" -eq 0 ]; then ok "the installer's check passes once the stale copies are gone"
else bad "verify after repair" "exit $HEALED_RC: $(printf '%s' "$HEALED_OUT" | tail -3 | tr '\n' ' ')"; fi

# The user's own hooks come out of the update exactly as they went in.
"$LAUNCH_PY" - "$S5B" "$USERHOOKS5B" <<'PY'
import json, sys
settings = json.load(open(sys.argv[1]))
lost = []
for event, matcher, hook in json.load(open(sys.argv[2])):
    found = sum(1 for g in settings["hooks"].get(event, []) if g.get("matcher") == matcher
                for h in g["hooks"] if h == hook)
    if found != 1:
        lost.append((event, matcher, found, hook["command"][:60]))
for item in lost:
    print(f"   user hook found {item[2]} time(s): {item[0]} [{item[1]}] {item[3]}")
sys.exit(1 if lost else 0)
PY
if [ $? -eq 0 ]; then ok "every hook of the user's own is still there once, exactly as written"
else bad "user hooks" "the update changed or removed a hook of the user's own"; fi

# What the interpreter check reads. It shares the interpreter-slot match with
# is_same_command, so it sees the four places hooks.json puts [PYTHON]: the start of a
# command, and after `&&`, `then` and `||`. It must stay quiet about a python that exists,
# a bare python3 (looked up on the PATH when the hook runs), a Windows launcher, and any
# hook no update rewrites.
"$LAUNCH_PY" - "$INSTALLER" "$LAUNCH_PY" <<'PY'
import importlib.util, os, sys

spec = importlib.util.spec_from_file_location("ih", sys.argv[1])
ih = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ih)
real, gone = sys.argv[2], "/gone/venv/bin/python3"
owned = "~/.claude/hooks/lint-claude-settings.py"
shapes = {
    "the start of a command": "{i} " + owned + " 2>/dev/null || true",
    "after &&": "[ -f " + owned + " ] && {i} " + owned + " || true",
    "after then": "if [ -f " + owned + " ]; then {i} " + owned + "; else echo ok; fi",
    "after ||": real + " " + owned + " 2>/dev/null || {i} " + owned,
}

def reported(cmd, template=None):
    settings = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": cmd}]}]}}
    required, _optional = ih.verify_paths_on_disk(settings, {} if template is None else template)
    return [path for _event, path, _short in required if path == gone]

problems = []
for place, shape in shapes.items():
    if reported(shape.format(i=gone)) != [gone]:
        problems.append(f"{place}: a python that is gone was not reported")
    if reported(shape.format(i=real)):
        problems.append(f"{place}: a python that exists was reported")
    if reported(shape.format(i="python3")):
        problems.append(f"{place}: a bare python3 was reported")
runner = ' "C:/r/hook_runner.py" --fallback silent "C:/Users/x/.claude/hooks/lint-claude-settings.py"'
if reported("C:/Python313/python.exe -X utf8" + runner):
    problems.append("a Windows launcher was reported")
os.environ["ABS_FORCE_WINDOWS"] = "1"
if reported(shapes["the start of a command"].format(i=gone)):
    problems.append("a python that is gone was reported while checking for Windows")
del os.environ["ABS_FORCE_WINDOWS"]
if reported(gone + " ~/mine/own-hook.py 2>/dev/null || true"):
    problems.append("a user's own hook was reported")
# A command the template ships with no owned script is read as the installer's own only
# because the template ships it.
unowned = "[PYTHON] ~/.claude/skills/ai-brain-starter/hooks/surface-backup-status.py 2>/dev/null || true"
template = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": unowned}]}]}}
if reported(unowned.replace("[PYTHON]", gone), template) != [gone]:
    problems.append("a copy of a command the template ships was not reported")
if reported(unowned.replace("[PYTHON]", gone)):
    problems.append("that same command was reported with no template to say the installer ships it")
for problem in problems:
    print("   " + problem)
sys.exit(1 if problems else 0)
PY
if [ $? -eq 0 ]; then ok "the interpreter check reads every place a command names its python, and only where an update rewrites"
else bad "interpreter check" "it missed a python that is gone, or reported one that is fine or not the installer's"; fi

# The same property for every [PYTHON] command hooks.json ships, whatever the
# interpreter is spelled as. is_same_command() settles the 59 owned commands by their
# script name before it reaches the interpreter-slot match, so the match itself is
# asserted here directly too: only that reaches every place hooks.json puts [PYTHON].
"$LAUNCH_PY" - "$INSTALLER" "$REPO_ROOT/hooks.json" <<'PY'
import importlib.util, json, sys

spec = importlib.util.spec_from_file_location("ih", sys.argv[1])
ih = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ih)
template = json.load(open(sys.argv[2]))["hooks"]
# A free-threaded build ends its name in a `t`: python3.14t, which is what
# sys.executable can be when the installer runs under one.
spellings = ["python3", "python", "/usr/bin/python3", "/opt/homebrew/bin/python3.14",
             "/opt/homebrew/bin/python3.14t", "python3.13t", "/tmp/proj/.venv/bin/python3"]
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
                other = cmd.replace("[PYTHON]", spelling)
                if not ih.is_same_command(pinned, other):
                    failures.append((event, spelling, "read as a different hook", cmd[:90]))
                    break
                if ih._without_interpreter(pinned) != ih._without_interpreter(other):
                    failures.append((event, spelling, "differs once the interpreter is set aside", cmd[:90]))
                    break
if checked == 0:
    failures.append(("hooks.json", "", "no [PYTHON] command found, so nothing was checked", ""))
for event, spelling, why, cmd in failures[:5]:
    print(f"   {why}: {event} [{spelling}] {cmd}")
print(f"   checked {checked} [PYTHON] commands, {len(failures)} failed")
sys.exit(1 if failures else 0)
PY
if [ $? -eq 0 ]; then ok "every [PYTHON] command reads as the same hook under any interpreter spelling"
else bad "interpreter spelling" "a [PYTHON] command reads as a different hook when only its interpreter differs"; fi

# Each place a command can name its python, for a command no owned script name decides:
# only the interpreter-slot match tells two spellings of it apart. Taking the `then` or
# the `||` alternative out of the match leaves every other check on is_same_command green,
# because hooks.json uses them only in owned commands, so each gets a command of its own
# where it is the only place the interpreter appears.
"$LAUNCH_PY" - "$INSTALLER" <<'PY'
import importlib.util, sys

spec = importlib.util.spec_from_file_location("ih", sys.argv[1])
ih = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ih)
script = "~/mine/not-an-owned-hook.py"
places = {
    "the start of a command": "{i} " + script + " 2>/dev/null || echo ok",
    "after &&": "[ -f " + script + " ] && {i} " + script + " || true",
    "after then": "if [ -f " + script + " ]; then {i} " + script + "; else echo ok; fi",
    "after ||": "echo first || {i} " + script,
}
spellings = ["python3", "python", "/usr/bin/python3", "/opt/homebrew/bin/python3.14",
             "/opt/homebrew/bin/python3.14t", "python3.13t"]
problems = []
for place, shape in places.items():
    base = shape.format(i="/tmp/proj/.venv/bin/python3")
    if ih.is_abs_owned(base):
        problems.append(f"{place}: the command is owned, so it proves nothing about the match")
    for spelling in spellings:
        if not ih.is_same_command(base, shape.format(i=spelling)):
            problems.append(f"{place}: [{spelling}] reads as a different hook")
    if ih.is_same_command(base, shape.format(i="/usr/bin/node")):
        problems.append(f"{place}: another interpreter reads as the same hook")
    if ih.is_same_command(base, shape.format(i="python3").replace("not-an-owned", "another")):
        problems.append(f"{place}: another script reads as the same hook")
for problem in problems:
    print("   " + problem)
sys.exit(1 if problems else 0)
PY
if [ $? -eq 0 ]; then ok "an interpreter reads as the same hook at the start, after &&, after then and after ||, free-threaded python included"
else bad "interpreter slot" "a command read as a different hook where only its interpreter differs, or two different hooks read as one"; fi

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

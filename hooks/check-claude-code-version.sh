#!/usr/bin/env bash
# Check Claude Code installed version against the latest GitHub release.
# When behind, also surfaces what's new (bullets between current and latest)
# so the user sees WHAT changed, not just THAT she's behind.
# Caches result for 6h to avoid hammering GitHub.
#
# Wired into SessionStart. Permanent guard against (a) falling behind on releases
# AND (b) missing release-payload features that should drive setup changes.
# Cantrill blind-spot fix codified 2026-05-08: the previous version was a tier-1
# alarm without payload — surfaced "you're behind" but not "here's the diff that
# changed worktree.baseRef behavior."
#
# WHICH BINARY IS MEASURED (MYC-5205). The version that matters is the one of the
# Claude Code process that spawned this hook, NOT whichever `claude` the PATH
# reaches first. A machine can carry several copies at once -- an npm install per
# node version, a Homebrew one, the desktop app's bundled one -- and each reaches
# a different consumer: interactive terminals, the desktop app, and scheduled
# jobs whose PATH differs from the terminal's. Measuring only the PATH-first copy
# printed "2.1.258" inside a desktop session that was running 2.1.284, and let
# two other copies sit weeks behind with every upgrade "verified" against the
# wrong one.
#   1. Walk up the process tree from this hook's parent to the first ancestor
#      whose executable is named `claude` (or `claude.exe`) and run THAT file with
#      --version. macOS reads the path from `ps`; Linux reads /proc/<pid>/exe, and
#      runs that magic link rather than the path, so a binary replaced on disk
#      since the session started still reports the image that is actually running.
#      macOS has no such link: after an upgrade in place the reading is the new
#      file's until the session is restarted.
#   2. Only when there is no such ancestor (the hook was run by hand, or the
#      launcher hides it), fall back to `claude` on PATH. The printed line says
#      which source it used and which file, so a reading is never anonymous.
#   3. The cache is keyed by the binary measured (its path -- the running one, or
#      PATH's when there is none), so one binary's reading is never replayed into
#      a session running another; and a binary that is NEWER than its reading
#      invalidates that reading, so an upgrade shows at once instead of after the
#      TTL. When the running binary reports no version and PATH's is measured
#      instead, that reading is saved under both names, so the running binary's
#      next session finds it. Every fresh reading is also written to the original,
#      un-keyed file name as a mirror: this hook never reads it back, but other
#      tools read that name as "the last banner".
#   4. Skew watchdog, on a cache miss only: list every `claude` reachable from the
#      hook's PATH, each LaunchAgent's PATH (plus launchd's default PATH when a
#      plist sets none), the usual install locations and the newest desktop
#      bundle. npm installs are read from package.json (never spawned); one line
#      names the copies (the first eight, newest first) when their versions
#      disagree, and nothing prints when they agree. A scan that CRASHES says so:
#      an empty answer must never be able to mean "could not look".
#
# Environment (all optional; for odd launchers and for tests):
#   CLAUDE_VERSION_CHECK_WALK_FROM_PID      pid the ancestor walk starts at
#                                           (default: this hook's parent)
#   CLAUDE_VERSION_CHECK_KNOWN_INSTALLS     colon-separated glob patterns of
#                                           install locations the skew scan checks
#                                           (default: ~/local/node-*/bin/claude,
#                                           ~/.local/bin/claude, /opt/homebrew/bin/claude,
#                                           /usr/local/bin/claude)
#   CLAUDE_VERSION_CHECK_PROBE_TIMEOUT_SEC  bound on each `claude --version` run
#                                           (default 10)
#   CLAUDE_VERSION_CHECK_CACHE_FILE         use exactly this file as the cache: no
#                                           per-binary key, no mirror, no cleanup
#
# Bounded by construction: a few `ps` calls and one cached read; on a miss only,
# one directory level of ~/Library/LaunchAgents plus time-bounded `--version`
# probes. No recursive walk, and no file is run that another user could have
# written.

set -uo pipefail

# --- ai-brain-starter: shim-safe PATH (strip refuse-shims) ----------------
# Some machines carry a python3/python PATH shim (e.g. trailofbits
# modern-python) that exit-1s on bare invocation and would turn every bare
# python call below into a silent no-op. Drop any */hooks/shims dir from PATH
# so bare python calls here (and, via export, in children) hit a real python.
if [ "${PATH#*/hooks/shims}" != "$PATH" ]; then
  _abs_new=""; _abs_oifs=$IFS; IFS=:
  for _abs_d in $PATH; do
    case $_abs_d in */hooks/shims|*/hooks/shims/) ;; *) _abs_new=${_abs_new:+$_abs_new:}$_abs_d ;; esac
  done
  IFS=$_abs_oifs; PATH=$_abs_new; export PATH
  unset _abs_new _abs_d _abs_oifs
fi
# --------------------------------------------------------------------------

CACHE_FILE="$HOME/.claude/.claude-code-version-check"
LEGACY_CACHE_FILE="$CACHE_FILE"   # un-keyed name: written as the "last banner" mirror
# 6h, not 24h. Claude Code ships ~daily, so a 24h cache made this banner
# SYSTEMATICALLY one release stale: every reading was up to a full release train
# behind by the time anyone saw it. Measured stale-by-one on three consecutive
# upstream delta audits. The cache exists to avoid hammering the API; one version
# check every 6h costs nothing and keeps the reading current. The root cause was
# the TTL, NOT a releases-feed-vs-npm lag (both feeds verified in agreement).
CACHE_TTL_SEC=$((6 * 60 * 60))    # 6 hours
WARN_VERSION_GAP=3                # warn loudly if behind by N or more patch versions
DIFF_BULLET_LIMIT=8               # max bullets to surface from the changelog diff
KEYED_CACHE_KEEP_DAYS=14          # drop per-binary cache files untouched this long
PROBE_TIMEOUT_SEC=${CLAUDE_VERSION_CHECK_PROBE_TIMEOUT_SEC:-10}
case $PROBE_TIMEOUT_SEC in ''|*[!0-9]*) PROBE_TIMEOUT_SEC=10 ;; esac

# Sets MTIME to the epoch mtime of $1, cross-platform; empty when unknown.
# GNU/Linux `stat -c %Y` first, then BSD/macOS `stat -f %m`, validating each result
# is a plain integer before trusting it.
# GNU's `-f` flag means `--file-system`, so `stat -f %m FILE` on Linux does not
# fail the way a BSD-first `||` chain assumes -- it can hand back non-numeric text
# instead of a clean fallback, which then poisoned the `age` arithmetic outright
# (unbound-variable abort under `set -u`, measured on GNU coreutils 9.4). See
# PORTABILITY.md #1. A variable rather than output, so the caller pays for no
# command-substitution subshell: this runs on every session start, cached or not.
file_mtime() {
  MTIME=$(stat -c %Y "$1" 2>/dev/null)                                       # GNU/Linux
  case "$MTIME" in ''|*[!0-9]*) MTIME=$(stat -f %m "$1" 2>/dev/null) ;; esac # BSD/macOS
  case "$MTIME" in ''|*[!0-9]*) MTIME="" ;; esac  # neither gave a plain integer -> unknown
}

# Physical path of $1 with every symlink followed. Pure shell: stock macOS only
# gained `readlink -f` in 12.3 and this hook runs on bash 3.2. Prints $1 unchanged
# when the directory cannot be entered.
resolve_path() {
  local p=$1 hops=0 link dir
  while [ -L "$p" ] && [ "$hops" -lt 32 ]; do
    link=$(readlink "$p") || break
    case $link in /*) p=$link ;; *) p="${p%/*}/$link" ;; esac
    hops=$((hops + 1))
  done
  case $p in */*) dir=${p%/*}; [ -n "$dir" ] || dir=/ ;; *) dir=. ;; esac
  dir=$(cd "$dir" 2>/dev/null && pwd -P) || { printf '%s\n' "$p"; return 0; }
  printf '%s/%s\n' "${dir%/}" "${p##*/}"
}

# $1 with control characters removed. Every path this hook prints comes from the
# process table, a PATH or a plist and ends up in a model's context, where a
# directory named with a newline and a sentence would otherwise read as a line of
# its own.
plain() {
  printf '%s' "$1" | tr -d '\000-\037\177'
}

# $1 with a leading $HOME shown as ~ (shorter, and keeps the user name out of a
# line someone may paste elsewhere), control characters removed.
tilde() {
  local p
  case $1 in "$HOME"/*) p="~${1#"$HOME"}" ;; *) p=$1 ;; esac
  plain "$p"
}

# Run "$@" for at most $1 seconds. GNU `timeout` is absent on stock macOS; perl is
# on every macOS and nearly every Linux. With neither, run unbounded (as before).
run_bounded() {
  local secs=$1; shift
  if command -v perl >/dev/null 2>&1; then
    perl -e 'alarm shift; exec @ARGV' "$secs" "$@"
  elif command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  else
    "$@"
  fi
}

# Version a Claude Code binary reports: the first word of the first non-empty
# line of `<bin> --version`, bounded, stdin closed. Prints nothing unless it
# starts like a version -- a path that is not Claude Code (a node shim, a wrapper
# that errors) must not be reported as a version.
probe_version() {
  local out v
  out=$(run_bounded "$PROBE_TIMEOUT_SEC" "$1" --version 2>/dev/null </dev/null) || true
  v=$(printf '%s\n' "$out" | awk 'NF { print $1; exit }')
  case $v in [0-9]*.[0-9]*.[0-9]*) printf '%s' "$v" ;; esac
}

# Find the Claude Code process above this hook. Sets ANC_PATH (the file it runs
# from, for display), ANC_EXEC (what to execute to ask it for its version) and, when
# a claude was found but cannot be used, ANC_NOTE (why). All empty when there is no
# claude above us. Stops at the FIRST claude: a nested outer session is a
# different binary.
find_claude_ancestor() {
  ANC_PATH=""; ANC_EXEC=""; ANC_NOTE=""
  local pid depth=0 ppid="" exe="" pname="" base="" line="" matched
  pid=${CLAUDE_VERSION_CHECK_WALK_FROM_PID:-$PPID}
  case $pid in ''|*[!0-9]*) pid=$PPID ;; esac
  while [ "$depth" -lt 16 ]; do
    case $pid in ''|*[!0-9]*) break ;; esac
    [ "$pid" -ge 1 ] || break
    ppid=""; exe=""; pname=""; base=""; matched=0
    if [ -r "/proc/$pid/status" ]; then
      # Linux. /proc/<pid>/exe is the image itself; comm is the name it was
      # started under (a native install's exe can be named after its version,
      # while comm stays "claude"). "(deleted)" marks a binary replaced since
      # launch: the link still executes, and runs the OLD image.
      exe=$(readlink "/proc/$pid/exe" 2>/dev/null)
      case $exe in *" (deleted)") exe=${exe% (deleted)} ;; esac
      read -r pname 2>/dev/null < "/proc/$pid/comm" || pname=""
      ppid=$(awk '/^PPid:/ { print $2; exit }' "/proc/$pid/status" 2>/dev/null)
      base=${exe##*/}
      if [ "$base" = claude ] || [ "$base" = claude.exe ] || [ "$pname" = claude ]; then
        matched=1
        ANC_EXEC="/proc/$pid/exe"
      fi
    else
      # macOS/BSD. `comm` is the path the process was exec'd by; everything after
      # the ppid column is the path, spaces included ("Application Support").
      line=$(ps -o ppid=,comm= -p "$pid" 2>/dev/null)
      read -r ppid exe <<< "$line"
      base=${exe##*/}
      if [ "$base" = claude ] || [ "$base" = claude.exe ]; then
        matched=1
        ANC_EXEC=$exe
      fi
    fi
    if [ "$matched" -eq 1 ]; then
      ANC_PATH=$exe
      if [ -z "$ANC_PATH" ]; then
        ANC_NOTE="could not read the executable of the claude above this hook (pid $pid)"
      else
        case $ANC_PATH in
          /*) [ -x "$ANC_EXEC" ] || ANC_NOTE="the claude above this hook ($ANC_PATH) is no longer an executable file" ;;
          *) ANC_NOTE="the claude above this hook was started by a relative path ($ANC_PATH)" ;;
        esac
      fi
      if [ -n "$ANC_NOTE" ]; then ANC_PATH=""; ANC_EXEC=""; fi
      return 0
    fi
    [ "$pid" -eq 1 ] && break
    pid=$ppid
    depth=$((depth + 1))
  done
  return 0
}

# Point CACHE_FILE at the reading for the binary at $1, and CACHE_BIN at the file
# whose being newer than that reading voids it. The name is the path with '%' and
# '/' escaped: injective, so two binaries can never share a file, and it needs no
# subprocess -- this runs on every session start, cached or not. (A path too long
# for a filename falls back to a checksum.) An explicit
# CLAUDE_VERSION_CHECK_CACHE_FILE wins and is never voided; with no binary to key
# on (nothing running, nothing on PATH) the un-keyed file is read.
select_cache_file() {
  local enc
  CACHE_BIN=""
  if [[ -n "${CLAUDE_VERSION_CHECK_CACHE_FILE:-}" ]]; then
    CACHE_FILE=$CLAUDE_VERSION_CHECK_CACHE_FILE
  elif [[ -n "$1" ]]; then
    enc=${1//\%/%25}
    enc=${enc//\//%2F}
    if (( ${#enc} > 180 )); then
      enc=$(printf '%s' "$1" | cksum)
      enc=sum-${enc%% *}
    fi
    CACHE_FILE="$LEGACY_CACHE_FILE.$enc"
    CACHE_BIN=$1
  fi
}

find_claude_ancestor
key_path=$ANC_PATH
[[ -z "$key_path" ]] && key_path=$(command -v claude 2>/dev/null)
select_cache_file "$key_path"
# Where THIS session looks for a reading. The measurement below can end up keyed
# elsewhere (the claude above us said nothing, so PATH's is measured instead), but the
# next session under the same claude will look here again, so a reading is also
# saved here.
LOOKUP_CACHE_FILE=$CACHE_FILE

now=$(date +%s)
# `-nt` is a shell builtin (no stat), and follows symlinks: a bin entry that points
# at a reinstalled file is newer than a reading taken before the reinstall.
if [[ -f "$CACHE_FILE" ]] && ! { [[ -n "$CACHE_BIN" ]] && [[ "$CACHE_BIN" -nt "$CACHE_FILE" ]]; }; then
  file_mtime "$CACHE_FILE"
  last=$MTIME
  if [[ -n "$last" ]]; then
    age=$(( now - last ))
    if (( age < CACHE_TTL_SEC )); then
      # DATE the snapshot. A cached reading is byte-identical in shape to a live
      # one, so replaying it bare lets a stale version number read as current --
      # the reader has no way to tell. Stamp the age whenever it is old enough to
      # matter, so a stale answer announces itself instead of impersonating a
      # fresh one.
      cat "$CACHE_FILE"
      if [[ -s "$CACHE_FILE" ]] && (( age >= 3600 )); then
        printf '[claude-code-version] (reading is %dh old; upstream ships ~daily, so the real head may already be newer)\n' "$(( age / 3600 ))"
      fi
      exit 0
    fi
  fi
  # else: mtime unreadable -> treat the cache as stale rather than trust an
  # unprovable age. Fall through and refetch from the GitHub API below.
fi

# Need gh CLI; if missing, exit silently
if ! command -v gh >/dev/null 2>&1; then
  exit 0
fi

# Measure the running binary; fall back to PATH only when there is none.
current=""
measured_path=""
src_label=""
if [[ -n "$ANC_PATH" ]]; then
  current=$(probe_version "$ANC_EXEC")
  if [[ -n "$current" ]]; then
    measured_path=$ANC_PATH
    src_label="running binary: $(tilde "$ANC_PATH")"
  else
    ANC_NOTE="the running claude at $(tilde "$ANC_PATH") reported no version"
  fi
fi
if [[ -z "$current" ]]; then
  # This reading is of PATH's claude, so it is cached under PATH's claude (and, when
  # a claude above us was found but reported nothing, under that one too).
  path_claude=$(command -v claude 2>/dev/null)
  select_cache_file "$path_claude"
  if [[ -n "$path_claude" ]]; then
    current=$(probe_version "$path_claude")
    measured_path=$path_claude
    src_label="PATH claude: $(tilde "$path_claude"); $(plain "${ANC_NOTE:-no claude process above this hook}")"
  fi
fi
[[ -z "$current" ]] && exit 0

latest=$(gh api repos/anthropics/claude-code/releases/latest --jq .tag_name 2>/dev/null | sed 's/^v//')
[[ -z "$latest" ]] && exit 0

# Skew watchdog. Prints ONE line naming every distinct Claude Code copy when their
# versions disagree; prints nothing when they agree. $1 = the running binary (may
# be empty). Python because it reads plists, package.json and globs; no recursive
# walk, no network, and an npm install is never spawned -- its version comes from
# the package.json beside it. A copy whose version cannot be read from its layout
# (a wrapper, a shim) is asked `--version` once, under a wall-clock budget.
IFS= read -r -d '' SKEW_PY <<'PY' || true
import glob, json, os, plistlib, re, subprocess, sys, time

HOME = os.path.expanduser("~")
NPM_NAME = "@anthropic-ai/claude-code"
LAUNCHD_DEFAULT_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
VER = re.compile(r"\d+\.\d+\.\d+")
DEADLINE = time.monotonic() + 20
running = sys.argv[1] if len(sys.argv) > 1 else ""


def real(p):
    try:
        return os.path.realpath(p)
    except OSError:
        return p


def runnable(p):
    return os.path.isfile(p) and os.access(p, os.X_OK)


def pkg_version(pkg_dir):
    try:
        with open(os.path.join(pkg_dir, "package.json"), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and data.get("name") == NPM_NAME \
            and isinstance(data.get("version"), str):
        return data["version"]
    return None


def layout_version(p):
    """Version of the install that owns p, from files only. None = layout unknown."""
    r = real(p)
    # npm: <pkg>/bin/claude.exe -> <pkg>/package.json (or the file sits directly in <pkg>)
    for d in (os.path.dirname(os.path.dirname(r)), os.path.dirname(r)):
        v = pkg_version(d)
        if v:
            return v
    # npm prefix layout reached through a bin entry that is not a symlink
    prefix = os.path.dirname(os.path.dirname(os.path.abspath(p)))
    v = pkg_version(os.path.join(prefix, "lib", "node_modules", "@anthropic-ai", "claude-code"))
    if v:
        return v
    # native installer, cask, desktop bundle: a path component that IS the version
    for comp in reversed(r.split(os.sep)):
        if re.fullmatch(r"\d+\.\d+\.\d+", comp):
            return comp
    return None


def safe_to_spawn(p):
    """Only run a file this user (or root) owns and no one else can write: the scan
    reaches into other jobs' PATHs, which the interactive user never ran."""
    try:
        st = os.stat(p)
    except OSError:
        return False
    return st.st_uid in (os.getuid(), 0) and not (st.st_mode & 0o022)


def spawn_version(p):
    left = DEADLINE - time.monotonic()
    if left <= 0 or not safe_to_spawn(p):
        return None
    try:
        out = subprocess.run([p, "--version"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=min(5, left), encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    m = VER.search(out.stdout or "")
    return m.group(0) if m else None


cands = []


def add(p):
    if p and runnable(p):
        cands.append(p)


add(running)
for d in os.environ.get("PATH", "").split(":"):
    if d:
        add(os.path.join(d, "claude"))

unreadable = 0
agents = os.path.join(HOME, "Library", "LaunchAgents")
for plist in sorted(glob.glob(os.path.join(glob.escape(agents), "*.plist"))):
    try:
        with open(plist, "rb") as fh:
            pl = plistlib.load(fh)
    except Exception:  # unreadable or malformed plist: counted, not fatal
        unreadable += 1
        continue
    env = pl.get("EnvironmentVariables") if isinstance(pl, dict) else None
    job_path = env.get("PATH") if isinstance(env, dict) else None
    if not isinstance(job_path, str) or not job_path:
        job_path = LAUNCHD_DEFAULT_PATH
    for d in job_path.split(":"):
        if d:
            add(os.path.join(d, "claude"))

known = os.environ.get("CLAUDE_VERSION_CHECK_KNOWN_INSTALLS")
if known is None:
    patterns = [
        os.path.join(glob.escape(HOME), "local", "node-*", "bin", "claude"),
        os.path.join(glob.escape(HOME), ".local", "bin", "claude"),
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
    ]
else:
    patterns = [x for x in known.split(":") if x]
for pat in patterns:
    for hit in sorted(glob.glob(pat)):
        add(hit)

bundles = []
bundle_root = os.path.join(HOME, "Library", "Application Support", "Claude", "claude-code")
for d in glob.glob(os.path.join(glob.escape(bundle_root), "*")):
    name = os.path.basename(d)
    if re.fullmatch(r"\d+\.\d+\.\d+", name):
        bundles.append((tuple(int(x) for x in name.split(".")), d))
if bundles:
    newest = sorted(bundles)[-1][1]
    inside = os.path.join(newest, "claude.app", "Contents", "MacOS", "claude")
    add(inside if runnable(inside) else os.path.join(newest, "claude"))

seen = set()
rows = []
for p in cands:
    r = real(p)
    if r in seen:
        continue
    seen.add(r)
    rows.append((layout_version(p) or spawn_version(p) or "?", p))

if len({v for v, _ in rows}) < 2:
    sys.exit(0)


def vkey(v):
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else (-1,)


def short(p):
    home = HOME.rstrip(os.sep)
    shown = "~" + p[len(home):] if home and p.startswith(home + os.sep) else p
    return re.sub(r"[\x00-\x1f\x7f]", "?", shown)


rows.sort(key=lambda row: row[1])
rows.sort(key=lambda row: vkey(row[0]), reverse=True)
shown = "; ".join("%s %s" % (v, short(p)) for v, p in rows[:8])
if len(rows) > 8:
    shown += "; +%d more" % (len(rows) - 8)
line = ("[claude-code-version] SKEW: %d Claude Code installs report %d different versions: %s. "
        "Sessions and scheduled jobs run whichever copy their PATH reaches first. "
        "Upgrade each npm install with its own --prefix; a bare npm i -g installs under "
        "whichever node comes first on PATH."
        % (len(rows), len({v for v, _ in rows}), shown))
if unreadable:
    line += " (%d LaunchAgent plist(s) could not be read.)" % unreadable
sys.stdout.buffer.write((line + "\n").encode("utf-8", "replace"))
PY

skew_line=""
if command -v python3 >/dev/null 2>&1; then
  skew_line=$(python3 -c "$SKEW_PY" "$measured_path" 2>/dev/null)
  skew_rc=$?
  if [[ "$skew_rc" -ne 0 ]]; then
    skew_line="[claude-code-version] The install-skew scan failed (python3 exited $skew_rc), so the installed copies were NOT compared."
  fi
fi

# Write $2 (empty -> an empty file) to $1 via a temp file, so a session reading
# the cache while another refreshes it never sees a half-written banner.
write_cache() {
  local f=$1 body=$2 tmp
  tmp=$(mktemp "$f.tmp.XXXXXX" 2>/dev/null) || tmp=""
  if [[ -z "$tmp" ]]; then
    if [[ -n "$body" ]]; then printf '%s\n' "$body" > "$f" 2>/dev/null; else : > "$f" 2>/dev/null; fi
    return 0
  fi
  if [[ -n "$body" ]]; then printf '%s\n' "$body" > "$tmp"; else : > "$tmp"; fi
  mv -f "$tmp" "$f" 2>/dev/null || rm -f "$tmp"
}

msg=""
if [[ "$current" != "$latest" ]]; then
  cur_patch=$(echo "$current" | awk -F. '{print $3}')
  lat_patch=$(echo "$latest" | awk -F. '{print $3}')
  gap=""
  # Both fields are external text; arithmetic on a non-number ("286-beta") would
  # abort the whole hook under `set -u`, so only subtract two plain integers.
  case "$cur_patch$lat_patch" in
    ''|*[!0-9]*) ;;
    *) [[ -n "$cur_patch" && -n "$lat_patch" ]] && gap=$(( lat_patch - cur_patch )) ;;
  esac

  # How to upgrade THE BINARY THAT WAS MEASURED. A bare `npm i -g` installs under
  # whichever node is first on PATH, which is how three copies drifted apart.
  measured_real=$(resolve_path "$measured_path")
  if [[ -n "$gap" ]] && (( gap >= WARN_VERSION_GAP )); then
    up_verb="Upgrade"; behind=" ($gap versions behind)"
  else
    up_verb="Upgrade when convenient"; behind=""
  fi
  case $measured_real in
    */lib/node_modules/@anthropic-ai/claude-code/*)
      up_prefix=$(plain "${measured_real%/lib/node_modules/@anthropic-ai/claude-code/*}")
      up_hint="$up_verb: npm i -g --prefix '$up_prefix' @anthropic-ai/claude-code@latest" ;;
    */Claude/claude-code/*/claude.app/*)
      up_hint="This is the desktop app's bundled copy; it updates with the app." ;;
    *)
      up_hint="$up_verb: npm i -g @anthropic-ai/claude-code@latest" ;;
  esac
  headline="[claude-code-version] $current ($src_label) → latest $latest${behind}. $up_hint"

  # Fetch the CHANGELOG.md diff between current and latest. Best-effort:
  # any failure here just means we fall back to the headline-only message.
  # Use a temp file rather than a pipe to avoid SIGPIPE in nested heredocs.
  diff_block=""
  changelog_tmp=$(mktemp -t claude-code-changelog.XXXXXX 2>/dev/null)
  if [[ -n "$changelog_tmp" ]]; then
    if gh api repos/anthropics/claude-code/contents/CHANGELOG.md \
         -H "Accept: application/vnd.github.raw" \
         > "$changelog_tmp" 2>/dev/null && [[ -s "$changelog_tmp" ]]; then
      diff_block=$(python3 - "$current" "$latest" "$DIFF_BULLET_LIMIT" "$changelog_tmp" <<'PY' 2>/dev/null
import sys, re
current = sys.argv[1]
latest = sys.argv[2]
limit = int(sys.argv[3])
text = open(sys.argv[4]).read()

sections = re.split(r'^## ', text, flags=re.MULTILINE)

def parse_version(s):
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)', s.strip())
    return tuple(int(x) for x in m.groups()) if m else None

cur_t = parse_version(current)
lat_t = parse_version(latest)
if not cur_t or not lat_t:
    sys.exit(0)

picked = []
for sec in sections[1:]:
    head_line = sec.split('\n', 1)[0].strip()
    v = parse_version(head_line)
    if not v:
        continue
    if cur_t < v <= lat_t:
        picked.append((v, head_line, sec))

if not picked:
    sys.exit(0)

picked.sort(reverse=True)

bullets = []
for v, head, sec in picked:
    body = sec.split('\n', 1)[1] if '\n' in sec else ''
    for line in body.splitlines():
        line = line.rstrip()
        if line.startswith('- ') and not line.startswith('  - '):
            bullets.append(f"  . [{head.split()[0]}] {line[2:]}")
            if len(bullets) >= limit:
                break
    if len(bullets) >= limit:
        break

if bullets:
    print(f"[claude-code-version] What's new since {current} (top {len(bullets)} bullets):")
    print('\n'.join(bullets))
PY
      )
    fi
    rm -f "$changelog_tmp"
  fi

  if [[ -n "$diff_block" ]]; then
    msg="${headline}
${diff_block}"
  else
    msg="$headline"
  fi
fi

if [[ -n "$skew_line" ]]; then
  if [[ -n "$msg" ]]; then
    msg="${msg}
${skew_line}"
  else
    msg=$skew_line
  fi
fi

# Cache for $CACHE_TTL_SEC. Up to date with no skew -> an empty cache, so the next
# sessions inside the window print nothing.
write_cache "$CACHE_FILE" "$msg"
if [[ -z "${CLAUDE_VERSION_CHECK_CACHE_FILE:-}" && "$CACHE_FILE" != "$LEGACY_CACHE_FILE" ]]; then
  # A reading taken from PATH's claude because the one above us reported no version
  # belongs under that one's name as well, or its next session finds nothing.
  if [[ "$LOOKUP_CACHE_FILE" != "$CACHE_FILE" && "$LOOKUP_CACHE_FILE" != "$LEGACY_CACHE_FILE" ]]; then
    write_cache "$LOOKUP_CACHE_FILE" "$msg"
  fi
  write_cache "$LEGACY_CACHE_FILE" "$msg"
  # One file per binary ever seen adds up across upgrades; drop the long-idle ones.
  find "$(dirname "$LEGACY_CACHE_FILE")" -maxdepth 1 -name "${LEGACY_CACHE_FILE##*/}.*" \
    -mtime +"$KEYED_CACHE_KEEP_DAYS" -exec rm -f {} + 2>/dev/null
fi
[[ -n "$msg" ]] && echo "$msg" >&2
exit 0

#!/usr/bin/env bash
#
# scripts/test-utf8-console-guard.sh - regression test for scripts/check-utf8-stdout.py,
# the fail-loud guard against the Windows cp1252 print crash class (ai-brain-starter#313).
#
# Bug class: a vault script that print()s the "gear Meta" emoji, an em dash, or an
# accented name works on a UTF-8 console (macOS/Linux) and silently ships. On a
# Windows cp1252 console - or a C-locale pipe - the SAME print() raises
# UnicodeEncodeError, the caller captures an empty string, and downstream logic
# misreads it (#313: sync-vault-scripts.ps1 read the empty output as "no Meta
# folder"). PR #313 fixed the two files that had already broken; this lint makes
# the NEXT one fail CI instead of a user's console.
#
# The assertions below prove the lint (a) FAILS on an unguarded non-ASCII-printing
# CLI - the negative control, because a guard earns trust only by failing on the
# thing it catches - (b) PASSES a guarded one, (c) honors the documented bypass,
# (d) does NOT over-flag a genuinely ASCII-only CLI, and (e) that the guard it
# enforces is load-bearing: the unguarded fixture actually crashes under cp1252
# while the guarded one prints clean.
#
# MYC-3520 adds the case the predicate used to be structurally blind to: a CLI
# whose source is pure ASCII but which prints a path resolved off the vault
# FILESYSTEM, where every top-level folder is emoji-prefixed. Fixtures G/H/I
# assert (f) that such a CLI is flagged unguarded and clean guarded, (g) that
# with ONLY the new resolver branch reverted the same fixture goes GREEN - so the
# check is not tautological - and (h) the runtime control: under a forced cp1252
# console the unguarded fixture really does die with UnicodeEncodeError while the
# guarded one prints the emoji path.
#
# Finally it runs the lint over the real scripts/ tree and requires it clean, so
# a future unguarded script fails here.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKER="$HERE/check-utf8-stdout.py"

fail=0
check() {  # check <description> <expected> <actual>
  if [ "$2" = "$3" ]; then
    echo "  ok: $1"
  else
    echo "  FAIL: $1"
    echo "        expected: [$2]"
    echo "        actual:   [$3]"
    fail=1
  fi
}

# Non-ASCII bytes built at runtime so THIS shell file stays ASCII-clean; the
# fixture .py files below carry the real UTF-8 bytes that trigger the crash.
GEAR="$(printf '\xe2\x9a\x99\xef\xb8\x8f')"   # U+2699 U+FE0F  "gear Meta" emoji
EMDASH="$(printf '\xe2\x80\x94')"             # U+2014          em dash

base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT

# The checker reads its inputs through the shared bounded-read primitive and
# resolves it as <checker>/../hooks/_lib. Any COPY of the checker therefore
# needs that layout around it, or it dies on import and every fixture using the
# copy reports a misleading verdict. Mirror the real tree once, here.
mkdir -p "$base/scripts" "$base/hooks/_lib"
cp "$HERE/../hooks/_lib/__init__.py" "$base/hooks/_lib/__init__.py"
cp "$HERE/../hooks/_lib/safe_read.py" "$base/hooks/_lib/safe_read.py"

# A CRASH IS NOT A VERDICT. A traceback (say, the checker's own imports failing
# in a copied tree) exits 1 exactly like a real violation, so a fixture that
# expects 1 would go green while asserting nothing. Both helpers echo the
# literal string CRASH in that case, which matches no expected value and fails
# the assertion loudly. This hole was live: fixture I's reverted-checker copy
# could not import _lib and "reverted checker still flags the non-ASCII-source
# class (exit 1)" passed on the traceback.
_rc_of() {  # _rc_of <python-args...> -> exit code, or CRASH
  local _err _code
  _err="$(mktemp)"
  if python3 "$@" >/dev/null 2>"$_err"; then _code=0; else _code=$?; fi
  if grep -q '^Traceback (most recent call last):' "$_err"; then _code="CRASH"; fi
  rm -f "$_err"
  echo "$_code"
}

rc() {  # rc <file...> -> echo the checker's exit code without tripping set -e
  _rc_of "$CHECKER" "$@"
}

# --- Fixture A: unguarded CLI that prints non-ASCII (the crash class) --------
cat > "$base/unguarded.py" <<PY
#!/usr/bin/env python3
import sys


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")


if __name__ == "__main__":
    main()
PY
check "unguarded non-ASCII CLI is FLAGGED (exit 1)" "1" "$(rc "$base/unguarded.py")"

# --- Fixture B: same, guarded -> passes -------------------------------------
cat > "$base/guarded.py" <<PY
#!/usr/bin/env python3
import sys


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    main()
PY
check "guarded non-ASCII CLI PASSES (exit 0)" "0" "$(rc "$base/guarded.py")"

# --- Fixture C: unguarded but opted out via the documented bypass ------------
cat > "$base/bypass.py" <<PY
#!/usr/bin/env python3
# utf8-stdout-ok: console output below is provably ASCII; non-ASCII is doc only.
import sys


def main():
    print("${GEAR}")  # marker only


if __name__ == "__main__":
    main()
PY
check "bypass marker is honored (exit 0)" "0" "$(rc "$base/bypass.py")"

# --- Fixture D: genuinely ASCII-only CLI -> never flagged (no over-strict) ---
cat > "$base/ascii_only.py" <<'PY'
#!/usr/bin/env python3
import sys


def main():
    print("plain ascii output only, count", len(sys.argv))


if __name__ == "__main__":
    main()
PY
check "ASCII-only CLI is NOT flagged (exit 0)" "0" "$(rc "$base/ascii_only.py")"

# --- Fixture E: the guard is load-bearing under a real cp1252 console --------
if PYTHONIOENCODING=cp1252 PYTHONUTF8=0 python3 "$base/unguarded.py" >/dev/null 2>"$base/err"; then
  check "unguarded fixture CRASHES under cp1252" "crash" "no-crash"
else
  if grep -q UnicodeEncodeError "$base/err"; then
    check "unguarded fixture CRASHES under cp1252" "crash" "crash"
  else
    check "unguarded fixture CRASHES under cp1252" "crash" "other-error"
  fi
fi
if out="$(PYTHONIOENCODING=cp1252 PYTHONUTF8=0 python3 "$base/guarded.py" 2>/dev/null)"; then
  case "$out" in
    *Meta*) check "guarded fixture PRINTS under cp1252" "ok" "ok" ;;
    *)      check "guarded fixture PRINTS under cp1252" "ok" "bad-output[$out]" ;;
  esac
else
  check "guarded fixture PRINTS under cp1252" "ok" "crash"
fi

# =============================================================================
# MYC-3520: the ASCII-ONLY CLI that prints a RUNTIME emoji path.
#
# The lint used to state: "A genuinely ASCII-only CLI (no non-ASCII byte
# anywhere) can never hit the crash and is never flagged." That premise is FALSE.
# The crash comes from the VALUE printed, not from a literal in the source. Every
# vault's top-level folders are emoji-prefixed ("<gear> Meta/"), so a pure-ASCII
# script that resolves a Meta dir and prints it crashes on cp1252 exactly like
# one with the emoji inline - and the old predicate could not see it. Six shipped
# scripts/*.py were in that state (guarded by hand in #404, but still invisible
# to the lint). Fixtures G/H/I lock the widened predicate.
# =============================================================================

# A real emoji-named Meta folder on disk: U+2699 U+FE0F + " Meta", spelled with
# chr() so THIS shell file and the fixtures below stay byte-for-byte ASCII. That
# is the whole point - none of the sources carry the crashing bytes; the vault
# does.
vault="$base/vault"
python3 -c "import sys,pathlib; (pathlib.Path(sys.argv[1])/(chr(0x2699)+chr(0xFE0F)+' Meta')/'Decisions').mkdir(parents=True, exist_ok=True)" "$vault"

is_ascii() {  # is_ascii <file> -> "ascii" | "non-ascii"
  python3 -c "import sys; d=open(sys.argv[1],'rb').read(); print('non-ascii' if any(b>0x7f for b in d) else 'ascii')" "$1"
}
rc_with() {  # rc_with <checker> <file...> -> exit code, or CRASH (see _rc_of)
  _rc_of "$@"
}

# --- Fixture G: ASCII-only, resolves a Meta dir, prints it, NO guard ---------
# A faithful miniature of the six: imports the REAL scripts/_meta_resolver.py,
# resolves the emoji Meta dir off the filesystem, prints the Path.
cat > "$base/meta_path_unguarded.py" <<'PY'
#!/usr/bin/env python3
"""ASCII-only CLI that prints a Meta path resolved at runtime.

usage: meta_path_unguarded.py REPO_SCRIPTS_DIR VAULT_ROOT
"""
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from _meta_resolver import find_meta_dir  # noqa: E402


def main():
    meta = find_meta_dir(Path(sys.argv[2]))
    print("META: {}".format(meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

# The control is only meaningful if the fixture is genuinely ASCII: otherwise the
# OLD "source carries non-ASCII" signal would catch it and prove nothing.
check "Meta-path fixture source is genuinely ASCII-only" \
  "ascii" "$(is_ascii "$base/meta_path_unguarded.py")"
check "ASCII-only Meta-path CLI without the guard is FLAGGED (exit 1)" \
  "1" "$(rc "$base/meta_path_unguarded.py")"

# --- Fixture H: identical, guarded -> passes ---------------------------------
cat > "$base/meta_path_guarded.py" <<'PY'
#!/usr/bin/env python3
"""ASCII-only CLI that prints a Meta path resolved at runtime. Guarded.

usage: meta_path_guarded.py REPO_SCRIPTS_DIR VAULT_ROOT
"""
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from _meta_resolver import find_meta_dir  # noqa: E402


def main():
    meta = find_meta_dir(Path(sys.argv[2]))
    print("META: {}".format(meta))
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
PY
check "same fixture WITH the guard PASSES (exit 0)" \
  "0" "$(rc "$base/meta_path_guarded.py")"

# --- Fixture I: the negative control is LIVE, not tautological ---------------
# Build a copy of the checker with ONLY the resolver branch neutered (its regex
# rewritten to never match) and require the fixture to go GREEN under it. That is
# "revert the new check and the fixture stops failing", asserted instead of
# claimed - it proves the flag above comes from the NEW branch and not from some
# pre-existing signal. Fails loud if the anchor line is gone (control went blind).
python3 - "$CHECKER" "$base/scripts/checker-reverted.py" <<'PY'
import sys

src = open(sys.argv[1], encoding="utf-8").read().splitlines(keepends=True)
anchor = "_RESOLVER_RE = re.compile("
hits = [i for i, line in enumerate(src) if line.startswith(anchor)]
if len(hits) != 1:
    sys.stderr.write(
        "BLIND CONTROL: expected exactly ONE line starting with '%s' in %s, "
        "found %d. The negative control can no longer revert the resolver "
        "branch - update this test to track the new shape, or it is asserting "
        "nothing.\n" % (anchor, sys.argv[1], len(hits))
    )
    raise SystemExit(3)
src[hits[0]] = '_RESOLVER_RE = re.compile(r"(?!x)x")  # neutered for the negative control\n'
open(sys.argv[2], "w", encoding="utf-8").write("".join(src))
PY
check "with the resolver branch REVERTED, the fixture goes GREEN (exit 0)" \
  "0" "$(rc_with "$base/scripts/checker-reverted.py" "$base/meta_path_unguarded.py")"
# ...and the reverted checker must still catch the ORIGINAL non-ASCII class, so
# the revert is surgical (only the new branch was removed).
check "reverted checker still flags the non-ASCII-source class (exit 1)" \
  "1" "$(rc_with "$base/scripts/checker-reverted.py" "$base/unguarded.py")"

# --- Runtime control: the crash the lint is only a proxy for ------------------
# The lint asserts a source property; THIS asserts the behaviour. Force a cp1252
# console (portable: PYTHONIOENCODING works on Windows, macOS and the Linux CI
# runner) and require the unguarded fixture to die with UnicodeEncodeError on a
# path whose emoji came from the FILESYSTEM, and the guarded one to print it.
if PYTHONIOENCODING=cp1252 PYTHONUTF8=0 python3 "$base/meta_path_unguarded.py" "$HERE" "$vault" \
     >/dev/null 2>"$base/meta_err"; then
  check "unguarded Meta-path fixture CRASHES under cp1252" "crash" "no-crash"
elif grep -q UnicodeEncodeError "$base/meta_err"; then
  check "unguarded Meta-path fixture CRASHES under cp1252" "crash" "crash"
else
  echo "        stderr was: $(tr '\n' ' ' < "$base/meta_err")"
  check "unguarded Meta-path fixture CRASHES under cp1252" "crash" "other-error"
fi
if out="$(PYTHONIOENCODING=cp1252 PYTHONUTF8=0 python3 "$base/meta_path_guarded.py" "$HERE" "$vault" 2>/dev/null)"; then
  case "$out" in
    *META:*Meta*) check "guarded Meta-path fixture PRINTS the path under cp1252" "ok" "ok" ;;
    *)            check "guarded Meta-path fixture PRINTS the path under cp1252" "ok" "bad-output[$out]" ;;
  esac
else
  check "guarded Meta-path fixture PRINTS the path under cp1252" "ok" "crash"
fi

# =============================================================================
# MYC-3530: the SCOPE gap. Everything above tests the PREDICATE. None of it
# tested WHICH FILES the predicate is pointed at, and the answer was
# "scripts/*.py only" - so hooks/, the surface where this crash is WORSE, had
# never been scanned. A hook that dies mid-gate either fails silently open or
# denies every Write with no legible cause (#375, #409).
#
# Fixtures J/K/L assert (i) a planted unguarded hook that prints a Meta path
# FAILS the fleet lint, (ii) the same hook PASSES once guarded, (iii) with ONLY
# the scan-scope reverted to scripts-only the planted hook goes GREEN - so the
# widening is load-bearing and not tautological - and (iv) the revert is
# surgical: the scripts-only checker still fails a planted SCRIPT.
#
# Fixtures M/N assert the ratchet: a pinned row pardons, an EDITED pinned file
# goes STALE, and the pin is over NEWLINE-NORMALIZED content so a CRLF checkout
# and an LF checkout produce the same digest (#411 - hashing raw pins the
# CHECKOUT, not the CONTENT, and reds the other platform).
#
# These run against a hermetic throwaway git repo, never the real tree: the
# fleet scan is defined by `git ls-files` from the checker's own repo root, so
# planting into the real checkout would be the only alternative and would leave
# debris on an interrupted run.
# =============================================================================

repo="$base/fleet"
mkdir -p "$repo/scripts" "$repo/hooks/_lib"
cp "$CHECKER" "$repo/scripts/check-utf8-stdout.py"
cp "$HERE/_meta_resolver.py" "$repo/scripts/_meta_resolver.py"
# The planted hook below is DELIBERATELY unguarded (that is what fixtures J/K/L
# assert), and it imports + calls this resolver. The real scripts/_meta_resolver.py
# keeps its guard inside a function, which the seam rule correctly does not count
# as module scope -- so in the real tree that pair is safe only because every
# importer carries its own guard, and here it would form a genuine seam and red
# fixture M, which is testing the BASELINE RATCHET, not seams. Guard the COPY at
# module scope so each fixture exercises exactly one rule. Appending is enough:
# module-scope code runs at import, before any of its functions are called.
cat >> "$repo/scripts/_meta_resolver.py" <<'PY'

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
PY
# The checker reads its inputs through the shared bounded-read primitive
# (scripts/check-cloud-safe-file-walkers.py obliges it), and resolves _lib
# relative to its OWN repo root -- so the hermetic fleet needs the package too,
# or the copied checker dies on import and every fixture below reports a
# misleading "no".
cp "$HERE/../hooks/_lib/__init__.py" "$repo/hooks/_lib/__init__.py"
cp "$HERE/../hooks/_lib/safe_read.py" "$repo/hooks/_lib/safe_read.py"
git -C "$repo" init -q >/dev/null 2>&1
FLEET="$repo/scripts/check-utf8-stdout.py"
BASELINE="$repo/scripts/utf8-stdout-baseline.txt"
echo "# hermetic fixture baseline - intentionally empty" > "$BASELINE"

# The planted hook is a faithful miniature of the real population: ASCII-only
# source, resolves a Meta dir off the FILESYSTEM, prints the path. Its flag can
# therefore only come from the resolver signal + the scan reaching hooks/.
planted="$repo/hooks/planted-meta-print.py"
cat > "$planted" <<'PY'
#!/usr/bin/env python3
"""PreToolUse-shaped hook that prints a Meta path resolved at runtime.

usage: planted-meta-print.py VAULT_ROOT
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _meta_resolver import find_meta_dir  # noqa: E402


def main():
    meta = find_meta_dir(Path(sys.argv[1]))
    print("GATE: inspecting {}".format(meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

# The control is only meaningful if the fixture is genuinely ASCII: otherwise
# the ORIGINAL non-ASCII-source signal would catch it and prove nothing about
# scope.
check "planted hook source is genuinely ASCII-only" "ascii" "$(is_ascii "$planted")"

# --- Fixture J: the planted hook FAILS the fleet lint ------------------------
check "planted unguarded hooks/ CLI FAILS the fleet lint (exit 1)" \
  "1" "$(rc_with "$FLEET")"
# Exit code alone could come from anything in the fixture repo; require the
# planted hook to be NAMED, so this cannot pass green-for-the-wrong-reason.
named="$(python3 "$FLEET" 2>&1 | grep -c 'planted-meta-print.py' || true)"
check "the failure NAMES the planted hook" "yes" "$([ "$named" -gt 0 ] && echo yes || echo no)"

# --- Fixture K: same hook, guarded -> the fleet lint passes ------------------
cp "$planted" "$base/planted-backup.py"
python3 - "$planted" <<'PY'
import sys
p = sys.argv[1]
src = open(p, encoding="utf-8").read()
src = src.replace(
    'if __name__ == "__main__":\n    raise SystemExit(main())\n',
    'if __name__ == "__main__":\n'
    '    for _stream in (sys.stdout, sys.stderr):\n'
    '        try:\n'
    '            _stream.reconfigure(encoding="utf-8")  # Python 3.7+\n'
    '        except (AttributeError, ValueError):\n'
    '            pass\n'
    '    raise SystemExit(main())\n',
)
open(p, "w", encoding="utf-8", newline="\n").write(src)
PY
check "planted hooks/ CLI WITH the guard passes the fleet lint (exit 0)" \
  "0" "$(rc_with "$FLEET")"
cp "$base/planted-backup.py" "$planted"   # back to unguarded for the control

# --- Fixture L: the scope widening is LIVE, not tautological -----------------
# Build a copy of the checker with ONLY the scan scope reverted to the
# pre-MYC-3530 tuple and require the planted hook to go GREEN under it. That is
# "revert the scope change and the fixture stops failing", asserted instead of
# claimed. Fails loud if the anchor line is gone (control went blind).
python3 - "$FLEET" "$repo/scripts/checker-scripts-only.py" <<'PY'
import sys

src = open(sys.argv[1], encoding="utf-8").read().splitlines(keepends=True)
anchor = "_SCAN_PATHSPECS = ("
hits = [i for i, line in enumerate(src) if line.startswith(anchor)]
if len(hits) != 1:
    sys.stderr.write(
        "BLIND CONTROL: expected exactly ONE line starting with '%s' in %s, "
        "found %d. The negative control can no longer revert the scan scope - "
        "update this test to track the new shape, or it is asserting nothing.\n"
        % (anchor, sys.argv[1], len(hits))
    )
    raise SystemExit(3)
src[hits[0]] = '_SCAN_PATHSPECS = ("scripts/*.py",)  # pre-MYC-3530, for the negative control\n'
open(sys.argv[2], "w", encoding="utf-8", newline="\n").write("".join(src))
PY
check "with the scan scope REVERTED to scripts-only, the planted hook goes GREEN (exit 0)" \
  "0" "$(rc_with "$repo/scripts/checker-scripts-only.py")"

# ...and the revert must be surgical: scripts/ is still scanned, so the SAME
# body planted under scripts/ still fails the scripts-only checker. Without
# this, a control that broke the checker entirely would also "pass".
cp "$planted" "$repo/scripts/planted-meta-print.py"
check "reverted checker still FAILS the same body planted under scripts/ (exit 1)" \
  "1" "$(rc_with "$repo/scripts/checker-scripts-only.py")"
rm -f "$repo/scripts/planted-meta-print.py"

# --- Fixture M: the ratchet pardons a pinned row and BITES on an edit --------
pin() {  # pin <relpath> -> append a baseline row for its normalized content
  python3 - "$repo" "$1" "$BASELINE" <<'PY'
import hashlib, sys
from pathlib import Path
root, rel, baseline = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
text = (root / rel).read_bytes().decode("utf-8", "replace")
norm = text.replace("\r\n", "\n").replace("\r", "\n")
digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
with baseline.open("a", encoding="utf-8", newline="\n") as fh:
    fh.write("{} SEV-1-hard-crash {}\n".format(digest, rel))
PY
}
pin "hooks/planted-meta-print.py"
check "a pinned legacy row PARDONS the file (exit 0)" "0" "$(rc_with "$FLEET")"

printf '\n# touched\n' >> "$planted"
check "EDITING a pinned file goes STALE and fails (exit 1)" "1" "$(rc_with "$FLEET")"
stale_named="$(python3 "$FLEET" 2>&1 | grep -c 'STALE BASELINE' || true)"
check "the stale row is reported as STALE BASELINE" \
  "yes" "$([ "$stale_named" -gt 0 ] && echo yes || echo no)"

# --- Fixture N: the pin is over CONTENT, not the checkout (#411) -------------
# Same body written LF and then CRLF must hash identically, or a baseline pinned
# on a Windows checkout reds every row on the Linux runner (and vice versa).
digests="$(python3 - "$FLEET" <<'PY'
import importlib.util, sys, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("cu", sys.argv[1])
cu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cu)
body = 'import sys\n\n\ndef main():\n    print("x")\n\n\nif __name__ == "__main__":\n    main()\n'
out = []
with tempfile.TemporaryDirectory() as td:
    for name, data in (("lf.py", body), ("crlf.py", body.replace("\n", "\r\n"))):
        p = Path(td) / name
        p.write_bytes(data.encode("utf-8"))
        out.append(cu.content_digest(p))
print("same" if out[0] == out[1] else "DIFFER:%s/%s" % (out[0][:8], out[1][:8]))
PY
)"
check "LF and CRLF copies of one body hash IDENTICALLY (content-pinned)" "same" "$digests"

# =============================================================================
# THE LAUNCHER SEAM (#652 follow-up): two files that each pass ALONE while the
# seam between them is unguarded.
#
# scripts/vault-metadata-extract.py and scripts/journal-metadata-extract.py are
# thin launchers - they have `__main__` but print nothing of their own, so the
# per-file predicate never flags them. extractors/_dispatcher.py prints plenty
# and DID carry the guard - inside its own `if __name__ == "__main__":`, which
# never executes when a launcher does `import _dispatcher; _dispatcher.main()`.
# That is the only supported way to run extraction, so the entire metadata run
# had no cp1252 protection while both files linted clean.
#
# Measured before the fix on an emoji vault path under PYTHONIOENCODING=cp1252:
# the launcher died with UnicodeEncodeError at `print(f"Vault: {VAULT}")` while
# running _dispatcher.py directly exited 0 - same code, same vault, same
# console, differing only in which __main__ ran.
#
# Fixtures O/P/Q/R lock the cross-file check: (O) each file clean alone but the
# PAIR flagged, (P) moving the guard to module scope clears it, (Q) a guarded
# importer is NOT a seam (the clause that keeps this quiet on the repo's four
# benign importers), (R) the runtime control - the pair really does crash under
# cp1252 and really is clean once the guard moves.
# =============================================================================

seam="$base/seam"
mkdir -p "$seam"

write_seam_module() {  # write_seam_module <main-only|module-scope>
  if [ "$1" = "main-only" ]; then
    cat > "$seam/seammod.py" <<PY
#!/usr/bin/env python3
import sys


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass
    main()
PY
  else
    cat > "$seam/seammod.py" <<PY
#!/usr/bin/env python3
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # Python 3.7+
    except (AttributeError, ValueError):
        pass


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")
    return 0


if __name__ == "__main__":
    main()
PY
  fi
}

write_seam_launcher() {  # write_seam_launcher <unguarded|guarded>
  if [ "$1" = "unguarded" ]; then
    cat > "$seam/seamlaunch.py" <<'PY'
#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import seammod  # noqa: E402

if __name__ == "__main__":
    sys.exit(seammod.main() or 0)
PY
  else
    cat > "$seam/seamlaunch.py" <<'PY'
#!/usr/bin/env python3
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # Python 3.7+
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import seammod  # noqa: E402

if __name__ == "__main__":
    sys.exit(seammod.main() or 0)
PY
  fi
}

# --- Fixture O: each file clean ALONE, the PAIR is flagged -------------------
write_seam_module main-only
write_seam_launcher unguarded
check "seam: launcher ALONE is not flagged (it prints nothing)" \
  "0" "$(rc "$seam/seamlaunch.py")"
check "seam: module ALONE is not flagged (it has a guard)" \
  "0" "$(rc "$seam/seammod.py")"
check "seam: the PAIR is FLAGGED (exit 1) - the seam the old predicate missed" \
  "1" "$(rc "$seam/seamlaunch.py" "$seam/seammod.py")"
seam_named="$(python3 "$CHECKER" "$seam/seamlaunch.py" "$seam/seammod.py" 2>&1 \
  | grep -c "seammod.py has its UTF-8 console guard only under" || true)"
check "seam: the failure NAMES the imported module" \
  "yes" "$([ "$seam_named" -gt 0 ] && echo yes || echo no)"

# --- Fixture P: guard moved to MODULE scope clears the seam ------------------
write_seam_module module-scope
check "seam: guard at MODULE scope clears the seam (exit 0)" \
  "0" "$(rc "$seam/seamlaunch.py" "$seam/seammod.py")"

# --- Fixture Q: a GUARDED importer is not a seam (no false positive) ---------
# .reconfigure() mutates the process-wide sys.stdout, so an importer that
# guards its own streams has already protected everything it then calls. Without
# this clause the check would fire on every benign importer in the repo.
write_seam_module main-only
write_seam_launcher guarded
check "seam: a GUARDED importer is NOT reported (exit 0)" \
  "0" "$(rc "$seam/seamlaunch.py" "$seam/seammod.py")"

# --- Fixture R: the runtime control - the seam really crashes under cp1252 ---
write_seam_module main-only
write_seam_launcher unguarded
if PYTHONIOENCODING=cp1252 PYTHONUTF8=0 python3 "$seam/seamlaunch.py" >/dev/null 2>"$seam/err"; then
  check "seam: unguarded launcher CRASHES under cp1252" "crash" "no-crash"
else
  if grep -q UnicodeEncodeError "$seam/err"; then
    check "seam: unguarded launcher CRASHES under cp1252" "crash" "crash"
  else
    check "seam: unguarded launcher CRASHES under cp1252" "crash" "other-error"
  fi
fi
write_seam_module module-scope
if seam_out="$(PYTHONIOENCODING=cp1252 PYTHONUTF8=0 python3 "$seam/seamlaunch.py" 2>/dev/null)"; then
  case "$seam_out" in
    *Meta*) check "seam: SAME launcher PRINTS once the guard moves to module scope" "ok" "ok" ;;
    *)      check "seam: SAME launcher PRINTS once the guard moves to module scope" "ok" "bad-output[$seam_out]" ;;
  esac
else
  check "seam: SAME launcher PRINTS once the guard moves to module scope" "ok" "crash"
fi

# --- Fixture S: the target has NO guard at all -- the WORSE case -------------
# The first cut of this check required the target's guard to be __main__-only,
# so a printing module with ZERO guard and no __main__ was invisible to BOTH
# rules: the per-file rule skips it (is_cli false, it is a library) and the seam
# rule skipped it too. That is strictly worse than a __main__-only guard, which
# at least fires on direct execution. Two live pairs in this repo were in
# exactly that state when this fixture was written.
write_seam_launcher unguarded
cat > "$seam/seammod.py" <<PY
#!/usr/bin/env python3
import sys


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")
    return 0
PY
check "seam: a target with NO guard and no __main__ is FLAGGED (exit 1)" \
  "1" "$(rc "$seam/seamlaunch.py" "$seam/seammod.py")"
noguard_msg="$(python3 "$CHECKER" "$seam/seamlaunch.py" "$seam/seammod.py" 2>&1 \
  | grep -c "carries NO UTF-8 console guard at all" || true)"
check "seam: the message says NO guard, not 'only under __main__'" \
  "yes" "$([ "$noguard_msg" -gt 0 ] && echo yes || echo no)"

# --- Fixture T: protection inherited from a module-scope import --------------
# A module with no guard of its own is still safe if it imports, at module
# scope, an in-scope module whose guard IS module-scope: that import
# reconfigures the shared streams before any of its functions can print. This
# is the real shape in this repo (extractors/_dispatcher.py -> _base.py), and
# without it the gate would fire on a correctly-protected pair.
cat > "$seam/seamdep.py" <<'PY'
#!/usr/bin/env python3
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
PY
cat > "$seam/seammod.py" <<PY
#!/usr/bin/env python3
import sys

import seamdep  # noqa: F401  -- module-scope guard arrives with this import


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")
    return 0
PY
check "seam: target protected via a module-scope import is NOT flagged (exit 0)" \
  "0" "$(rc "$seam/seamlaunch.py" "$seam/seammod.py" "$seam/seamdep.py")"
# ...and that exemption must be LOAD-BEARING: strip the dependency's guard and
# the same three files must go back to failing.
cat > "$seam/seamdep.py" <<'PY'
#!/usr/bin/env python3
import sys  # noqa: F401  -- no guard here any more
PY
check "seam: with the dependency's guard REMOVED, the pair FAILS again (exit 1)" \
  "1" "$(rc "$seam/seamlaunch.py" "$seam/seammod.py" "$seam/seamdep.py")"

# --- Fixture U: a guard inside a FUNCTION is not module scope ----------------
# reconfigure() in a never-called (or merely not-yet-called) function runs only
# if something calls it, so it cannot protect an import path. Position-based
# detection counted it as a guard.
cat > "$seam/seammod.py" <<PY
#!/usr/bin/env python3
import sys


def _setup():
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main():
    print("MARK ${GEAR} Meta ${EMDASH} done")
    return 0
PY
check "seam: a guard inside a function does NOT count as module scope (exit 1)" \
  "1" "$(rc "$seam/seamlaunch.py" "$seam/seammod.py")"

# --- Fixture F: the real scripts/ + hooks/ tree must be clean ----------------
check "real scripts/ + hooks/ tree passes the lint (exit 0)" "0" "$(rc)"

if [ "$fail" != 0 ]; then
  echo "FAILED: utf8-console-guard regression test"
  exit 1
fi
echo "PASSED: utf8-console-guard regression test"

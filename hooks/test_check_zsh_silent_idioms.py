#!/usr/bin/env python3
"""Controls for check-zsh-silent-idioms.py.

THE NEGATIVE CONTROL IS THE POINT. A guard earns trust only by failing on the
thing it catches. This hook's whole job is to refuse command shapes that, under
zsh, run, exit 0 and return a wrong answer that looks like a right one -- so a
guard that silently did nothing would be indistinguishable from the bug it
exists to prevent, and from a correctly-quiet run. Every leg below drives the
REAL hook as a subprocess over REAL stdin JSON and asserts on the signal a
caller actually reads.

WHY EXIT CODE IS NOT THE ASSERTION, and this is the load-bearing detail: the
hook exits 0 on EVERY path, deny included. The refusal travels as
`hookSpecificOutput.permissionDecision == "deny"` on stdout. A test asserting
`returncode != 0` would pass identically against a hook that had been gutted to
`sys.exit(0)`. So every leg here asserts the PARSED DECISION, never the status.

The two defects being guarded, for whoever reads this next. Both are silent
under zsh and both are correct in bash, so they only bite on a zsh box:
  * `git show "$SHA:src/app.py"` -- `$VAR:` is a history modifier, so the
    command emits nothing and succeeds. Every absence concluded from it is a
    false clean.
  * `set -- $r` / `for c in $CHECKS` -- zsh does not word-split an unquoted
    parameter expansion, so `$1` holds the whole string and the loop runs once.

Detector 1, git-ref (any shell):
   1. DENIES  git show "$SHA:path"                  <- the incident shape
   2. DENIES  git show $SHA:path                    <- unquoted, same hazard
   3. DENIES  git grep -n foo "$REF:path"           <- not just `show`
   4. SILENT  git show "${SHA}:path"                <- the correct form
   5. SILENT  git show origin/main:path             <- literal ref, no variable
   6. SILENT  echo "$MSG: done"                     <- a colon after a var is
                                                       not a git object read
   7. SILENT  git log --format="%H"                 <- ordinary git
   8. SILENT  non-Bash tool                         <- wrong tool, no opinion
   9. SILENT  malformed stdin                       <- fail-open, never crash
  10. Bypass honored from the ENVIRONMENT
  11. Bypass honored INLINE (VAR=1 prefix)
  12. DENIES when the bypass token appears only in a HEREDOC BODY, with a real
      offending command chained after it. A guard whose own bypass token can be
      smuggled in as decoration is disarmed by ordinary text -- the MYC-4724
      GUARD-DISARMED-BY-ITS-OWN-OUTPUT class.
  13. The deny reason names the offending variable AND shows the braced fix, so
      the refusal is actionable rather than merely obstructive.

Detector 2, word-split (zsh only):
  14. DENIES the witnessed commands VERBATIM, plus every other shape it owns.
  15. SILENT on every allowed form: `${=v}`, `"$@"`, `$@`, command
      substitution, an array assigned in the same command, literal lists,
      `bash -c` / `sh -c` strings, heredoc bodies, quoted words, comments.
  16. The shell gate follows how Claude Code picks the Bash tool's shell
      (CLAUDE_CODE_SHELL, then SHELL, then whether zsh is installed): silent on
      a bash box, while detector 1 still fires there.
  17. The bypass covers this detector too, and cannot be smuggled in.
  18. The reason names the trap, the variable and all three fixes, and does
      not print the bypass token.

Both detectors:
  19. ISOLATION. A detector that raises is skipped loudly and never disarms
      the other, in either order, and a partial install that lacks the shared
      parser still leaves detector 1 armed.
  20. One command that trips both gets ONE deny carrying both blocks.

Detector 1 again:
  21. Detector 1 reads CODE, not text. Ordinary commands that merely contain a
      `$VAR:` stay allowed (a different statement, a URL's host:port, single
      quotes, comments, heredoc bodies) and the real shapes still deny.
  22. The verb list also covers `git rev-parse` and `git ls-tree`, which take a
      <rev>:<path> spec too.
  23. The detector-1 refusal says the unbraced form is unpredictable, and does
      not claim the command prints nothing (zsh can also fail outright).

Stdlib only. Exit 0 = all pass.
"""

from __future__ import annotations

import atexit
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
HOOK = HOOKS_DIR / "check-zsh-silent-idioms.py"
BYPASS = "ZSH_SILENT_IDIOMS_BYPASS"

FAILURES: list[str] = []
CHECKS = 0

W_SET = 'for r in "repo 1420 1421"; do set -- $r; echo "$1"; done'   # witnessed
W_FOR = 'for c in $CHECKS; do node "$c"; done'                      # witnessed

# A stub `zsh` on PATH makes "zsh is installed" true on any runner, and an empty
# PATH dir makes it false, so the shell-gate legs never depend on the machine.
ZSH_DIR = tempfile.mkdtemp(prefix="zsh-present-")
NO_ZSH_DIR = tempfile.mkdtemp(prefix="zsh-absent-")
atexit.register(shutil.rmtree, ZSH_DIR, ignore_errors=True)
atexit.register(shutil.rmtree, NO_ZSH_DIR, ignore_errors=True)
for _name in ("zsh", "zsh.exe", "zsh.cmd"):
    _stub = Path(ZSH_DIR) / _name
    _stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    _stub.chmod(0o755)


def run_full(command: str, *, tool: str = "Bash", env: dict | None = None,
             raw: str | None = None, hook: Path = HOOK) -> tuple[int, str, str]:
    """Drive the real hook over real stdin. Returns (returncode, stdout, stderr).

    `env` values of None REMOVE the variable from the child environment.
    """
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command}}
    )
    child_env = dict(os.environ)
    child_env.pop(BYPASS, None)               # never inherit a bypass from the runner
    child_env.pop("CLAUDE_CODE_SHELL", None)  # nor a shell override
    # Detector 2 arms only when the Bash tool's shell is zsh. Pin that: SHELL says
    # zsh and a stub `zsh` is on PATH, so the answer never depends on the runner.
    child_env["SHELL"] = "/bin/zsh"
    child_env["PATH"] = ZSH_DIR + os.pathsep + child_env.get("PATH", "")
    for key, value in (env or {}).items():
        if value is None:
            child_env.pop(key, None)
        else:
            child_env[key] = value
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=payload,
        capture_output=True,
        text=True,
        # Decode explicitly: `text=True` alone uses the LOCALE encoding, which
        # raises UnicodeDecodeError on a non-UTF-8 Windows console for any
        # non-ASCII path or output. The deny reason here carries em dashes.
        encoding="utf-8",
        errors="replace",
        env=child_env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run(command: str, **kw) -> tuple[int, str]:
    code, out, _ = run_full(command, **kw)
    return code, out


def decision(stdout: str) -> str | None:
    """The signal a caller actually reads. None when the hook stayed silent."""
    if not stdout.strip():
        return None
    try:
        parsed = json.loads(stdout)
    except Exception:
        return f"UNPARSEABLE:{stdout[:80]}"
    return (parsed.get("hookSpecificOutput") or {}).get("permissionDecision")


def reason_of(command: str, **kw) -> str:
    _, out = run(command, **kw)
    parsed = json.loads(out) if out.strip() else {}
    return (parsed.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}".rstrip(": "))


def expect_deny(label: str, command: str, **kw) -> None:
    code, out = run(command, **kw)
    got = decision(out)
    if got != "deny":
        check(label, False, f"expected deny, got {got!r} (rc={code})")
    elif code != 0:
        # The contract is "deny via stdout, always exit 0". A non-zero exit here
        # would break the wrapper, which treats a crash as fail-open.
        check(label, False, f"denied but exited {code}, expected 0")
    else:
        check(label, True)


def expect_silent(label: str, command: str, **kw) -> None:
    code, out = run(command, **kw)
    got = decision(out)
    if got is not None:
        check(label, False, f"expected silence, got {got!r}")
    elif code != 0:
        check(label, False, f"silent but exited {code}, expected 0")
    else:
        check(label, True)


def load_hook():
    spec = importlib.util.spec_from_file_location("check_zsh_silent_idioms", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if not HOOK.exists():
        print(f"FAIL: hook not found at {HOOK}")
        return 1

    # ===== Detector 1: git-ref ================================================
    # --- 1-3: the shapes that must be refused --------------------------------
    expect_deny("1 quoted $SHA:path", 'git show "$SHA:src/app.py"')
    expect_deny("2 bare $SHA:path", "git show $SHA:src/app.py")
    expect_deny("3 git grep with $REF:path", 'git grep -n foo "$REF:path/x.py"')

    # --- 4-7: the shapes that must NOT be refused ----------------------------
    # A guard that fires on these trains a reflexive bypass, which disables it.
    expect_silent("4 braced ${SHA}:path", 'git show "${SHA}:src/app.py"')
    expect_silent("5 literal ref", "git show origin/main:src/app.py")
    expect_silent("6 colon after a var, not a ref", 'echo "$MSG: done"')
    expect_silent("7 ordinary git", 'git log --format="%H"')

    # --- 8-9: out of scope, and never crash ----------------------------------
    expect_silent("8 non-Bash tool", 'git show "$SHA:x.py"', tool="Read")
    code, out = run("", raw="{not json at all")
    check("9 malformed stdin is a silent exit 0",
          decision(out) is None and code == 0, f"rc={code}")

    # --- 10-11: the bypass works both ways -----------------------------------
    expect_silent("10 env bypass", 'git show "$SHA:x.py"', env={BYPASS: "1"})
    expect_silent("11 inline bypass", f'{BYPASS}=1 git show "$SHA:x.py"')

    # --- 12: the bypass token cannot be smuggled in as decoration ------------
    # A heredoc BODY is not the command line. If the hook split on newlines and
    # honored a bypass found on any segment, this decoration would disarm it.
    smuggled = f'cat <<EOF\n{BYPASS}=1\nEOF\ngit show "$SHA:x.py"'
    expect_deny("12 heredoc-smuggled bypass still denies", smuggled)

    # --- 13: the refusal is actionable ---------------------------------------
    reason = reason_of('git show "$SHA:src/app.py"')
    check("13a reason names the offending variable", "SHA" in reason)
    check("13b reason shows the braced fix", "${SHA}" in reason)
    # Printing the bypass token in the refusal is how a guard teaches its own
    # defeat (MYC-4724). The doc should carry it, not the deny message.
    check("13c reason does not print the bypass token", BYPASS not in reason)

    # ===== Detector 2: word-split =============================================
    # --- 14: the shapes that must be refused ---------------------------------
    expect_deny("14a witnessed: set -- $r inside a loop", W_SET)
    expect_deny("14b witnessed: for c in $CHECKS", W_FOR)
    expect_deny("14c bare set -- $r", "set -- $r")
    expect_deny("14d $NAME among other words", 'for x in a $v b; do echo "$x"; done')
    expect_deny("14e braced ${v}", 'for x in ${v}; do echo "$x"; done')
    expect_deny("14f only the bare word of a mixed list",
                'for x in "$a" $b; do :; done')
    expect_deny("14g scalar built from a command substitution",
                "v=$(cat list.txt); for x in $v; do :; done")
    expect_deny("14h after then", 'if [ -n "$q" ]; then for x in $v; do :; done; fi')
    expect_deny("14i inside a brace group", "echo ok && { for x in $v; do :; done; }")
    expect_deny("14j inside $( )", 'out=$(for x in $v; do echo "$x"; done)')
    expect_deny("14k array text that sits only inside a string",
                'echo "v=(a b)"; for x in $v; do :; done')
    expect_deny("14l unsetopt shwordsplit turns splitting OFF",
                "unsetopt shwordsplit; for x in $v; do :; done")
    expect_deny("14m noshwordsplit turns splitting OFF",
                "setopt noshwordsplit; for x in $v; do :; done")
    expect_deny("14n shwordsplit named only in a heredoc body",
                "cat <<EOF\nsetopt shwordsplit\nEOF\nfor x in $v; do :; done")
    expect_deny("14o multi-line loop", 'for x in $v\ndo\n  echo "$x"\ndone')

    # --- 15: the shapes that must NOT be refused -----------------------------
    silent_forms = [
        ("zsh splitting flag in a loop", "for x in ${=v}; do :; done"),
        ("zsh splitting flag in set --", "set -- ${=v}"),
        ('quoted "$@"', 'for x in "$@"; do :; done'),
        ("bare $@, which zsh splits", "for x in $@; do :; done"),
        ('set -- "$@"', 'set -- "$@"'),
        ("set -- $@", "set -- $@"),
        ("command substitution, which zsh splits", "for x in $(ls); do :; done"),
        ("backtick substitution", "for x in `ls`; do :; done"),
        ("array assigned in the same command", "v=(a b); for x in $v; do :; done"),
        ("typeset -a array", "typeset -a v; v+=(c); for x in $v; do :; done"),
        ("read -A array", 'read -A v <<< "a b"; for x in $v; do :; done'),
        ("literal words", "for x in a b c; do :; done"),
        ("glob", "for f in *.txt; do :; done"),
        ("brace range", "for n in {1..3}; do :; done"),
        ("zsh's own array parameter", 'for p in $path; do echo "$p"; done'),
        ("shwordsplit switched on", "setopt shwordsplit; for x in $v; do :; done"),
        ("quoted word", 'for x in "$v"; do :; done'),
        ("single-quoted word", "for x in '$v'; do :; done"),
        ("bash -c string", "bash -c 'for x in $v; do echo \"$x\"; done'"),
        ("sh -c string", "sh -c 'set -- $v; echo \"$1\"'"),
        ("heredoc body read by bash",
         "bash <<'EOF'\nfor x in $v; do echo \"$x\"; done\nEOF"),
        ("`for` as an argument, not a loop", "echo for x in $v"),
        ("`set` inside a quoted message", 'git commit -m "set -- $v"'),
        ("a word that merely STARTS with the parameter", "for x in $v/*.txt; do :; done"),
        ("parameter with a default", "for x in ${v:-a b}; do :; done"),
        ("array subscript expansion", "for x in ${v[@]}; do :; done"),
        ("comment line", "# for x in $v; do :; done"),
        ("comment tail", "echo ok  # for x in $v"),
        ("set without --", "set -euo pipefail"),
        ("arithmetic then a literal loop", "n=$(( 2 * 3 )); for x in a b; do :; done"),
    ]
    for label, command in silent_forms:
        expect_silent(f"15 {label}", command)
    expect_silent("15 non-Bash tool", W_FOR, tool="Read")

    # --- 16: the shell gate follows how Claude Code picks the Bash tool's shell:
    # CLAUDE_CODE_SHELL when it names bash or zsh, else bash if SHELL names bash,
    # else zsh when it is installed, else bash. `${=VAR}` is a bad substitution in
    # bash and the idiom is already correct there, so on a bash box detector 2
    # must have no opinion at all. `run_full` puts a stub zsh on PATH by default.
    expect_silent("16a SHELL=bash", W_FOR, env={"SHELL": "/bin/bash"})
    expect_deny("16b SHELL unset, zsh installed", W_FOR, env={"SHELL": None})
    expect_deny("16c SHELL=fish, zsh installed", W_FOR,
                env={"SHELL": "/usr/bin/fish"})
    expect_silent("16d SHELL unset, zsh NOT installed", W_FOR,
                  env={"SHELL": None, "PATH": NO_ZSH_DIR})
    expect_silent("16e CLAUDE_CODE_SHELL=bash beats SHELL=zsh", W_FOR,
                  env={"CLAUDE_CODE_SHELL": "/bin/bash", "SHELL": "/bin/zsh"})
    expect_deny("16f CLAUDE_CODE_SHELL=zsh beats SHELL=bash", W_FOR,
                env={"CLAUDE_CODE_SHELL": "/bin/zsh", "SHELL": "/bin/bash"})
    expect_silent("16g a CLAUDE_CODE_SHELL naming neither is ignored", W_FOR,
                  env={"CLAUDE_CODE_SHELL": "/usr/bin/fish", "SHELL": "/bin/bash"})
    expect_deny("16h detector 1 still fires on a bash box",
                'git show "$SHA:x.py"', env={"SHELL": "/bin/bash"})

    # --- 17: the bypass covers this detector, and cannot be smuggled in ------
    expect_silent("17a env bypass", W_FOR, env={BYPASS: "1"})
    expect_silent("17b inline export bypass", f"export {BYPASS}=1; {W_FOR}")
    expect_deny("17c heredoc-smuggled bypass still denies",
                f"cat <<EOF\n{BYPASS}=1\nEOF\n{W_FOR}")

    # --- 18: the refusal is actionable ---------------------------------------
    reason = reason_of(W_FOR)
    check("18a reason names the variable", "$CHECKS" in reason)
    check("18b reason names the trap", "zsh" in reason and "word-split" in reason)
    check("18c reason offers ${=VAR}", "${=CHECKS}" in reason)
    check("18d reason offers read -r a b c <<<", 'read -r a b c <<< "$CHECKS"' in reason)
    check("18e reason offers bash -c", "bash -c" in reason)
    check("18f reason does not print the bypass token", BYPASS not in reason)
    reason = reason_of("set -- $r")
    check("18g set -- reason shows the set -- fix", "set -- ${=r}" in reason)

    # ===== Both detectors =====================================================
    # --- 19: one failing detector never disarms the other --------------------
    module = load_hook()
    real = module.DETECTORS

    def boom(command, zsh):
        raise RuntimeError("injected failure")

    noise = io.StringIO()
    word_split, git_ref = [], []
    try:
        with contextlib.redirect_stderr(noise):
            module.DETECTORS = (("boom", boom),) + real
            try:
                word_split = module.run_detectors("for c in $CHECKS; do :; done", True)
            except Exception as exc:                 # the regression this leg pins
                noise.write(f"run_detectors raised {type(exc).__name__}\n")
            module.DETECTORS = real + (("boom", boom),)
            try:
                git_ref = module.run_detectors('git show "$SHA:x.py"', True)
            except Exception as exc:
                noise.write(f"run_detectors raised {type(exc).__name__}\n")
    finally:
        module.DETECTORS = real
    check("19a word-split survives a detector that raised before it",
          len(word_split) == 1 and "CHECKS" in word_split[0], noise.getvalue().strip())
    check("19b git-ref survives a detector that raised after it",
          len(git_ref) == 1 and "SHA" in git_ref[0], noise.getvalue().strip())
    check("19c the failure is loud on stderr, not silent", "boom" in noise.getvalue())

    # A partial install that lacks the shared parser: detector 2 cannot run, and
    # that must cost detector 1 nothing.
    with tempfile.TemporaryDirectory() as tmp:
        partial = Path(tmp) / HOOK.name
        shutil.copy2(HOOK, partial)
        shutil.copytree(
            HOOKS_DIR / "_lib", Path(tmp) / "_lib",
            ignore=shutil.ignore_patterns("__pycache__", "shell_parse.py"),
        )
        code, out, _ = run_full('git show "$SHA:x.py"', hook=partial)
        check("19d partial install: git-ref still denies",
              decision(out) == "deny" and code == 0, f"rc={code}")
        code, out, err = run_full(W_FOR, hook=partial)
        check("19e partial install: word-split skipped, hook does not crash",
              decision(out) is None and code == 0, f"rc={code}")
        check("19f partial install: the skip is announced on stderr",
              "word-split" in err, repr(err[:120]))

    # --- 20: one command tripping both gets one deny with both blocks --------
    both = f'git show "$SHA:src/app.py"; {W_FOR}'
    code, out = run(both)
    reason = reason_of(both)
    check("20a one deny for a command that trips both",
          decision(out) == "deny" and code == 0)
    check("20b both blocks are in it", "$SHA:" in reason and "$CHECKS" in reason)

    # --- 21: detector 1 reads CODE, not text -----------------------------------
    # Each of these was a measured wrong deny. A guard that refuses ordinary
    # commands trains a reflexive bypass, which disables it.
    for label, command in [
        ("a PATH append in another statement",
         "export PATH=$PATH:/opt/bin && git log -1 --oneline"),
        ("host:port in a URL", "git log -1 && curl -s http://$HOST:8080/health"),
        ("a docker volume spec", "git diff --stat && docker run -v $PWD:/work img ls"),
        ("the pattern sits in single quotes",
         "git grep -n 'show \"$SHA:path\"' -- '*.md'"),
        ("a single-quoted echo", "echo 'never: git show \"$SHA:path\"'"),
        ("a comment line, then another command", "# git show $SHA:x\ngit status"),
        ("a heredoc body written to a file",
         "cat >> notes.md <<'EOF'\ngit show \"$SHA:path\"\nEOF"),
        ("a heredoc commit message",
         "git commit -F - <<'EOF'\nfix: git show \"$SHA:path\" reads\nEOF"),
        ("a letter after the colon, but in a DIFFERENT statement",
         "git log -1 && echo $KEY:path"),
        ("a dot after the colon is not a modifier", 'git show "$SHA:.gitignore"'),
        ("a variable after the colon is not a modifier", 'git show "$SHA:$FILE"'),
    ]:
        expect_silent(f"21 {label}", command)
    expect_deny("21 still denies inside $( )", 'x=$(git show "$SHA:src/app.py")')
    expect_deny("21 still denies before a pipe",
                'cd "$D" && git show $SHA:src/app.py | head')
    expect_deny("21 still denies after another statement",
                'echo ok; git show "$SHA:src/app.py"')

    # --- 22: every git read that takes a <rev>:<path> spec is covered ----------
    expect_deny("22a git rev-parse", 'git rev-parse --verify -q "$SHA:hooks.json"')
    expect_deny("22b git ls-tree", 'git ls-tree "$SHA:hooks"')
    expect_silent("22c braced rev-parse",
                  'git rev-parse --verify -q "${SHA}:hooks.json"')
    expect_silent("22d braced ls-tree", 'git ls-tree "${SHA}:hooks"')

    # --- 23: the refusal does not claim what zsh does not do -------------------
    # Measured: "$SHA:src/app.py" is a bad substitution, "$SHA:hooks/x" reads
    # .ooks/x, "$SHA:path/x" happens to work. Only "unpredictable" is true of all.
    reason = reason_of('git show "$SHA:src/app.py"')
    check("23a reason says the unbraced form is unpredictable",
          "unpredictable" in reason)
    check("23b reason does not claim the command prints nothing",
          "prints NOTHING" not in reason)

    if FAILURES:
        print(f"FAIL: {len(FAILURES)} of {CHECKS} control(s) failed")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"PASS: {CHECKS}/{CHECKS} controls")
    return 0


if __name__ == "__main__":
    sys.exit(main())

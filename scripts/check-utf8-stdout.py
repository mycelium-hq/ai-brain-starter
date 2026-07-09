#!/usr/bin/env python3
"""check-utf8-stdout.py - fail-loud guard against the Windows cp1252 print crash.

A vault script that print()s the "gear Meta" emoji, an em dash, or an accented
name works on macOS/Linux (UTF-8 consoles) and silently ships. On a Windows
cp1252 console - or any C-locale pipe - the SAME print() raises
UnicodeEncodeError, the caller captures an empty string, and downstream logic
misreads it (ai-brain-starter#313: sync-vault-scripts.ps1 read the empty result
as "no Meta folder"). The fix is a 5-line reconfigure guard at the CLI entry:

    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass

This lint enforces that guard so the class cannot recur. It is the class-level
watchdog for the SILENT-NO-OP / cp1252-crash bug: PR #313 fixed the two files
that had already broken; this makes the NEXT one fail CI instead of a user's
Windows console.

Rule (deterministic, near-zero false positive):
    A tracked script FAILS if ALL of:
      - it is a runnable CLI ............ has `if __name__ == "__main__":`
      - it writes to the console ........ a print() with no non-console file=,
                                          or sys.stdout/sys.stderr .write()
      - its source carries non-ASCII .... any byte > 0x7F anywhere in the file
                                          (the emoji, an em dash, an accented
                                          name - the exact bytes that crash)
      - it lacks the guard ............. no stdout/stderr .reconfigure(utf-8)
      - it is not opted out ............ no `# utf8-stdout-ok: <reason>` marker

Why "source carries non-ASCII" rather than "a print literal is non-ASCII":
_meta_resolver.py print()s a DYNAMIC Path (`print(resolved)`) that holds the
emoji at runtime - there is no non-ASCII print literal to key on, yet it was one
of the two crashing files. The presence of the emoji anywhere in its source is
the reliable marker that the script handles emoji-bearing text and can emit it.
A genuinely ASCII-only CLI (no non-ASCII byte anywhere) can never hit the crash
and is never flagged.

Escape hatch: a script whose console output is provably ASCII-only despite a
non-ASCII comment can add `# utf8-stdout-ok: <reason>` on its own line. The guard
itself is a harmless no-op on POSIX (already UTF-8), so adding it is almost
always the right fix rather than a bypass.

Usage:
    check-utf8-stdout.py                 # lint tracked scripts/*.py, exit 1 on any violation
    check-utf8-stdout.py FILE [FILE ...] # lint the named files
    check-utf8-stdout.py --report [glob] # classify every file, never fail (enumeration)
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

# The guard is detected structurally: a .reconfigure(encoding="utf-8") call
# (single/double quotes, optional hyphen, flexible whitespace). Both files PR
# #313 fixed use exactly `.reconfigure(encoding="utf-8")`.
_GUARD_RE = re.compile(r"\.reconfigure\(\s*encoding\s*=\s*['\"]utf-?8['\"]", re.IGNORECASE)
_BYPASS_RE = re.compile(r"#\s*utf8-stdout-ok\b", re.IGNORECASE)


def _utf8_streams():
    """Reconfigure our own CLI streams; this lint prints file paths that can
    themselves contain the emoji, so it must not crash on the console it guards."""
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass


def _is_console_print(node):
    """True if this Call writes to the console (stdout/stderr)."""
    func = node.func
    # print(...) - console unless a non-stdout/stderr file= redirects it.
    if isinstance(func, ast.Name) and func.id == "print":
        for kw in node.keywords:
            if kw.arg == "file":
                val = kw.value
                # file=sys.stdout / file=sys.stderr stays console; anything else
                # (an open file, a StringIO) is not a console write.
                if isinstance(val, ast.Attribute) and val.attr in ("stdout", "stderr"):
                    return True
                return False
        return True
    # sys.stdout.write(...) / sys.stderr.write(...) / .writelines(...)
    if isinstance(func, ast.Attribute) and func.attr in ("write", "writelines"):
        owner = func.value
        if isinstance(owner, ast.Attribute) and owner.attr in ("stdout", "stderr"):
            return True
    return False


def classify(path):
    """Return a dict describing the file against the four signals."""
    data = path.read_bytes()
    has_non_ascii = any(b > 0x7F for b in data)
    text = data.decode("utf-8", errors="replace")

    has_guard = bool(_GUARD_RE.search(text))
    has_bypass = bool(_BYPASS_RE.search(text))

    is_cli = False
    prints_console = False
    parse_error = None
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:  # py_compile gate owns syntax; we just skip.
        parse_error = str(exc)
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                # if __name__ == "__main__":
                if (
                    isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"
                ):
                    is_cli = True
            if isinstance(node, ast.Call) and _is_console_print(node):
                prints_console = True

    flagged = (
        is_cli
        and prints_console
        and has_non_ascii
        and not has_guard
        and not has_bypass
        and parse_error is None
    )
    return {
        "path": path,
        "is_cli": is_cli,
        "prints_console": prints_console,
        "has_non_ascii": has_non_ascii,
        "has_guard": has_guard,
        "has_bypass": has_bypass,
        "parse_error": parse_error,
        "flagged": flagged,
    }


def _tracked_scripts():
    """Default target: tracked scripts/*.py, resolved from the repo root."""
    root = Path(__file__).resolve().parent.parent
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "--", "scripts/*.py"],
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Not a git checkout - fall back to a plain glob.
        return sorted((root / "scripts").glob("*.py"))
    return [root / line for line in out.splitlines() if line.strip()]


def main(argv):
    _utf8_streams()
    report_mode = False
    args = list(argv)
    if args and args[0] == "--report":
        report_mode = True
        args = args[1:]

    if args:
        # In --report mode a bare glob string is allowed; otherwise treat as paths.
        if report_mode and len(args) == 1 and any(ch in args[0] for ch in "*?"):
            targets = sorted(Path().glob(args[0]))
        else:
            targets = [Path(a) for a in args]
    else:
        targets = _tracked_scripts()

    results = [classify(p) for p in targets if p.suffix == ".py" and p.is_file()]

    if report_mode:
        _print_report(results)
        return 0

    violations = [r for r in results if r["flagged"]]
    if violations:
        print(
            "::error::vault script(s) print to a Windows-hostile console without "
            "the UTF-8 stdout/stderr guard (the ai-brain-starter#313 cp1252 crash "
            "class). Add the 5-line reconfigure block at the CLI entrypoint:",
            file=sys.stderr,
        )
        print(
            "    for _stream in (sys.stdout, sys.stderr):\n"
            "        try:\n"
            '            _stream.reconfigure(encoding="utf-8")  # Python 3.7+\n'
            "        except (AttributeError, ValueError):\n"
            "            pass",
            file=sys.stderr,
        )
        for r in violations:
            rel = r["path"]
            print(
                "::error file={f}::{f} is a runnable CLI that writes to the "
                "console and carries non-ASCII source, but never reconfigures "
                "stdout/stderr to UTF-8 (add the guard, or `# utf8-stdout-ok: "
                "<reason>` if its console output is provably ASCII-only).".format(f=rel),
                file=sys.stderr,
            )
        print(
            "\nFAILED: {n} script(s) missing the UTF-8 console guard.".format(
                n=len(violations)
            ),
            file=sys.stderr,
        )
        return 1

    print(
        "OK - {n} script(s) checked; every printing CLI with non-ASCII source "
        "carries the UTF-8 console guard.".format(n=len(results))
    )
    return 0


def _print_report(results):
    """Human enumeration: one row per file, with why it is / is not flagged."""
    flagged = [r for r in results if r["flagged"]]
    clean_cli = [r for r in results if r["is_cli"] and not r["flagged"]]
    non_cli = [r for r in results if not r["is_cli"]]

    def _reason(r):
        bits = []
        bits.append("cli" if r["is_cli"] else "lib")
        bits.append("print" if r["prints_console"] else "no-print")
        bits.append("non-ascii" if r["has_non_ascii"] else "ascii")
        bits.append("guard" if r["has_guard"] else "no-guard")
        if r["has_bypass"]:
            bits.append("bypass")
        if r["parse_error"]:
            bits.append("PARSE-ERR")
        return ",".join(bits)

    print("== FLAGGED (needs the guard) : {} ==".format(len(flagged)))
    for r in flagged:
        print("  FIX  {}  [{}]".format(r["path"], _reason(r)))
    print("\n== printing CLIs already safe : {} ==".format(len(clean_cli)))
    for r in clean_cli:
        print("  ok   {}  [{}]".format(r["path"], _reason(r)))
    print("\n== non-CLI / library files : {} ==".format(len(non_cli)))
    for r in non_cli:
        print("  -    {}  [{}]".format(r["path"], _reason(r)))
    print(
        "\nTotals: {} flagged, {} safe CLIs, {} non-CLI, {} files.".format(
            len(flagged), len(clean_cli), len(non_cli), len(results)
        )
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

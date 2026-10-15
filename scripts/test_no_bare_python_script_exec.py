#!/usr/bin/env python3
"""
Python under scripts/ and skills/ must not launch a Python SCRIPT through a bare
interpreter name.

THE BUG CLASS
    `subprocess.run(["python3", path, ...])` looks the interpreter up on PATH.
    Some machines put a shim there first (a Python-tooling plugin ships one for
    interactive sessions). It refuses exactly one invocation shape,
    `python3 <script path>`: advice on stderr, exit 1, nothing run. It forwards
    `-c`, `-m` and `-`, so a probe in any of those forms passes while the real
    call fails, which is why the defect sits unnoticed.

    journal-preflight.py started its message fetcher this way, and on such a
    machine the /journal digest lost its MESSAGES section.
    tests/integration/test_journal_preflight_shim_safe_fetch.sh pins that one
    site end to end. This suite is the class half: it reads every Python file
    under scripts/ and skills/ and fails on any new site of the same shape, so
    the next one is caught where it is written and not on a user's machine.

    The fix is almost always the interpreter already running the caller:
    sys.executable, as most of this tree already does.

WHAT IT FLAGS (an AST scan; the literal shapes, not data flow across functions)
    1. An argv list whose first element is a bare python / python3 / python3.N
       (a string literal, or a name bound to one, including through
       shutil.which(...) or os.environ.get(..., "python3")) followed by a script
       path: a path-looking string, or a computed value (a name, attribute,
       call, f-string or join).
       `["python3", fp]`, `[PY, "scripts/x.py"]`, `["python3", "-X", "utf8", fp]`
       and `["python3"] + [fp]` are flagged.
    2. A shell string that starts `python3 <script>`, handed to os.system,
       os.popen, subprocess.getoutput, or to a subprocess call with shell=True.

WHAT IT LEAVES ALONE
    - `-c` and `-m` forms: the shim forwards them, and they run code, not a path.
    - sys.executable and absolute interpreter paths: not looked up on PATH.
    - Lists of plain words (argparse choices, interpreter candidate names).
    - Text a program PRINTS for a person to run. That is a different defect
      (the printed command is run by a session, not by this code), and it is
      not an execution, so it is out of this suite's scope.

SCOPE, STATED SO A CLEAN RUN IS NOT READ AS MORE THAN IT IS
    Scans scripts/ and skills/ only. hooks/ and tests/eval/ hold older sites of
    the same shape that this suite does not look at; widening it needs those
    fixed or pinned first, not a silent pass over them.

AN EXEMPTION
    A genuine exception carries `# bare-python-ok: <reason>` on the flagged line
    or the line above it. A marker with no reason is itself a violation.

Runs automatically: scripts/ci.sh gate (f) globs scripts/test_*.py, so a new
suite here can never sit dormant. Stdlib only; works on Python 3.9.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("scripts", "skills")

BARE_NAME = re.compile(r"^(?:python|python3|python3\.\d+)$")
# A shell string that STARTS with a bare interpreter followed by a non-flag word.
SHELL_HEAD = re.compile(r"^\s*(?:python|python3|python3\.\d+)\s+(?!-)\S")
EXEMPT = re.compile(r"#\s*bare-python-ok:\s*(\S.*)$")
EXEMPT_NO_REASON = re.compile(r"#\s*bare-python-ok:\s*$")
EXEC_FUNCS = {"run", "call", "check_call", "check_output", "Popen",
              "system", "popen", "getoutput", "getstatusoutput"}
ALWAYS_SHELL = {"system", "popen", "getoutput", "getstatusoutput"}


def _func_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    return getattr(f, "id", "")


def _is_bare_interp(node: ast.AST, bound: set) -> bool:
    """Does this expression statically evaluate to a bare interpreter name?"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return bool(BARE_NAME.match(node.value))
    if isinstance(node, ast.Name):
        return node.id in bound
    if isinstance(node, ast.IfExp):
        return _is_bare_interp(node.body, bound) or _is_bare_interp(node.orelse, bound)
    if isinstance(node, ast.BoolOp):
        return any(_is_bare_interp(v, bound) for v in node.values)
    if isinstance(node, ast.Call) and _func_name(node) in ("which", "get", "getenv"):
        return any(_is_bare_interp(a, bound) for a in node.args)
    return False


def _script_like(node: ast.AST) -> bool:
    """Would this argv element be a script path (as opposed to a flag or a plain word)?"""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, str):
            return False
        v = node.value
        if v.startswith("-"):
            return False
        return "/" in v or "\\" in v or v.endswith(".py")
    # A computed value that can hold a path. Container literals (a nested argv in a
    # (name, argv) pair), starred contents and comparisons are not guessed at.
    return isinstance(node, (ast.Name, ast.Attribute, ast.Call, ast.Subscript,
                             ast.JoinedStr, ast.BinOp, ast.IfExp, ast.BoolOp))


def _rest_is_script_exec(rest: list) -> bool:
    """argv after the interpreter: does it run a script path (not -c / -m, not flags only)?"""
    for e in rest:
        if isinstance(e, ast.Constant) and e.value in ("-c", "-m"):
            return False                # forwarded by the shim: runs code, not a path
    for e in rest:
        if isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value.startswith("-"):
            continue                    # a flag
        if isinstance(e, ast.Starred):
            return False
        if _script_like(e):
            return True
        # a plain word (an option value such as `utf8`): keep looking
    return False


def _leading_text(node: ast.AST) -> str:
    """Best-effort leading text of a command expression; placeholders become '{}'."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}"
                       for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _leading_text(node.left) + _leading_text(node.right)
    return "{}"


def _docstring_ids(tree: ast.AST) -> set:
    ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def find_violations(source: str, filename: str = "<src>") -> list:
    """Return [(lineno, reason), ...] for one file's source text."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [(exc.lineno or 0, "does not parse: %s" % exc.msg)]
    lines = source.splitlines()

    bound = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and _is_bare_interp(n.value, set()):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    bound.add(t.id)

    found = []

    def add(lineno: int, reason: str) -> None:
        found.append((lineno, reason))

    for n in ast.walk(tree):
        # 1. argv list / tuple literal
        if isinstance(n, (ast.List, ast.Tuple)) and not isinstance(getattr(n, "ctx", None), ast.Store):
            if n.elts and _is_bare_interp(n.elts[0], bound) and _rest_is_script_exec(list(n.elts[1:])):
                add(n.lineno, "argv starts with a bare interpreter and runs a script path")
        # ["python3"] + [script, ...]
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            left, right = n.left, n.right
            if isinstance(left, (ast.List, ast.Tuple)) and len(left.elts) == 1 \
                    and _is_bare_interp(left.elts[0], bound) \
                    and isinstance(right, (ast.List, ast.Tuple)) and _rest_is_script_exec(list(right.elts)):
                add(n.lineno, "bare interpreter list joined to a script path")
        # 2. shell string
        if isinstance(n, ast.Call) and _func_name(n) in EXEC_FUNCS and n.args:
            shell = _func_name(n) in ALWAYS_SHELL or any(
                k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True
                for k in n.keywords)
            if shell and SHELL_HEAD.match(_leading_text(n.args[0])):
                add(n.lineno, "shell command starts with a bare interpreter and a script")

    # exemptions: marker on the flagged line or the one above, reason required
    out = []
    for lineno, reason in found:
        window = lines[max(lineno - 2, 0):lineno]
        if any(EXEMPT_NO_REASON.search(ln) for ln in window):
            out.append((lineno, reason + " (bare-python-ok marker has no reason)"))
        elif any(EXEMPT.search(ln) for ln in window):
            continue
        else:
            out.append((lineno, reason))
    return sorted(set(out))


def python_files(root: Path = REPO) -> list:
    """Tracked .py files under SCAN_ROOTS, listed by git (the same source ci.sh gate (a) uses)."""
    # A caller's git-location variables (a git-hook context exports them) would point
    # `git -C` at a different repo than the one being scanned.
    drop = {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES",
            "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_PREFIX"}
    env = {k: v for k, v in os.environ.items() if k not in drop}
    proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--"] + list(SCAN_ROOTS),
                          capture_output=True, timeout=60, env=env)
    if proc.returncode != 0:
        raise RuntimeError("git ls-files failed: " + proc.stderr.decode("utf-8", "replace").strip())
    names = sorted(os.fsdecode(item) for item in proc.stdout.split(b"\0") if item)
    return [root / n for n in names if n.endswith(".py")]


# --- controls: the scanner is only trusted for what it is shown to catch --------------

# (label, source, expected number of violations)
SELF_CASES = [
    ("argv: bare python3 + a computed path is flagged",
     'import subprocess\nsubprocess.run(["python3", fp, "--x"])\n', 1),
    ("argv: bare python3 + a path-looking string is flagged",
     'import subprocess\nsubprocess.run(["python3", "scripts/x.py"])\n', 1),
    ("argv: python (no 3) is flagged",
     'import subprocess\nsubprocess.run(["python", fp])\n', 1),
    ("argv: python3.12 is flagged",
     'import subprocess\nsubprocess.run(["python3.12", fp])\n', 1),
    ("argv: a name bound through shutil.which is flagged",
     'import shutil, subprocess\nPY = shutil.which("python3") or "python3"\nsubprocess.run([PY, fp])\n', 1),
    ("argv: a name bound to an environment default is flagged",
     'import os, subprocess\nPY = os.environ.get("PYTHON", "python3")\nsubprocess.run([PY, fp])\n', 1),
    ("argv: an option before the script does not hide it",
     'import subprocess\nsubprocess.run(["python3", "-X", "utf8", fp])\n', 1),
    ("argv: list concatenation is flagged",
     'import subprocess\nsubprocess.run(["python3"] + [fp, "--x"])\n', 1),
    ("shell: f-string command with shell=True is flagged",
     'import subprocess\nsubprocess.run(f"python3 {fp} --y", shell=True)\n', 1),
    ("shell: os.system with a concatenated command is flagged",
     'import os\nos.system("python3 " + fp)\n', 1),
    ("ok: sys.executable",
     'import subprocess, sys\nsubprocess.run([sys.executable, fp])\n', 0),
    ("ok: -c form (forwarded by the shim)",
     'import subprocess\nsubprocess.run(["python3", "-c", "pass"])\n', 0),
    ("ok: -m form even with a path after it",
     'import subprocess\nsubprocess.run(["python3", "-m", "pytest", "tests/x.py"])\n', 0),
    ("ok: absolute interpreter path",
     'import subprocess\nsubprocess.run(["/usr/bin/python3", fp])\n', 0),
    ("ok: a version probe",
     'import subprocess\nsubprocess.run(["python3", "--version"])\n', 0),
    ("ok: argparse choices of plain words",
     'ap.add_argument("--m", choices=["python", "minimax", "haiku"])\n', 0),
    ("ok: interpreter candidate names",
     'for name in ("python3", "python"):\n    pass\n', 0),
    ("ok: unpacking target is not an argv",
     'PY = "python3"\nPY, rest = parse()\n', 0),
    ("ok: (name, argv) candidate pairs",
     'for c, argv in (("python", ["python"]), ("python3", ["python3"])):\n    pass\n', 0),
    ("ok: shell string without shell=True is not run through a shell",
     'import subprocess\nsubprocess.run(f"python3 {fp}")\n', 0),
    ("ok: shell string with -c",
     'import os\nos.system("python3 -c pass")\n', 0),
    ("ok: a message printed for a person to run",
     'print(f"run: python3 {fp}")\n', 0),
    ("exempt: marker with a reason on the line above",
     'import subprocess\n# bare-python-ok: runs the probe under test, on purpose\nsubprocess.run(["python3", fp])\n', 0),
    ("exempt: marker with a reason on the same line",
     'import subprocess\nsubprocess.run(["python3", fp])  # bare-python-ok: fixture\n', 0),
    ("violation: a marker with no reason does not exempt",
     'import subprocess\n# bare-python-ok:\nsubprocess.run(["python3", fp])\n', 1),
]


def main() -> int:
    passed = 0
    failed = 0

    def ok(label: str) -> None:
        nonlocal passed
        passed += 1
        print("PASS  %s" % label)

    def bad(label: str, why: str) -> None:
        nonlocal failed
        failed += 1
        print("FAIL  %s :: %s" % (label, why))

    print("=== 1. controls: the scanner flags what it should and leaves the rest ===")
    for label, src, want in SELF_CASES:
        got = len(find_violations(src))
        if got == want:
            ok(label)
        else:
            bad(label, "expected %d violation(s), got %d" % (want, got))

    print("=== 2. the scan can see the tree (a guard over an empty set passes forever) ===")
    try:
        files = python_files()
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        bad("enumerate tracked python files", "%s: %s" % (type(exc).__name__, exc))
        print()
        print("=== summary: %d passed, %d failed ===" % (passed, failed))
        return 1
    names = {str(p.relative_to(REPO)).replace(os.sep, "/") for p in files}
    if len(files) >= 25:
        ok("scanned %d python files under %s" % (len(files), "/ and ".join(SCAN_ROOTS) + "/"))
    else:
        bad("scan reaches the tree", "only %d python files found; did scripts/ move?" % len(files))
    if "scripts/journal-preflight.py" in names:
        ok("scripts/journal-preflight.py is in scope")
    else:
        bad("journal-preflight in scope", "not found under the scanned roots")

    print("=== 3. the historical defect, in the real file ===")
    pf = REPO / "scripts" / "journal-preflight.py"
    if pf.is_file():
        src = pf.read_text(encoding="utf-8")
        if "sys.executable" not in src:
            bad("negative control can be built", "no sys.executable in journal-preflight.py to put back")
        else:
            reverted = src.replace("sys.executable", '"python3"')
            if find_violations(reverted, str(pf)):
                ok("the old bare-python3 call, put back in the real file, is flagged")
            else:
                bad("negative control bites", "the scanner missed the bare python3 in a copy of the real file")
    else:
        bad("negative control", "scripts/journal-preflight.py is missing")

    print("=== 4. the tree itself is clean ===")
    dirty = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            dirty.append("%s: unreadable (%s)" % (p.relative_to(REPO), type(exc).__name__))
            continue
        for lineno, reason in find_violations(text, str(p)):
            dirty.append("%s:%d: %s" % (str(p.relative_to(REPO)).replace(os.sep, "/"), lineno, reason))
    if dirty:
        bad("no bare-interpreter script launches under scripts/ or skills/",
            "\n      " + "\n      ".join(dirty)
            + "\n      Use sys.executable (see the header), or add `# bare-python-ok: <reason>`.")
    else:
        ok("no bare-interpreter script launches under scripts/ or skills/")

    print()
    print("=== summary: %d passed, %d failed ===" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
A script under scripts/ or hooks/ that carries a shebang, and is an entry point,
must be tracked executable (git mode 100755).

THE BUG CLASS
    A shebang promises the file can be run by its path. Git keeps the other
    half of that promise, the executable bit, separately, and a file written by
    an editor or a tool usually starts at 0644, so `git add` records 100644.
    Run by path, such a script dies before its first line: `permission denied`
    from the shell, PermissionError from subprocess, and from a `[ -x ... ]` or
    os.access(..., X_OK) gate nothing at all, because the gate just skips it.

    scripts/vault-safe-commit.sh shipped this way. Its usage header documents
    direct invocation (`VAULT_ROOT=... vault-safe-commit.sh "msg" path...`), and
    callers outside this repo tell sessions to commit through it. Invoked that
    way it never started, so nothing was committed, and a caller that chained
    further commands without checking HEAD carried on as if it had been.

    It was one of many. Measured 2026-10-02: 222 tracked shebang files under
    scripts/ and hooks/ were 100644, next to 215 at 100755. Nothing enforced the
    bit, so whether a script could be run by path depended on how it happened
    to be created.

WHAT IT REQUIRES
    Every tracked file under scripts/ or hooks/ whose first bytes are `#!` is
    100755, unless it is a library (below). The shebang is the declaration that
    a file is a program; this suite makes git agree with it.

WHAT IT LEAVES ALONE: LIBRARIES (running one does nothing, so it is not run)
    - A Python module with no `if __name__ == "__main__":` block, whose name is
      importable, that sits in a package (an `__init__.py` beside it) or is
      imported by another tracked Python file. The extractor plugins and the
      hooks/_lib helpers are this shape.
    - A shell file another tracked shell script sources (`. "$X"`, `source x`),
      unless it also carries the BASH_SOURCE run-directly guard, which makes it
      a program as well.
    A library MAY be executable. Nothing here requires 100644 of anything.
    There is no exemption marker: a file that must not be executable does not
    need a shebang.

SCOPE, STATED SO A CLEAN RUN IS NOT READ AS MORE THAN IT IS
    scripts/ and hooks/ only: the files users, hooks, scheduled jobs, docs and
    other repos run by path. tests/, skills/ and templates/ also hold shebang
    files at 100644, but every caller runs those through an interpreter
    (`bash tests/integration/...`, `python3 skills/...`); widening the scope
    is a separate decision, not a silent pass over them.
    Modes come from the INDEX (`git ls-files -s`), which is what a commit
    records, not from the working tree, whose bit git ignores when
    core.fileMode is false.

THE FIX FOR A FINDING
    chmod +x <path> && git update-index --chmod=+x <path>
    Both halves: the index alone leaves the checkout at 0644, and with
    core.fileMode on, the next `git add` or `git commit <path>` stages 100644
    again from the working tree.

Runs automatically: scripts/ci.sh gate (f) globs scripts/test_*.py, so a new
suite here can never sit dormant. Stdlib only; works on Python 3.9.
"""

from __future__ import annotations

import ast
import keyword
import re
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # Python 3.7+
    except (AttributeError, ValueError):
        pass

REPO = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("scripts", "hooks")
SELF = "scripts/" + Path(__file__).name
INCIDENT = "scripts/vault-safe-commit.sh"

EXECUTABLE = "100755"
NOT_A_FILE = ("120000", "160000")     # symlink, submodule
SHELL_EXT = (".sh", ".bash")
# Same word-boundary shebang rule as tests/integration/test_bash32_portability.sh:
# sh/bash/ksh/zsh/ash/dash, but not the `sh` inside `fish` or `osascript`.
SHELL_SHEBANG = re.compile(rb"^#!.*\b(?:ba|k|z|a|da)?sh\b")
PY_SHEBANG = re.compile(rb"^#!.*\bpython")

# A shell `source` / `.` in command position; group 1 is the rest of the command.
SOURCE_CMD = re.compile(r"(?:^|[;&|(){]|\bthen\b|\bdo\b|\belse\b)\s*(?:source|\.)\s+([^;&|]+)")
ASSIGN = re.compile(r"^\s*(?:export\s+|local\s+|readonly\s+|declare\s+(?:-\w+\s+)*)?"
                    r"([A-Za-z_][A-Za-z0-9_]*)=(\S.*)$")
VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
RUN_DIRECTLY = re.compile(r"BASH_SOURCE[^\n]*(?:==?|!=)\s*[\"']?\$\{?0\b"
                          r"|\$\{?0\}?[\"']?\s*(?:==?|!=)[^\n]*BASH_SOURCE")


def _first_line(data: bytes) -> bytes:
    return data.split(b"\n", 1)[0]


def _is_python(path: str, data: bytes) -> bool:
    return path.endswith(".py") or bool(PY_SHEBANG.match(_first_line(data)))


def _is_shell(path: str, data: bytes) -> bool:
    return path.endswith(SHELL_EXT) or bool(SHELL_SHEBANG.match(_first_line(data)))


def _parse(data: bytes):
    try:
        return ast.parse(data)
    except (SyntaxError, ValueError):
        return None


def _has_main_guard(mod: ast.Module) -> bool:
    for node in mod.body:
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)):
            continue
        t = node.test
        if len(t.ops) != 1 or not isinstance(t.ops[0], ast.Eq):
            continue
        sides = (t.left, t.comparators[0])
        if (any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides)
                and any(isinstance(s, ast.Constant) and s.value == "__main__" for s in sides)):
            return True
    return False


def _import_index(modules: dict) -> dict:
    """Every name an import could bind to a module, mapped to the files that import it."""
    index: dict = {}
    for path, mod in modules.items():
        for node in ast.walk(mod):
            names = []
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names += alias.name.split(".")
            elif isinstance(node, ast.ImportFrom):
                names += (node.module or "").split(".")
                names += [alias.name for alias in node.names]
            elif isinstance(node, ast.Call):
                fn = node.func
                fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if fname in ("import_module", "__import__", "spec_from_file_location", "run_path"):
                    for sub in ast.walk(node):   # literal module names and file paths
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                            base = sub.value.replace("\\", "/").rsplit("/", 1)[-1]
                            if base.endswith(".py"):
                                base = base[:-3]
                            names += base.split(".")
            for name in names:
                if name:
                    index.setdefault(name, set()).add(path)
    return index


def _names_file(text: str, base: str) -> bool:
    """Does `text` name `base` as a whole path component (not as part of a longer name)?"""
    return re.search(r"(?:^|[/\"'\s=])" + re.escape(base) + r"(?:$|[\"'\s;)])", text) is not None


def _sourced_by_another(path: str, shell_texts: dict) -> bool:
    base = path.rsplit("/", 1)[-1]
    for other, text in shell_texts.items():
        if other == path or base not in text:
            continue
        lines = text.splitlines()
        assigned: dict = {}
        for line in lines:
            m = ASSIGN.match(line)
            if m:
                assigned.setdefault(m.group(1), []).append(m.group(2))
        for line in lines:
            for m in SOURCE_CMD.finditer(line):
                rest = m.group(1)
                if _names_file(rest, base):
                    return True
                for var in VAR_REF.findall(rest):
                    if any(_names_file(v, base) for v in assigned.get(var, ())):
                        return True
    return False


def find_violations(tree: dict, roots=SCAN_ROOTS) -> tuple:
    """tree: {path: (git mode, blob bytes)} for EVERY tracked file (importers and
    sourcers can live anywhere). Returns (violations, entry_points, libraries)
    for the shebang files under `roots`; a violation is (path, reason)."""
    prefixes = tuple(r.rstrip("/") + "/" for r in roots)
    files = {p: md for p, md in tree.items() if md[0] not in NOT_A_FILE}

    modules = {}
    shell_texts = {}
    for p, (_mode, data) in files.items():
        if p.endswith(".py"):
            mod = _parse(data)
            if mod is not None:
                modules[p] = mod
        if _is_shell(p, data):
            shell_texts[p] = data.decode("utf-8", "replace")
    imports = _import_index(modules)

    violations, entry_points, libraries = [], [], []
    for p in sorted(files):
        mode, data = files[p]
        if not p.startswith(prefixes) or not data.startswith(b"#!"):
            continue
        library = False
        if _is_python(p, data):
            mod = modules.get(p) if p.endswith(".py") else _parse(data)
            stem = p.rsplit("/", 1)[-1][:-3] if p.endswith(".py") else ""
            importable = bool(stem) and stem.isidentifier() and not keyword.iskeyword(stem)
            pkg_init = (p.rsplit("/", 1)[0] + "/__init__.py") if "/" in p else "__init__.py"
            in_package = pkg_init in files
            imported = any(src != p for src in imports.get(stem, ())) if importable else False
            library = (mod is not None and not _has_main_guard(mod)
                       and importable and (in_package or imported))
        elif _is_shell(p, data):
            library = (_sourced_by_another(p, shell_texts)
                       and not RUN_DIRECTLY.search(data.decode("utf-8", "replace")))
        (libraries if library else entry_points).append(p)
        if not library and mode != EXECUTABLE:
            violations.append((p, "shebang entry point tracked %s, not %s" % (mode, EXECUTABLE)))
    return violations, entry_points, libraries


def _git(*args: str, data: bytes = b"") -> bytes:
    r = subprocess.run(["git", "-C", str(REPO), *args], input=data,
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("git %s exited %d: %s" % (
            " ".join(args), r.returncode, r.stderr.decode("utf-8", "replace").strip()))
    return r.stdout


def load_tree() -> dict:
    """{path: (mode, blob)} for every stage-0 entry in the INDEX, blobs read from git."""
    entries = []
    for rec in _git("ls-files", "-s", "-z").split(b"\0"):
        if not rec:
            continue
        meta, raw = rec.split(b"\t", 1)
        mode, sha, stage = meta.decode("ascii").split(" ")
        if stage == "0":
            entries.append((raw.decode("utf-8", "replace"), mode, sha))
    shas = sorted({sha for _p, mode, sha in entries if mode not in NOT_A_FILE})
    out = _git("cat-file", "--batch", data=("\n".join(shas) + "\n").encode("ascii"))
    blobs = {}
    i = 0
    while i < len(out):
        nl = out.index(b"\n", i)
        head = out[i:nl].decode("ascii", "replace").split(" ")
        if len(head) != 3:
            raise RuntimeError("git cat-file --batch: unexpected header %r" % out[i:nl])
        size = int(head[2])
        blobs[head[0]] = out[nl + 1:nl + 1 + size]
        i = nl + 1 + size + 1
    missing = [sha for sha in shas if sha not in blobs]
    if missing:
        raise RuntimeError("%d blob(s) unreadable, e.g. %s" % (len(missing), missing[0]))
    return {p: (mode, blobs.get(sha, b"")) for p, mode, sha in entries}


# ---- controls ----------------------------------------------------------------
# (label, tree, paths that must be flagged). Both directions, so a rule that
# flags everything and a rule that flags nothing each fail here.
PY_MAIN = b'#!/usr/bin/env python3\ndef main():\n    pass\n\nif __name__ == "__main__":\n    main()\n'
PY_TOPLEVEL = b"#!/usr/bin/env python3\nimport sys\nprint(sys.argv)\n"
PY_LIB = b"#!/usr/bin/env python3\nVALUE = 1\n\ndef helper():\n    return VALUE\n"
SH = b"#!/bin/bash\necho run\n"
SH_LIB = b"#!/bin/bash\nhelper() { :; }\n"
INIT = ("100644", b"")
SELF_CASES = [
    ("flagged: a shell script at 100644",
     {"scripts/run.sh": ("100644", SH)}, ["scripts/run.sh"]),
    ("ok: the same script at 100755",
     {"scripts/run.sh": ("100755", SH)}, []),
    ("ok: no shebang, no promise",
     {"scripts/notes.sh": ("100644", b"echo run\n")}, []),
    ("ok: outside scripts/ and hooks/ is out of scope",
     {"tests/run.sh": ("100644", SH)}, []),
    ("ok: a symlink is not a file to check",
     {"scripts/link.sh": ("120000", b"run.sh")}, []),
    ("flagged: an extensionless shell script",
     {"hooks/rotate": ("100644", b"#!/bin/sh\necho run\n")}, ["hooks/rotate"]),
    ("flagged: a shebang that is neither shell nor python",
     {"scripts/notify": ("100644", b"#!/usr/bin/osascript\nbeep\n")}, ["scripts/notify"]),
    ("flagged: a python CLI with a __main__ block",
     {"scripts/tool.py": ("100644", PY_MAIN)}, ["scripts/tool.py"]),
    ("flagged: a python script with top-level code that nothing imports",
     {"hooks/guard.py": ("100644", PY_TOPLEVEL)}, ["hooks/guard.py"]),
    ("ok: a library module in a package",
     {"hooks/_lib/__init__.py": INIT, "hooks/_lib/util.py": ("100644", PY_LIB)}, []),
    ("flagged: a package module with a __main__ block is a program too",
     {"hooks/_lib/__init__.py": INIT, "hooks/_lib/tool.py": ("100644", PY_MAIN)},
     ["hooks/_lib/tool.py"]),
    ("flagged: a hyphenated name cannot be imported, even inside a package",
     {"hooks/_lib/__init__.py": INIT, "hooks/_lib/run-me.py": ("100644", PY_LIB)},
     ["hooks/_lib/run-me.py"]),
    ("ok: a library module another tracked file imports",
     {"scripts/_helpers.py": ("100644", PY_LIB),
      "scripts/cli.py": ("100755", b"#!/usr/bin/env python3\nfrom _helpers import helper\n")}, []),
    ("ok: a library module loaded by file path from a test",
     {"scripts/_helpers.py": ("100644", PY_LIB),
      "tests/t.py": ("100644", b'import importlib.util\n'
                                b'spec = importlib.util.spec_from_file_location("h", "scripts/_helpers.py")\n')}, []),
    ("flagged: importing its own name does not make a file a library",
     {"scripts/selfish.py": ("100644", b"#!/usr/bin/env python3\nimport selfish\n")},
     ["scripts/selfish.py"]),
    ("flagged: a string that mentions the name is not an import",
     {"scripts/_helpers.py": ("100644", PY_LIB),
      "scripts/cli.py": ("100755", b'#!/usr/bin/env python3\nprint("import _helpers")\n')},
     ["scripts/_helpers.py"]),
    ("ok: a shell library sourced through a variable",
     {"scripts/_lib.sh": ("100644", SH_LIB),
      "scripts/main.sh": ("100755", b'#!/bin/bash\nLIB="$DIR/_lib.sh"\nif [ -f "$LIB" ]; then\n  . "$LIB"\nfi\n')}, []),
    ("ok: a shell library sourced by a literal path",
     {"scripts/_lib.sh": ("100644", SH_LIB),
      "hooks/main.sh": ("100755", b'#!/bin/bash\nsource "$(dirname "$0")/../scripts/_lib.sh"\n')}, []),
    ("flagged: a sourced file with the BASH_SOURCE run-directly guard is a program too",
     {"scripts/_lib.sh": ("100644", SH_LIB + b'if [ "${BASH_SOURCE[0]}" = "$0" ]; then helper; fi\n'),
      "scripts/main.sh": ("100755", b'#!/bin/bash\n. "$DIR/_lib.sh"\n')},
     ["scripts/_lib.sh"]),
    ("flagged: naming a file is not sourcing it (find . -name, echo)",
     {"scripts/_lib.sh": ("100644", SH_LIB),
      "scripts/main.sh": ("100755", b'#!/bin/bash\nfind . -name _lib.sh\necho "see _lib.sh"\n')},
     ["scripts/_lib.sh"]),
    ("flagged: a commented-out source line does not count",
     {"scripts/_lib.sh": ("100644", SH_LIB),
      "scripts/main.sh": ("100755", b'#!/bin/bash\n# . "$DIR/_lib.sh"\n')},
     ["scripts/_lib.sh"]),
    ("flagged: sourcing a different file with a longer name does not count",
     {"scripts/_lib.sh": ("100644", SH_LIB),
      "scripts/main.sh": ("100755", b'#!/bin/bash\n. "$DIR/my_lib.sh"\n')},
     ["scripts/_lib.sh"]),
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

    print("=== 1. controls: the rule flags what it should and leaves the rest ===")
    for label, tree, want in SELF_CASES:
        got = sorted(p for p, _why in find_violations(tree)[0])
        if got == sorted(want):
            ok(label)
        else:
            bad(label, "expected %s, got %s" % (sorted(want), got))

    print("=== 2. the scan can see the tree (a guard over an empty set passes forever) ===")
    try:
        tree = load_tree()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        bad("read the index", "%s: %s" % (type(exc).__name__, exc))
        print()
        print("=== summary: %d passed, %d failed ===" % (passed, failed))
        return 1
    violations, entry_points, libraries = find_violations(tree)
    total = len(entry_points) + len(libraries)
    if total >= 300:
        ok("%d shebang files under %s: %d entry points, %d libraries"
           % (total, " and ".join(r + "/" for r in SCAN_ROOTS), len(entry_points), len(libraries)))
    else:
        bad("scan reaches the tree", "only %d shebang files under %s; did they move?"
            % (total, " and ".join(r + "/" for r in SCAN_ROOTS)))
    for path in (INCIDENT, SELF):
        if path in entry_points:
            ok("%s is in scope as an entry point" % path)
        else:
            bad("%s in scope" % path, "not classified as an entry point (missing, or wrongly a library)")

    print("=== 3. the historical defect, rebuilt from the real files ===")
    for path, what in ((INCIDENT, "the incident script"), (SELF, "a python entry point (this suite)")):
        if path not in tree:
            bad("negative control for %s" % path, "file is not tracked")
            continue
        reverted = dict(tree)
        reverted[path] = ("100644", tree[path][1])
        if path in [p for p, _why in find_violations(reverted)[0]]:
            ok("%s, put back at 100644, is flagged" % what)
        else:
            bad("negative control bites", "%s at 100644 was not flagged" % path)

    print("=== 4. the tree itself is clean ===")
    if violations:
        bad("every shebang entry point under %s is 100755"
            % " and ".join(r + "/" for r in SCAN_ROOTS),
            "\n      " + "\n      ".join("%s: %s" % v for v in violations)
            + "\n      Fix each with: chmod +x <path> && git update-index --chmod=+x <path>"
            + "\n      (or, if it is a library that is never run, drop the shebang).")
    else:
        ok("every shebang entry point under %s is 100755"
           % " and ".join(r + "/" for r in SCAN_ROOTS))

    print()
    print("=== summary: %d passed, %d failed ===" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

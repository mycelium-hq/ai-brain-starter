#!/usr/bin/env bash
#
# Integration test: warn-journal-saved-without-context.py must gate a journal
# written from an INLINE INTERPRETER SCRIPT, and must not gate anything else.
#
# The fail-open (measured 2026-08-24): journals saved as
#
#     cd "<vault>" && python3 - <<'PY'
#     Path('<emoji> Journals/August 2026/e.md').write_text(...)
#     PY
#
# carry none of the shell redirect markers ("cat >", "tee ", " > ", ...) the gate
# looked for, so `blob` stayed empty and the hook no-opped. An entire /journal
# session's edits were written that way and the guard never fired once -- the
# silent direction of failure, which is the one this guard exists to prevent.
#
# The fix composes with _strip_heredocs, and the composition is the delicate part.
# _strip_heredocs narrows the gate to the command LINES so that a heredoc BODY
# merely quoting a journal path cannot be mistaken for a journal save (the
# 2026-08-28 false-positive class). But for the interpreter form the body IS the
# program: its journal path and its write call are the real ones. So the split is
#
#     interpreter token -> looked for in the command LINES  (body stripped)
#     write call + path -> looked for in the FULL text      (body included)
#
# A `python3` on the command line is what makes the body a PROGRAM. A `python3`
# appearing only inside a body is inert data. Every control below pins one half
# of that split; the CONTROLs run with NO marker planted, so an ALLOW verdict
# means the gate never opened rather than that the marker satisfied it.
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
PY="${PYTHON:-python3}"

"$PY" - "$REPO_ROOT" <<'PYEOF'
import json, os, subprocess, sys, tempfile

repo = sys.argv[1]
hook = os.path.join(repo, "hooks", "warn-journal-saved-without-context.py")
EMOJI = "\U0001F4D3"
DATE = "2026-08-24"
failures = 0

def check(label, got, want):
    global failures
    if got == want:
        print("PASS  %s" % label)
    else:
        print("FAIL  %s (got %r, want %r)" % (label, got, want))
        failures += 1

def run(command, cwd):
    """Returns True if the hook DENIED the write."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}, "cwd": cwd}
    env = dict(os.environ)
    env.pop("JOURNAL_CONTEXT_BYPASS", None)   # the harness itself must not bypass
    p = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    if p.returncode != 0:
        return "CRASH: rc=%d %s" % (p.returncode, p.stderr.strip()[:200])
    if not p.stdout.strip():
        return False
    try:
        out = json.loads(p.stdout)
    except ValueError:
        return "CRASH: non-JSON stdout %r" % p.stdout[:200]
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

with tempfile.TemporaryDirectory() as tmp:
    tmp = os.path.realpath(tmp)
    vault = os.path.join(tmp, "vault")
    jdir = os.path.join(vault, EMOJI + " Journals", "August 2026")
    os.makedirs(jdir)
    os.makedirs(os.path.join(vault, "scripts"))
    entry_rel = "%s Journals/August 2026/An Entry.md" % EMOJI
    entry_abs = os.path.join(jdir, "An Entry.md")
    body = "---\\ntype: journal\\ncreationDate: %sT22:45\\n---\\n\\n## Journal\\nx\\n" % DATE

    stdin_dash = (
        'cd "%s" && python3 - <<\'PY\'\n'
        'from pathlib import Path\n'
        'Path("%s").write_text("""%s""")\n'
        'PY' % (vault, entry_rel, body))
    stdin_plain = (
        'cd "%s" && python3 <<\'PY\'\n'
        'open("%s", "w").write("x")\n'
        'PY' % (vault, entry_abs))
    node_form = (
        'cd "%s" && node -e \'require("fs").writeFileSync("%s","x")\''
        % (vault, entry_rel))

    # === NEGATIVE CONTROLS: no marker -> every interpreter write form must DENY ===
    check("NEGATIVE CONTROL: `python3 - <<PY` journal write is DENIED without a marker",
          run(stdin_dash, vault), True)
    check("NEGATIVE CONTROL: `python3 <<PY` (no dash) is DENIED without a marker",
          run(stdin_plain, vault), True)
    check("NEGATIVE CONTROL: `node -e` journal write is DENIED without a marker",
          run(node_form, vault), True)

    # === CONTROLS: the gate must stay SHUT on these, all with no marker planted ===
    read_only = (
        'cd "%s" && python3 - <<\'PY\'\n'
        'from pathlib import Path\n'
        'print(Path("%s").read_text())\n'
        'PY' % (vault, entry_rel))
    check("CONTROL: a read-only python script naming a journal is not gated",
          run(read_only, vault), False)

    # The 2026-08-28 class: a FIXTURE whose body quotes a journal path and also
    # happens to contain python write code. `cat` is not an interpreter, so the
    # interpreter token is absent from the command lines and the gate stays shut.
    fixture = (
        'cd "%s" && cat > tests/t.sh <<\'EOF\'\n'
        '# the guard must block writes to %s\n'
        'python3 -c "open(\'a\',\'w\').write(\'z\')"\n'
        'EOF' % (vault, entry_rel))
    check("CONTROL: a fixture quoting a journal path + python write code is not gated",
          run(fixture, vault), False)

    # The interpreter token must sit in COMMAND position: a mere substring in a
    # FILENAME must not promote a heredoc body to a program.
    named_python = (
        'cd "%s" && cat > scripts/python3_helper.sh <<\'EOF\'\n'
        'Path("%s").write_text("hola")\n'
        'EOF' % (vault, entry_rel))
    check("CONTROL: a file NAMED python3_helper.sh is not gated",
          run(named_python, vault), False)

    # === POSITIVE: with the marker planted, the same write is allowed through ===
    marker_dir = os.path.join(vault, "⚙️ Meta", ".journal-context")
    os.makedirs(marker_dir)
    open(os.path.join(marker_dir, "%s.json" % DATE), "w").write("{}")
    check("`python3 - <<PY` journal write is ALLOWED with the marker",
          run(stdin_dash, vault), False)

print("")
if failures:
    print("FAILED: %d assertion(s)" % failures)
    sys.exit(1)
print("ALL PASS (7 assertions; 3 negative controls, 3 gate-shut controls)")
PYEOF

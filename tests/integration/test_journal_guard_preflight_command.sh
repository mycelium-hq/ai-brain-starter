#!/usr/bin/env bash
#
# Integration test: the fix command warn-journal-saved-without-context.py prints
# must RUN in the session that reads it.
#
# Step 1 of the block message used to be the literal
#
#     python3 "⚙️ Meta/scripts/journal-preflight.py"
#
# which fails twice inside a Claude Code session:
#   - a PATH shim (the trailofbits modern-python plugin) refuses
#     `python3 <script>` with exit 1 and an error on stderr, and
#   - the path is relative, so it only resolves when the session's cwd is the
#     vault root, which is rarely where a session sits.
# The guard fired correctly and then handed the session a command that could not
# work, so the one sanctioned way past the block was dead on arrival.
#
# Asserted on the SHIPPED hook over real stdin, against real temp vaults. The
# printed command is split with shlex and must be exactly [the interpreter the
# hook runs under, the absolute preflight path]. Then the printed TEXT is run
# through a shell from `/`, and the fixture preflight must print a sentinel:
# a refusal or a wrong path cannot produce it, so a pass here means it ran.
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
PY="${PYTHON:-python3}"

"$PY" - "$REPO_ROOT" <<'PYEOF'
import json, os, shlex, subprocess, sys, tempfile

repo = sys.argv[1]
hook = os.path.join(repo, "hooks", "warn-journal-saved-without-context.py")
EMOJI = "\U0001F4D3"
DATE = "2026-09-24"
SENTINEL = "PREFLIGHT-RAN"
failures = 0

def check(label, got, want):
    global failures
    if got == want:
        print("PASS  %s" % label)
    else:
        print("FAIL  %s (got %r, want %r)" % (label, got, want))
        failures += 1

def reason(tool_name, tool_input, cwd):
    """The deny reason, or None when the hook allowed the write."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name,
               "tool_input": tool_input, "cwd": cwd}
    env = dict(os.environ)
    env.pop("JOURNAL_CONTEXT_BYPASS", None)   # the harness itself must not bypass
    p = subprocess.run([sys.executable, hook], input=json.dumps(payload),
                       capture_output=True, text=True, errors="replace", env=env)
    if p.returncode != 0:
        return "CRASH: rc=%d %s" % (p.returncode, p.stderr.strip()[:200])
    if not p.stdout.strip():
        return None
    out = json.loads(p.stdout).get("hookSpecificOutput", {})
    return out.get("permissionDecisionReason") if out.get("permissionDecision") == "deny" else None

def step1(text):
    for line in (text or "").splitlines():
        if line.startswith("  1. "):
            return line[len("  1. "):]
    return None

def make_vault(root, meta, journals):
    vault = os.path.join(root, "vault-" + meta.replace(" ", "_"))
    os.makedirs(os.path.join(vault, journals, "September 2026"))
    scripts = os.path.join(vault, meta, "scripts")
    os.makedirs(scripts)
    pre = os.path.join(scripts, "journal-preflight.py")
    with open(pre, "w", encoding="utf-8") as fh:
        fh.write("print(%r)\n" % SENTINEL)
    return vault, pre

body = "---\ntype: journal\ncreationDate: %sT22:45\n---\n\n## Journal\nx\n" % DATE

with tempfile.TemporaryDirectory() as tmp:
    tmp = os.path.realpath(tmp)
    vault, pre = make_vault(tmp, "⚙️ Meta", EMOJI + " Journals")
    entry_rel = "%s Journals/September 2026/An Entry.md" % EMOJI
    entry_abs = os.path.join(vault, entry_rel)
    bash_rel = 'cd "%s" && cat > "%s" << \'EOF\'\n%sEOF' % (vault, entry_rel, body)

    for label, tool, tin in [
        ("Write tool", "Write", {"file_path": entry_abs, "content": body}),
        ("relative cd-and-write", "Bash", {"command": bash_rel}),
    ]:
        r = reason(tool, tin, vault)
        check("NEGATIVE CONTROL (%s): no marker -> DENIED" % label,
              isinstance(r, str) and not r.startswith("CRASH"), True)
        cmd = step1(r)
        toks = shlex.split(cmd) if cmd else []
        check("%s: step 1 is exactly [interpreter, script]" % label, len(toks), 2)
        check("%s: interpreter is the one the hook runs under" % label,
              toks[0] if toks else None, sys.executable)
        check("%s: script is the ABSOLUTE preflight path" % label,
              toks[1] if len(toks) > 1 else None, pre)
        if cmd:
            ran = subprocess.run(["bash", "-c", cmd], cwd="/",
                                 capture_output=True, text=True, errors="replace")
            check("%s: the printed text runs from / and reaches the preflight" % label,
                  (ran.returncode, ran.stdout.strip()), (0, SENTINEL))

    # A vault whose meta folder has no emoji must get ITS preflight path, not a
    # hard-coded "⚙️ Meta" that does not exist there.
    plain, plain_pre = make_vault(tmp, "Meta", "Journals")
    r = reason("Write", {"file_path": os.path.join(plain, "Journals", "September 2026", "e.md"),
                         "content": body}, plain)
    toks = shlex.split(step1(r) or "")
    check("plain-Meta vault: script is its own Meta/scripts path",
          toks[1] if len(toks) > 1 else None, plain_pre)
    marker_line = "  %s/Meta/.journal-context/%s.json" % (plain, DATE)
    check("plain-Meta vault: the marker path it names is under Meta too",
          marker_line in (r or "").splitlines(), True)

    # CONTROL: with the marker present there is nothing to print at all.
    os.makedirs(os.path.join(vault, "⚙️ Meta", ".journal-context"))
    open(os.path.join(vault, "⚙️ Meta", ".journal-context", "%s.json" % DATE), "w").write("{}")
    check("CONTROL: marker present -> ALLOWED, no command printed",
          reason("Write", {"file_path": entry_abs, "content": body}, vault), None)

print()
if failures:
    print("FAILED (%d)" % failures)
    sys.exit(1)
print("ALL PASS (13 assertions; 2 negative controls)")
PYEOF

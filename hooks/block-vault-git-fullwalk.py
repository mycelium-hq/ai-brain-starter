#!/usr/bin/env python3
"""
PreToolUse hook: block full-tree git staging inside a large vault.

Dangerous patterns (all walk the full tree, lock .git/index.lock for many minutes):
  git add -A
  git add --all
  git add .          (whole-tree, not git add ./path/to/file)

Safe patterns (pass through):
  git add "specific/file.md"
  git add CLAUDE.md "Meta/rules/foo.md"
  git diff --cached --name-only

Configuration:
    Set VAULT_ROOT env var to the absolute path of your vault. If unset, the
    hook no-ops.
"""
import json, sys, re, os

VAULT = os.environ.get("VAULT_ROOT", "")


def _effective_cwd(command: str, initial: str) -> str:
    """Resolve cwd after any leading `cd <path>` commands in the command string."""
    cwd = os.path.expanduser(initial) if initial else ""
    for chunk in re.split(r"\s*(?:&&|\|\||;)\s*", command):
        chunk = chunk.strip()
        m = re.match(r"cd\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", chunk)
        if m:
            new_path = os.path.expanduser(next(g for g in m.groups() if g is not None))
            cwd = new_path if os.path.isabs(new_path) else os.path.normpath(os.path.join(cwd, new_path))
    return cwd


try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

command = data.get("tool_input", {}).get("command", "")
cwd = os.environ.get("CLAUDE_CWD", data.get("cwd", ""))
cwd = _effective_cwd(command, cwd)

if not VAULT or not cwd.startswith(VAULT):
    sys.exit(0)

# Block git add -A / --all / bare dot.
# Only match at command-start positions (line start, after &&, ;, or |)
# to avoid false positives inside commit messages, heredocs, or comments.
# Does NOT match: git add ./relative/path, git add .gitignore, or
#   mentions of "git add -A" inside quoted strings/heredocs.
DANGEROUS = re.compile(
    r'(?:^|&&|;(?!;)|\|\|?)\s*git\s+add\s+('
    r'-A\b'
    r'|--all\b'
    r'|\.\s*($|&&|;|2>|>>|>|\|)'  # lone dot (not ./path or .gitignore)
    r')',
    re.MULTILINE
)

if DANGEROUS.search(command):
    print(
        "BLOCKED by block-vault-git-fullwalk hook:\n"
        "  git add -A / --all / . walks the whole vault tree.\n"
        "  In a large vault that locks .git/index.lock for many minutes and burns context.\n"
        "  Use explicit paths instead:\n"
        "    git add \"Meta/Sessions/file.md\" \"Meta/rules/foo.md\"",
        file=sys.stderr
    )
    sys.exit(2)

sys.exit(0)

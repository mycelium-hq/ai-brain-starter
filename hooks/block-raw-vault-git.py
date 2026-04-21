#!/usr/bin/env python3
"""
PreToolUse hook: force mutating git ops in a large vault through a safe-commit wrapper.

Why: raw `git add/commit/checkout/reset/merge/rebase` inside a vault with tens of
thousands of files bypasses any vault-wide mutex and races with other sessions
on .git/index.lock. Documented fallout in the wild: index corruption, 10-min
stalls, huge token waste while the assistant waits.

Blocks these subcommands when cwd is under the vault:
    git add / commit / checkout / reset / merge / rebase / restore / switch / stash

Allows read-only ops through:
    git status / diff / log / show / ls-files / rev-parse / branch / config / blame

Allows explicit escapes:
    vault-safe-commit.sh ...   (the sanctioned wrapper)
    GIT_VAULT_BYPASS=1 git ... (emergency escape hatch)

Configuration:
    Set VAULT_ROOT env var (in ~/.claude/settings.json or your shell) to the
    absolute path of your vault. If unset, the hook no-ops.
"""
import json, sys, re, os

VAULT = os.environ.get("VAULT_ROOT", "")

MUTATING = {
    "add", "commit", "checkout", "reset", "merge", "rebase",
    "restore", "switch", "stash", "cherry-pick", "revert", "am",
}

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

command = data.get("tool_input", {}).get("command", "")
cwd = os.environ.get("CLAUDE_CWD", data.get("cwd", ""))

if not VAULT or not cwd.startswith(VAULT):
    sys.exit(0)

if "GIT_VAULT_BYPASS=1" in command or "vault-safe-commit.sh" in command:
    sys.exit(0)

# Find every `git <subcommand>` invocation at a command-start position
# (line start, or after &&, ||, ;, |). Ignore mentions inside quoted strings
# by only matching the first token after separators.
pattern = re.compile(
    r'(?:^|&&|\|\|?|;(?!;))\s*'      # command boundary
    r'(?:[A-Z_][A-Z0-9_]*=\S+\s+)*'   # optional env assignments
    r'git\s+'                          # git
    r'(?:-[A-Za-z]\S*\s+|--\S+\s+)*'  # optional git options (-C dir, --git-dir=...)
    r'([a-z][a-z-]*)',                 # subcommand
    re.MULTILINE,
)

hits = [m.group(1) for m in pattern.finditer(command)]
blocked = [h for h in hits if h in MUTATING]

if blocked:
    print(
        "BLOCKED by block-raw-vault-git hook:\n"
        f"  Raw `git {blocked[0]}` in the vault races with other sessions on\n"
        "  .git/index.lock and bypasses the vault-wide mutex.\n"
        "  Use the wrapper:\n"
        "    bash scripts/vault-safe-commit.sh \\\n"
        "        \"path/one.md\" \"path/two.md\" -m \"commit message\"\n"
        "  Emergency bypass (use sparingly): prefix with GIT_VAULT_BYPASS=1",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)

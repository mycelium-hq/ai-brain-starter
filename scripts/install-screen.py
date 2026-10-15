#!/usr/bin/env python3
# exit-contract: ENFORCING
"""install-screen.py -- render the screen the assistant shows before the one yes.

The paste that starts an install is the request. This screen is the consent:
the assistant prints one of these files verbatim, asks once, and a yes covers
exactly what the screen lists.

    install/screen/<profile>-<platform>.<lang>.txt

`bootstrap.sh --dry-run` and `bootstrap.ps1 -DryRun` print the same file, so
the dry-run and the screen cannot disagree, and the assistant never writes a
number of its own.

Where each part comes from:
  hook counts  the installer's own functions (load_hooks_template,
               normalize_path_substitutions, platformize_template_for_windows,
               merge_hooks). A hook added to hooks.json changes the screen, and
               the default check fails until the screens are regenerated.
  allow hooks  how many of those commands can answer Claude Code's permission
               prompt with "allow" (allow_hooks below). The screen says so while
               that is more than 0, and the line goes away when it reaches 0.
  names        SETS below. scripts/test_install_screen.py runs bootstrap.sh
               --dry-run and fails unless the marketplaces, plugins, cloned
               repos and MCP servers it would add are exactly the ones named.
  words        install/screen/template.<lang>.txt. A line that starts with
               `?key ` is kept only when `key` is set for that screen. A line
               that starts with `*mcp ` is written once per MCP server, with
               {name} and {host} filled in.

Usage:
    install-screen.py           exit 1 if a committed screen is stale (CI)
    install-screen.py --write   regenerate every screen
"""
from __future__ import annotations

import functools
import importlib.util
import re
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCREENS = REPO / "install" / "screen"
HOOKS_JSON = REPO / "hooks.json"
HOOKS_DIR = REPO / "hooks"
WIDTH = 72
LANGS = ("en", "es")

# The optional packs: bootstrap.sh skips all of them under SKIP_VENDOR_SKILLS=1,
# which the corporate profile forces. bootstrap.ps1 does not install them yet.
OPTIONAL_MARKETPLACES = [
    "getsentry/sentry-skills", "trailofbits/skills", "stripe/agent-toolkit",
    "cloudflare/skills", "AgriciDaniel/claude-seo", "obra/superpowers",
    "coreyhaines31/marketingskills",
]
OPTIONAL_PLUGINS = [
    "sentry-skills", "insecure-defaults", "sharp-edges", "property-based-testing",
    "static-analysis", "testing-handbook-skills", "differential-review",
    "ask-questions-if-underspecified", "stripe", "cloudflare", "claude-seo",
    "superpowers", "marketing-skills",
]
OPTIONAL_CLONES = ["yvgude/lean-ctx", "CyberZenithX/Rich-Elicitation-Skill", "vercel-labs/agent-skills"]
KEPANO = ["kepano/obsidian-skills"]
MCP = ["granola", "chatprd"]
# Both are remote servers: the screen names each host, and scripts/test_install_screen.py
# fails unless it is the one bootstrap.sh and bootstrap.ps1 register.
MCP_HOSTS = {"granola": "mcp.granola.ai", "chatprd": "app.chatprd.ai"}

SETS = {
    ("default", "posix"): dict(
        marketplaces=OPTIONAL_MARKETPLACES + KEPANO,
        plugins=OPTIONAL_PLUGINS + ["obsidian", "context7", "playwright"],
        clones=["adelaidasofia/humanizer", "obra/superpowers"] + OPTIONAL_CLONES,
        mcp=MCP,
        tools=["Homebrew (macOS)", "git", "Python", "Node", "pipx", "gh", "Claude Code",
               "Obsidian", "graphify", "fastmcp", "skill-seekers"],
        optional=len(OPTIONAL_MARKETPLACES)),
    ("corporate", "posix"): dict(
        marketplaces=KEPANO,
        plugins=["obsidian", "context7"],
        clones=["adelaidasofia/humanizer", "obra/superpowers"],
        tools=["Python", "Node", "pipx", "gh", "Claude Code", "Obsidian", "graphify", "fastmcp"],
        it_tools=["Homebrew (macOS)", "git"]),
    ("default", "windows"): dict(
        marketplaces=KEPANO,
        plugins=["obsidian", "context7", "playwright"],
        clones=["adelaidasofia/humanizer"],
        mcp=MCP,
        tools=["git", "Python", "Node", "pipx", "gh", "Claude Code", "Obsidian", "graphify", "fastmcp"]),
    ("corporate", "windows"): dict(
        marketplaces=KEPANO,
        plugins=["obsidian", "context7"],
        clones=["adelaidasofia/humanizer"],
        tools=["pipx", "gh", "Claude Code", "graphify", "fastmcp"],
        it_tools=["git", "Python", "Node", "Obsidian"]),
}


@functools.lru_cache(maxsize=None)
def _wired(platform: str, with_vault: bool, hooks_json: Path) -> tuple[dict, int]:
    """What the installer's own functions write into an empty settings.json:
    (the merged settings, how many hooks it added)."""
    spec = importlib.util.spec_from_file_location(
        "install_hooks_user_level", REPO / "scripts" / "install-hooks-user-level.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    # Any existing path stands in for the vault.
    t = installer.normalize_path_substitutions(
        installer.load_hooks_template(hooks_json), str(REPO) if with_vault else None)
    if platform == "windows":
        t, _ = installer.platformize_template_for_windows(t, launcher=["py", "-3"])
    merged, summary = installer.merge_hooks({}, t)
    return merged, len(summary["added"])


def hook_counts(platform: str, hooks_json: Path = HOOKS_JSON) -> tuple[int, int]:
    """(hooks wired at install, hooks wired once a vault exists)."""
    return _wired(platform, False, hooks_json)[1], _wired(platform, True, hooks_json)[1]


def can_allow(text: str) -> bool:
    """True if a hook command, or the script it runs, can print the decision that
    makes Claude Code skip its permission prompt: `--fallback allow` (Windows) or a
    text that names permissionDecision and has a quoted "allow". It would rather
    count a hook that never prints it than miss one that does."""
    return "--fallback allow" in text or (
        "permissionDecision" in text and re.search(r"""["']allow["']""", text) is not None)


@functools.lru_cache(maxsize=None)
def allow_hooks(platform: str, hooks_json: Path = HOOKS_JSON, hooks_dir: Path = HOOKS_DIR) -> int:
    """How many wired PreToolUse commands can answer "allow" (only PreToolUse can),
    from the command's own fallback text or the source of each hooks/ script it
    runs. A named script that is not in `hooks_dir` raises: it cannot be read, and
    skipping it would make the count quietly too low."""
    count = 0
    for group in _wired(platform, True, hooks_json)[0].get("hooks", {}).get("PreToolUse", []):
        for hook in group.get("hooks", []):
            command = hook.get("command", "")
            texts = [command] + [(hooks_dir / name).read_text(encoding="utf-8", errors="replace")
                                 for name in re.findall(r"/hooks/([\w.-]+\.(?:py|sh))", command)]
            count += any(can_allow(text) for text in texts)
    return count


def render(profile: str, platform: str, lang: str, hooks_json: Path = HOOKS_JSON,
           hooks_dir: Path = HOOKS_DIR) -> str:
    names = SETS[profile, platform]
    now, with_vault = hook_counts(platform, hooks_json)
    values = {key: ", ".join(v) if isinstance(v, list) else v for key, v in names.items()}
    values.update({profile: True, platform: True, "hooks": now, "vault_hooks": with_vault - now,
                   "allow_hooks": allow_hooks(platform, hooks_json, hooks_dir)})
    out = []
    for line in (SCREENS / f"template.{lang}.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("?"):
            key, _, line = line[1:].partition(" ")
            if not values.get(key):
                continue
        rows = [values]
        if line.startswith("*"):
            key, _, line = line[1:].partition(" ")
            rows = [dict(values, name=name, host=MCP_HOSTS[name]) for name in names.get(key, [])]
        for row in rows:
            text = line.format_map(row)
            indent = len(text) - len(text.lstrip(" "))
            if len(text) > WIDTH:
                text = textwrap.fill(text, WIDTH, subsequent_indent=" " * (indent + 2 if indent else 0),
                                     break_on_hyphens=False, break_long_words=False)
            out.append(text)
    return "\n".join(out) + "\n"


def screen_path(profile: str, platform: str, lang: str) -> Path:
    return SCREENS / f"{profile}-{platform}.{lang}.txt"


def main(argv: list[str]) -> int:
    if argv not in ([], ["--write"]):
        print("usage: install-screen.py [--write]", file=sys.stderr)
        return 2
    stale = []
    for profile, platform in SETS:
        for lang in LANGS:
            path, text = screen_path(profile, platform, lang), render(profile, platform, lang)
            if argv == ["--write"]:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            elif not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(path.relative_to(REPO).as_posix())
    if stale:
        print("Install screens out of date with the installer:", file=sys.stderr)
        for name in stale:
            print("  " + name, file=sys.stderr)
        print("Regenerate them: python3 scripts/install-screen.py --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

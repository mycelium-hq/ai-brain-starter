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
  names        SETS below. scripts/test_install_screen.py runs bootstrap.sh
               --dry-run and fails unless the marketplaces, plugins, cloned
               repos and MCP servers it would add are exactly the ones named.
  words        install/screen/template.<lang>.txt. A line that starts with
               `?key ` is kept only when `key` is set for that screen.

Usage:
    install-screen.py           exit 1 if a committed screen is stale (CI)
    install-screen.py --write   regenerate every screen
"""
from __future__ import annotations

import functools
import importlib.util
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCREENS = REPO / "install" / "screen"
HOOKS_JSON = REPO / "hooks.json"
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
def hook_counts(platform: str, hooks_json: Path = HOOKS_JSON) -> tuple[int, int]:
    """(hooks wired at install, hooks wired once a vault exists), counted by the
    functions install-hooks-user-level.py itself uses to wire them."""
    spec = importlib.util.spec_from_file_location(
        "install_hooks_user_level", REPO / "scripts" / "install-hooks-user-level.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    template = installer.load_hooks_template(hooks_json)

    def wired(vault: str | None) -> int:
        t = installer.normalize_path_substitutions(template, vault)
        if platform == "windows":
            t, _ = installer.platformize_template_for_windows(t, launcher=["py", "-3"])
        return len(installer.merge_hooks({}, t)[1]["added"])

    return wired(None), wired(str(REPO))  # any existing path stands in for the vault


def render(profile: str, platform: str, lang: str, hooks_json: Path = HOOKS_JSON) -> str:
    names = SETS[profile, platform]
    now, with_vault = hook_counts(platform, hooks_json)
    values = {key: ", ".join(v) if isinstance(v, list) else v for key, v in names.items()}
    values.update({profile: True, platform: True, "hooks": now, "vault_hooks": with_vault - now})
    out = []
    for line in (SCREENS / f"template.{lang}.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("?"):
            key, _, line = line[1:].partition(" ")
            if not values.get(key):
                continue
        line = line.format_map(values)
        indent = len(line) - len(line.lstrip(" "))
        if len(line) > WIDTH:
            line = textwrap.fill(line, WIDTH, subsequent_indent=" " * (indent + 2 if indent else 0),
                                 break_on_hyphens=False, break_long_words=False)
        out.append(line)
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

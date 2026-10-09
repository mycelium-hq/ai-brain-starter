#!/usr/bin/env python3
"""Tests for the install screen, the one consent the installing assistant asks for.

A yes covers exactly what the screen lists, so each block checks that the
screen tells the truth about the install, from the code that runs it:

  1. the committed screens are what scripts/install-screen.py renders now;
  2. the hook count is the installer's: one hook added to a copy of hooks.json
     raises the number on the screen by one (a hand-typed count fails this);
  3. layout: 72 columns, 48 lines (40 for corporate), English ASCII-only, no "!"
     or em dash;
  4. bootstrap.sh --dry-run, per profile, would add exactly the marketplaces,
     plugins, cloned repos and MCP servers its screen names (POSIX only; the
     windows-install workflow checks the Windows screen against a real install);
  5. ABS_CONSENTED=1 makes bootstrap.sh record one yes line, and nothing is
     written without it or under --dry-run;
  6. install-telemetry.py tells a finished run from one that stopped after a yes;
  7. the screen says that hooks approve edits and commands exactly when one of the
     wired hooks can, and a planted hook that answers "allow" is counted;
  8. each remote MCP server is named with the host bootstrap registers, and the
     jobs the interview schedules later are stated in plain words;
  9. every screen file the README and phase-00 point to is a committed file.

Plain script, no pytest (the CI job runs scripts/test_*.py directly on 3.9).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


screen = _load("install_screen", "install-screen.py")
telemetry = _load("install_telemetry", "install-telemetry.py")
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: object = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  -> {detail!r}"))
    if not cond:
        FAILURES.append(name)


def bash(script: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script, "_", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=900)


print("1. committed screens are current")
check("install-screen.py check exits 0", screen.main([]) == 0, "run: python3 scripts/install-screen.py --write")

print("2. the hook count comes from the installer")
with tempfile.TemporaryDirectory() as tmp:
    hooks = json.loads((REPO / "hooks.json").read_text(encoding="utf-8"))
    # The shape every shipped Python hook has, so the Windows rewrite keeps it.
    hooks["hooks"]["SessionStart"].append({"hooks": [{"type": "command", "command":
        "[PYTHON] ~/.claude/skills/ai-brain-starter/hooks/planted-by-test.py 2>/dev/null"
        " || echo '{\"continue\":true,\"suppressOutput\":true}'"}]})
    planted = Path(tmp) / "hooks.json"
    planted.write_text(json.dumps(hooks), encoding="utf-8")
    for platform in ("posix", "windows"):
        base, plus = screen.hook_counts(platform)[0], screen.hook_counts(platform, planted)[0]
        check(f"{platform}: one planted hook raises the count by one", plus == base + 1, (base, plus))
        text = screen.render("default", platform, "en", planted)
        check(f"{platform}: the screen shows the raised count", f"  {plus} hooks in " in text, text[:300])

print("3. layout")
# Why the default screen may run to 48 lines when the ticket asked for 40: the
# names are the consent. The default install adds a long list of marketplaces,
# plugins, skill repos, remote MCP servers and tools, and a yes is only as
# informed as that list is complete, so cutting it to fit 40 would cut the
# consent, and the plain-words facts about hooks and scheduled jobs it must
# also carry would be next. The corporate profile installs a handful of parts
# and has no such list, so it keeps the original 40.
LINE_LIMIT = {"default": 48, "corporate": 40}
for profile, platform in screen.SETS:
    for lang in screen.LANGS:
        path = screen.screen_path(profile, platform, lang)
        lines = path.read_text(encoding="utf-8").splitlines()
        label = path.name
        check(f"{label}: at most 72 columns", all(len(line) <= 72 for line in lines),
              [line for line in lines if len(line) > 72])
        check(f"{label}: at most {LINE_LIMIT[profile]} lines", len(lines) <= LINE_LIMIT[profile], len(lines))
        check(f"{label}: no '!' and no em dash", not any(c in "".join(lines) for c in "!—"))
        reply = 'Reply "yes"' if lang == "en" else 'Respondé "sí"'
        check(f"{label}: ends on the one question", reply in "\n".join(lines[-3:]), lines[-3:])
        if lang == "en":
            check(f"{label}: ASCII only", "".join(lines).isascii())

print("4. bootstrap.sh --dry-run adds exactly what the screen names")
DRY_RUN = r'''
. "$1/tests/integration/lib/sandbox_home.sh"
sandbox_home "$2"
touch "$HOME/.claude/.ai-brain-starter-email-on-file"
mkdir -p "$HOME/.claude/skills" && ln -s "$1" "$HOME/.claude/skills/ai-brain-starter"
repo="$1"; shift 2
EMAIL=ci@example.com NAME=CI LANG_HINT=en BOOTSTRAP_LANG=en bash "$repo/bootstrap.sh" --dry-run "$@"
'''


def would_add(out: str) -> dict:
    out = re.sub(r"\x1b\[[0-9;]*m", "", out)
    found = {
        "marketplaces": re.findall(r"would: claude plugin marketplace add (\S+)", out)
        + re.findall(r"marketplace \(([\w.-]+/[\w.-]+)\) and enable:", out),
        "plugins": [p.split("@")[0] for p in re.findall(r"would: claude plugin install (\S+)", out)],
        "clones": re.findall(r"clone \(https://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?\) ", out),
        "mcp": [],
    }
    for enabled in re.findall(r"and enable: ([^\n(]+)", out):
        found["plugins"] += [p.strip() for p in enabled.split(",") if p.strip()]
    for servers in re.findall(r"would register (.+?) MCPs", out):
        found["mcp"] += [s.strip() for s in servers.split("+")]
    return {key: sorted(v) for key, v in found.items()}


if os.name == "nt":
    print("  skip: POSIX dry-run (Windows is checked by .github/workflows/windows-install.yml)")
else:
    for profile, extra in (("default", ()), ("corporate", ("--profile", "corporate"))):
        with tempfile.TemporaryDirectory() as tmp:
            run = bash(DRY_RUN, str(REPO), tmp, *extra)
        check(f"{profile}: dry-run exits 0", run.returncode == 0, run.stdout[-800:] + run.stderr[-800:])
        found, named = would_add(run.stdout), screen.SETS[profile, "posix"]
        for key in ("marketplaces", "plugins", "clones", "mcp"):
            check(f"{profile}: {key} match the screen", found[key] == sorted(named.get(key, [])),
                  {"dry-run": found[key], "screen": sorted(named.get(key, []))})
        check(f"{profile}: dry-run ends on its screen", run.stdout.rstrip().endswith(
            screen.screen_path(profile, "posix", "en").read_text(encoding="utf-8").rstrip()))

print("5. ABS_CONSENTED=1 records the yes")
source = (REPO / "bootstrap.sh").read_text(encoding="utf-8")
block = re.search(r"# ai-brain:consent-record:start\n(.*?)# ai-brain:consent-record:end", source, re.S)
check("consent-record block found in bootstrap.sh", block is not None)
for consented, dry, corporate, expect in (("1", "0", "0", "default"), ("1", "0", "1", "corporate"),
                                          ("0", "0", "0", None), ("1", "1", "0", None)):
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(Path(tmp) / ".claude")
        env = dict(os.environ, HOME=tmp, ABS_CONSENTED=consented, DRY_RUN=dry, CORPORATE_PROFILE=corporate)
        bash(block.group(1) if block else "exit 3", env=env)
        log = Path(tmp) / ".claude" / ".ai-brain-starter-install.jsonl"
        lines = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
        label = f"ABS_CONSENTED={consented} DRY_RUN={dry} corporate={corporate}"
        if expect is None:
            check(f"{label}: writes nothing", lines == [], lines)
        else:
            record = json.loads(lines[0]) if len(lines) == 1 else {}
            check(f"{label}: one yes_recorded line", record.get("outcome") == "yes_recorded"
                  and record.get("phase") == "consent" and record.get("profile") == expect, lines)

print("6. install-telemetry.py splits runs at each yes")
events = [{"outcome": "yes_recorded", "ts": "a"}, {"phase": "0", "outcome": "completed"},
          {"phase": telemetry.TERMINAL_PHASE, "outcome": "completed"},
          {"outcome": "yes_recorded", "ts": "b"}, {"phase": "3", "outcome": "completed"},
          {"phase": "4", "outcome": "skipped_on_user_no"}, {"outcome": "yes_recorded", "ts": "c"}]
runs = telemetry.consent_runs(events)
check("three runs", len(runs) == 3, runs)
check("first run finished", runs[0]["finished"] and runs[0]["last"] == telemetry.TERMINAL_PHASE, runs[0])
check("second run stopped after phase 3", not runs[1]["finished"] and runs[1]["last"] == "3", runs[1])
check("third run never completed a phase", not runs[2]["finished"] and runs[2]["last"] is None, runs[2])

print("7. the screen says hooks approve edits and commands exactly when a wired hook can")
APPROVES = '("allow")'  # how both languages name it
# The line follows the count. A screen without it while a wired hook can answer
# "allow" leaves the README's sentence about it untrue; one with it when none can
# says something false. The fix that stops those hooks answering reads 0 here and
# the line goes away with no copy edit.
for profile, platform in screen.SETS:
    n = screen.allow_hooks(platform)
    for lang in screen.LANGS:
        text = screen.screen_path(profile, platform, lang).read_text(encoding="utf-8")
        check(f"{profile}-{platform}.{lang}: names hooks that approve iff one can ({n} can)",
              (APPROVES in text) == (n > 0), n)
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "hooks").mkdir()
    (tmp / "hooks" / "quiet.py").write_text("print('{}')\n", encoding="utf-8")
    (tmp / "hooks" / "approves.py").write_text(
        'import json\nprint(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", '
        '"permissionDecision": "allow"}}))\n', encoding="utf-8")
    echo_allow = ("2>/dev/null || echo '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\","
                  "\"permissionDecision\":\"allow\"}}'")

    def planted_template(name: str, *commands: str) -> Path:
        path = tmp / f"{name}.json"
        hooks = [{"type": "command", "command": "[PYTHON] ~/.claude/skills/ai-brain-starter/hooks/" + c}
                 for c in commands]
        path.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": hooks}]}}),
                        encoding="utf-8")
        return path

    for platform in ("posix", "windows"):
        quiet = planted_template(f"quiet-{platform}", "quiet.py")
        script = planted_template(f"script-{platform}", "quiet.py", "approves.py")
        fallback = planted_template(f"fallback-{platform}", "quiet.py " + echo_allow)
        count = {name: screen.allow_hooks(platform, path, tmp / "hooks")
                 for name, path in (("quiet", quiet), ("script", script), ("fallback", fallback))}
        check(f"{platform}: hooks that never answer allow are not counted", count["quiet"] == 0, count)
        check(f"{platform}: a planted script that answers allow raises the count", count["script"] == 1, count)
        check(f"{platform}: a planted allow fallback raises the count", count["fallback"] == 1, count)
        shown = {name: APPROVES in screen.render("default", platform, "en", path, tmp / "hooks")
                 for name, path in (("quiet", quiet), ("script", script))}
        check(f"{platform}: the planted script puts the line on the screen, quiet hooks do not",
              shown == {"quiet": False, "script": True}, shown)
    missing = planted_template("missing", "not-there.py")
    try:
        screen.allow_hooks("posix", missing, tmp / "hooks")
        unread = False
    except FileNotFoundError:
        unread = True
    check("a hook script that cannot be read stops the render instead of lowering the count", unread)

print("8. the remote MCP servers and the later jobs are stated in plain words")
MCP_ROW = {"en": "receives conversation content when used", "es": "recibe tu conversación cuando se usa"}
for installer in ("bootstrap.sh", "bootstrap.ps1"):
    registered = dict(re.findall(
        r"""\[["'](\w+)["']\]\s*=\s*\{["']type["']:\s*["']url["'],\s*["']url["']:\s*["']https://([\w.-]+)/""",
        (REPO / installer).read_text(encoding="utf-8")))
    check(f"{installer} registers the MCP hosts the screen names", registered == screen.MCP_HOSTS, registered)
# The interview schedules these after the yes (phase-18 and install_auto_gc), so
# the screen has to say what they do. Words per language: what each job does,
# and whether it runs unattended; the daily job exists on macOS and Linux only.
SAYS = {"en": ("deletes merged git branches", "unattended"), "es": ("borra ramas de git fusionadas", "sin supervisión")}
for profile, platform in screen.SETS:
    for lang in screen.LANGS:
        path = screen.screen_path(profile, platform, lang)
        text = path.read_text(encoding="utf-8")
        for name in screen.SETS[profile, platform].get("mcp", []):
            rows = [line for line in text.splitlines() if line.strip().startswith(name)]
            check(f"{path.name}: {name} names its host and says it receives conversation content",
                  len(rows) == 1 and screen.MCP_HOSTS[name] in rows[0] and MCP_ROW[lang] in rows[0], rows)
        daily, unattended = SAYS[lang]
        check(f"{path.name}: says the insights jobs run unattended", unattended in text, text[-900:])
        has_daily = platform == "posix"
        check(f"{path.name}: {'states' if has_daily else 'does not claim'} the daily cleanup job",
              all(w in text for w in (daily, "~/dev", "ABS_NO_AUTO_GC=1")) == has_daily
              and ("ABS_NO_AUTO_GC=1" in text) == has_daily, text[-900:])
insights = (REPO / "phases" / "phase-18-insights.md").read_text(encoding="utf-8")
check("phase-18 runs the insights jobs unattended, allowed to edit files and run shell commands",
      "--permission-mode acceptEdits" in insights and '--allowedTools "Read,Write,Edit,Glob,Grep,Bash"' in insights)

print("9. every screen file the README and phase-00 point to is a committed file")
SCREEN_FILE = re.compile(r"install[/\\]screen[/\\]([\w.-]+\.txt)")


def missing_screen_files(text: str) -> list:
    return sorted({n for n in SCREEN_FILE.findall(text) if not (screen.SCREENS / n).is_file()})


for doc in ("README.md", "phases/phase-00-install.md"):
    text = (REPO / doc).read_text(encoding="utf-8")
    check(f"{doc}: names screen files", len(set(SCREEN_FILE.findall(text))) >= 2, SCREEN_FILE.findall(text))
    check(f"{doc}: every screen file it names exists", missing_screen_files(text) == [],
          missing_screen_files(text))
check("a screen file that does not exist is caught",
      missing_screen_files(r"install/screen/default-posix.fr.txt install\screen\nope.txt") ==
      ["default-posix.fr.txt", "nope.txt"])

if FAILURES:
    print(f"\n{len(FAILURES)} check(s) failed")
    sys.exit(1)
print("\nPASS: the install screen matches the installer")

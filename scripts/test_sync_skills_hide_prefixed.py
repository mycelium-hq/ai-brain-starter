#!/usr/bin/env python3
"""Each skill shows once in the slash menu after an update (tickets#6817).

Runs hide_prefixed_copies() from sync-skills.py against throwaway homes.
Run: python3 scripts/test_sync_skills_hide_prefixed.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sync_skills", HERE / "sync-skills.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failures = []


def home(settings_text, plugins=("ai-brain-starter", "humanizer")):
    root = Path(tempfile.mkdtemp())
    skills = root / ".claude" / "skills"
    for name in plugins:
        (skills / name / ".claude-plugin").mkdir(parents=True)
        (skills / name / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (skills / "ai-brain-starter").mkdir(parents=True, exist_ok=True)
    if settings_text is not None:
        (root / ".claude" / "settings.json").write_text(settings_text, encoding="utf-8")
    return root, skills / "ai-brain-starter", skills


def check(name, cond):
    if not cond:
        failures.append(name)
    print(("PASS " if cond else "FAIL ") + name)


def read(root):
    return json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))


# Turns both copies off, keeps other keys and comments.
root, starter, skills = home('{"_comment": "keep", "hooks": {"Stop": []}}')
check("reports the change", mod.hide_prefixed_copies(starter, skills) is not None)
s = read(root)
check("both turned off", s["enabledPlugins"] == {"ai-brain-starter@skills-dir": False,
                                                  "humanizer@skills-dir": False})
check("other keys kept", s["_comment"] == "keep" and s["hooks"] == {"Stop": []})
check("second run changes nothing", mod.hide_prefixed_copies(starter, skills) is None)

# A choice the user made stays.
root, starter, skills = home('{"enabledPlugins": {"humanizer@skills-dir": true}}')
mod.hide_prefixed_copies(starter, skills)
check("user's true kept", read(root)["enabledPlugins"]["humanizer@skills-dir"] is True)

# No humanizer folder: its key is not added.
root, starter, skills = home("{}", plugins=("ai-brain-starter",))
mod.hide_prefixed_copies(starter, skills)
check("no humanizer key without the folder",
      "humanizer@skills-dir" not in read(root)["enabledPlugins"])

# Odd files are left alone, never crash.
for label, text in [("missing", None), ("malformed", "{nope"), ("list", "[]"),
                    ("plugins null", '{"enabledPlugins": null}')]:
    root, starter, skills = home(text)
    check(label + " returns quietly", mod.hide_prefixed_copies(starter, skills) is None)
    path = root / ".claude" / "settings.json"
    check(label + " left as it was",
          (not path.exists()) if text is None else path.read_text(encoding="utf-8") == text)

# BOM file still works.
root, starter, skills = home("﻿{}")
check("BOM file handled", mod.hide_prefixed_copies(starter, skills) is not None)

# Not a clone install: nothing changes.
root, starter, skills = home("{}")
check("non-clone untouched", mod.hide_prefixed_copies(starter, root / "elsewhere") is None)

sys.exit(1 if failures else 0)

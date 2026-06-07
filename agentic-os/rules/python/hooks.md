---
name: python
paths: ["**/*.py"]
description: Quality rules applied automatically to Python files on edit.
---

# Python rules

These apply automatically when you edit a `.py` file — the `paths_scoped_rules`
hook matches the glob above and surfaces this block. No per-file wiring.

- **Lint clean.** `ruff check` (or flake8) passes on touched files.
- **Types check** where annotated: `mypy` / `pyright` on the module you edited.
- **No `print()` debugging** and no stray `breakpoint()` in committed code.
- **`from __future__ import annotations`** if the project targets Python < 3.10
  and you use `X | None` syntax in annotations.
- **No bare `except:`** — catch the specific exception; never swallow silently.

Tune this list to your stack. The glob (`paths:`) decides which files it governs;
edit the glob, not the wiring.

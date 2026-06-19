#!/usr/bin/env python3
"""SessionStart hook: surface a connector that has silently gone empty.

The visible-alert half of the connector liveness watchdog (the 0-vs-0 gap). An
ingest connector (Granola, WhatsApp, iMessage, Slack, Gmail) can keep exiting 0
while quietly returning 0 items after a vendor changes a surface, so the brain
goes stale with no signal. scripts/check-connector-liveness.py is the tested
detection core + the diagnose/sunday surface; this hook is the every-session
canary that names the broken connector at the NEXT session start.

It does NOT re-implement detection — it loads the same module the integration
test and `diagnose` exercise, so the alert and the gate can never drift.

Output: silent when every connector is fresh (or none exist). One systemMessage
block listing each connector that is silently overdue.

Bypass: CONNECTOR_LIVENESS_SURFACE_BYPASS=1 in env.
Test seam: CONNECTOR_LIVENESS_NOW=YYYY-MM-DD pins "today" (hermetic tests only).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path


def _load_check_module():
    """Import scripts/check-connector-liveness.py by path (the hyphenated name is
    not a legal module identifier, so spec_from_file_location is required)."""
    script = Path(__file__).resolve().parent.parent / "scripts" / "check-connector-liveness.py"
    if not script.is_file():
        return None
    spec = importlib.util.spec_from_file_location("check_connector_liveness", script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_vault_root(cwd: Path) -> Path | None:
    """Walk up to the vault root: a dir holding External Inputs/ or a Meta-ish
    folder. If cwd is inside a worktree, reset to the main checkout first.
    Mirrors find_vault_root() in surface-stranded-session-artifacts.py."""
    parts = cwd.parts
    if ".claude" in parts:
        idx = parts.index(".claude")
        if idx + 1 < len(parts) and parts[idx + 1] == "worktrees" and idx > 0:
            cwd = Path(*parts[:idx])

    p = cwd.resolve()
    for _ in range(8):
        if not p.is_dir():
            break
        if (p / "External Inputs").is_dir():
            return p
        try:
            children = list(p.iterdir())
        except OSError:
            children = []
        if any(c.is_dir() and c.name.endswith("Meta") for c in children):
            return p
        parent = p.parent
        if parent == p:
            break
        p = parent
    return None


def _resolve_now() -> date:
    override = os.environ.get("CONNECTOR_LIVENESS_NOW")
    if override:
        try:
            return datetime.strptime(override, "%Y-%m-%d").date()
        except ValueError:
            pass
    return datetime.now().date()


def main() -> int:
    if os.environ.get("CONNECTOR_LIVENESS_SURFACE_BYPASS"):
        return 0

    # SessionStart payload arrives on stdin (JSON). Drain so we never block.
    try:
        sys.stdin.read()
    except Exception:
        pass

    # Fail silent on ANY error: a watchdog must never break session start.
    try:
        mod = _load_check_module()
        if mod is None:
            return 0
        vault = find_vault_root(Path.cwd())
        if vault is None:
            return 0
        cadence = mod._load_cadence_config(None, vault)
        connectors = mod.discover_external_inputs(vault)
        connectors.update(mod.discover_granola(vault))
        if not connectors:
            return 0
        gaps = mod.evaluate(connectors, _resolve_now(), cadence)
    except Exception:
        return 0

    if not gaps:
        return 0

    lines = []
    for source, scope, silence, tol in gaps:
        lines.append(
            f"  - {source}/{scope}: no new data for {silence} day(s) "
            f"(its {tol}-day tolerance is blown)."
        )
    msg = (
        f"[connector-liveness] {len(gaps)} ingest connector(s) have silently "
        f"stopped producing data (the 0-vs-0 gap — they can exit 0 while "
        f"returning 0 items after a vendor changes a surface):\n"
        + "\n".join(lines)
        + "\n\nCheck each source's auth/permissions, re-run its ingest skill, "
        "and confirm it pulls >0 items. Full report: "
        "scripts/check-connector-liveness.py (also wired into /diagnose)."
    )
    print(json.dumps({"systemMessage": msg}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

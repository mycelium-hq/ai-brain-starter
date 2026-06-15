#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
context-budget-measure.py — SessionStart guard: measure the always-loaded TEXT
layer and warn when it grows.

The always-loaded text layer — global ~/.claude/CLAUDE.md + the project's
CLAUDE.md + MEMORY.md + the project's CONTEXT.md — is paid in tokens on EVERY
turn of EVERY session, forever. It is the most expensive context in the system
and the one with no measurement guard: plugin / MCP load is measured
(token-economics), MEMORY.md has its own cliff guard, but the CLAUDE.md kernel
files themselves silently grow until a new session opens already-full.

This hook measures that layer each SessionStart and:
  • warns if a file exceeds its hard ceiling (default: global CLAUDE.md > 40 KB),
  • warns if the TOTAL grew past a stored baseline (drift detection),
  • silently RATCHETS the baseline DOWN when the layer shrinks (records new low),
  • stays silent when healthy.

Ratchet semantics: baseline = the lowest total seen (the floor). Growth above
floor + tolerance warns and does NOT move the floor — it keeps surfacing until
you slim back, OR run `--accept` to acknowledge an intentional add as the new
floor. A shrink updates the floor silently. This is a measure-and-warn ratchet,
NOT a governance framework — match the guard to the recurrence rate.

Fail-open: a SessionStart nudge must NEVER crash-block a session.
Freq-capped: warns at most once per day.
Bypass:  CONTEXT_BUDGET_BYPASS=1
Accept an intentional growth as the new floor:  context-budget-measure.py --accept
Tune ceilings (bytes):  CONTEXT_BUDGET_GLOBAL_CEILING (default 40000)

Modes:
  (no args, reads stdin JSON)  SessionStart hook mode — emits additionalContext or no-ops
  --report                     print the table to stdout (human / CLI)
  --accept                     set the baseline floor to the current total
  --self-test                  positive + negative control; exit 0 iff all pass

Bug class: ALWAYS-LOADED-TEXT-UNMEASURED (sibling of ARTIFACT-WITHOUT-MEASUREMENT).
MEMORY.md remediation is owned by check-memory-md-cap.py — this hook measures
MEMORY.md for the total but does NOT duplicate its cliff warning.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

# --- tunables (env-overridable) ------------------------------------------------
GLOBAL_CEILING = int(os.environ.get("CONTEXT_BUDGET_GLOBAL_CEILING", 40000))
# growth tolerance: absorb normal small adds, catch real drift
TOL_BYTES = int(os.environ.get("CONTEXT_BUDGET_TOL_BYTES", 4096))
TOL_FRAC = float(os.environ.get("CONTEXT_BUDGET_TOL_FRAC", 0.02))

HOME = Path.home()
BASELINE_PATH = HOME / ".claude" / ".context-budget-baseline.json"
LASTWARN_PATH = HOME / ".claude" / ".context-budget-last-warn"


def noop():
    print(json.dumps({"continue": True, "suppressOutput": True}))
    sys.exit(0)


# --- file discovery (generic, name-free) --------------------------------------
def _memory_md(cwd: str) -> Path | None:
    """Locate MEMORY.md the way Claude Code loads it (sanitized-cwd projects dir),
    falling back to the in-vault canonical path. Mirrors check-memory-md-cap.py."""
    cands: list[Path] = []
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        cands.append(Path(env) / "⚙️ Meta/Agent Memory/MEMORY.md")
    try:
        san = "-" + str(Path(cwd)).replace("/", "-")
        cands.append(HOME / ".claude/projects" / san / "memory/MEMORY.md")
        m = re.match(r"(.*)--claude-worktrees-[^/]+$", san)
        if m:
            cands.append(HOME / ".claude/projects" / m.group(1) / "memory/MEMORY.md")
    except Exception:
        pass
    try:
        cur = Path(cwd)
        for _ in range(10):
            cands.append(cur / "⚙️ Meta/Agent Memory/MEMORY.md")
            if cur.parent == cur:
                break
            cur = cur.parent
    except Exception:
        pass
    for c in cands:
        try:
            if c.is_file():
                return c
        except Exception:
            continue
    return None


def _project_file(cwd: str, name: str) -> Path | None:
    """Find <name> (CLAUDE.md / CONTEXT.md) at the project root: CLAUDE_PROJECT_DIR
    first, else walk up from cwd."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        p = Path(env) / name
        try:
            if p.is_file():
                return p
        except Exception:
            pass
    try:
        cur = Path(cwd)
        for _ in range(10):
            p = cur / name
            if p.is_file():
                return p
            if cur.parent == cur:
                break
            cur = cur.parent
    except Exception:
        pass
    return None


def discover(cwd: str) -> list[dict]:
    """Return the always-loaded text files present, each with size + ceiling.

    `kind` drives reporting; `ceiling` is the hard per-file warn threshold (None =
    baseline-drift only); `defer_to` names a guard that owns this file's hard
    warning so we don't double-nag (MEMORY.md -> check-memory-md-cap.py)."""
    items: list[dict] = []

    def add(path: Path | None, kind: str, ceiling: int | None, defer_to: str | None = None):
        if path is None:
            return
        try:
            size = path.stat().st_size
        except Exception:
            return
        items.append({"path": str(path), "kind": kind, "bytes": size,
                      "ceiling": ceiling, "defer_to": defer_to})

    add(HOME / ".claude" / "CLAUDE.md", "global CLAUDE.md", GLOBAL_CEILING)
    add(_project_file(cwd, "CLAUDE.md"), "project CLAUDE.md", None)
    add(_memory_md(cwd), "MEMORY.md", None, defer_to="check-memory-md-cap.py")
    add(_project_file(cwd, "CONTEXT.md"), "project CONTEXT.md", None)
    # de-dup by resolved path (global and project CLAUDE.md can coincide)
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        try:
            rp = str(Path(it["path"]).resolve())
        except Exception:
            rp = it["path"]
        if rp in seen:
            continue
        seen.add(rp)
        out.append(it)
    return out


# --- baseline persistence ------------------------------------------------------
def load_baseline() -> dict | None:
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_baseline(total: int, files: dict) -> None:
    try:
        BASELINE_PATH.write_text(
            json.dumps({"total": total, "files": files}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def warned_today() -> bool:
    try:
        return LASTWARN_PATH.read_text(encoding="utf-8").strip() == date.today().isoformat()
    except Exception:
        return False


def mark_warned() -> None:
    try:
        LASTWARN_PATH.write_text(date.today().isoformat(), encoding="utf-8")
    except Exception:
        pass


# --- core evaluation -----------------------------------------------------------
def evaluate(items: list[dict], baseline: dict | None) -> dict:
    """Pure decision function (no I/O) so the self-test can drive it directly.

    Returns {total, ceiling_hits, grew, growth_bytes, ratchet_down}."""
    total = sum(it["bytes"] for it in items)
    ceiling_hits = [it for it in items
                    if it["ceiling"] is not None and it["bytes"] > it["ceiling"]]
    base_total = baseline.get("total") if baseline else None
    grew = False
    growth = 0
    ratchet_down = False
    if base_total is None:
        # first run: establish the floor; do not claim growth
        ratchet_down = True
    elif total <= base_total:
        ratchet_down = True
    else:
        tol = max(TOL_BYTES, int(base_total * TOL_FRAC))
        if total > base_total + tol:
            grew = True
            growth = total - base_total
    return {"total": total, "ceiling_hits": ceiling_hits, "grew": grew,
            "growth_bytes": growth, "ratchet_down": ratchet_down,
            "base_total": base_total}


def _kb(n: int) -> str:
    return f"{n / 1000:.1f} KB"


def _tok(n: int) -> str:
    return f"~{round(n / 4):,} tok"


def render_report(items: list[dict], ev: dict) -> str:
    lines = ["Always-loaded text layer:"]
    for it in sorted(items, key=lambda x: -x["bytes"]):
        flag = ""
        if it["ceiling"] is not None and it["bytes"] > it["ceiling"]:
            flag = f"  🔴 over {_kb(it['ceiling'])} ceiling"
        elif it["defer_to"]:
            flag = f"  (cliff guard: {it['defer_to']})"
        lines.append(f"  {_kb(it['bytes']):>9}  {_tok(it['bytes']):>12}  {it['kind']}{flag}")
    lines.append(f"  {'—' * 7}")
    lines.append(f"  {_kb(ev['total']):>9}  {_tok(ev['total']):>12}  TOTAL")
    if ev["base_total"] is not None:
        delta = ev["total"] - ev["base_total"]
        sign = "+" if delta >= 0 else ""
        lines.append(f"  baseline floor {_kb(ev['base_total'])} (Δ {sign}{delta} B)")
    return "\n".join(lines)


def build_warning(items: list[dict], ev: dict) -> str | None:
    """The additionalContext message, or None when healthy."""
    if not ev["ceiling_hits"] and not ev["grew"]:
        return None
    parts = [render_report(items, ev), ""]
    if ev["ceiling_hits"]:
        for it in ev["ceiling_hits"]:
            over = it["bytes"] - it["ceiling"]
            parts.append(
                f"🔴 {it['kind']} is {_kb(it['bytes'])} — {over} B over the "
                f"{_kb(it['ceiling'])} ceiling. The always-loaded kernel pays this "
                f"every turn; move rationale into linked rule files and keep the "
                f"kernel to one-line pointers."
            )
    if ev["grew"]:
        parts.append(
            f"⚠️ Total always-loaded text grew {ev['growth_bytes']} B past the "
            f"baseline floor ({_kb(ev['base_total'])} → {_kb(ev['total'])}). Slim "
            f"back, or run `context-budget-measure.py --accept` to set this as the "
            f"new floor if the growth is intentional."
        )
    parts.append("Guard: context-budget-measure.py (MYC-619). Bypass: CONTEXT_BUDGET_BYPASS=1")
    return "\n".join(parts)


# --- modes ---------------------------------------------------------------------
def hook_mode():
    if os.environ.get("CONTEXT_BUDGET_BYPASS") == "1":
        noop()
    cwd = os.getcwd()
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            cwd = data.get("cwd") or data.get("workspace") or cwd
    except Exception:
        pass

    items = discover(cwd)
    if not items:
        noop()
    baseline = load_baseline()
    ev = evaluate(items, baseline)
    files_map = {it["path"]: it["bytes"] for it in items}

    # Ratchet the floor DOWN silently when at/below baseline (records the new low).
    if ev["ratchet_down"]:
        save_baseline(ev["total"], files_map)

    msg = build_warning(items, ev)
    if msg is None or warned_today():
        noop()

    mark_warned()
    total_kb = _kb(ev["total"])
    print(json.dumps({
        "systemMessage": f"📏 Always-loaded context {total_kb} — context-budget guard flagged growth/ceiling. See details.",
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg},
    }))


def report_mode():
    items = discover(os.getcwd())
    ev = evaluate(items, load_baseline())
    print(render_report(items, ev))
    msg = build_warning(items, ev)
    if msg:
        print("\n" + msg)


def accept_mode():
    items = discover(os.getcwd())
    total = sum(it["bytes"] for it in items)
    save_baseline(total, {it["path"]: it["bytes"] for it in items})
    print(f"baseline floor set to {_kb(total)} ({total} B)")


def self_test() -> int:
    """Positive (over-ceiling fires) + negative (lean is silent) + drift + shrink.
    Drives the pure evaluate() so no real home files are touched."""
    fails = []

    def mk(bytes_, kind, ceiling, defer=None):
        return {"path": f"/tmp/{kind}", "kind": kind, "bytes": bytes_,
                "ceiling": ceiling, "defer_to": defer}

    # 1. POSITIVE: a global CLAUDE.md over the 40KB ceiling must fire.
    items = [mk(74100, "global CLAUDE.md", GLOBAL_CEILING),
             mk(10000, "project CONTEXT.md", None)]
    ev = evaluate(items, {"total": 84100})  # baseline == current -> no growth
    if not ev["ceiling_hits"] or build_warning(items, ev) is None:
        fails.append("POSITIVE: over-ceiling did not fire")

    # 2. NEGATIVE: a lean layer at/under the floor and ceilings must be silent.
    items = [mk(30000, "global CLAUDE.md", GLOBAL_CEILING),
             mk(8000, "project CONTEXT.md", None)]
    ev = evaluate(items, {"total": 40000})  # current 38000 < baseline -> shrink
    if build_warning(items, ev) is not None:
        fails.append("NEGATIVE: lean layer warned when it should be silent")
    if not ev["ratchet_down"]:
        fails.append("SHRINK: did not ratchet the floor down")

    # 3. DRIFT: total grows past floor + tolerance -> warn (no ceiling hit).
    items = [mk(20000, "global CLAUDE.md", GLOBAL_CEILING),
             mk(20000, "project CLAUDE.md", None)]
    ev = evaluate(items, {"total": 30000})  # +10000 over 30000 floor >> tol
    if not ev["grew"] or build_warning(items, ev) is None:
        fails.append("DRIFT: growth past baseline did not fire")

    # 4. TOLERANCE: a tiny add under tolerance must NOT warn.
    items = [mk(30500, "global CLAUDE.md", GLOBAL_CEILING)]
    ev = evaluate(items, {"total": 30000})  # +500 < max(4096, 2%) tol
    if ev["grew"]:
        fails.append("TOLERANCE: tiny add false-fired")

    # 5. END-TO-END: real discover() + a synthesized over-ceiling global file in a
    #    temp HOME proves the I/O path, not just the pure function. Isolate from a
    #    live CLAUDE_PROJECT_DIR so the real vault files can't leak into the check.
    global HOME, BASELINE_PATH
    old_home, old_base = HOME, BASELINE_PATH
    old_proj = os.environ.pop("CLAUDE_PROJECT_DIR", None)
    try:
        with tempfile.TemporaryDirectory() as td:
            fake_global = Path(td) / ".claude"
            fake_global.mkdir(parents=True)
            (fake_global / "CLAUDE.md").write_text("x" * 50000, encoding="utf-8")
            HOME = Path(td)
            BASELINE_PATH = Path(td) / ".claude" / ".context-budget-baseline.json"
            its = discover(td)
            g = [i for i in its if i["kind"] == "global CLAUDE.md"]
            ev2 = evaluate(its, None)
            if not g or not ev2["ceiling_hits"]:
                fails.append("E2E: temp-home over-ceiling not detected")
    except Exception as e:
        fails.append(f"E2E: raised {e}")
    finally:
        HOME, BASELINE_PATH = old_home, old_base
        if old_proj is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = old_proj

    if fails:
        for f in fails:
            print(f"FAIL: {f}")
        return 1
    print("OK: context-budget-measure self-test passed (positive + negative + drift + tolerance + e2e)")
    return 0


def main():
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    if "--report" in sys.argv:
        report_mode()
        return
    if "--accept" in sys.argv:
        accept_mode()
        return
    hook_mode()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # never crash-block a session start
        noop()

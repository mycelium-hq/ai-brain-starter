#!/usr/bin/env python3
"""footprint-sla-check.py - the Footprint SLA gate for the hook fleet (MYC-2358).

The substrate's `hooks.json` is what EVERY install runs (free self-install and
paid commercial install alike - same fleet, per docs/HOOK_FLEET_RESOURCE_GOVERNANCE.md).
Each wired hook is a COLD `python3` start. The felt cost of a hot event is
therefore interpreter-startup x fan-out: a `Write` fans out to several cold
starts, SessionStart to more. Without a budget gate, that fan-out silently
re-grows every time a hook is added, and the install slowly slows the machine -
bug class SLOW-INSTALL-FROM-LAZY-PLUMBING. This gate is the ratchet that holds
"100% value under a bounded footprint" for every future hook.

WHAT IS GATED (hard, deterministic, OS-independent) vs REPORTED (advisory)
-------------------------------------------------------------------------
Hooks for one event run CONCURRENTLY in Claude Code, so felt WALL-CLOCK latency
= MAX(hook), not SUM (this corrected the Stage 0 over-statement; see
docs/adr/0004-footprint-sla-gate.md). A wall-clock-ms gate would also be FLAKY on
a shared CI runner, and a gate that fails on timing noise teaches bypass
(over-strict-verification-teaches-bypass). So the HARD gate keys only on
DETERMINISTIC axes that parse committed source - no timing, no execution:

  HARD (block merge):
    A. per-event substrate cold-start FAN-OUT count vs budget. This is the
       CPU/battery axis (N cold `python3` spawns) AND a reliability axis (one
       slow hook stalls the whole event to its timeout). Per-message events
       exclude `once: true` entries (they fire once per session, not per turn -
       so UPS steady = the recurring cost). PreToolUse / PostToolUse are
       matcher-gated, so fan-out is computed PER TOOL (Write / Edit / Bash / ...).
    B. default-on background daemon count (idle-CPU axis) - a coarse structural
       tripwire: the default install path (bootstrap.sh) must wire 0 launchd/cron
       daemons (daemons are opt-in). Trips if a change makes one default-on.

  ADVISORY (printed by --measure --execute, NEVER blocks CI):
    C. per-hook cold-start TIME (median vs the bare `python3 -c pass` floor) and
       the per-event felt = MAX(hook). Flaky on shared runners -> reported only.
    D. per-message injected BYTES from the UserPromptSubmit context-injectors -
       the recurring-token axis (MYC-2359). Install-specific (a clean CI box has
       no vault) -> reported only.

SessionStart *boundedness* (the corpus-walk freeze class) is a SEPARATE, already
-wired gate (scripts/audit-sessionstart-boundedness.py + test_sessionstart_boundedness.sh).
This gate does NOT duplicate it - it governs fan-out + footprint, that one
governs per-hook work shape.

Budgets live in footprint-budgets.json: budget = the clean-install measured
fan-out + a small headroom, so the gate ships GREEN (an auto-managed gate must
never ship known-red) and bites only on real growth. As Stage 2 (precise
triggers + async) reduces the fan-out, tighten the budgets with --update-budgets.

Command classification - a wired command is one of:
  * substrate-python : `python3 .../skills/ai-brain-starter/(hooks|scripts)/X.py`
                       - the real cold-start the budget governs. Ships in this repo.
  * userlevel-guarded: `[ -f ~/.claude/hooks/X.py ] && python3 ... || true` -
                       maintainer-personal user-level hook; the `[ -f ]` is FALSE
                       on a fresh install -> a shell builtin test, no python
                       cold-start. EXCLUDED from the budgeted count (matches the
                       Stage 0 "fresh-install excludes these" finding).
  * vault-script     : `bash '[VAULT_PATH]/...'` - a vault-side template script,
                       not in this repo; reported, not in the python budget.
  * inline-bash      : pure bash (the auto-update / pinned-echo entries); reported.

Modes:
  --gate [--json]       THE CI GATE. Compare current fan-out + daemon count vs
                        footprint-budgets.json. Exit 0 = within budget; exit 1 =
                        over (the gate BITES); exit 2 = internal error (missing /
                        unparseable hooks.json or budgets - fail LOUD, never a
                        silent green).
  --measure [--execute] Human report of the current fan-out (+ advisory timing /
                        injected-bytes when --execute). No pass/fail.
  --selftest            Positive + negative controls: a synthetic over-budget
                        fleet trips --gate; a within-budget one passes; a missing
                        budgets file fails loud (exit 2); a default-on daemon
                        trips axis B. Exit 1 on any wrong verdict, 2 on internal
                        error. This is the gate's built-in negative control.
  --update-budgets      Maintainer convenience: rewrite footprint-budgets.json to
                        the current measured fan-out + headroom. NOT run in CI.

Stdlib only. Reads are bounded (1 MB cap, binary skip) - cloud-safe-walk
compliant. --gate / --selftest fail LOUD (exit 2) on internal error so a broken
gate can never silently pass CI.

Provenance: MYC-2358 (epic MYC-2348 "100% value, near-zero felt footprint";
Stage 0 footprint report + corrections). Sibling-by-design with
scripts/audit-sessionstart-boundedness.py (MYC-571), whose proven shape this
mirrors.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MAX_READ = 1_000_000  # 1 MB bounded read (cloud-safe-walk: never block on a placeholder)

# Hot events whose per-event fan-out is budgeted directly (not matcher-gated).
NON_MATCHER_EVENTS = ["SessionStart", "UserPromptSubmit", "Stop", "PreCompact", "SessionEnd"]
# Matcher-gated events whose fan-out is budgeted PER TOOL.
MATCHER_EVENTS = ["PreToolUse", "PostToolUse"]
# Representative tools to compute matcher-gated fan-out for. mcp__ is a class.
REPRESENTATIVE_TOOLS = ["Write", "Edit", "MultiEdit", "Bash", "Read", "Glob",
                        "Grep", "Task", "Agent", "Skill", "NotebookEdit",
                        "mcp__server__tool"]

# A wired command that runs a substrate hook/script via python3. Any path under
# `skills/ai-brain-starter/.../<name>.py` is the substrate signature (matched at
# any depth so a future hook in a new subdir can't silently escape the count); it
# matches even the `[VAULT_PATH]/... || ~/.claude/...` fallback form because both
# halves carry that segment.
SUBSTRATE_RE = re.compile(r"skills/ai-brain-starter/(?:[\w.\-]+/)*([\w.\-]+\.(?:py|sh))")
# A maintainer-personal user-level hook, guarded so it no-ops on a fresh install.
USERLEVEL_GUARD_RE = re.compile(r"\[\s*-f\s+[^\]]*~/\.claude/hooks/")
VAULT_PATH_RE = re.compile(r"\[VAULT_PATH\]")

# Daemon-ACTIVATION tokens (a default install must contain none). Deliberately
# only activation signals - `launchctl load/bootstrap`, `crontab -`, or a named
# daemon-installer invocation - NOT plist-CONTENT tokens like `<key>StartInterval`,
# which a bootstrap may legitimately write into a template for an OPT-IN installer
# without making anything default-on (that would be an over-strict false trip).
DAEMON_TOKENS = [
    r"launchctl\s+(?:load|bootstrap)\b",
    r"\bcrontab\s+-",
    r"install-closed-loop-daemon",
    r"install-dev-hub-refresh-daemon",
    r"install-vault-daily-maintenance",
]
DAEMON_RE = re.compile("|".join(DAEMON_TOKENS))


# ---- bounded read -------------------------------------------------------------
def _read_bounded(path: Path) -> str:
    """Read up to MAX_READ bytes; skip binary / oversize / unreadable. Fail-open."""
    try:
        if path.stat().st_size > MAX_READ:
            return ""
        b = path.read_bytes()
        if b"\x00" in b[:4096]:
            return ""
        return b.decode("utf-8", "ignore")
    except Exception:
        return ""


# ---- command classification ---------------------------------------------------
def classify_command(cmd: str) -> tuple[str, str | None]:
    """Return (klass, basename). klass in {substrate-python, userlevel-guarded,
    vault-script, inline-bash}. basename is set only for substrate-python."""
    m = SUBSTRATE_RE.search(cmd)
    if m:
        return "substrate-python", m.group(1)
    if USERLEVEL_GUARD_RE.search(cmd):
        return "userlevel-guarded", None
    if VAULT_PATH_RE.search(cmd):
        return "vault-script", None
    return "inline-bash", None


def resolve_substrate(basename: str, hooks_dir: Path, scripts_dir: Path) -> Path | None:
    """Resolve a substrate basename to its shipped file (hooks/ then scripts/)."""
    for d in (hooks_dir, scripts_dir):
        p = d / basename
        if p.exists():
            return p
    return None


# ---- fleet parsing ------------------------------------------------------------
def load_fleet(hooks_json: Path) -> dict:
    """Parse hooks.json -> {event: [ {matcher, entries:[{command, once}]} ]}.

    Raises on missing / unparseable: the gate must fail LOUD, never treat an
    unreadable fleet as an empty (passing) one."""
    data = json.loads(hooks_json.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    out: dict[str, list] = {}
    for event, blocks in hooks.items():
        rows = []
        for block in (blocks or []):
            entries = []
            for h in (block.get("hooks") or []):
                cmd = (h.get("command") or "").strip()
                if not cmd:
                    continue
                entries.append({"command": cmd, "once": bool(h.get("once"))})
            rows.append({"matcher": block.get("matcher"), "entries": entries})
        out[event] = rows
    return out


def _matcher_matches(matcher: str | None, tool: str) -> bool:
    """A None matcher (non-matcher event) matches nothing here - those events are
    counted directly, not per tool. A present matcher is a Claude Code tool-name
    regex / alternation; a tool fires the block iff it fullmatches."""
    if matcher is None:
        return False
    try:
        return re.fullmatch(matcher, tool) is not None
    except re.error:
        return False


def event_fanout(fleet: dict, event: str) -> dict:
    """Fan-out for a NON-matcher event. Returns counts by class + the budgeted
    metric (substrate-python entries that are NOT once:true = the recurring cost),
    plus the once-only first-message extra and any substrate basenames missing in
    the repo (a wiring-drift integrity note)."""
    counts = {"substrate-python": 0, "userlevel-guarded": 0, "vault-script": 0,
              "inline-bash": 0}
    budgeted = 0          # substrate-python AND not once:true (recurring)
    once_only = 0         # substrate-python AND once:true (first-message extra)
    basenames: list[str] = []
    for block in fleet.get(event, []):
        for e in block["entries"]:
            klass, bn = classify_command(e["command"])
            counts[klass] += 1
            if klass == "substrate-python":
                basenames.append(bn) if bn else None
                if e["once"]:
                    once_only += 1
                else:
                    budgeted += 1
    return {"counts": counts, "budgeted": budgeted, "once_only": once_only,
            "entries": sum(counts.values()), "basenames": basenames}


def tool_fanout(fleet: dict, event: str, tool: str) -> dict:
    """Fan-out for a matcher-gated event, for one tool. Budgeted = substrate-python
    blocks whose matcher fires for this tool (excluding once:true)."""
    budgeted = 0
    basenames: list[str] = []
    classes = {"substrate-python": 0, "userlevel-guarded": 0, "vault-script": 0,
               "inline-bash": 0}
    for block in fleet.get(event, []):
        if not _matcher_matches(block["matcher"], tool):
            continue
        for e in block["entries"]:
            klass, bn = classify_command(e["command"])
            classes[klass] += 1
            if klass == "substrate-python" and not e["once"]:
                budgeted += 1
                if bn:
                    basenames.append(bn)
    return {"budgeted": budgeted, "classes": classes, "basenames": basenames}


def daemon_count(bootstrap: Path) -> int:
    """Coarse structural tripwire: count daemon-activation tokens on the default
    install path. A default install must wire 0 (daemons are opt-in)."""
    src = _read_bounded(bootstrap)
    if not src:
        return 0
    return len(DAEMON_RE.findall(src))


def missing_in_repo(fleet: dict, hooks_dir: Path, scripts_dir: Path) -> list[str]:
    """Substrate basenames wired in hooks.json but absent from hooks/ + scripts/.
    A wiring-drift integrity note (reported), not a footprint failure."""
    missing: set[str] = set()
    for blocks in fleet.values():
        for block in blocks:
            for e in block["entries"]:
                klass, bn = classify_command(e["command"])
                if klass == "substrate-python" and bn and \
                        resolve_substrate(bn, hooks_dir, scripts_dir) is None:
                    missing.add(bn)
    return sorted(missing)


# ---- current footprint snapshot ----------------------------------------------
def snapshot(fleet: dict, bootstrap: Path) -> dict:
    """The deterministic current footprint: budgeted fan-out per event + per tool
    for matcher-gated events, plus the default-on daemon count."""
    per_event = {ev: event_fanout(fleet, ev)["budgeted"] for ev in NON_MATCHER_EVENTS}
    per_tool: dict[str, dict[str, int]] = {}
    for ev in MATCHER_EVENTS:
        per_tool[ev] = {t: tool_fanout(fleet, ev, t)["budgeted"] for t in REPRESENTATIVE_TOOLS}
    return {"per_event": per_event, "per_tool": per_tool,
            "daemons": daemon_count(bootstrap)}


# ---- budgets ------------------------------------------------------------------
def load_budgets(path: Path) -> dict:
    """Load the budgets file. Raises on missing / unparseable (gate fails loud)."""
    return json.loads(path.read_text(encoding="utf-8"))


def build_budgets(snap: dict, headroom: int) -> dict:
    """Budgets = current measured + headroom (per-tool budgets only for tools with
    a nonzero fan-out, plus the mcp class). Records the measured baseline for
    transparency."""
    per_event = {ev: n + headroom for ev, n in snap["per_event"].items()}
    per_tool: dict[str, dict[str, int]] = {}
    for ev, tools in snap["per_tool"].items():
        per_tool[ev] = {t: n + headroom for t, n in tools.items() if n > 0}
    return {
        "_doc": "Footprint SLA budgets for the ai-brain-starter hook fleet. "
                "HARD axes (block merge): per-event/per-tool substrate cold-start "
                "fan-out + default-on daemon count. Advisory axes (timing, "
                "injected bytes) are reported by --measure, never gated. "
                "See docs/adr/0004-footprint-sla-gate.md.",
        "_headroom": headroom,
        "_baseline_measured": {"per_event": snap["per_event"],
                               "per_tool": {ev: {t: n for t, n in tools.items() if n > 0}
                                            for ev, tools in snap["per_tool"].items()},
                               "daemons": snap["daemons"]},
        "fanout_per_event": per_event,
        "fanout_per_tool": per_tool,
        "default_on_daemons": snap["daemons"],
    }


# ---- the gate -----------------------------------------------------------------
def evaluate(snap: dict, budgets: dict) -> list[dict]:
    """Pure comparison: list of breaches. Each breach: {axis, key, measured,
    budget}. Empty list = within budget. A budget missing for a measured surface
    is itself a breach (a new surface must be added to the budgets file
    deliberately - never silently ungoverned)."""
    breaches: list[dict] = []
    bpe = budgets.get("fanout_per_event", {})
    for ev, measured in snap["per_event"].items():
        budget = bpe.get(ev)
        if budget is None:
            # a measured surface with no budget is ungoverned -> breach, so a new
            # surface must be added to the budgets file deliberately. A 0-fan-out
            # event needs no budget (matches the per-tool guard below).
            if measured > 0:
                breaches.append({"axis": "fanout_per_event", "key": ev,
                                 "measured": measured, "budget": None})
        elif measured > budget:
            breaches.append({"axis": "fanout_per_event", "key": ev,
                             "measured": measured, "budget": budget})
    bpt = budgets.get("fanout_per_tool", {})
    for ev, tools in snap["per_tool"].items():
        ev_budgets = bpt.get(ev, {})
        for tool, measured in tools.items():
            budget = ev_budgets.get(tool)
            if budget is None:
                # only govern tools the budgets file lists (those with real
                # fan-out); a tool with 0 measured + no budget is fine.
                if measured > 0:
                    breaches.append({"axis": "fanout_per_tool", "key": f"{ev}:{tool}",
                                     "measured": measured, "budget": None})
            elif measured > budget:
                breaches.append({"axis": "fanout_per_tool", "key": f"{ev}:{tool}",
                                 "measured": measured, "budget": budget})
    dbudget = budgets.get("default_on_daemons")
    if dbudget is not None and snap["daemons"] > dbudget:
        breaches.append({"axis": "default_on_daemons", "key": "bootstrap.sh",
                         "measured": snap["daemons"], "budget": dbudget})
    return breaches


def cmd_gate(hooks_json: Path, hooks_dir: Path, scripts_dir: Path,
             budgets_path: Path, bootstrap: Path, as_json: bool) -> int:
    fleet = load_fleet(hooks_json)          # raises -> fail loud (exit 2)
    budgets = load_budgets(budgets_path)    # raises -> fail loud (exit 2)
    snap = snapshot(fleet, bootstrap)
    breaches = evaluate(snap, budgets)
    drift = missing_in_repo(fleet, hooks_dir, scripts_dir)

    if as_json:
        print(json.dumps({"snapshot": snap, "breaches": breaches,
                          "missing_in_repo": drift}, indent=2))
        return 1 if breaches else 0

    print("=" * 78)
    print("Footprint SLA gate (MYC-2358) - hook fan-out + default-on daemons")
    print("=" * 78)
    print(f"hooks.json: {hooks_json}\nbudgets:    {budgets_path}\n")
    print("Per-event substrate cold-start fan-out (recurring; excludes once:true):")
    bpe = budgets.get("fanout_per_event", {})
    for ev in NON_MATCHER_EVENTS:
        m = snap["per_event"][ev]
        b = bpe.get(ev)
        flag = "  OVER" if (b is not None and m > b) else ("  NO-BUDGET" if b is None else "")
        print(f"    {ev:<18} {m:>3} / {('-' if b is None else b)!s:<3}{flag}")
    print("\nPer-tool fan-out for matcher-gated events (Write/Bash/... cold starts):")
    bpt = budgets.get("fanout_per_tool", {})
    for ev in MATCHER_EVENTS:
        for tool in REPRESENTATIVE_TOOLS:
            m = snap["per_tool"][ev][tool]
            b = bpt.get(ev, {}).get(tool)
            if b is None and m == 0:
                continue
            flag = "  OVER" if (b is not None and m > b) else ("  NO-BUDGET" if b is None else "")
            print(f"    {ev}:{tool:<16} {m:>3} / {('-' if b is None else b)!s:<3}{flag}")
    db = budgets.get("default_on_daemons")
    print(f"\nDefault-on daemons (bootstrap.sh): {snap['daemons']} / "
          f"{'-' if db is None else db}"
          f"{'  OVER' if (db is not None and snap['daemons'] > db) else ''}")
    if drift:
        print(f"\n  note: {len(drift)} substrate hook(s) wired but missing in repo "
              f"(hooks/+scripts/): {', '.join(drift)}")
    if breaches:
        print("\nFOOTPRINT BUDGET EXCEEDED:")
        for br in breaches:
            if br["budget"] is None:
                print(f"  - {br['axis']} '{br['key']}' has NO budget ({br['measured']} "
                      f"measured). Add it to footprint-budgets.json deliberately.")
            else:
                print(f"  - {br['axis']} '{br['key']}': {br['measured']} > budget "
                      f"{br['budget']}. Optimize the fan-out (Stage 2: precise "
                      f"triggers / async / dispatcher) or, if intentional, raise "
                      f"the budget with a one-line rationale.")
        return 1
    print("\nAll footprint axes within budget. OK.")
    return 0


# ---- measure (advisory) -------------------------------------------------------
def _time_script(path: Path, runs: int, env_home: str) -> float | None:
    """Median wall-clock ms of `python3 <path>` with empty stdin, in a sandboxed
    HOME, per-run timeout. Advisory only. None on failure."""
    import os
    samples = []
    env = dict(os.environ)
    env["HOME"] = env_home
    for _ in range(runs):
        t0 = time.perf_counter()
        try:
            subprocess.run([sys.executable, str(path)], input=b"",
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=20, env=env)
        except Exception:
            return None
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    return samples[len(samples) // 2]


def cmd_measure(hooks_json: Path, hooks_dir: Path, scripts_dir: Path,
                bootstrap: Path, execute: bool) -> int:
    fleet = load_fleet(hooks_json)
    snap = snapshot(fleet, bootstrap)
    print("Footprint measurement (advisory - no pass/fail)\n")
    print("Per-event recurring substrate cold-start fan-out:")
    for ev in NON_MATCHER_EVENTS:
        fo = event_fanout(fleet, ev)
        extra = f"  (+{fo['once_only']} once:true first-message)" if fo["once_only"] else ""
        print(f"    {ev:<18} budgeted={fo['budgeted']:>3}  entries={fo['entries']:>3}  "
              f"classes={fo['counts']}{extra}")
    print("\nPer-tool matcher-gated fan-out:")
    for ev in MATCHER_EVENTS:
        for tool in REPRESENTATIVE_TOOLS:
            fo = tool_fanout(fleet, ev, tool)
            if fo["budgeted"] == 0 and sum(fo["classes"].values()) == 0:
                continue
            print(f"    {ev}:{tool:<16} budgeted={fo['budgeted']:>3}  classes={fo['classes']}")
    print(f"\nDefault-on daemons (bootstrap.sh): {snap['daemons']}")

    if not execute:
        print("\n(Advisory timing + injected-bytes skipped. Re-run with --execute to "
              "measure per-hook cold-start ms and per-event felt = MAX. CI does NOT "
              "execute hooks - the gate is the static --gate path.)")
        return 0

    # --- advisory C: per-hook timing + per-event felt = MAX ---
    floor = None
    with tempfile.TemporaryDirectory() as home:
        floor_samples = []
        for _ in range(5):
            t0 = time.perf_counter()
            try:
                subprocess.run([sys.executable, "-c", "pass"], timeout=20,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                break
            floor_samples.append((time.perf_counter() - t0) * 1000.0)
        if floor_samples:
            floor_samples.sort()
            floor = floor_samples[len(floor_samples) // 2]
        print(f"\nAdvisory timing (sandboxed HOME; flaky - NOT gated). "
              f"python3 -c pass floor = {floor:.1f} ms" if floor else
              "\nAdvisory timing unavailable (floor measurement failed).")
        if floor is not None:
            for ev in NON_MATCHER_EVENTS + MATCHER_EVENTS:
                times = []
                seen: set[str] = set()
                for block in fleet.get(ev, []):
                    for e in block["entries"]:
                        klass, bn = classify_command(e["command"])
                        if klass != "substrate-python" or not bn or bn in seen:
                            continue
                        seen.add(bn)
                        p = resolve_substrate(bn, hooks_dir, scripts_dir)
                        if p is None:
                            continue
                        ms = _time_script(p, 3, home)
                        if ms is not None:
                            times.append((bn, ms))
                if times:
                    felt_max = max(t for _, t in times)
                    print(f"    {ev:<18} felt=MAX {felt_max:6.1f} ms over "
                          f"{len(times)} hook(s); slowest "
                          f"{max(times, key=lambda x: x[1])[0]}")
    print("\n(Per-message injected-byte measurement (axis D, MYC-2359) needs a "
          "populated vault; on a clean box it is ~0. Run on a real install to "
          "size the recurring-token cost.)")
    return 0


# ---- update-budgets (maintainer) ---------------------------------------------
def cmd_update_budgets(hooks_json: Path, bootstrap: Path, budgets_path: Path,
                       headroom: int) -> int:
    fleet = load_fleet(hooks_json)
    snap = snapshot(fleet, bootstrap)
    budgets = build_budgets(snap, headroom)
    budgets_path.write_text(json.dumps(budgets, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {budgets_path} (headroom={headroom}).")
    print(f"  per-event budgets: {budgets['fanout_per_event']}")
    print(f"  per-tool budgets:  {budgets['fanout_per_tool']}")
    print(f"  default_on_daemons: {budgets['default_on_daemons']}")
    return 0


# ---- selftest (positive + negative controls) ----------------------------------
_EVIL_HOOK = "python3 ~/.claude/skills/ai-brain-starter/hooks/evil-{i}.py 2>/dev/null || echo '{{}}'"


def _write_synthetic(d: Path, write_hooks: int, daemons: int) -> tuple[Path, Path]:
    """A synthetic hooks.json wiring `write_hooks` substrate-python hooks on Write,
    and a bootstrap.sh with `daemons` launchctl activations."""
    hj = d / "hooks.json"
    entries = [{"type": "command", "command": _EVIL_HOOK.format(i=i)}
               for i in range(write_hooks)]
    hj.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": entries}]}}), encoding="utf-8")
    bs = d / "bootstrap.sh"
    bs.write_text("#!/usr/bin/env bash\n" +
                  "".join(f"launchctl load ~/Library/LaunchAgents/d{i}.plist\n"
                          for i in range(daemons)), encoding="utf-8")
    return hj, bs


def cmd_selftest() -> int:
    fails: list[str] = []

    # 0. classification unit checks - each known command form maps to its class.
    cases = [
        ("python3 ~/.claude/skills/ai-brain-starter/hooks/x.py 2>/dev/null || echo '{}'",
         "substrate-python", "x.py"),
        ("python3 ~/.claude/skills/ai-brain-starter/scripts/y.py 2>/dev/null || echo '{}'",
         "substrate-python", "y.py"),
        ("python3 '[VAULT_PATH]/.claude/skills/ai-brain-starter/hooks/z.py' || "
         "python3 ~/.claude/skills/ai-brain-starter/hooks/z.py || echo '{}'",
         "substrate-python", "z.py"),               # fallback form -> still substrate
        ("[ -f ~/.claude/hooks/retry-budget.py ] && python3 ~/.claude/hooks/retry-budget.py || true",
         "userlevel-guarded", None),
        ("bash '[VAULT_PATH]/⚙️ Meta/scripts/write-hook.sh'", "vault-script", None),
        ("if [ -f ~/.claude/.pinned ]; then echo '{}'; fi", "inline-bash", None),
    ]
    for cmd, want_k, want_bn in cases:
        k, bn = classify_command(cmd)
        if k != want_k or bn != want_bn:
            fails.append(f"classify {cmd[:40]!r}: got ({k},{bn}) want ({want_k},{want_bn})")

    # matcher matching
    if not _matcher_matches("Write|Edit|MultiEdit", "Write"):
        fails.append("matcher alternation should match Write")
    if not _matcher_matches("mcp__.*", "mcp__server__tool"):
        fails.append("matcher mcp__.* should match an mcp tool")
    if _matcher_matches("Bash", "Write"):
        fails.append("matcher Bash should NOT match Write")
    if _matcher_matches(None, "Write"):
        fails.append("None matcher should match no tool")

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        hooks_dir = d / "hooks"
        hooks_dir.mkdir()
        scripts_dir = d / "scripts"
        scripts_dir.mkdir()

        # 1. NEGATIVE CONTROL: a 30-hook Write fan-out vs a budget of 7 -> --gate BITES.
        hj, bs = _write_synthetic(d, write_hooks=30, daemons=0)
        budgets = {"fanout_per_event": {ev: 50 for ev in NON_MATCHER_EVENTS},
                   "fanout_per_tool": {"PreToolUse": {"Write": 7, "Edit": 7},
                                       "PostToolUse": {}},
                   "default_on_daemons": 0}
        bp = d / "footprint-budgets.json"
        bp.write_text(json.dumps(budgets), encoding="utf-8")
        rc = cmd_gate(hj, hooks_dir, scripts_dir, bp, bs, as_json=True)
        if rc != 1:
            fails.append(f"NEG: 30-hook Write fan-out vs budget 7 should exit 1, got {rc}")

        # 2. POSITIVE CONTROL: a 3-hook Write fan-out vs budget 7 -> --gate passes.
        hj2, bs2 = _write_synthetic(d, write_hooks=3, daemons=0)
        rc = cmd_gate(hj2, hooks_dir, scripts_dir, bp, bs2, as_json=True)
        if rc != 0:
            fails.append(f"POS: 3-hook Write fan-out vs budget 7 should exit 0, got {rc}")

        # 3. DAEMON NEGATIVE CONTROL: a default-on daemon vs budget 0 -> BITES.
        hj3, bs3 = _write_synthetic(d, write_hooks=3, daemons=2)
        rc = cmd_gate(hj3, hooks_dir, scripts_dir, bp, bs3, as_json=True)
        if rc != 1:
            fails.append(f"DAEMON-NEG: 2 default-on daemons vs budget 0 should exit 1, got {rc}")

        # 4. FAIL-LOUD: a missing budgets file -> cmd_gate raises -> caller exits 2.
        try:
            cmd_gate(hj2, hooks_dir, scripts_dir, d / "nope.json", bs2, as_json=True)
            fails.append("FAIL-LOUD: missing budgets file did not raise")
        except Exception:
            pass

        # 5. FAIL-LOUD: a missing hooks.json -> raises (fail loud, not empty-pass).
        try:
            cmd_gate(d / "nope-hooks.json", hooks_dir, scripts_dir, bp, bs2, as_json=True)
            fails.append("FAIL-LOUD: missing hooks.json did not raise")
        except Exception:
            pass

        # 6. NO-BUDGET BREACH: a measured tool with no budget entry is a breach
        #    (a new surface must be governed deliberately, never silently ungoverned).
        budgets_nobudget = {"fanout_per_event": {ev: 50 for ev in NON_MATCHER_EVENTS},
                            "fanout_per_tool": {"PreToolUse": {}, "PostToolUse": {}},
                            "default_on_daemons": 0}
        bp2 = d / "budgets-nobudget.json"
        bp2.write_text(json.dumps(budgets_nobudget), encoding="utf-8")
        rc = cmd_gate(hj2, hooks_dir, scripts_dir, bp2, bs2, as_json=True)
        if rc != 1:
            fails.append(f"NO-BUDGET: ungoverned Write fan-out should exit 1, got {rc}")

    if fails:
        print("SELFTEST FAIL:")
        for f in fails:
            print("  - " + f)
        return 1
    print("SELFTEST PASS: gate bites over-budget fan-out + default-on daemons + "
          "ungoverned surfaces, passes within-budget, fails loud on missing "
          "hooks.json/budgets; classification + matcher logic correct.")
    return 0


# ---- main ---------------------------------------------------------------------
def main() -> int:
    here = Path(__file__).resolve().parent
    repo = here.parent
    ap = argparse.ArgumentParser(description="Footprint SLA gate for the hook fleet (MYC-2358).")
    ap.add_argument("--gate", action="store_true", help="CI gate: fan-out + daemons vs budgets")
    ap.add_argument("--measure", action="store_true", help="advisory report (no pass/fail)")
    ap.add_argument("--execute", action="store_true", help="(with --measure) time hooks + felt=MAX")
    ap.add_argument("--selftest", action="store_true", help="positive + negative controls")
    ap.add_argument("--update-budgets", action="store_true", help="(maintainer) rewrite budgets")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--headroom", type=int, default=2, help="budget = measured + headroom")
    ap.add_argument("--hooks-json", default=str(repo / "hooks.json"))
    ap.add_argument("--hooks-dir", default=str(repo / "hooks"))
    ap.add_argument("--scripts-dir", default=str(repo / "scripts"))
    ap.add_argument("--bootstrap", default=str(repo / "bootstrap.sh"))
    ap.add_argument("--budgets", default=str(repo / "footprint-budgets.json"))
    a = ap.parse_args()

    # --gate / --selftest / --update-budgets are gates: fail LOUD (exit 2) on any
    # internal error so a broken gate can never silently pass CI.
    try:
        if a.selftest:
            return cmd_selftest()
        if a.update_budgets:
            return cmd_update_budgets(Path(a.hooks_json), Path(a.bootstrap),
                                      Path(a.budgets), a.headroom)
        if a.measure:
            return cmd_measure(Path(a.hooks_json), Path(a.hooks_dir),
                               Path(a.scripts_dir), Path(a.bootstrap), a.execute)
        if a.gate:
            return cmd_gate(Path(a.hooks_json), Path(a.hooks_dir), Path(a.scripts_dir),
                            Path(a.budgets), Path(a.bootstrap), a.json)
    except Exception as e:
        print(f"[footprint-sla] FATAL: {e}", file=sys.stderr)
        return 2
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

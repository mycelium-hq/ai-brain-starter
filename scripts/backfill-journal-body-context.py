#!/usr/bin/env python3
"""backfill-journal-body-context.py

Walks every daily journal entry in a date range and appends a "Body track"
section BELOW the original verbatim content. Pulls health-mcp data for each
date and renders a Floor-paired interpretation.

Idempotent: skips entries that already have the section (unless --force).
The original journal text is NEVER modified.

Usage:
  python3 backfill-journal-body-context.py --year 2026 --vault-root /path/to/vault
  python3 backfill-journal-body-context.py --start 2026-01-01 --end 2026-05-10 --vault-root /path/to/vault
  python3 backfill-journal-body-context.py --dry-run --year 2026
  python3 backfill-journal-body-context.py --start 2026-05-09 --end 2026-05-09  # daily-cron mode

Model routing (--llm-model):
  python   - Python template only (fastest, zero cost, deterministic)
  minimax  - Python template + MiniMax for the interpretation line (cheap)
  haiku    - Python template + Haiku via Claude Code
  sonnet   - Python template + Sonnet (highest quality, costly per entry)

Default: python (works without any LLM dependency). Use --llm-model minimax
for richer prose. The structural facts in the section come from health-mcp
regardless of model.

Discovers the health-mcp install at ~/.claude/health-mcp/ and imports its
modules in-process - no MCP stdio round-trips.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def _find_health_mcp() -> Path | None:
    candidates = [
        Path.home() / ".claude" / "health-mcp",
        Path.home() / "dev" / "ai-brain-starter" / "services" / "health-mcp",
    ]
    for p in candidates:
        if p.is_dir() and (p / "main.py").exists():
            return p
    return None


def _load_health_modules(health_mcp_dir: Path) -> dict[str, Any]:
    sys.path.insert(0, str(health_mcp_dir))
    venv_site = health_mcp_dir / ".venv" / "lib"
    if venv_site.is_dir():
        for py_dir in venv_site.glob("python*/site-packages"):
            sys.path.insert(0, str(py_dir))
    import db
    import scores
    import vault_aware
    import cycle
    import voice_bridge
    return {"db": db, "scores": scores, "vault_aware": vault_aware, "cycle": cycle, "voice_bridge": voice_bridge}


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_FLOOR_LEVEL_RE = re.compile(r"^floor_level:\s*(-?\d+)", re.MULTILINE)
_FLOOR_NAME_RE = re.compile(r"^floor:\s*\"?([^\"\n]+?)\"?\s*$", re.MULTILINE)
_DATE_RE = re.compile(r"^creationDate:\s*(\S+)", re.MULTILINE)
_LANG_RE = re.compile(r"^language:\s*(\S+)", re.MULTILINE)
_BACKFILL_MARKER = "## Body track (health-mcp, backfilled"


def _parse_entry_meta(p: Path) -> dict[str, Any]:
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    m = _FRONTMATTER_RE.match(text)
    fm = m.group(1) if m else ""
    out: dict[str, Any] = {"_path": p, "_full_text": text}
    fl = _FLOOR_LEVEL_RE.search(fm)
    if fl:
        try:
            out["floor_level"] = int(fl.group(1))
        except ValueError:
            pass
    fn = _FLOOR_NAME_RE.search(fm)
    if fn:
        out["floor"] = fn.group(1).strip()
    cd = _DATE_RE.search(fm)
    if cd:
        try:
            out["date"] = datetime.fromisoformat(cd.group(1).rstrip("Z").replace("Z", "")).date()
        except ValueError:
            try:
                out["date"] = datetime.strptime(cd.group(1)[:10], "%Y-%m-%d").date()
            except ValueError:
                pass
    if "date" not in out:
        fn_match = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
        if fn_match:
            try:
                out["date"] = datetime.strptime(fn_match.group(1), "%Y-%m-%d").date()
            except ValueError:
                pass
    lang_match = _LANG_RE.search(fm)
    out["language"] = lang_match.group(1) if lang_match else "en"
    return out


def _find_journals(vault_root: Path, start: date, end: date) -> list[Path]:
    candidates: list[Path] = []
    for sub in ("Journals", "\U0001f4d3 Journals"):
        d = vault_root / sub
        if not d.is_dir():
            continue
        for p in d.rglob("*.md"):
            if _BACKFILL_MARKER in p.name:
                continue
            meta = _parse_entry_meta(p)
            ed = meta.get("date")
            if ed and start <= ed <= end:
                candidates.append(p)
    return sorted(set(candidates))


def _interpret_template(body: dict[str, Any], cycle_ctx: dict[str, Any] | None,
                        floor: str | None, recovery: dict[str, Any] | None,
                        lab_flags: list[dict[str, Any]],
                        language: str = "en") -> str:
    hrv = body.get("hrv_ms")
    rhr = body.get("rhr_bpm")
    asleep = body.get("sleep_asleep_min", 0)
    rem = body.get("sleep_rem_min", 0)
    deep = body.get("sleep_deep_min", 0)
    hrv_base = body.get("hrv_baseline_30d_ms")
    delta_pct = ((hrv - hrv_base) / hrv_base * 100) if (hrv and hrv_base) else None
    score = recovery.get("score") if recovery else None
    phase = cycle_ctx.get("phase") if cycle_ctx else None
    is_es = (language or "en").lower().startswith("es")

    parts: list[str] = []
    if lab_flags:
        markers = ", ".join(f"{l['marker']} {l.get('status', 'flag')}" for l in lab_flags[:3])
        if is_es:
            parts.append(f"Marcadores fuera de rango en los ultimos 180 dias: {markers}. Vale considerar si el patron emocional de este dia tiene un piso metabolico debajo.")
        else:
            parts.append(f"Out-of-range labs from the prior 180 days: {markers}. Worth considering whether the emotional pattern of this day has a metabolic floor under it.")

    if phase == "luteal" and delta_pct is not None and delta_pct < -10:
        if is_es:
            parts.append(f"HRV {round(delta_pct)}% bajo la linea base, pero estabas en fase lutea. Es fisiologia, no deficit de recuperacion.")
        else:
            parts.append(f"HRV ran {round(delta_pct)}% below baseline, but you were in luteal phase. That's physiology, not a recovery deficit.")
    elif phase == "menstrual" and asleep > 0 and asleep < 420:
        if is_es:
            parts.append(f"Dia menstrual con poco sueno ({asleep // 60}h {asleep % 60}min). El cuerpo pidio descanso que no obtuvo.")
        else:
            parts.append(f"Menstrual day with short sleep ({asleep // 60}h {asleep % 60}min). The body asked for rest it didn't get.")

    if floor and asleep > 0:
        if delta_pct is not None and delta_pct < -15 and asleep < 360:
            if is_es:
                parts.append(f"Piso {floor} con HRV {round(delta_pct)}% abajo Y sueno corto. Cuerpo y mente registraron la presion simultaneamente. Sin el journal el score de recuperacion habria dicho 'descansa mas'; con el journal el detalle es: el descanso solo no resuelve esto.")
            else:
                parts.append(f"Floor {floor} with HRV {round(delta_pct)}% below baseline AND short sleep. Body and mind registered the pressure at the same time. Without the journal the recovery score would have said 'rest more'; with the journal the read is: rest alone won't fix this.")
        elif score is not None and score >= 70 and floor:
            if is_es:
                parts.append(f"Piso {floor} con score de recuperacion {score}/100. Dia solido en ambas pistas.")
            else:
                parts.append(f"Floor {floor} with recovery {score}/100. Solid on both tracks.")
        elif score is not None and score < 50 and floor in {"Fear", "Anger", "Shame", "Apathy", "Grief", "Miedo", "Rabia", "Verguenza", "Apatia", "Duelo"}:
            if is_es:
                parts.append(f"Piso {floor} y score {score}. Piso emocional bajo, recuperacion fisica baja. Dia para no agendar nada nuevo si se puede.")
            else:
                parts.append(f"Floor {floor} and recovery {score}. Low on both tracks. Don't schedule anything new today if you can avoid it.")
        elif rem + deep < 60 and asleep > 360:
            if is_es:
                parts.append(f"Tiempo dormido decente pero solo {rem + deep}min de sueno restaurador (REM + profundo). El cuerpo durmio pero no descanso.")
            else:
                parts.append(f"Decent total sleep but only {rem + deep}min of restorative sleep (REM + deep). Body slept but did not rest.")

    if not parts:
        if is_es:
            parts.append("Datos corporales dentro del rango habitual para este dia.")
        else:
            parts.append("Body data within your usual range for this day.")
    return " ".join(parts)


def _render_body_track(date_iso: str, body: dict[str, Any], cycle_ctx: dict[str, Any] | None,
                       recovery: dict[str, Any] | None, sleep_score: dict[str, Any] | None,
                       lab_flags: list[dict[str, Any]], floor: str | None,
                       floor_level: int | None, interpretation: str,
                       language: str = "en", today_iso: str | None = None) -> str:
    is_es = (language or "en").lower().startswith("es")
    today_iso = today_iso or date.today().isoformat()
    floor_disp = floor or (f"level_{floor_level}" if floor_level is not None else ("desconocido" if is_es else "unknown"))
    cycle_line = ""
    if cycle_ctx and cycle_ctx.get("phase") and cycle_ctx.get("phase") not in {"unknown"}:
        if is_es:
            cycle_line = f"**Fase del ciclo:** {cycle_ctx['phase']}, dia {cycle_ctx.get('cycle_day', '?')} ({cycle_ctx.get('irregularity', 'regular')})\n\n"
        else:
            cycle_line = f"**Cycle phase:** {cycle_ctx['phase']}, day {cycle_ctx.get('cycle_day', '?')} ({cycle_ctx.get('irregularity', 'regular')})\n\n"

    def _fmt(v: Any, suffix: str = "") -> str:
        return f"{v}{suffix}" if v is not None else "-"

    hrv = body.get("hrv_ms")
    rhr = body.get("rhr_bpm")
    asleep = body.get("sleep_asleep_min", 0)
    eff = body.get("sleep_efficiency", 0)
    rem = body.get("sleep_rem_min", 0)
    deep = body.get("sleep_deep_min", 0)
    steps = body.get("steps_total", 0)
    workouts = body.get("workout_count", 0)
    workout_min = body.get("workout_min", 0)
    mindful = body.get("mindful_min", 0)
    hrv_base = body.get("hrv_baseline_30d_ms")
    delta = ((hrv - hrv_base) / hrv_base * 100) if (hrv and hrv_base) else None

    score_line = ""
    if recovery and recovery.get("score") is not None:
        score_line += ("- " + ("Recuperacion" if is_es else "Recovery") + f": {recovery['score']}/100 ({recovery.get('confidence', '?')} confidence)\n")
    if sleep_score and sleep_score.get("score") is not None:
        score_line += ("- " + ("Sueno" if is_es else "Sleep") + f": {sleep_score['score']}/100\n")

    lab_block = ""
    if lab_flags:
        lab_lines = "\n".join(f"  - {l['marker']}: {l.get('value', '?')} {l.get('unit', '')} ({l.get('status', '?')})" for l in lab_flags[:5])
        lab_block = ("\n**" + ("Marcadores de laboratorio fuera de rango" if is_es else "Out-of-range labs") + "** (last 180d):\n" + lab_lines + "\n")

    if is_es:
        header = f"\n\n---\n\n{_BACKFILL_MARKER} {today_iso})\n\n*Contexto auto-generado. La entrada original se preserva verbatim arriba.*\n\n"
        floor_line = f"**Piso ese dia:** {floor_disp}" + (f" (nivel {floor_level})" if floor_level is not None else "") + "\n\n"
        body_header = "**El cuerpo ese dia:**\n"
        body_lines = (
            f"- HRV: {_fmt(round(hrv, 1) if hrv else None, ' ms')}"
            + (f" ({round(delta)}% vs linea base 30d)" if delta is not None else "")
            + "\n"
            + f"- RHR: {_fmt(round(rhr) if rhr else None, ' bpm')}\n"
            + f"- Sueno: {asleep} min (eficiencia {round(eff * 100)}%, REM {rem}min, profundo {deep}min)\n"
            + f"- Pasos: {steps}\n"
            + f"- Entrenamientos: {workouts} ({workout_min}min)\n"
            + f"- Mindful: {mindful}min\n"
        )
        scores_header = "**Scores:**\n" if score_line else ""
        interp_header = f"\n**Interpretacion pareada con el piso:** {interpretation}\n"
    else:
        header = f"\n\n---\n\n{_BACKFILL_MARKER} {today_iso})\n\n*Auto-generated context. Original journal entry above is preserved verbatim.*\n\n"
        floor_line = f"**Floor that day:** {floor_disp}" + (f" (level {floor_level})" if floor_level is not None else "") + "\n\n"
        body_header = "**The body that day:**\n"
        body_lines = (
            f"- HRV: {_fmt(round(hrv, 1) if hrv else None, ' ms')}"
            + (f" ({round(delta)}% vs 30-day baseline)" if delta is not None else "")
            + "\n"
            + f"- RHR: {_fmt(round(rhr) if rhr else None, ' bpm')}\n"
            + f"- Sleep: {asleep} min ({round(eff * 100)}% efficiency, REM {rem}min, deep {deep}min)\n"
            + f"- Steps: {steps}\n"
            + f"- Workouts: {workouts} ({workout_min}min)\n"
            + f"- Mindful: {mindful}min\n"
        )
        scores_header = "**Scores:**\n" if score_line else ""
        interp_header = f"\n**Floor-paired interpretation:** {interpretation}\n"

    return (
        header + floor_line + cycle_line + body_header + body_lines
        + ("\n" + scores_header + score_line if score_line else "")
        + lab_block + interp_header
    )


def _collect_body(mods: dict[str, Any], target: date) -> dict[str, Any]:
    db = mods["db"]
    scores = mods["scores"]
    vault_aware = mods["vault_aware"]
    cycle = mods["cycle"]
    with db.connect(read_only=True) as con:
        body = vault_aware.journal_context(con, target)
        baseline_row = con.execute(
            "SELECT AVG(daily) FROM (SELECT DATE_TRUNC('day', start_date) AS d, AVG(value) AS daily "
            "FROM records WHERE type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN' "
            "AND start_date >= ? AND start_date < ? GROUP BY d)",
            [datetime.combine(target - timedelta(days=30), datetime.min.time()), datetime.combine(target, datetime.min.time())],
        ).fetchone()
        body["hrv_baseline_30d_ms"] = round(float(baseline_row[0]), 1) if baseline_row and baseline_row[0] is not None else None

        cycle_ctx = cycle.cycle_context(con, target)
        if cycle_ctx.get("phase") == "unknown":
            cycle_ctx = None

        recovery = scores.recovery_score(con, target)
        sleep_score = scores.sleep_score(con, target)

        rows = con.execute(
            "SELECT marker, test_date, value, unit, range_low, range_high, status FROM labs "
            "WHERE test_date >= ? AND test_date <= ? AND status IN ('low', 'high') ORDER BY test_date DESC",
            [target - timedelta(days=180), target],
        ).fetchall()
        seen: set[str] = set()
        lab_flags: list[dict[str, Any]] = []
        for r in rows:
            if r[0] in seen:
                continue
            seen.add(r[0])
            lab_flags.append({"marker": r[0], "test_date": str(r[1]), "value": float(r[2]) if r[2] is not None else None, "unit": r[3], "status": r[6]})
    return {"body": body, "cycle_ctx": cycle_ctx, "recovery": recovery, "sleep_score": sleep_score, "lab_flags": lab_flags}


def _resolve_minimax_helper() -> Path | None:
    """Look up the user's minimax helper via $MINIMAX_HELPER, or fall back to
    a conventional location inside $VAULT_ROOT. Generic - never hardcoded to
    any single user's vault path."""
    env = os.environ.get("MINIMAX_HELPER")
    if env and Path(env).is_file():
        return Path(env)
    vroot = os.environ.get("VAULT_ROOT")
    if vroot:
        candidate = Path(vroot) / "scripts" / "minimax.sh"
        if candidate.is_file():
            return candidate
        meta_candidate = Path(vroot) / "Meta" / "scripts" / "minimax.sh"
        if meta_candidate.is_file():
            return meta_candidate
    return None


def _try_minimax_interpret(prompt: str) -> str | None:
    """Try to call the MiniMax helper if the user has one set up. Returns the
    interpretation string on success, None on failure.

    Token budget = 1500: MiniMax M2.7 emits reasoning_content first; with
    only 200 tokens the model burns the entire budget on reasoning and the
    `content` field comes back empty. 1500 gives enough headroom for both
    reasoning + a 1-3 sentence interpretation. Verified 2026-05-11 on
    M2.7 (reasoning_tokens averaged ~80 per 1-3 sentence prompt).
    """
    script = _resolve_minimax_helper()
    if not script:
        return None
    try:
        proc = subprocess.run(["bash", str(script), prompt, "1500"], capture_output=True, text=True, timeout=30, check=False)
        out = proc.stdout.strip()
        if proc.returncode == 0 and out:
            return out[:600]
    except subprocess.SubprocessError:
        return None
    return None


_BODY_TRACK_SECTION_RE = re.compile(
    r"\n*---\n+## Body track \(health-mcp, backfilled \d{4}-\d{2}-\d{2}\).*?\Z",
    re.DOTALL,
)


def _strip_existing_body_track(text: str) -> str:
    """Remove a previously-appended body-track section from a journal file.

    The section format is: leading blank line(s), '---', '## Body track ...'
    through end-of-file. Used by --force to avoid duplicating the section
    when re-running. Idempotent; returns text unchanged if no section.
    """
    return _BODY_TRACK_SECTION_RE.sub("", text).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill journal entries with body-track context from health-mcp.")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--start", type=str, default=None)
    ap.add_argument("--end", type=str, default=None)
    ap.add_argument("--vault-root", type=str, default=None)
    ap.add_argument("--llm-model", choices=["python", "minimax", "haiku", "sonnet"], default="python")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    today = date.today()
    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    elif args.year:
        start = date(args.year, 1, 1)
        end = date(args.year, 12, 31) if args.year < today.year else today
    else:
        start = date(today.year, 1, 1)
        end = today

    vault_root_str = args.vault_root or os.environ.get("VAULT_ROOT")
    if not vault_root_str:
        print("ERROR: vault root not set. Pass --vault-root or export VAULT_ROOT.", file=sys.stderr)
        return 2
    vault_root = Path(vault_root_str).expanduser().resolve()
    if not vault_root.is_dir():
        print(f"ERROR: vault_root {vault_root} not found", file=sys.stderr)
        return 2

    health_mcp_dir = _find_health_mcp()
    if not health_mcp_dir:
        print("ERROR: health-mcp install not found at ~/.claude/health-mcp/ or ~/dev/ai-brain-starter/services/health-mcp/. Run /health-setup first.", file=sys.stderr)
        return 2

    mods = _load_health_modules(health_mcp_dir)

    journals = _find_journals(vault_root, start, end)
    print(f"Found {len(journals)} journal entries in {start} .. {end}.")
    if not journals:
        print("Nothing to backfill.")
        return 0

    backfilled = 0
    skipped = 0
    errored = 0
    today_iso = date.today().isoformat()
    for p in journals:
        text = p.read_text(encoding="utf-8")
        if _BACKFILL_MARKER in text and not args.force:
            skipped += 1
            continue
        meta = _parse_entry_meta(p)
        d = meta.get("date")
        if not d:
            errored += 1
            continue
        floor = meta.get("floor")
        floor_level = meta.get("floor_level")
        language = meta.get("language", "en")
        try:
            data = _collect_body(mods, d)
        except Exception as e:
            print(f"  ERROR on {p.name}: {e}", file=sys.stderr)
            errored += 1
            continue

        interpretation = _interpret_template(
            data["body"], data["cycle_ctx"], floor, data["recovery"],
            data["lab_flags"], language=language,
        )

        if args.llm_model == "minimax":
            prompt = (
                f"Render ONE warm, helpful, 1-3 sentence interpretation in {'Spanish' if language.startswith('es') else 'English'} "
                f"of a journal day's body data paired with the Floor tag. Floor: {floor or 'unspecified'} "
                f"(level {floor_level}). HRV: {data['body'].get('hrv_ms')} ms (baseline {data['body'].get('hrv_baseline_30d_ms')}). "
                f"Sleep: {data['body'].get('sleep_asleep_min')} min, efficiency {data['body'].get('sleep_efficiency')}. "
                f"Recovery score: {data['recovery'].get('score')}. "
                f"Cycle phase: {data['cycle_ctx'].get('phase') if data['cycle_ctx'] else 'n/a'}. "
                f"Out-of-range labs: {[(l['marker'], l['status']) for l in data['lab_flags'][:3]]}. "
                "Shape: pattern named, hypothesis, specific next-action if applicable. No fluff."
            )
            mini = _try_minimax_interpret(prompt)
            if mini:
                interpretation = mini

        section = _render_body_track(
            d.isoformat(), data["body"], data["cycle_ctx"], data["recovery"],
            data["sleep_score"], data["lab_flags"], floor, floor_level,
            interpretation, language=language, today_iso=today_iso,
        )

        if args.dry_run:
            print(f"  WOULD APPEND to {p.name}:")
            print("    " + section[:200].replace("\n", "\n    "))
        else:
            # When --force, strip any prior body-track section so we replace
            # in-place instead of appending duplicates.
            base_text = _strip_existing_body_track(text) if args.force else text
            new_text = base_text.rstrip() + section
            p.write_text(new_text, encoding="utf-8")
        backfilled += 1
        if backfilled % 25 == 0:
            print(f"  Backfilled {backfilled} entries so far...")

    print()
    print(f"Done. Processed {len(journals)}; backfilled {backfilled}; skipped (already had section) {skipped}; errored {errored}.")
    print(f"Range covered: {start} .. {end}.")
    if args.dry_run:
        print("Dry run - no files were modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

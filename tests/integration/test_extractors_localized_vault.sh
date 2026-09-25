#!/usr/bin/env bash
# Test: metadata extraction + the insight engine on a SPANISH vault, end to end.
#
# Bug class: three silent zeros, all found on one Spanish vault where every
# extractor ran green and every floor-based finding was empty:
#
#   1. person.py scanned a hardcoded "📓 Journals" folder. A Spanish install
#      has "📓 Diarios" (that is what Phase 1 tells the installer to create), so
#      the scan found nothing: every person got mention_count 0 and an empty
#      floor co-occurrence, and the insight engine's lucky-charm / drag-people
#      sections — which are built on those — never fired.
#   2. The journal writes the floor as a NAME (`floor: Entusiasmo`, `floor:
#      Hope`); person.py and the insight engine only read `floor_num`, and the
#      journal extractor's own name→number map was the pre-expansion 17-level
#      English list. Spanish names scored nothing; 16 of the 34 English floors
#      scored nothing; the rest scored on the wrong scale.
#   3. Spanish type names (`reunion`, `nota`, `estrategia`, …) and a few this
#      repo's own skills write (`rise`, `profile`) had no extractor, so those
#      notes dropped out of the index with no message.
#
# Fix under test: _floors.py (one canonical en+es map, name beats stored
# number), person.py journal-folder detection, TYPE_ALIASES for es + repo-own
# types (an explicit <type>.py still wins over an alias), and the engine
# deriving floor_num from the name.
#
# Self-contained: tmpdir fake vault + a private copy of scripts/ (so a custom
# extractor can be added without touching the repo). Every path the scripts
# touch is pinned by VAULT_ROOT / INSIGHTS_OUTPUT; nothing here reads or writes
# the home directory, so HOME is deliberately NOT redirected — the extractors
# import PyYAML, and a redirected HOME would hide a user-site install of it.
# Exit 0 = pass, 1 = fail. If no python3 on this machine can import yaml the
# suite says so and exits 0 (the CI job installs PyYAML for exactly this test).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
for f in scripts/vault-metadata-extract.py scripts/vault-insight-engine.py \
         scripts/extractors/_dispatcher.py scripts/extractors/_floors.py; do
  if [ ! -f "$REPO_ROOT/$f" ]; then
    echo "ERROR: $REPO_ROOT/$f not found" >&2
    exit 1
  fi
done

# The extractors and the engine `import yaml`. Prefer the python3 on PATH; fall
# back to any other interpreter that has it (a pipx venv from /graphify counts).
PY=""
for cand in python3 python3.13 python3.12 python3.11 python3.10 python3.9 "$HOME"/.local/pipx/venvs/*/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import yaml" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "SKIP: no python3 with PyYAML found on this machine (pip install pyyaml); the extractor end-to-end assertions did not run."
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Private copy of the scripts tree: lets us add a custom extractor (plan.py)
# and proves the tree works when it is a plain copy, not the repo checkout.
STARTER="$TMP/starter"
mkdir -p "$STARTER/scripts"
cp -R "$REPO_ROOT/scripts/extractors" "$STARTER/scripts/extractors"
rm -rf "$STARTER/scripts/extractors/__pycache__"
cp "$REPO_ROOT/scripts/vault-metadata-extract.py" "$REPO_ROOT/scripts/vault-insight-engine.py" "$STARTER/scripts/"
cat > "$STARTER/scripts/extractors/plan.py" <<'PY'
# A user's own extractor for `type: plan`. It must keep winning over the
# built-in `plan -> strategy` alias.
from _base import count_words, ExtractionResult
AUTO_FIELDS = ("plan_marker", "word_count")
def extract(filepath, body, fm, context):
    return ExtractionResult({"plan_marker": "custom-extractor", "word_count": count_words(body)}, AUTO_FIELDS, auto_fields=AUTO_FIELDS)
PY

# The Spanish vault, laid out the way the setup interview lays it out.
V="$TMP/vault"
mkdir -p "$V/📓 Diarios/2026-08" "$V/👤 CRM" "$V/📝 Notas" "$V/⚙️ Meta"

cat > "$V/📓 Diarios/2026-08/2026-08-01.md" <<'MD'
---
creationDate: 2026-08-01T21:10
type: journal
floor: Entusiasmo
floor_level: Alto
---

Hoy hablé con [[Ana Pérez]] sobre el proyecto y salió mejor de lo que esperaba.
MD
cat > "$V/📓 Diarios/2026-08/2026-08-02.md" <<'MD'
---
creationDate: 2026-08-02T21:10
type: journal
floor: Miedo
floor_level: Bajo
---

Día pesado. La reunión con [[Ana Pérez]] me dejó pensando en los plazos del banco.
MD
cat > "$V/📓 Diarios/2026-08/2026-08-03.md" <<'MD'
---
creationDate: 2026-08-03T21:10
type: journal
floor: Hope
floor_num: 9
---

An English-tagged day, with a stale floor_num from an older extractor still in the frontmatter.
MD
cat > "$V/📓 Diarios/2026-08/2026-08-04 Rise.md" <<'MD'
---
creationDate: 2026-08-04T07:30
type: rise
floor: Alegría
floor_level: Alto
priorities:
  - "cerrar el presupuesto"
---

Amanecí con energía y ganas de cerrar el presupuesto de una vez.
MD
cat > "$V/👤 CRM/Ana Pérez.md" <<'MD'
---
type: person
relationship: colega
company: Ejemplo S.A.
---

Ana lidera el equipo comercial y es la persona con la que más coordino.
MD
cat > "$V/📝 Notas/Comité de gerencia.md" <<'MD'
---
type: reunion
date: 2026-08-02
---

Comité semanal. Asistió [[Ana Pérez]] y repasamos el flujo de caja del mes.

## Decisiones
- Cerrar el presupuesto esta semana
MD
cat > "$V/📝 Notas/Plan comercial.md" <<'MD'
---
type: plan
---

Plan comercial del segundo semestre, con metas por canal y responsables por línea.
MD
cat > "$V/📝 Notas/Sistema de archivo.md" <<'MD'
---
type: sistema
---

Cómo se organizan las carpetas del vault y qué va en cada una, con ejemplos.
MD

# ── Run extraction, then the engine ─────────────────────────────────────
# VAULT_ROOT_FORCE=1: the copied extractors live under $STARTER (their
# auto-detected root per _base.py's _resolve_vault_root()), but the fixture
# content is at $V, a sibling directory under $TMP. Without the force flag
# the resolver treats that mismatch as the wrong-vault hazard it exists to
# catch and silently falls back to $STARTER (which holds no fixture content
# at all), so every assertion below would see None/empty rather than the
# planted Spanish journals -- same override _resolve_vault_root() documents
# for scripts/aggregate-sessions.py callers that legitimately target a
# non-default vault.
if ! VAULT_ROOT="$V" VAULT_ROOT_FORCE=1 "$PY" "$STARTER/scripts/vault-metadata-extract.py" --progress-every 0 >"$TMP/extract.log" 2>&1; then
  echo "FAIL: vault-metadata-extract.py exited non-zero" >&2
  cat "$TMP/extract.log" >&2
  exit 1
fi
if ! VAULT_ROOT="$V" VAULT_ROOT_FORCE=1 INSIGHTS_OUTPUT="$TMP/insights.md" \
     "$PY" "$STARTER/scripts/vault-insight-engine.py" --quiet >"$TMP/engine.log" 2>&1; then
  echo "FAIL: vault-insight-engine.py exited non-zero" >&2
  cat "$TMP/engine.log" >&2
  exit 1
fi

# ── Assertions ──────────────────────────────────────────────────────────
"$PY" - "$V" "$TMP/insights.md" "$TMP/extract.log" <<'PY'
import os, re, sys, yaml
V, report, extract_log = sys.argv[1], sys.argv[2], sys.argv[3]

def fm_of(rel):
    text = open(os.path.join(V, rel), encoding="utf-8").read()
    end = text.find("\n---", 3)
    return yaml.safe_load(text[3:end]) or {}

failed = 0
def check(cond, label):
    global failed
    if not cond:
        failed += 1
        print(f"FAIL: {label}", file=sys.stderr)

j1 = fm_of("📓 Diarios/2026-08/2026-08-01.md")
j2 = fm_of("📓 Diarios/2026-08/2026-08-02.md")
j3 = fm_of("📓 Diarios/2026-08/2026-08-03.md")
rise = fm_of("📓 Diarios/2026-08/2026-08-04 Rise.md")
person = fm_of("👤 CRM/Ana Pérez.md")
meeting = fm_of("📝 Notas/Comité de gerencia.md")
plan = fm_of("📝 Notas/Plan comercial.md")
sistema = fm_of("📝 Notas/Sistema de archivo.md")

# 1. journal extractor: floor NAME -> 34-floor number, Spanish and English
check(j1.get("floor_num") == 31, f"journal 'Entusiasmo' -> floor_num 31 (got {j1.get('floor_num')!r})")
check(j2.get("floor_num") == 13, f"journal 'Miedo' -> floor_num 13 (got {j2.get('floor_num')!r})")
check(j3.get("floor_num") == 20 or j3.get("floor_num") == 9,
      f"journal 'Hope' keeps a floor_num (got {j3.get('floor_num')!r})")
# (the stale 9 survives in the FILE without --force — the idempotency contract —
#  but must NOT survive into the person index or the engine, checked below)

# 2. rise -> journal alias: the morning entry is in the index with its floor
check("smart_excerpt" in rise or "word_count" in rise, "rise entry was routed to the journal extractor")
check(rise.get("floor_num") == 33, f"rise 'Alegría' -> floor_num 33 (got {rise.get('floor_num')!r})")

# 3. person.py found 📓 Diarios and translated the names (2 mentions, floors 31 + 13)
check(person.get("person_journal_mention_count") == 2,
      f"person mention count from 📓 Diarios == 2 (got {person.get('person_journal_mention_count')!r})")
co = [str(x) for x in (person.get("person_floor_cooccurrence") or [])]
check(sorted(co) == ["13", "31"], f"person floor co-occurrence == [31, 13] (got {co!r})")
check(person.get("person_last_journal_iso") == "2026-08-02",
      f"person last journal iso == 2026-08-02 (got {person.get('person_last_journal_iso')!r})")

# 4. Spanish type aliases routed to real extractors
check(meeting.get("meeting_date_iso") == "2026-08-02" and "Ana Pérez" in (meeting.get("meeting_attendees") or []),
      f"type: reunion -> meeting extractor (got {meeting!r})")
check("Cerrar el presupuesto esta semana" in (meeting.get("meeting_decisions") or []),
      "meeting extractor read the Spanish '## Decisiones' section")
check("reference_topic" in sistema or "word_count" in sistema, "type: sistema -> reference extractor")

# 5. an explicit extractor beats an alias
check(plan.get("plan_marker") == "custom-extractor", f"type: plan -> the user's plan.py, not the strategy alias (got {plan!r})")
check("strategy_counterpart" not in plan and "strategy_stakes" not in plan, "strategy fields were NOT written to the plan note")

# 6. nothing fell out of the index without an extractor
log = open(extract_log, encoding="utf-8").read()
for t in ("reunion", "rise", "sistema", "plan"):
    check(f"NO_EXTRACTOR_FOR:{t}" not in log, f"no NO_EXTRACTOR_FOR:{t} in the extraction log")

# 7. the insight engine has a floor baseline and used the canonical scale for
#    the stale-number entry (mean of 31, 13, 20 = 21.3; with the stale 9 it
#    would be 17.7)
rep = open(report, encoding="utf-8").read()
m = re.search(r"\| Journal floor: mean / p25 / p75 \| ([\d.]+) / ([\d.]+) / ([\d.]+) \|", rep)
check(m is not None, "engine report has a 'Journal floor' baseline row (floor_num derived from names)")
if m:
    mean = float(m.group(1))
    check(abs(mean - 21.3) < 0.15, f"engine floor mean == 21.3 from names (31,13,20), not from the stale stored 9 (got {mean})")

if failed:
    print(f"FAIL: {failed} assertion(s) failed", file=sys.stderr)
    sys.exit(1)
print("PASS: Spanish vault — journals in 📓 Diarios are found, floor names (es+en) score on the 34-floor scale, "
      "es/rise types reach real extractors, a custom extractor beats an alias, and the engine has a floor baseline")
PY

# ── Regression: a note with MALFORMED UTF-8 is never rewritten ──────────────
# process_file() is a read-modify-WRITE. When it moved onto the shared bounded
# read (safe_read_text, obliged by scripts/check-cloud-safe-file-walkers.py),
# passing errors="replace" would decode an undecodable byte to U+FFFD and then
# write that replacement character back -- silently corrupting the user's note.
# The pre-migration code used a strict open() and let the exception become
# READ_ERR, leaving the file untouched.
#
# MEASURED, not assumed. On an identical planted note (a real prose sentence, so
# the journal extractor actually emits and the write path is reached):
#   errors="replace" -> "Wrote: 1", 0xFF GONE, U+FFFD written into the note
#   strict decoding  -> "Wrote: 0", a READ_ERR, note byte-identical
# An earlier, thinner fixture returned EXTRACTOR_SKIPPED and never reached the
# write at all, which looked exactly like "no corruption". A fixture for this
# bug MUST reach the write.
#
# The assertion deliberately matches READ_ERR + "decode" rather than one exact
# string: a plain strict open() says "'utf-8' codec can't decode byte 0xff..."
# and safe_read_text says "decode-error". Pinning either spelling would make
# this test fail on a refactor that kept the property intact.
MAL="$TMP/mal-vault"
mkdir -p "$MAL/📓 Diarios"
"$PY" - "$MAL" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "\U0001f4d3 Diarios" / "malformed.md"
body = (b"Hoy fue un dia largo y aprendi algo importante sobre el trabajo con "
        + b"\xff" + b" y sigo pensando en ello.\n")
p.write_bytes("---\ntype: journal\ndate: 2026-09-24\n---\n\n".encode() + body)
PY
mal_before="$("$PY" -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$MAL/📓 Diarios/malformed.md")"
VAULT_ROOT="$MAL" VAULT_ROOT_FORCE=1 "$PY" "$STARTER/scripts/vault-metadata-extract.py" \
  --progress-every 0 >"$TMP/mal.log" 2>&1 || true
mal_after="$("$PY" -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$MAL/📓 Diarios/malformed.md")"

mal_fail=0
if [ "$mal_before" != "$mal_after" ]; then
  echo "FAIL: a malformed-UTF-8 note was REWRITTEN by extraction (data corruption)" >&2
  mal_fail=1
fi
if ! grep -Eq "READ_ERR:.*([Dd]ecode|codec)" "$TMP/mal.log"; then
  echo "FAIL: malformed note did not surface as a decode READ_ERR (silent skip?)" >&2
  cat "$TMP/mal.log" >&2
  mal_fail=1
fi
# The undecodable byte must still be on disk and no replacement char written.
if ! "$PY" - "$MAL/📓 Diarios/malformed.md" <<'PY'
import sys
d = open(sys.argv[1], "rb").read()
ok = b"\xff" in d and "�".encode() not in d
print("ok" if ok else "FAIL: 0xFF present=%s U+FFFD written=%s" % (
    b"\xff" in d, "�".encode() in d), file=sys.stderr if not ok else sys.stdout)
sys.exit(0 if ok else 1)
PY
then
  mal_fail=1
fi
if [ "$mal_fail" != 0 ]; then
  echo "FAIL: malformed-note regression" >&2
  exit 1
fi
echo "PASS: a malformed-UTF-8 note is reported as a decode READ_ERR and left byte-identical"

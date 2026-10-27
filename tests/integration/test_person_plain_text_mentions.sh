#!/usr/bin/env bash
# Test: a person's journal mentions count plain-text names and aliases, not only
# [[wikilinks]], without crediting the wrong person.
#
# Bug class: person.py counted a journal as a mention only when it held the
# exact wikilink [[Full Name]]. People are mostly written without one ("lunch
# with Maya", "talked to my manager"), so a person seen every week read as 0
# mentions, and the insight engine's "going cold" and floor co-occurrence
# findings fired on exactly the people the journal talks about most.
#
# Fix under test: a plain-text pass over the same journals for the note's file
# name and its `aliases:`, with guards that keep it from crediting the wrong
# person:
#   - a name or alias two CRM notes claim (two "Leo"s) is not used for either;
#   - a capitalized alias inside a longer name ("Ana Maria", "Rosa Ana", "Ana
#     de la Fuente") does not count, while a capital that only opens a
#     sentence ("Yesterday Maya said") does;
#   - inside a [[link]] it counts only when the link is to one of the person's
#     own names ([[Maya]]), never inside a link to someone else;
#   - matches are whole words ("Anabel" is not "Ana").
# A day already counted through a wikilink is not counted twice, and
# PERSON_PLAIN_TEXT_MENTIONS=0 turns the pass off.
#
# Self-contained: tmpdir fake vault + a private copy of scripts/, every path
# pinned by VAULT_ROOT. Exit 0 = pass, 1 = fail. If no python3 on this machine
# can import yaml the suite says so and exits 0 (CI installs PyYAML for it).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
for f in scripts/vault-metadata-extract.py scripts/extractors/person.py; do
  if [ ! -f "$REPO_ROOT/$f" ]; then
    echo "ERROR: $REPO_ROOT/$f not found" >&2
    exit 1
  fi
done

PY=""
for cand in python3 python3.13 python3.12 python3.11 python3.10 python3.9 "$HOME"/.local/pipx/venvs/*/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import yaml" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "SKIP: no python3 with PyYAML found on this machine (pip install pyyaml); the plain-text mention assertions did not run."
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

STARTER="$TMP/starter"
mkdir -p "$STARTER/scripts"
cp -R "$REPO_ROOT/scripts/extractors" "$STARTER/scripts/extractors"
rm -rf "$STARTER/scripts/extractors/__pycache__"
cp "$REPO_ROOT/scripts/vault-metadata-extract.py" "$STARTER/scripts/"

build_vault() { # $1 = vault dir
  local V="$1"
  mkdir -p "$V/📓 Journals/2026-09" "$V/👤 CRM"
  person() { # $1 = name, $2 = aliases YAML (flow list) or empty
    {
      printf -- '---\ntype: person\nrelationship: friend\n'
      [ -n "$2" ] && printf 'aliases: %s\n' "$2"
      printf -- '---\n\nA fictional contact.\n'
    } > "$V/👤 CRM/$1.md"
  }
  person "Maya Torres" '[Maya, "my manager"]'
  person "Ana Ruiz" '[Ana]'
  person "Leo Park" '[Leo]'
  person "Leo Grant" '[Leo]'
  person "Ana Lima" ''
  journal() { # $1 = day, $2 = body
    printf -- '---\ncreationDate: 2026-09-%sT21:00\ntype: journal\nfloor: Hope\n---\n\n%s\n' "$1" "$2" \
      > "$V/📓 Journals/2026-09/2026-09-$1.md"
  }
  journal 01 "Coffee with Maya Torres this morning."
  journal 02 "Maya sent the deck. Then Leo called about the trip."
  journal 03 "Yesterday Maya said yes. Later [[Maya Torres]] sent the contract."
  journal 04 "Talked to my manager about the budget."
  journal 05 "Dinner with Ana Maria and her kids."
  journal 06 "Drinks with Rosa Ana after work."
  journal 07 "Ana confirmed the date for the workshop."
  journal 08 "Brunch at Anabel's house."
  journal 09 "Call with [[Maya]] about the launch."
  journal 10 "Met [[Ana Belén Soto]] and Ana de la Fuente at the fair."
  journal 11 "Lunch with [[Ana Lima|Ana]] near the office."
  journal 12 "Got notes from [[M. Torres|Maya]] today."
}

run_extract() { # $1 = vault, $2 = log, extra env via caller
  if ! VAULT_ROOT="$1" VAULT_ROOT_FORCE=1 "$PY" "$STARTER/scripts/vault-metadata-extract.py" --progress-every 0 >"$2" 2>&1; then
    echo "FAIL: vault-metadata-extract.py exited non-zero" >&2
    cat "$2" >&2
    exit 1
  fi
}

V="$TMP/vault"
build_vault "$V"
run_extract "$V" "$TMP/extract.log"

V_OFF="$TMP/vault-off"
build_vault "$V_OFF"
PERSON_PLAIN_TEXT_MENTIONS=0 run_extract "$V_OFF" "$TMP/extract-off.log"

"$PY" - "$V" "$V_OFF" <<'PY'
import os, sys, yaml
V, V_OFF = sys.argv[1], sys.argv[2]

def fm_of(vault, name):
    text = open(os.path.join(vault, "👤 CRM", name + ".md"), encoding="utf-8").read()
    end = text.find("\n---", 3)
    return yaml.safe_load(text[3:end]) or {}

failed = 0
def check(cond, label):
    global failed
    if not cond:
        failed += 1
        print(f"FAIL: {label}", file=sys.stderr)

def count(vault, name):
    return fm_of(vault, name).get("person_journal_mention_count")

# 1. Full name and aliases in plain text count; the wikilink day is not doubled.
#    Days 01 (full name), 02 (alias at a sentence start), 03 (alias after a
#    sentence-opening capital, plus a wikilink the same day), 04 (lowercase
#    alias), 09 (a link to the alias, [[Maya]]), 12 (the alias shown on a link
#    that resolves to no note).
maya = fm_of(V, "Maya Torres")
check(count(V, "Maya Torres") == 6,
      f"Maya Torres counted on 6 days (got {count(V, 'Maya Torres')!r})")
check(maya.get("person_last_journal_iso") == "2026-09-12",
      f"Maya Torres last journal == 2026-09-12 (got {maya.get('person_last_journal_iso')!r})")

# 2. An alias inside a longer name, inside another word, or on a link to another
#    note does not count: days 05 ("Ana Maria"), 06 ("Rosa Ana"), 08 ("Anabel"),
#    10 ("[[Ana Belén Soto]]", "Ana de la Fuente") and 11 ("[[Ana Lima|Ana]]")
#    are out.
check(count(V, "Ana Ruiz") == 1,
      f"Ana Ruiz counted only on day 07 (got {count(V, 'Ana Ruiz')!r})")

# 3. An alias two notes claim is used for neither.
check(count(V, "Leo Park") == 0, f"ambiguous 'Leo' not credited to Leo Park (got {count(V, 'Leo Park')!r})")
check(count(V, "Leo Grant") == 0, f"ambiguous 'Leo' not credited to Leo Grant (got {count(V, 'Leo Grant')!r})")

# 4. Off switch: wikilinks only, the count from before this change.
check(count(V_OFF, "Maya Torres") == 1,
      f"PERSON_PLAIN_TEXT_MENTIONS=0 counts wikilinks only (got {count(V_OFF, 'Maya Torres')!r})")
check(count(V_OFF, "Ana Ruiz") == 0,
      f"PERSON_PLAIN_TEXT_MENTIONS=0 leaves Ana Ruiz at 0 (got {count(V_OFF, 'Ana Ruiz')!r})")

if failed:
    print(f"{failed} assertion(s) failed", file=sys.stderr)
    sys.exit(1)
print("PASS: plain-text names and aliases count as journal mentions, without crediting the wrong person")
PY

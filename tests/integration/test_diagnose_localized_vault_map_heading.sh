#!/usr/bin/env bash
# Test: /diagnose recognizes a Spanish-localized "Vault Map" heading.
#
# Bug class: both diagnose surfaces (scripts/diagnose.sh, scripts/diagnose.ps1)
# looked for the literal English heading "## Vault Map". A vault set up in
# Spanish names the same section "## Mapa del vault" (the setup phases say to
# translate where idiomatic), so /diagnose warned "No '## Vault Map' section"
# on a vault that had one, with the advice "Claude will create duplicate
# folders without it" -- advice that is false for that vault.
#
# Under test:
#   1. diagnose.sh reports the section present for "## Mapa del vault" (and
#      "## Mapa del Vault", "## Mapa de la bóveda"), still for "## Vault Map".
#   2. NEGATIVE CONTROL: a CLAUDE.md with neither heading still warns, so the
#      wider pattern did not turn the check into a rubber stamp.
#   3. diagnose.ps1 carries the same pattern (it cannot run here; this keeps
#      the two surfaces from drifting apart).
#
# Self-contained: tmpdir vault, HOME redirected. Exit 0 = pass, 1 = fail.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SH="$REPO_ROOT/scripts/diagnose.sh"
PS1="$REPO_ROOT/scripts/diagnose.ps1"
for f in "$SH" "$PS1"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: $f not found" >&2
    exit 1
  fi
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/fake-home"
export USERPROFILE="$TMP/fake-home"
mkdir -p "$HOME/.claude"

# Long enough to clear the "CLAUDE.md is tiny" (< 200 bytes) branch.
filler="$(printf 'Linea de relleno para que el archivo supere el minimo de tamano.\n%.0s' 1 2 3 4)"

make_vault() {
  local dir="$TMP/$1" heading="$2"
  mkdir -p "$dir"
  {
    printf '# Memoria del vault\n\n%s\n\n' "$filler"
    [ -n "$heading" ] && printf '%s\n\n- Casa/\n- Trabajo/\n' "$heading"
  } > "$dir/CLAUDE.md"
  printf '%s' "$dir"
}

diagnose_out() {
  # diagnose.sh exits non-zero when other checks fail on a bare vault; only
  # its Vault Map line matters here.
  bash "$SH" "$1" 2>&1 || true
}

failed=0

for heading in "## Vault Map" "## Mapa del vault" "## Mapa del Vault" "## Mapa de la bóveda" "## Mapa de la Boveda"; do
  v="$(make_vault "present-$RANDOM" "$heading")"
  out="$(diagnose_out "$v")"
  if ! printf '%s' "$out" | grep -q "Vault Map section present"; then
    echo "FAIL [heading not recognized]: $heading" >&2
    failed=$((failed + 1))
  fi
done

v="$(make_vault "absent-$RANDOM" "")"
out="$(diagnose_out "$v")"
if ! printf '%s' "$out" | grep -q "No '## Vault Map' section"; then
  echo "FAIL [negative control]: a CLAUDE.md with no map heading did not warn" >&2
  failed=$((failed + 1))
fi

if ! grep -q 'Mapa del \[Vv\]ault' "$PS1" || ! grep -q 'Mapa de la \[Bb\](o|ó)veda' "$PS1"; then
  echo "FAIL: diagnose.ps1 lacks the Spanish heading pattern diagnose.sh has" >&2
  failed=$((failed + 1))
fi

if [ "$failed" -gt 0 ]; then
  echo "FAIL: $failed assertion(s) failed" >&2
  exit 1
fi
echo "PASS: diagnose recognizes '## Mapa del vault' and still warns when no map heading exists"

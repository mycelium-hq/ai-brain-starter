#!/usr/bin/env bash
# Regression test: the install must pre-frame Claude Code's built-in trust
# prompt for third-party plugins, marketplaces, and MCP servers.
#
# Bug class: a non-technical installer hits Claude Code's trust prompt
# (approve these third-party tools / they are not verified by Anthropic)
# with no warning, reads it as malware sneaking onto the machine, panics,
# and abandons the install. The trust prompt itself is correct and is NOT
# suppressed. The fix is to get ahead of it so the user expects it and
# knows approving is the normal, safe choice.
#
# Source incident: a real installer of the free public ai-brain-starter
# saw the trust prompt mid-install and messaged the maintainer, worried
# that malicious agents were being slipped onto the machine. At the time
# the README promised the install "just runs, no questions" and the
# maintainer guide told the installing assistant not to surface warnings,
# so the prompt arrived completely unframed.
#
# This test fails if any pre-framing surface is removed, or if the false
# "no questions, it just runs" promise returns to the README.
#
# Self-contained. Exit 0 = pass. Exit 1 = fail with details.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
README="$REPO_ROOT/README.md"
PHASE00="$REPO_ROOT/phases/phase-00-install.md"
BOOTSTRAP_SH="$REPO_ROOT/bootstrap.sh"
BOOTSTRAP_PS1="$REPO_ROOT/bootstrap.ps1"

FAILED=0

# must_contain <file> <failure-label> <literal-substring>
must_contain() {
  local file="$1" label="$2" needle="$3"
  if [ ! -f "$file" ]; then
    echo "FAIL: $label" >&2
    echo "  file not found: $file" >&2
    FAILED=$((FAILED + 1))
    return 0
  fi
  if ! grep -qF -- "$needle" "$file"; then
    echo "FAIL: $label" >&2
    echo "  expected to find in $(basename "$file"): \"$needle\"" >&2
    FAILED=$((FAILED + 1))
  fi
  return 0
}

# must_not_contain <file> <failure-label> <literal-substring>
must_not_contain() {
  local file="$1" label="$2" needle="$3"
  if [ -f "$file" ] && grep -qF -- "$needle" "$file"; then
    echo "FAIL: $label" >&2
    echo "  banned string is back in $(basename "$file"): \"$needle\"" >&2
    echo "  the install must not promise a friction-free run it cannot deliver." >&2
    FAILED=$((FAILED + 1))
  fi
  return 0
}

# 1. The README explains the trust prompt to the human reader, EN + ES.
must_contain "$README" \
  "README is missing the English 'What Claude will ask you' section" \
  "What Claude will ask you"
must_contain "$README" \
  "README is missing the Spanish trust-prompt section" \
  "Qué te va a preguntar Claude"

# 2. The README must NOT promise a no-questions install. That false promise
#    is what turned a routine safety prompt into an ambush.
must_not_contain "$README" \
  "README regressed to the false English 'no questions' promise" \
  "No questions first"
must_not_contain "$README" \
  "README regressed to the false Spanish 'no questions' promise" \
  "Sin preguntas primero"

# 3. The maintainer guide must require the installing assistant to pre-frame
#    the trust prompt. It used to tell the assistant not to surface warnings.
must_contain "$README" \
  "README maintainer guide no longer requires pre-framing the trust prompt" \
  "Pre-framing it is part of the install"

# 4. phase-00 carries the assistant-facing pre-framing step.
must_contain "$PHASE00" \
  "phase-00-install.md is missing the trust-prompt pre-framing step (Step 0.0b)" \
  "Step 0.0b"

# 5. Both bootstrap scripts print the heads-up before registering marketplaces.
must_contain "$BOOTSTRAP_SH" \
  "bootstrap.sh is missing the trust-prompt heads-up line" \
  "may pause to ask you to approve these tools"
must_contain "$BOOTSTRAP_PS1" \
  "bootstrap.ps1 is missing the trust-prompt heads-up line" \
  "may pause to ask you to approve these tools"

# 6. The README must tell the installing assistant NOT to put up a menu.
#    Sibling install-UX regression class to the trust-prompt ambush above:
#    a fresh Claude reading the README would respond to "install this for me"
#    with a 3-option menu (show me the script / just the skill / don't install)
#    instead of installing, stalling non-technical conversions. The fix is a
#    VISIBLE anti-menu directive at the top of each Install section (EN + ES);
#    these assertions guard it against silent removal. Source: PR #146.
must_contain "$README" \
  "README is missing the English anti-menu install directive (run now, no menu)" \
  "Do not put up a menu"
must_contain "$README" \
  "README is missing the Spanish anti-menu install directive (correr ya, sin menú)" \
  "No armes un menú"

# 7. The README + phase-00 must pre-frame Claude Code's command-approval prompt
#    (distinct from the trust prompt) and forbid the two failure modes a real
#    Windows installer hit: falling back to a menu when a command is blocked,
#    and downgrading to the /plugin-only install (which skips the system tools,
#    MCP wiring, and vault setup). Source: second install-UX incident (Windows,
#    command blocked by a stricter permission mode).
must_contain "$README" \
  "README is missing the English command-approval pre-frame" \
  "approve running the install command"
must_contain "$README" \
  "README is missing the Spanish command-approval pre-frame" \
  "apruebe correr el comando de instalación"
must_contain "$README" \
  "README is missing the '/plugin-only is not the full install' downgrade guard" \
  "not the full install"
must_contain "$PHASE00" \
  "phase-00 is missing the command-approval step (Step 0.0c)" \
  "Step 0.0c"

if [ "$FAILED" -gt 0 ]; then
  echo "" >&2
  echo "$FAILED trust-prompt pre-framing check(s) failed." >&2
  echo "The install must keep getting ahead of Claude Code's built-in trust prompt:" >&2
  echo "suppress nothing, surprise no one. See phases/phase-00-install.md Step 0.0b." >&2
  exit 1
fi

echo "PASS: trust-prompt pre-framing intact (README EN+ES, maintainer guide, phase-00 Step 0.0b, bootstrap.sh, bootstrap.ps1) + anti-menu install directive (README EN+ES) + command-approval pre-frame & no-/plugin-downgrade guard (README EN+ES, phase-00 Step 0.0c)."

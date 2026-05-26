#!/bin/bash
# PreCompact hook: point the model at the session-close rule before
# context is compacted and the conversation history is lost.
#
# The phases themselves live in ⚙️ Meta/rules/session-close.md — we
# don't restate them here so the rule stays the single source of truth.

cat <<'EOF'
{"decision":"allow","additionalContext":"CRITICAL: Context compaction imminent. READ AND EXECUTE `$HOME/vault/⚙️ Meta/rules/session-close.md` NOW in full before compacting. Every phase runs, none skipped, zeros reported. File all captures to the vault before history is erased. Then proceed with compaction."}
EOF

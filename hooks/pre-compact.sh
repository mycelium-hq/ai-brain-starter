#!/bin/bash
# PreCompact hook: injects a reminder to run session-close captures
# before context is compacted and conversation history is lost.
#
# Returns additionalContext so the model sees the reminder before compacting.

cat <<'EOF'
{"decision":"allow","additionalContext":"CRITICAL: Context is about to be compacted. Before proceeding, run the FULL session-close capture routine NOW: journal seeds, Substack notes, actionable content filing, to-do scan, delegation scan, decision scan, and change impact audit. Do NOT skip any lane. File everything to the vault before compaction erases this context. After filing, proceed with compaction."}
EOF

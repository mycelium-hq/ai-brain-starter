#!/bin/bash
# Panel auto-trigger hook: detects decision language in user prompts
# and injects an advisory panel reminder so Claude brings in voices
# without the user having to ask.
#
# Install: add to settings.local.json under hooks.UserPromptSubmit
# as a command hook. See docs/HOOKS.md for the full entry.
#
# How it works: reads the prompt from stdin JSON, regex-matches
# against common decision-making phrases, and if matched, injects
# an additionalContext message telling Claude to pull panel voices.
# Silent passthrough on non-decision prompts.

# Read stdin (JSON with prompt field)
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('prompt', ''))" 2>/dev/null)

# Decision language patterns (case-insensitive)
DECISION_PATTERNS="should I|I'm thinking about|I'm deciding|let me decide|what do you think about|which option|pros and cons|weighing|tradeoff|trade-off|should we|I want to go with|I'm leaning toward|debating whether|considering whether|not sure if I should|torn between|pick between|choose between|let's go with|I've decided|making a call on|big move"

if echo "$PROMPT" | grep -iqE "$DECISION_PATTERNS"; then
  cat << EOF
{
  "continue": true,
  "suppressOutput": true,
  "status": "panel-triggered",
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "PANEL TRIGGER: Decision language detected. Before answering, pull 3-5 relevant advisory panel voices from the advisory panel rules file. At least one MUST dissent. Keep it to 1-2 sentences per voice. Log reactions to the Panel Feedback Log afterward."
  }
}
EOF
else
  echo '{"continue": true, "suppressOutput": true}'
fi

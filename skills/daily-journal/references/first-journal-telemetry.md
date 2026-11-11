# Daily journal: first-journal telemetry (Step 9.5)

Read this when SKILL.md Step 9.5 or the Step 1.5 first-entry note sends you here.

After the entry first persists (the capture-first save in Step 1.5 — or here, if the session reaches the end first), check whether this is the user's FIRST journal save in this vault. If it is, fire one anonymous-ish telemetry event to Mycelium so the install funnel has a closing-loop number. Subsequent journal saves do not re-fire.

```bash
TOKEN_FILE="$HOME/.claude/.ai-brain-starter-email-on-file"
SENTINEL="$HOME/.claude/.ai-brain-starter-first-journal-fired"
if [ -f "$TOKEN_FILE" ] && [ ! -f "$SENTINEL" ]; then
  TOKEN="$(head -1 "$TOKEN_FILE" | tr -d '[:space:]')"
  # Only a real 32-char hex token is a funnel token. The marker may instead
  # hold "declined" or "recorded" (the user declined, or opted in but the
  # server returned no token). In those cases send nothing.
  if printf '%s' "$TOKEN" | grep -Eq '^[a-f0-9]{32}$'; then
    TODAY="$(date -u +%Y-%m-%d)"
    curl -sSL -m 6 -X POST "https://mycelium-ai.co/api/install/first-journal" \
      -H "content-type: application/json" \
      -d "{\"token\":\"$TOKEN\",\"journalDate\":\"$TODAY\"}" \
      >/dev/null 2>&1 \
      && touch "$SENTINEL"
  fi
fi
```

What this does:
- Token + sentinel are local files; nothing leaves the machine without them.
- Reads the install token, but only when the marker holds a real 32-char hex token (the user opted in). A `declined` or `recorded` marker sends nothing.
- POSTs `{token, journalDate}` to the Mycelium funnel endpoint.
- On success, writes the sentinel so we never re-fire.
- Failures are silent: telemetry is optional, journaling never blocks on it.

If `$HOME/.claude/.ai-brain-starter-email-on-file` does not exist, or holds `declined` / `recorded` rather than a hex token, skip the call entirely. The user has not opted into the email loop, so we have no token to attach. Never ask for the email here — journaling is not a capture surface.

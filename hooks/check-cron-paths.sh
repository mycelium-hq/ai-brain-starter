#!/usr/bin/env bash
# SessionStart guard: warn when crontab references scripts that no longer exist.
#
# Reads `crontab -l`, extracts every absolute path under $HOME ending in .py or .sh,
# and warns to stderr if any are missing. Silent on success. Never blocks.
#
# Useful after any directory move that affects cron-scheduled scripts: if you
# relocate a repo or vault and forget to update crontab, the jobs silently fail.
# This hook surfaces the gap at the next session start.

set -uo pipefail

cron_text=$(crontab -l 2>/dev/null) || exit 0
[[ -z "$cron_text" ]] && exit 0

home_re="^${HOME}/"
missing=()

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  [[ "$path" =~ $home_re ]] || continue
  [[ -e "$path" ]] || missing+=("$path")
done < <(printf '%s\n' "$cron_text" \
  | grep -v '^[[:space:]]*#' \
  | grep -oE '/[^[:space:]"'"'"']+\.(py|sh)' \
  | sort -u)

if (( ${#missing[@]} > 0 )); then
  printf '⚠️  %d stale cron path(s) — run `crontab -e` to fix:\n' "${#missing[@]}" >&2
  for p in "${missing[@]}"; do
    printf '   %s\n' "$p" >&2
  done
fi

exit 0

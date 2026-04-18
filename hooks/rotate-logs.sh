#!/bin/bash
# Rotate hook logs when they exceed a size threshold.
# Keeps last N rotated copies, gzipped. Safe to call every SessionStart.
# Runs silently and fast (~10ms for small logs); exits 0 always.
#
# Policy: rotate at >500KB, keep 3 generations (.1.gz .2.gz .3.gz).
# Total cap per log ~2MB on disk after compression.
#
# Usage:
#   LOG_DIR=~/.claude/hooks bash rotate-logs.sh
#
# Or add specific log paths to LOGS array below.

set +e

LOG_DIR="${LOG_DIR:-$HOME/.claude/hooks}"
MAX_BYTES="${MAX_BYTES:-512000}"
KEEP="${KEEP:-3}"

# Auto-collect all .log files in LOG_DIR, or override by setting LOGS explicitly.
if [ ${#LOGS[@]:-0} -eq 0 ]; then
  mapfile -t LOGS < <(find "$LOG_DIR" -maxdepth 1 -name "*.log" 2>/dev/null)
fi

rotate() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local size
  size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
  (( size > MAX_BYTES )) || return 0

  local i
  for (( i = KEEP - 1; i >= 1; i-- )); do
    [[ -f "${f}.${i}.gz" ]] && mv "${f}.${i}.gz" "${f}.$((i + 1)).gz" 2>/dev/null
  done
  gzip -c "$f" > "${f}.1.gz" 2>/dev/null && : > "$f"
}

for log in "${LOGS[@]}"; do
  rotate "$log"
done

# Evict generations beyond KEEP
for log in "${LOGS[@]}"; do
  ls "${log}."*.gz 2>/dev/null | sort -rn -t. -k2 | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f "$old"
  done
done

exit 0

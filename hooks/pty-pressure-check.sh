#!/bin/bash
# SessionStart hook: warn in-conversation when the macOS pty pool is near full.
#
# macOS exposes a pseudo-terminal pool sized by `kern.tty.ptmx_max` (default 511).
# Some long-running Claude desktop processes leak pty file descriptors over
# multi-day sessions; at 100% usage no new terminal or shell can spawn
# (forkpty: Device not configured). This hook is a second, independent
# detector alongside any external launchd watchdog you may run.
#
# Silent unless usage >= 75%. Never blocks.

MAX=$(sysctl -n kern.tty.ptmx_max 2>/dev/null)
case "$MAX" in ''|*[!0-9]*|0) MAX=511 ;; esac
USED=$(lsof /dev/ptmx 2>/dev/null | awk 'NR>1 && NF' | wc -l | tr -d ' ')
case "$USED" in ''|*[!0-9]*) USED=0 ;; esac
PCT=$(( USED * 100 / MAX ))
if [ "$PCT" -ge 75 ]; then
  echo "[pty-pressure] macOS pseudo-terminal pool at ${PCT}% (${USED}/${MAX} ptys). The Claude desktop app can leak pty file descriptors over multi-day runs; at 100% no new terminal or shell can spawn (forkpty: Device not configured). Remedy: quit and relaunch Claude, or close idle terminals to free ptys."
fi
exit 0

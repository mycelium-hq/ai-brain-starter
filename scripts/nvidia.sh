#!/usr/bin/env bash
# exit-contract: NOT-A-CHECKER -- shells an OpenAI-compatible NVIDIA
#   completion request

# nvidia.sh — Route grunt-work text to NVIDIA build (build.nvidia.com)
#
# Free credits on developer accounts; OpenAI-compatible.
# Use for grunt-work (classification, extraction, format conversion,
# structured-output regex-class tasks). NEVER use for judgment,
# voice-sensitive prose, or agentic tool-use loops.
#
# Usage:
#   nvidia.sh "prompt" [max_tokens]                       # diffusiongemma-26b (default; ~1.5s warm, 10-15s cold)
#   nvidia.sh --model deepseek "prompt" [max_tokens]      # reasoning; scratchpad in reasoning_content
#   nvidia.sh --model muse "prompt" [max_tokens]
#
# Model availability is PER-ACCOUNT and rotates fast. /v1/models lists models
# your key cannot call (404 "Not found for account") — probe a real completion
# before trusting any ID.
#
# Examples:
#   nvidia.sh "Extract dates from: $(cat note.md)" 500
#   nvidia.sh --model deepseek "Explain this stack trace: ..." 800
#
# Returns just the content. Exit 1 on API error.
# Reads NVIDIA_API_KEY via canonical fallback chain
# (env -> .zshenv -> .zsh_secrets -> .zshrc -> .zprofile -> .bashrc).

set -euo pipefail

MODEL_KEY="llama"
case "${1:-}" in
  --model)
    MODEL_KEY="${2:?--model requires a value}"
    shift 2
    ;;
esac

# Model IDs re-verified live 2026-09-09 by probing /v1/chat/completions, not
# /v1/models. KEY FINDING: the catalog lists models this account cannot call —
# they return 404 "Not found for account". Listing != access. Access is
# per-account, so no hardcoded map is right for everyone or for long: of the six
# IDs verified on 2026-08-23, four were gone eight days later, including the
# default; and minimaxai/minimax-m3, verified on 2026-08-31, answered 410 Gone
# ("end of life") nine days after that. Only these answered on this
# (free-tier) account today.
case "$MODEL_KEY" in
  llama|gemma|default|grunt)
    # Clean text in `content`, no reasoning scratchpad — the right SHAPE for
    # grunt work. But measured 2026-09-09 on a free-tier account: 3 of 5 calls
    # returned content; the other 2 hung past a 90s timeout with no body at all.
    # Latency on the successful ones ranged 8s to 86s. Give it a long timeout
    # and a retry, and do not put it in a path that cannot tolerate a miss.
    # It also needs headroom: at max_tokens=20 it returns 200 with an EMPTY
    # `content` and finish_reason "stop". Budget >= 50.
    MODEL="google/diffusiongemma-26b-a4b-it"
    ;;
  deepseek|deepseek-flash)
    # Emits its scratchpad in `reasoning_content` — wrong shape for extraction.
    # Also returned 529 "Service temporarily overloaded" on most probes today.
    MODEL="deepseek-ai/deepseek-v4-flash-0731"
    ;;
  muse)
    # Answers fast (~1s) but puts its output in `reasoning_content`, and at
    # max_tokens=50 returned an empty `content` 5 times out of 5. Needs a large
    # budget (200+) before anything usable lands in `content`. Not a grunt-work
    # model despite the speed.
    MODEL="meta/muse-glimmer-30b"
    ;;
  *)
    echo "Error: unknown --model '$MODEL_KEY'. Valid: llama/gemma (default) | deepseek | muse" >&2
    echo "Availability is per-account and changes often; re-probe before trusting this list." >&2
    exit 1
    ;;
esac

PROMPT="${1:?Usage: nvidia.sh [--model NAME] \"prompt\" [max_tokens]}"
MAX_TOKENS="${2:-1000}"
ENDPOINT="https://integrate.api.nvidia.com/v1/chat/completions"

# Canonical secret-loading: env first, then standard shell-init files.
if [[ -z "${NVIDIA_API_KEY:-}" ]]; then
  for f in "$HOME/.zshenv" "$HOME/.zsh_secrets" "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" "$HOME/.env"; do
    if [[ -f "$f" ]]; then
      key=$( { grep -E '^(export[[:space:]]+)?NVIDIA_API_KEY=' "$f" 2>/dev/null || true; } | tail -1 | sed -E 's/^(export[[:space:]]+)?NVIDIA_API_KEY=//' | sed -E 's/^"//;s/"$//;s/^'\''//;s/'\''$//')
      if [[ -n "$key" ]]; then
        export NVIDIA_API_KEY="$key"
        break
      fi
    fi
  done
fi

if [[ -z "${NVIDIA_API_KEY:-}" ]]; then
  echo "Error: NVIDIA_API_KEY not set (checked env + .zshenv + .zsh_secrets + .zshrc + fallback chain)" >&2
  echo "Add to ~/.zsh_secrets:  export NVIDIA_API_KEY=\"nvapi-...\"" >&2
  exit 1
fi

# Build payload via env-var passing (heredoc-safe; never python3 -c '...' for multiline).
PAYLOAD=$(PROMPT="$PROMPT" MODEL="$MODEL" MAX_TOKENS="$MAX_TOKENS" python3 - <<'PYEOF'
import json, os
print(json.dumps({
    "model": os.environ["MODEL"],
    "messages": [{"role": "user", "content": os.environ["PROMPT"]}],
    "max_tokens": int(os.environ["MAX_TOKENS"]),
    "temperature": 0.2,
    "stream": False,
}))
PYEOF
)

RESPONSE=$(curl -sS --max-time 60 -X POST "$ENDPOINT" \
  -H "Authorization: Bearer $NVIDIA_API_KEY" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" 2>&1) || {
    echo "nvidia.sh: curl failed: $RESPONSE" >&2
    exit 1
  }

# Parse + extract via env-var (response bounded by max_tokens, fits in env).
RESULT=$(RESPONSE="$RESPONSE" python3 - <<'PYEOF'
import json, os, sys
raw = os.environ["RESPONSE"]
try:
    r = json.loads(raw)
except Exception as e:
    print(f"PARSE_ERR:{e}:{raw[:300]}", file=sys.stderr)
    sys.exit(2)
if "error" in r:
    e = r["error"]
    msg = e.get("message", str(e)) if isinstance(e, dict) else str(e)
    print(f"API_ERR:{msg}", file=sys.stderr)
    sys.exit(2)
if not r.get("choices"):
    print(f"NO_CHOICES:{json.dumps(r)[:300]}", file=sys.stderr)
    sys.exit(2)
msg = r["choices"][0].get("message", {}) or {}
# Reasoning models (e.g. deepseek) deliver output in
# `reasoning_content` instead of `content`. Fall back when content is empty.
out = msg.get("content") or msg.get("reasoning_content") or ""
print(out)
PYEOF
) || {
  echo "nvidia.sh: response parse failed (see stderr above)" >&2
  exit 1
}

printf '%s\n' "$RESULT"

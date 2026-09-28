#!/bin/bash
# sdd-cache-post.sh — PostToolUse hook for WebFetch.
#
# After WebFetch, stores the response body with the current ETag /
# Last-Modified (captured via a HEAD request) so the pre hook can revalidate
# on the next fetch.
#
# Keyed by URL. The caller's prompt is stored as metadata (not part of the
# key) so a future cache hit can show what question produced the cached
# reading. Entries without ETag or Last-Modified are not cached.
#
# Where entries live (MYC-4623):
#   ~/.claude/.cache/sdd-cache/<repo-key>/<sha256(url)>.json
# OUTSIDE every project tree. The upstream wrote <project>/.claude/sdd-cache/,
# which put third-party page bodies in the working tree of whatever repo the
# session ran in (session commits swept them up) and let a cloned repo plant
# entries the pre hook would serve. <repo-key> is one directory per repository,
# so every worktree of a repo shares a cache and unrelated repos never see each
# other's prompts. The root is 0700.
#
# Each entry carries `tag`: a digest of the entry keyed with 32 random bytes in
# ~/.claude/.cache/sdd-cache/.key (0600, created here on first use, fed to the
# digest on stdin so it never appears in the process table). The pre hook
# serves nothing that lacks a matching tag, so only entries this machine wrote
# can ever be served.
#
# Bounded: at most SDD_CACHE_MAX_ENTRIES (default 256) entries per repository;
# the least recently written or served are evicted.
#
# Debug logging: SDD_CACHE_DEBUG=1 only. (The upstream also honoured a `.debug`
# file inside the project's cache dir, a switch any cloned repo could flip to
# log raw hook payloads, signed URLs included, into its own working tree.)
#
# Dependencies: jq, curl, shasum (or sha256sum). Missing any -> nothing stored.
#
# Adapted from addyosmani/agent-skills (MIT), cherry-picked 2026-05-26. The
# location, integrity tag, bound and debug switch are local changes.

set -euo pipefail
umask 077

command -v jq   >/dev/null 2>&1 || exit 0
command -v curl >/dev/null 2>&1 || exit 0
command -v shasum >/dev/null 2>&1 || command -v sha256sum >/dev/null 2>&1 || exit 0
[ -n "${HOME:-}" ] || exit 0

if [ -t 0 ]; then INPUT="{}"; else INPUT=$(cat); fi

# ---- identical in sdd-cache-pre.sh: keep these helpers in step --------------
sha256_hex() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256; else sha256sum; fi | cut -c1-64
}
CACHE_ROOT="$HOME/.claude/.cache/sdd-cache"
KEY_FILE="$CACHE_ROOT/.key"
repo_key() {
  local dir="${CLAUDE_PROJECT_DIR:-$PWD}" id=""
  id=$(git -C "$dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
  [ -n "$id" ] || id="$dir"
  printf '%s' "$id" | sha256_hex | cut -c1-16
}
entry_digest() {  # $1 = key file; stdin = entry JSON. Digest of the entry minus its tag.
  { cat "$1"; printf '\n'; jq -cS 'del(.tag)'; } | sha256_hex
}
dbg() {
  [ "${SDD_CACHE_DEBUG:-0}" = "1" ] || return 0
  { mkdir -p "$CACHE_ROOT" \
    && printf '%s [post] %s\n' "$(date -u +%FT%TZ)" "$*" >> "$CACHE_ROOT/.debug.log"; } 2>/dev/null || true
}
# ------------------------------------------------------------------------------

dbg "fired, input=$(printf '%s' "$INPUT" | head -c 400)"

URL=$(printf '%s'    "$INPUT" | jq -r '.tool_input.url    // empty' 2>/dev/null || true)
PROMPT=$(printf '%s' "$INPUT" | jq -r '.tool_input.prompt // empty' 2>/dev/null || true)
if [ -z "$URL" ]; then dbg "no url in tool_input, exit"; exit 0; fi
dbg "url=$URL prompt=$(printf '%s' "$PROMPT" | head -c 80)"

# WebFetch tool_response shape (Claude Code as of 2026-04): an object with
# keys bytes, code, codeText, durationMs, result, url — content lives at
# .result. The other keys (.output / .text / .content / .body) are kept as
# defensive fallbacks in case the shape changes; jq returns empty if none
# match. The string branch handles older/custom integrations.
TOOL_RESPONSE_TYPE=$(printf '%s' "$INPUT" | jq -r '.tool_response | type' 2>/dev/null || echo "unknown")
dbg "tool_response type=$TOOL_RESPONSE_TYPE keys=$(printf '%s' "$INPUT" | jq -r 'try (.tool_response | keys | join(",")) catch "n/a"' 2>/dev/null)"

CONTENT=$(printf '%s' "$INPUT" | jq -r '
  if (.tool_response | type) == "object" then
    (.tool_response.result
     // .tool_response.output
     // .tool_response.text
     // .tool_response.content
     // .tool_response.body
     // empty)
  elif (.tool_response | type) == "string" then
    .tool_response
  else
    empty
  end
' 2>/dev/null || true)

if [ -z "$CONTENT" ]; then
  dbg "could not extract content from tool_response, exit (shape unknown)"
  exit 0
fi
dbg "extracted content bytes=${#CONTENT}"

CACHE_DIR="$CACHE_ROOT/$(repo_key)"
mkdir -p "$CACHE_DIR"
# A root created by an earlier version (or by hand) may be group/world
# readable; entries and the key must not be.
chmod 700 "$CACHE_ROOT" "$CACHE_DIR" 2>/dev/null || true
CACHE_FILE="$CACHE_DIR/$(printf '%s' "$URL" | sha256_hex | cut -c1-32).json"

# Capture validators from the origin. Follow redirects so they match the
# URL the agent actually talked to. Strip CR so awk's paragraph mode
# recognises blank separators between response blocks on a redirect chain.
HEAD_OUT=$(curl -sI -L --max-time 5 "$URL" 2>/dev/null | tr -d '\r' || true)

# Take only the final response's headers (last paragraph) to avoid picking
# up validators from intermediate 301/302 hops.
FINAL_HEADERS=$(printf '%s' "$HEAD_OUT" | awk '
  BEGIN { RS = ""; last = "" }
  { last = $0 }
  END { print last }
')

extract_header() {
  local name="$1"
  printf '%s' "$FINAL_HEADERS" | awk -v h="$name" '
    BEGIN { FS = ":" }
    tolower($1) == tolower(h) {
      sub(/^[^:]*:[ \t]*/, "")
      sub(/[ \t]+$/, "")
      print
      exit
    }
  '
}

ETAG=$(extract_header "ETag")
LAST_MOD=$(extract_header "Last-Modified")
dbg "HEAD etag=$ETAG last_modified=$LAST_MOD"

if [ -z "$ETAG" ] && [ -z "$LAST_MOD" ]; then
  dbg "no validator from origin, removing any stale entry and exit"
  rm -f "$CACHE_FILE"
  exit 0
fi

# The machine key: created once. `ln` refuses to replace an existing file, so
# two first-ever runs racing each other still end up agreeing on one key.
if [ ! -s "$KEY_FILE" ]; then
  KEY_TMP="$KEY_FILE.$$.tmp"
  if head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$KEY_TMP"; then
    ln "$KEY_TMP" "$KEY_FILE" 2>/dev/null || true
  fi
  rm -f "$KEY_TMP"
fi
if [ ! -s "$KEY_FILE" ] || [ -L "$KEY_FILE" ]; then
  dbg "no usable machine key, not caching"
  exit 0
fi

NOW=$(date +%s)
TMP="${CACHE_FILE}.$$.tmp"
TAG=""
if jq -n \
  --arg url           "$URL" \
  --arg prompt        "$PROMPT" \
  --arg etag          "$ETAG" \
  --arg last_modified "$LAST_MOD" \
  --arg content       "$CONTENT" \
  --argjson fetched_at "$NOW" \
  '{url: $url, prompt: $prompt, etag: $etag, last_modified: $last_modified, content: $content, fetched_at: $fetched_at}' \
  > "$TMP" \
  && TAG=$(entry_digest "$KEY_FILE" < "$TMP") \
  && [ "${#TAG}" -eq 64 ] \
  && jq --arg tag "$TAG" '. + {tag: $tag}' "$TMP" > "$TMP.tagged"
then
  mv "$TMP.tagged" "$CACHE_FILE"
  dbg "wrote cache file $CACHE_FILE"
else
  dbg "jq or digest failed, temp cleaned"
fi
rm -f "$TMP" "$TMP.tagged"

# Evict past the bound: newest (written or served) first, everything past the
# cap goes. `ls -t` is the one portable mtime sort (BSD and GNU stat disagree),
# and entry names are hex + .json, so its output is safe to split.
MAX="${SDD_CACHE_MAX_ENTRIES:-256}"
case "$MAX" in ''|*[!0-9]*) MAX=256 ;; esac
[ "$MAX" -ge 1 ] || MAX=256
# shellcheck disable=SC2012
ls -1t -- "$CACHE_DIR"/*.json 2>/dev/null \
  | tail -n +"$((MAX + 1))" \
  | while IFS= read -r old; do
      case "${old##*/}" in
        [0-9a-f]*.json) rm -f -- "$old" ;;
      esac
    done || true

exit 0

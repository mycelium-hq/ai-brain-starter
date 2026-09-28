#!/bin/bash
# sdd-cache-pre.sh — PreToolUse hook for WebFetch.
#
# HTTP resource cache keyed by URL. Freshness is delegated to the origin via
# HTTP validators; 304 Not Modified is the only signal to serve from cache.
# On hit, exits 2 and writes the cached body to stderr so Claude Code can
# deliver it to the agent in place of the WebFetch result. Otherwise exits 0.
#
# No TTL: if validators don't catch a change, nothing will. Entries without
# ETag or Last-Modified are never cached (can't revalidate).
#
# Cached bodies are prompt-shaped (WebFetch post-processes through a model),
# so the key is URL-only and the original prompt is surfaced in the hit
# message so the next agent can tell if the earlier reading still applies.
#
# Which entries can be served (MYC-4623). The upstream read
# <project>/.claude/sdd-cache/, so a cloned repo could ship an entry with a
# far-future Last-Modified; a static origin answers If-Modified-Since with 304
# for any date after its file's mtime, and the planted text reached the agent
# as the page. Now an entry is served only if ALL of these hold:
#   - it lives under ~/.claude/.cache/sdd-cache/<repo-key>/ (see the post hook);
#     the old in-project directory is never read
#   - it is a regular file, not a symlink
#   - git does not track it (tracked means it arrived with a checkout)
#   - its `tag` matches the digest keyed with this machine's
#     ~/.claude/.cache/sdd-cache/.key, i.e. the post hook here wrote it
#   - its `url` is the URL being fetched
#
# Debug logging: SDD_CACHE_DEBUG=1 only, written to the cache root.
#
# Dependencies: jq, curl, shasum (or sha256sum). Missing any -> fetch proceeds.
#
# Adapted from addyosmani/agent-skills (MIT), cherry-picked 2026-05-26. The
# location and the integrity checks are local changes.

set -euo pipefail
umask 077

# Graceful degradation: if any dependency is missing, let the fetch through.
command -v jq   >/dev/null 2>&1 || exit 0
command -v curl >/dev/null 2>&1 || exit 0
command -v shasum >/dev/null 2>&1 || command -v sha256sum >/dev/null 2>&1 || exit 0
[ -n "${HOME:-}" ] || exit 0

if [ -t 0 ]; then INPUT="{}"; else INPUT=$(cat); fi

# ---- identical in sdd-cache-post.sh: keep these helpers in step -------------
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
    && printf '%s [pre]  %s\n' "$(date -u +%FT%TZ)" "$*" >> "$CACHE_ROOT/.debug.log"; } 2>/dev/null || true
}
# ------------------------------------------------------------------------------

dbg "fired"

URL=$(printf '%s' "$INPUT" | jq -r '.tool_input.url // empty' 2>/dev/null || true)
if [ -z "$URL" ]; then dbg "no url in tool_input, exit"; exit 0; fi
dbg "url=$URL"

CACHE_DIR="$CACHE_ROOT/$(repo_key)"
CACHE_FILE="$CACHE_DIR/$(printf '%s' "$URL" | sha256_hex | cut -c1-32).json"

if [ ! -f "$CACHE_FILE" ] || [ -L "$CACHE_FILE" ]; then
  dbg "no cache file at $CACHE_FILE, exit"; exit 0
fi
if [ ! -s "$KEY_FILE" ] || [ -L "$KEY_FILE" ]; then
  dbg "no machine key, nothing can be verified, exit"; exit 0
fi
if git -C "$CACHE_DIR" ls-files --error-unmatch -- "$(basename "$CACHE_FILE")" >/dev/null 2>&1; then
  dbg "entry is tracked by git, refusing"; exit 0
fi

STORED_TAG=$(jq -r '.tag // empty' "$CACHE_FILE" 2>/dev/null || true)
WANT_TAG=$(entry_digest "$KEY_FILE" < "$CACHE_FILE" 2>/dev/null || true)
if [ -z "$STORED_TAG" ] || [ "${#WANT_TAG}" -ne 64 ] || [ "$STORED_TAG" != "$WANT_TAG" ]; then
  dbg "integrity tag missing or wrong, refusing"; exit 0
fi
ENTRY_URL=$(jq -r '.url // empty' "$CACHE_FILE" 2>/dev/null || true)
if [ "$ENTRY_URL" != "$URL" ]; then
  dbg "entry is for a different url, refusing"; exit 0
fi
dbg "cache file verified: $CACHE_FILE"

FETCHED_AT=$(jq -r '.fetched_at // 0' "$CACHE_FILE" 2>/dev/null || echo 0)
ORIGINAL_PROMPT=$(jq -r '.prompt // empty' "$CACHE_FILE" 2>/dev/null || true)
ETAG=$(jq -r '.etag // empty' "$CACHE_FILE" 2>/dev/null || true)
LAST_MOD=$(jq -r '.last_modified // empty' "$CACHE_FILE" 2>/dev/null || true)

# No validator means we cannot verify freshness — never serve from cache.
if [ -z "$ETAG" ] && [ -z "$LAST_MOD" ]; then
  dbg "cached entry has no etag/last-modified, cannot revalidate, bypass"
  exit 0
fi

HEADERS=()
[ -n "$ETAG" ]     && HEADERS+=(-H "If-None-Match: $ETAG")
[ -n "$LAST_MOD" ] && HEADERS+=(-H "If-Modified-Since: $LAST_MOD")

STATUS=$(curl -sI -o /dev/null -w "%{http_code}" \
  --max-time 5 -L \
  "${HEADERS[@]}" \
  "$URL" 2>/dev/null || echo "000")
dbg "revalidation HEAD status=$STATUS"

if [ "$STATUS" != "304" ]; then
  dbg "not 304, letting WebFetch proceed"
  exit 0
fi

# Server confirmed content unchanged. Serve cached copy to the agent.
CONTENT=$(jq -r '.content // empty' "$CACHE_FILE" 2>/dev/null || true)
if [ -z "$CONTENT" ]; then dbg "cache file has empty content field, bypass"; exit 0; fi
dbg "cache HIT, blocking WebFetch with ${#CONTENT} bytes of cached content"
# A served entry counts as recently used, so the post hook's eviction keeps it.
touch "$CACHE_FILE" 2>/dev/null || true

VERIFIED_AT_ISO=$(date -u -r "$FETCHED_AT" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
              || date -u -d "@$FETCHED_AT" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
              || echo "unknown")

# Emit the payload with printf so $CONTENT is never interpreted by the shell
# (docs contain backticks, $vars, and backslashes in code examples; an
# unquoted heredoc would treat them as command substitution).
{
  printf '[sdd-cache] Cache hit for %s\n\n' "$URL"
  printf 'Revalidated via HTTP 304; unchanged since %s. Use the cached\n' "$VERIFIED_AT_ISO"
  printf 'content below as if WebFetch had just returned it.\n\n'
  if [ -n "$ORIGINAL_PROMPT" ]; then
    printf 'Original WebFetch prompt: "%s". If your angle differs, judge\n' "$ORIGINAL_PROMPT"
    printf 'whether this reading still covers it.\n\n'
  fi
  printf -- '----- BEGIN CACHED CONTENT -----\n'
  printf '%s\n' "$CONTENT"
  printf -- '----- END CACHED CONTENT -----\n'
} >&2
exit 2

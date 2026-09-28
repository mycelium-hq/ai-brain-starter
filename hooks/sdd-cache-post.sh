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
#   ~/.claude/.cache/sdd-cache/<project-key>/<sha256(url)>.json
# OUTSIDE every project tree. The upstream wrote <project>/.claude/sdd-cache/,
# which put third-party page bodies in the working tree of whatever repo the
# session ran in (session commits swept them up) and let a cloned repo plant
# entries the pre hook would serve. <project-key> is the project directory's
# canonical path, hashed: see project_key below for why it is never derived
# from git. The root is 0700 and carries a `*` .gitignore, so even a versioned
# home or ~/.claude cannot sweep the cache or its key into a commit.
#
# Each entry carries `tag`: a digest of the entry, keyed with 32 random bytes in
# ~/.claude/.cache/sdd-cache/.key (0600, created here on first use, never on a
# command line) and bound to its project key. The pre hook serves nothing
# whose tag does not verify, so only entries this machine wrote for this
# project can ever be served. An unreadable or malformed key turns the cache
# off rather than weakening the digest.
#
# Bounded: at most SDD_CACHE_MAX_ENTRIES (default 256) entries per project;
# the least recently written or served are evicted, and temp files abandoned
# by a killed run are swept after 10 minutes.
#
# Debug logging: SDD_CACHE_DEBUG=1 only. (The upstream also honoured a `.debug`
# file inside the project's cache dir, a switch any cloned repo could flip to
# log raw hook payloads, signed URLs included, into its own working tree.)
#
# Dependencies: jq, curl, shasum (or sha256sum). Missing any -> nothing stored.
#
# Adapted from addyosmani/agent-skills (MIT), cherry-picked 2026-05-26. The
# location, integrity tag, bound, https-only HEAD and debug switch are local
# changes.

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
# One cache directory per project directory, named from its canonical path.
# Deliberately NOT derived from git: git metadata lives inside the project, so
# the project could choose its key. An unpacked archive's .git/commondir can
# name another repo's git dir, an enclosing repo (a versioned home) lumps
# unrelated folders together, and git < 2.31 echoes --path-format back. Each of
# those was reproduced sharing one cache across unrelated projects.
project_key() {
  local dir="${CLAUDE_PROJECT_DIR:-$PWD}" canon=""
  canon=$(cd "$dir" 2>/dev/null && pwd -P) || canon=""
  [ -n "$canon" ] || canon="$dir"
  printf '%s' "$canon" | sha256_hex | cut -c1-16
}
# The machine key as exactly 64 hex chars, or nothing. Nothing means the cache
# is off: an unreadable key must never shrink the digest to one anyone could
# compute (a failed read inside the digest pipeline is otherwise masked).
read_key() {
  local k=""
  [ -f "$KEY_FILE" ] && [ ! -L "$KEY_FILE" ] && [ -r "$KEY_FILE" ] || return 0
  k=$(head -c 64 "$KEY_FILE" 2>/dev/null) || k=""
  case "$k" in *[!0-9a-f]*) k="" ;; esac
  if [ "${#k}" -eq 64 ]; then printf '%s' "$k"; fi
  return 0
}
# Digest binding an entry to this machine's key AND its project directory, so
# an entry copied into another project's cache does not verify there.
# $1 = key, $2 = project key; stdin = entry JSON (its own tag is ignored).
entry_digest() {
  { printf '%s\n%s\n' "$1" "$2"; jq -cS 'del(.tag)'; } | sha256_hex
}
dbg() {
  [ "${SDD_CACHE_DEBUG:-0}" = "1" ] || return 0
  [ -L "$CACHE_ROOT" ] && return 0
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

PKEY=$(project_key)
CACHE_DIR="$CACHE_ROOT/$PKEY"
# Every write below goes through these two directories; a symlink at either
# would carry the writes (and the eviction's deletes) somewhere else.
[ -L "$CACHE_ROOT" ] && exit 0
mkdir -p "$CACHE_ROOT"
[ -L "$CACHE_DIR" ] && exit 0
mkdir -p "$CACHE_DIR"
# A root created by an earlier version (or by hand) may be group/world
# readable; entries and the key must not be.
chmod 700 "$CACHE_ROOT" "$CACHE_DIR" 2>/dev/null || true
if [ ! -e "$CACHE_ROOT/.gitignore" ] && [ ! -L "$CACHE_ROOT/.gitignore" ]; then
  printf '*\n' > "$CACHE_ROOT/.gitignore" 2>/dev/null || true
fi
CACHE_FILE="$CACHE_DIR/$(printf '%s' "$URL" | sha256_hex | cut -c1-32).json"

# Capture validators from the origin, over https only (WebFetch itself upgrades
# http to https, and a plaintext HEAD would let the network choose the
# validators). Follow redirects so they match the URL the agent actually talked
# to. Strip CR so awk's paragraph mode recognises blank separators between
# response blocks on a redirect chain.
HEAD_OUT=$(curl -sI -L --max-time 5 --proto '=https' --proto-redir '=https' "$URL" 2>/dev/null | tr -d '\r' || true)

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
  if [ -f "$CACHE_FILE" ] && [ ! -L "$CACHE_FILE" ]; then rm -f -- "$CACHE_FILE"; fi
  exit 0
fi

# The machine key: created once, from a random-named temp (mktemp, so nothing
# pre-placed at a predictable name is followed). `ln` refuses to replace an
# existing file, so two first-ever runs racing each other agree on one key.
if [ ! -e "$KEY_FILE" ] && [ ! -L "$KEY_FILE" ]; then
  KEY_TMP=$(mktemp "$CACHE_ROOT/.key.XXXXXX" 2>/dev/null) || KEY_TMP=""
  if [ -n "$KEY_TMP" ]; then
    if head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$KEY_TMP"; then
      ln "$KEY_TMP" "$KEY_FILE" 2>/dev/null || true
    fi
    rm -f -- "$KEY_TMP"
  fi
fi
KEY=$(read_key)
if [ -z "$KEY" ]; then dbg "no usable machine key, not caching"; exit 0; fi

# Build the entry in memory; the page body goes to jq on stdin, never argv
# (Linux caps a single argument at 128 KiB, and argv is visible to `ps`).
NOW=$(date +%s)
ENTRY=$(printf '%s' "$CONTENT" | jq -Rs \
  --arg url           "$URL" \
  --arg prompt        "$PROMPT" \
  --arg etag          "$ETAG" \
  --arg last_modified "$LAST_MOD" \
  --argjson fetched_at "$NOW" \
  '{url: $url, prompt: $prompt, etag: $etag, last_modified: $last_modified, content: ., fetched_at: $fetched_at}' \
  2>/dev/null) || ENTRY=""
TAG=""
if [ -n "$ENTRY" ]; then
  TAG=$(printf '%s' "$ENTRY" | entry_digest "$KEY" "$PKEY" 2>/dev/null) || TAG=""
fi
if [ "${#TAG}" -ne 64 ]; then dbg "jq or digest failed, nothing written"; exit 0; fi

TMP=$(mktemp "$CACHE_DIR/.tmp.XXXXXX" 2>/dev/null) || TMP=""
if [ -z "$TMP" ]; then dbg "mktemp failed, nothing written"; exit 0; fi
if printf '%s' "$ENTRY" | jq --arg tag "$TAG" '. + {tag: $tag}' > "$TMP" 2>/dev/null \
   && ! [ -L "$CACHE_FILE" ] \
   && { [ ! -e "$CACHE_FILE" ] || [ -f "$CACHE_FILE" ]; }
then
  # Only ever onto a regular file or nothing: `mv` onto a directory (or a
  # symlink to one) would move the entry into it.
  mv -f -- "$TMP" "$CACHE_FILE"
  dbg "wrote cache file $CACHE_FILE"
else
  rm -f -- "$TMP"
  dbg "entry not written (jq failed, or the target is not a regular file)"
fi

# Evict past the bound: newest (written or served) first, everything past the
# cap goes. `ls -t` is the one portable mtime sort (BSD and GNU stat disagree).
# `-d` lists a directory operand as itself rather than its contents, and every
# path is checked to be a regular file directly inside the cache dir before it
# is removed.
MAX="${SDD_CACHE_MAX_ENTRIES:-256}"
case "$MAX" in ''|*[!0-9]*) MAX=256 ;; esac
[ "$MAX" -ge 1 ] || MAX=256
# shellcheck disable=SC2012
ls -1td -- "$CACHE_DIR"/*.json 2>/dev/null \
  | tail -n +"$((MAX + 1))" \
  | while IFS= read -r old; do
      case "$old" in
        "$CACHE_DIR"/[0-9a-f]*.json)
          if [ -f "$old" ] && [ ! -L "$old" ]; then rm -f -- "$old"; fi ;;
      esac
    done || true

# Temp files a killed run abandoned are never counted by the cap above.
find "$CACHE_DIR" -maxdepth 1 -type f -name '.tmp.*' -mmin +10 -exec rm -f -- {} + 2>/dev/null || true

exit 0

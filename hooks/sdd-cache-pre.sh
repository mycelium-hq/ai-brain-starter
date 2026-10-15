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
#   - it lives under ~/.claude/.cache/sdd-cache/<project-key>/ (see the post
#     hook); the old in-project directory is never read
#   - neither that directory, its root, nor the entry is a symlink
#   - git does not track it (tracked means it arrived with a checkout)
#   - its `tag` verifies against this machine's key and this project's key,
#     i.e. the post hook here wrote it for this project
#   - its `url` is the URL being fetched
# The entry is read once: the bytes that are verified are the bytes served.
#
# Debug logging: SDD_CACHE_DEBUG=1 only, written to the cache root.
#
# Dependencies: jq, curl, shasum (or sha256sum). Missing any -> fetch proceeds.
#
# Adapted from addyosmani/agent-skills (MIT), cherry-picked 2026-05-26. The
# location, the integrity checks and the https-only revalidation are local
# changes.

set -euo pipefail
umask 077
# Exit 2 is Claude Code's BLOCK signal for a PreToolUse hook, and `set -e` exits
# with the failing command's own status: a broken shasum (perl exits 2 when it
# cannot load a module) blocked every WebFetch. Anything nobody handled lets
# the fetch through instead. The one intended exit 2, a cache hit, is `exit`.
trap 'exit 0' ERR
# Everything these hooks parse (case patterns, ls, find, awk, git) runs in a
# known environment. The C locale, so [0-9a-f] is ten digits and six letters
# and nothing else (under a UTF-8 locale bash and BSD find also match A-E, and
# cleanup deleted names the hook never wrote). No CDPATH, which sends `cd`
# elsewhere and makes it print where it went. No GREP_OPTIONS, QUOTING_STYLE or
# colour switches, which change what a tool prints into a pipe.
# curl alone keeps the caller's LC_ALL: it takes its character set from the
# environment, and a libidn2 build (Linux) converts a non-ASCII host name from
# that set, which in the C locale is ASCII, so such a URL was never cached.
SDD_CALLER_LC_ALL=${LC_ALL-}
export LC_ALL=C
unset CDPATH GREP_OPTIONS GREP_COLOR GREP_COLORS QUOTING_STYLE CLICOLOR CLICOLOR_FORCE LS_COLORS

# Graceful degradation: if any dependency is missing, let the fetch through.
command -v jq   >/dev/null 2>&1 || exit 0
command -v curl >/dev/null 2>&1 || exit 0
command -v shasum >/dev/null 2>&1 || command -v sha256sum >/dev/null 2>&1 || exit 0
[ -n "${HOME:-}" ] || exit 0

if [ -t 0 ]; then INPUT="{}"; else INPUT=$(cat); fi

HOOK_TAG="pre"
# ---- identical in sdd-cache-post.sh: keep these helpers in step -------------
sha256_hex() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256; else sha256sum; fi | cut -c1-64
}
CACHE_ROOT="$HOME/.claude/.cache/sdd-cache"
KEY_FILE="$CACHE_ROOT/.key"
# One cache directory per project directory, named from its canonical path:
# `cd -P`, so `a/link/..` is the link target's parent, never `a` read lexically.
# Deliberately NOT derived from git: git metadata lives inside the project, so
# the project could choose its key. An unpacked archive's .git/commondir can
# name another repo's git dir, an enclosing repo (a versioned home) lumps
# unrelated folders together, and git < 2.31 echoes --path-format back. Each of
# those was reproduced sharing one cache across unrelated projects.
project_key() {
  local dir="${CLAUDE_PROJECT_DIR:-$PWD}" canon=""
  # The trailing `x` keeps any newline the path itself ends with: $(...)
  # strips trailing newlines, which gave "p<LF>" the key of its sibling "p".
  canon=$(cd -P "$dir" 2>/dev/null && pwd -P && echo x) || canon=""
  canon=${canon%x}; canon=${canon%$'\n'}
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
# The root: never a symlink, 0700, and carrying a `*` .gitignore BEFORE anything
# else (the key, an entry, a debug log) is written into it, so no repository
# that contains ~/.claude can pick any of it up. A .gitignore that is missing,
# is not exactly `*` (an empty one is what a full disk or a kill mid-write
# leaves), or is a symlink is rewritten through a temp and a rename, so it is
# never observed half-written. Non-zero when the root is unusable.
ensure_root() {
  local gi="$CACHE_ROOT/.gitignore" tmp=""
  [ -L "$CACHE_ROOT" ] && return 1
  mkdir -p "$CACHE_ROOT" 2>/dev/null || return 1
  chmod 700 "$CACHE_ROOT" 2>/dev/null || true
  [ -d "$gi" ] && return 1
  if [ -L "$gi" ] || [ "$(cat -- "$gi" 2>/dev/null || true)" != "*" ]; then
    tmp=$(mktemp "$CACHE_ROOT/.gitignore.XXXXXX" 2>/dev/null) || return 1
    if ! { printf '*\n' > "$tmp" && mv -f -- "$tmp" "$gi"; } 2>/dev/null; then
      rm -f -- "$tmp"
      return 1
    fi
  fi
  return 0
}
dbg() {
  [ "${SDD_CACHE_DEBUG:-0}" = "1" ] || return 0
  ensure_root || return 0
  printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$HOOK_TAG" "$*" >> "$CACHE_ROOT/.debug.log" 2>/dev/null || true
}
# ------------------------------------------------------------------------------

# 0 when $1's PHYSICAL path, or one of its ancestors, holds a .git entry: git
# discovers along the physical path, so a ~/.claude symlinked into a dotfiles
# checkout is inside that checkout, and the walk must see it too. A path that
# cannot be resolved counts as "no".
in_git_tree() {
  local d=""
  d=$(cd -P "$1" 2>/dev/null && pwd -P && echo x) || return 1
  d=${d%x}; d=${d%$'\n'}
  # Parent by parameter expansion, not `dirname`: a dirname that failed once
  # returned "" and the walk never reached "/" (the hook never exited).
  while :; do
    [ -e "$d/.git" ] && return 0
    [ "$d" = "/" ] && return 1
    d=${d%/*}
    [ -n "$d" ] || d=/
  done
}
# 0 = refuse: the entry is tracked by a repository containing the cache, or a
# repository is there and git could not answer (fail closed). 1 = untracked.
# The WHOLE path is folded from the work-tree top, not just the file name: on
# a case-folding disk a checkout can track the entry under an upper-case
# directory. (git folds ASCII only. A repository that tracks a Unicode-folded
# variant of this path would have to live in HOME itself, and whoever controls
# that controls ~/.claude/settings.json and so every hook: out of model.) The
# session's GIT_* location and pathspec variables are scrubbed, so they can
# neither point the check at another repository nor turn the pathspec magic
# off: GIT_LITERAL_PATHSPECS=1 makes ':(top,icase)...' a literal name that
# never matches, which reads as "untracked". A repository git cannot discover
# from here (a bare `--git-dir` dotfiles setup) is out of reach by
# construction; the root's `*` .gitignore means entries get into one only by
# an explicit `add -f`.
GIT_SCRUB=(-u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE -u GIT_COMMON_DIR
  -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES -u GIT_NAMESPACE
  -u GIT_LITERAL_PATHSPECS -u GIT_GLOB_PATHSPECS -u GIT_NOGLOB_PATHSPECS
  -u GIT_ICASE_PATHSPECS)
tracked_or_undecidable() {
  local dir="$1" name="$2" prefix="" rc=0
  in_git_tree "$dir" || return 1
  prefix=$(env "${GIT_SCRUB[@]}" git -C "$dir" rev-parse --show-prefix 2>/dev/null) || return 0
  env "${GIT_SCRUB[@]}" git -C "$dir" ls-files --error-unmatch -- ":(top,icase)${prefix}${name}" \
    >/dev/null 2>&1 || rc=$?
  [ "$rc" -eq 1 ] && return 1
  return 0
}

dbg "fired"

URL=$(printf '%s' "$INPUT" | jq -r '.tool_input.url // empty' 2>/dev/null || true)
if [ -z "$URL" ]; then dbg "no url in tool_input, exit"; exit 0; fi
dbg "url=$URL"

PKEY=$(project_key)
CACHE_DIR="$CACHE_ROOT/$PKEY"
CACHE_FILE="$CACHE_DIR/$(printf '%s' "$URL" | sha256_hex | cut -c1-32).json"

if [ -L "$CACHE_ROOT" ] || [ -L "$CACHE_DIR" ] || [ -L "$CACHE_FILE" ] || [ ! -f "$CACHE_FILE" ]; then
  dbg "no usable cache file at $CACHE_FILE, exit"; exit 0
fi
KEY=$(read_key)
if [ -z "$KEY" ]; then dbg "no usable machine key, nothing can be verified, exit"; exit 0; fi
if tracked_or_undecidable "$CACHE_DIR" "${CACHE_FILE##*/}"; then
  dbg "entry is tracked by git (or a repo around the cache cannot be read), refusing"; exit 0
fi

# Read the entry ONCE. Everything verified and everything served below comes
# from these bytes, so the file changing during the revalidation request
# cannot swap unverified content in.
ENTRY=$(cat -- "$CACHE_FILE" 2>/dev/null) || ENTRY=""
if [ -z "$ENTRY" ]; then dbg "cache file unreadable, exit"; exit 0; fi
field() { printf '%s' "$ENTRY" | jq -r "$1" 2>/dev/null || true; }

STORED_TAG=$(field '.tag // empty')
WANT_TAG=$(printf '%s' "$ENTRY" | entry_digest "$KEY" "$PKEY" 2>/dev/null || true)
if [ -z "$STORED_TAG" ] || [ "${#WANT_TAG}" -ne 64 ] || [ "$STORED_TAG" != "$WANT_TAG" ]; then
  dbg "integrity tag missing or wrong, refusing"; exit 0
fi
if [ "$(field '.url // empty')" != "$URL" ]; then
  dbg "entry is for a different url, refusing"; exit 0
fi
dbg "cache file verified: $CACHE_FILE"

FETCHED_AT=$(field '.fetched_at // 0')
ORIGINAL_PROMPT=$(field '.prompt // empty')
ETAG=$(field '.etag // empty')
LAST_MOD=$(field '.last_modified // empty')

# No validator means we cannot verify freshness — never serve from cache.
if [ -z "$ETAG" ] && [ -z "$LAST_MOD" ]; then
  dbg "cached entry has no etag/last-modified, cannot revalidate, bypass"
  exit 0
fi

HEADERS=()
[ -n "$ETAG" ]     && HEADERS+=(-H "If-None-Match: $ETAG")
[ -n "$LAST_MOD" ] && HEADERS+=(-H "If-Modified-Since: $LAST_MOD")

# https only, as WebFetch itself upgrades to it: over plaintext the network
# could answer 304 and pin a stale entry. `-q` (first, or curl ignores it) keeps
# ~/.curlrc out, where an `insecure` or proxy line would change who answers;
# `-g` stops URL globbing, which turns `[1-40]` into forty requests.
STATUS=$(env LC_ALL="$SDD_CALLER_LC_ALL" curl -q -sI -g -o /dev/null -w "%{http_code}" \
  --max-time 5 -L --proto '=https' --proto-redir '=https' \
  "${HEADERS[@]}" \
  "$URL" 2>/dev/null || echo "000")
dbg "revalidation HEAD status=$STATUS"

if [ "$STATUS" != "304" ]; then
  dbg "not 304, letting WebFetch proceed"
  exit 0
fi

# Server confirmed content unchanged. Serve the verified copy to the agent.
CONTENT=$(field '.content // empty')
if [ -z "$CONTENT" ]; then dbg "cache file has empty content field, bypass"; exit 0; fi
dbg "cache HIT, blocking WebFetch with ${#CONTENT} bytes of cached content"
# A served entry counts as recently used, so the post hook's eviction keeps it.
touch -- "$CACHE_FILE" 2>/dev/null || true

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

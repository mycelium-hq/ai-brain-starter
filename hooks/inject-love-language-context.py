#!/usr/bin/env python3
"""
UserPromptSubmit hook: when the prompt names a CRM person whose card has
a [[5 Love Languages]] section, inject that section as additionalContext
so the assistant uses it when drafting messages, planning gifts, choosing
how to apologize, or designing any relational interaction.

Pattern: vault-context.py. UserPromptSubmit → check prompt → optionally
inject additionalContext → exit 0 always (never block).

Vault root auto-detection (in order):
  1. VAULT_ROOT env var
  2. Walk up from cwd looking for any `CRM/` or `👤 CRM/` folder
  3. Walk up from cwd looking for `⚙️ Meta/Current Priorities.md`
  4. Silent exit if not found

CRM folder name auto-detection:
  - `👤 CRM/` (emoji prefix, vault default)
  - `CRM/` (plain)
  - Override via CRM_DIR_NAME env var

Index cache: ~/.claude/.love-language-index.json. Rebuilt when the newest
CRM .md file is newer than the cache, or when the cache is >1 day old.

Name matching:
  - Filename without .md (canonical name)
  - Any alias declared in frontmatter `aliases:` list (skips phone numbers)
  - First-name match ONLY if globally unique across the CRM
  - Accent-insensitive, case-insensitive

Wire into settings.json under hooks.UserPromptSubmit:
    {
      "type": "command",
      "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/inject-love-language-context.py"
    }

Bypass: set env var LOVE_LANGUAGE_HOOK_DISABLE=1 to suppress.
"""
import json
import os
import re
import sys
import time
import unicodedata
from typing import Optional, List, Dict

INDEX_PATH = os.path.expanduser("~/.claude/.love-language-index.json")
INDEX_MAX_AGE_SEC = 60 * 60 * 24  # 1 day
MAX_INJECTED_PEOPLE = 5  # cap to avoid context bloat
CRM_DIR_CANDIDATES = ["👤 CRM", "CRM"]


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize(s: str) -> str:
    return strip_accents(s).lower().strip()


def find_vault_root() -> Optional[str]:
    """Return the vault root path, or None if not found."""
    env_root = os.environ.get("VAULT_ROOT")
    if env_root and os.path.isdir(env_root):
        return env_root

    # Walk up from cwd looking for any CRM folder or the canonical meta file
    cur = os.getcwd()
    for _ in range(8):
        for name in CRM_DIR_CANDIDATES:
            if os.path.isdir(os.path.join(cur, name)):
                return cur
        if os.path.isfile(os.path.join(cur, "⚙️ Meta", "Current Priorities.md")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def find_crm_dir(vault_root: str) -> Optional[str]:
    """Locate the CRM folder inside the vault."""
    override = os.environ.get("CRM_DIR_NAME")
    candidates = [override] if override else []
    candidates.extend(CRM_DIR_CANDIDATES)
    for name in candidates:
        if not name:
            continue
        path = os.path.join(vault_root, name)
        if os.path.isdir(path):
            return path
    return None


def extract_love_language_section(content: str) -> Optional[str]:
    """Return the markdown section starting at a [[5 Love Languages]] heading.

    Handles both H2-style (## [[5 Love Languages]]) and Roam-template-style
    (  * [[5 Love Languages]] indented bullet). Stops at the next heading
    or sibling top-level bullet.
    """
    lines = content.splitlines()
    section_lines = []
    in_section = False
    indent_anchor: Optional[str] = None

    for line in lines:
        if not in_section:
            if re.match(r"^#{2,3}\s+\[\[5 Love Languages\]\]", line):
                in_section = True
                section_lines.append(line)
                indent_anchor = None
                continue
            m = re.match(r"^(\s*)\*\s+\[\[5 Love Languages\]\]\s*$", line)
            if m:
                in_section = True
                section_lines.append(line)
                indent_anchor = m.group(1)
                continue
        else:
            if re.match(r"^#{1,3}\s", line) and "[[5 Love Languages]]" not in line:
                break
            if indent_anchor is not None:
                m = re.match(r"^(\s*)\*\s", line)
                if m and len(m.group(1)) == len(indent_anchor):
                    break
            section_lines.append(line)

    if not section_lines:
        return None
    while section_lines and not section_lines[-1].strip():
        section_lines.pop()
    return "\n".join(section_lines)


def parse_frontmatter_aliases(content: str) -> List[str]:
    """Return aliases declared in YAML frontmatter (inline-list or block-list)."""
    if not content.startswith("---"):
        return []
    end = content.find("\n---", 4)
    if end < 0:
        return []
    fm = content[4:end]
    aliases: List[str] = []
    in_aliases = False
    for line in fm.splitlines():
        if re.match(r"^aliases\s*:\s*\[", line):
            inside = re.search(r"\[(.*?)\]", line)
            if inside:
                for item in inside.group(1).split(","):
                    val = item.strip().strip('"').strip("'")
                    if val:
                        aliases.append(val)
            in_aliases = False
            continue
        if re.match(r"^aliases\s*:\s*$", line):
            in_aliases = True
            continue
        if in_aliases:
            m = re.match(r"^\s+-\s+(.+)$", line)
            if m:
                val = m.group(1).strip().strip('"').strip("'")
                if val:
                    aliases.append(val)
            else:
                in_aliases = False
    return aliases


def build_index(crm_dir: str) -> dict:
    """Scan CRM folder and build {canonical_name: {section, aliases, first_name}}."""
    index: Dict[str, dict] = {}
    if not os.path.isdir(crm_dir):
        return {"_built_at": time.time(), "people": {}}
    for entry in os.scandir(crm_dir):
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        canonical = entry.name[:-3]
        try:
            with open(entry.path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        section = extract_love_language_section(content)
        if not section:
            continue
        aliases = parse_frontmatter_aliases(content)
        clean_aliases = [a for a in aliases if not a.startswith("+") and len(a) > 1]
        first_name = canonical.split()[0]
        index[canonical] = {
            "section": section,
            "aliases": clean_aliases,
            "first_name": first_name,
        }
    return {"_built_at": time.time(), "people": index, "_crm_dir": crm_dir}


def load_or_rebuild_index(crm_dir: str) -> dict:
    """Return the people index, rebuilding the cache when stale."""
    need_rebuild = True
    cache: Optional[dict] = None
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
            built_at = cache.get("_built_at", 0)
            cached_crm_dir = cache.get("_crm_dir")
            age = time.time() - built_at
            if age < INDEX_MAX_AGE_SEC and cached_crm_dir == crm_dir:
                crm_mtime = max(
                    (e.stat().st_mtime for e in os.scandir(crm_dir) if e.name.endswith(".md")),
                    default=0,
                )
                if crm_mtime <= built_at:
                    need_rebuild = False
        except Exception:
            need_rebuild = True

    if need_rebuild:
        cache = build_index(crm_dir)
        try:
            os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
            with open(INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return cache or {"_built_at": 0, "people": {}}


def find_matches(prompt: str, index: dict) -> List[str]:
    """Return canonical names whose person-tokens appear in the prompt."""
    people: Dict[str, dict] = index.get("people", {})
    if not people:
        return []

    first_name_counts: Dict[str, int] = {}
    for info in people.values():
        key = normalize(info["first_name"])
        first_name_counts[key] = first_name_counts.get(key, 0) + 1

    p_norm = " " + normalize(prompt) + " "
    matches: List[str] = []

    for canonical, info in people.items():
        candidates = [canonical] + info.get("aliases", [])
        fn = info["first_name"]
        if first_name_counts.get(normalize(fn), 0) == 1:
            candidates.append(fn)
        for cand in candidates:
            cand_norm = normalize(cand)
            if not cand_norm or len(cand_norm) < 3:
                continue
            pattern = r"\b" + re.escape(cand_norm) + r"\b"
            if re.search(pattern, p_norm):
                matches.append(canonical)
                break

    seen = set()
    uniq: List[str] = []
    for c in matches:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
        if len(uniq) >= MAX_INJECTED_PEOPLE:
            break
    return uniq


def main() -> None:
    if os.environ.get("LOVE_LANGUAGE_HOOK_DISABLE") == "1":
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = payload.get("prompt", "") or ""
    if not prompt.strip():
        sys.exit(0)

    vault_root = find_vault_root()
    if not vault_root:
        sys.exit(0)
    crm_dir = find_crm_dir(vault_root)
    if not crm_dir:
        sys.exit(0)

    index = load_or_rebuild_index(crm_dir)
    matches = find_matches(prompt, index)
    if not matches:
        sys.exit(0)

    parts = [
        "[love-language-context] CRM love language data for the people named in this prompt.",
        "USE this when drafting messages, planning gifts, choosing how to apologize, or",
        "designing any relational interaction with them — match the channel of care they",
        "actually receive love through, not the one you would default to.",
        "",
    ]
    for canonical in matches:
        info = index["people"][canonical]
        parts.append(f"=== {canonical} ===")
        parts.append(info["section"])
        parts.append("")

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(parts),
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()

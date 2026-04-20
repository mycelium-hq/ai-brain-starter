#!/usr/bin/env python3
"""
extractors/_base.py — shared helpers for all vault metadata extractors.

Every extractor imports from here. Keep it caveman-dense.

Contract: extractors NEVER generate prose. All fields are verbatim extractions,
regex matches, enum lookups, or counts. Zero LLM involvement in this base.
"""
import glob
import os
import re
import yaml

# VAULT: self-locating. Override with VAULT_ROOT env var, else climbs from
# scripts/extractors/_base.py two levels up (scripts/extractors/ → scripts/ → vault root).
VAULT = os.environ.get(
    "VAULT_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)

# CRM folder: override with CRM_FOLDER env var, else auto-detect.
CRM_ROOT = os.environ.get("CRM_FOLDER")
if not CRM_ROOT:
    for candidate in ("👤 CRM", "CRM", "People", "Contacts", "People & Contacts"):
        p = os.path.join(VAULT, candidate)
        if os.path.isdir(p):
            CRM_ROOT = p
            break
    if not CRM_ROOT:
        CRM_ROOT = os.path.join(VAULT, "CRM")  # sane default if nothing matches

# Folders to skip during vault scans. Covers common conventions across templates.
SKIP_PARTS = {
    "⚙️ Meta", "Meta",
    "Archive", "🗄 Archive", "Archive/",
    "_review_alternate_drafts",
    "📥 Inbox", "Inbox",
    ".obsidian", ".git", "node_modules",
}

SKIP_LINE_PREFIXES = (
    "#", "---", "**Gym", "**Sleep", "**RescueTime",
    "**Panel", "**Dissent", "**Omission", "*Floor", "## ",
    "![", "|", "- [ ]", "- [x]",
)

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


# ── Frontmatter ────────────────────────────────────────────────────────

def parse_frontmatter(content):
    """Return (fm_dict, fm_raw, body). fm_dict is None if no frontmatter."""
    if not content.startswith("---"):
        return None, "", content
    end = content.find("\n---", 3)
    if end == -1:
        return None, "", content
    fm_raw = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")
    try:
        fm_dict = yaml.safe_load(fm_raw) or {}
    except Exception:
        fm_dict = {}
    return fm_dict, fm_raw, body


def strip_auto_fields(fm_raw, auto_fields):
    """Remove previously-written auto-generated fields from raw frontmatter."""
    lines = fm_raw.split("\n")
    out = []
    skip_continuation = False
    for line in lines:
        key = line.split(":")[0].strip()
        if key in auto_fields:
            skip_continuation = True
            continue
        if skip_continuation and (line.startswith(" ") or line.startswith("\t")):
            continue
        skip_continuation = False
        out.append(line)
    return "\n".join(out).strip()


def reassemble_file(fm_raw, new_fields_block, body, had_fm):
    """Stitch frontmatter + new auto fields + body back into a single string."""
    if had_fm:
        if fm_raw:
            return f"---\n{fm_raw}\n{new_fields_block}\n---\n\n{body}"
        return f"---\n{new_fields_block}\n---\n\n{body}"
    return f"---\n{new_fields_block}\n---\n\n{body}"


# ── YAML safe writers ─────────────────────────────────────────────────

def yaml_str(s):
    """Single-line, quote-escaped string value."""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def yaml_list(items):
    """Inline YAML list, safe-escaped items."""
    if not items:
        return "[]"
    return "[" + ", ".join(yaml_str(i) for i in items) + "]"


def render_fields(field_dict, field_order):
    """Given a dict of computed fields and their insertion order, render YAML block.
    Skips None/empty values. List values → yaml_list, str/int → direct."""
    lines = []
    for key in field_order:
        val = field_dict.get(key)
        if val is None or val == "" or val == []:
            continue
        if isinstance(val, list):
            lines.append(f"{key}: {yaml_list(val)}")
        elif isinstance(val, bool):
            lines.append(f"{key}: {'true' if val else 'false'}")
        elif isinstance(val, (int, float)):
            lines.append(f"{key}: {val}")
        else:
            lines.append(f"{key}: {yaml_str(val)}")
    return "\n".join(lines)


# ── CRM matching ─────────────────────────────────────────────────────

_CRM_CACHE = None

def get_crm_names():
    """All CRM basenames (no extension). Cached per process."""
    global _CRM_CACHE
    if _CRM_CACHE is None:
        pattern = os.path.join(CRM_ROOT, "**", "*.md")
        files = glob.glob(pattern, recursive=True)  # Rule 36: glob.glob, not pathlib
        _CRM_CACHE = {os.path.splitext(os.path.basename(f))[0] for f in files}
    return _CRM_CACHE


# ── Text utilities ────────────────────────────────────────────────────

def strip_wikilinks(text):
    """Turn [[Foo]] and [[Foo|bar]] into plain text, strip md links."""
    text = WIKILINK_RE.sub(r"\1", text)
    text = MD_LINK_RE.sub(r"\1", text)
    return text


def count_words(body):
    clean = strip_wikilinks(body)
    clean = re.sub(r"[#*`>|\\-]", " ", clean)
    return len(clean.split())


def extract_first_prose_sentence(body, min_len=15, max_len=200):
    """Verbatim first prose sentence. Skips headers, metadata, blockquotes."""
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in SKIP_LINE_PREFIXES):
            continue
        if line.startswith(">"):
            continue
        plain = strip_wikilinks(line)
        if len(plain) < min_len:
            continue
        m = re.match(rf"(.{{{min_len},}}?[.!?])(?:\s|$)", line)
        if m:
            return m.group(1).strip()
        return line[:max_len].strip()
    return ""


def extract_section(body, section_regex, stop_at_next_h2=True):
    """Return the text of a markdown section (## Header). Empty if not found."""
    lines = body.split("\n")
    in_section = False
    out = []
    for line in lines:
        stripped = line.strip()
        if re.match(section_regex, stripped):
            in_section = True
            continue
        if in_section:
            if stop_at_next_h2 and stripped.startswith("##") and not re.match(section_regex, stripped):
                break
            out.append(line)
    return "\n".join(out).strip()


def wikilinks_in(text):
    """All wikilink targets in a string/section. Basename only."""
    return [os.path.basename(m.strip()) for m in WIKILINK_RE.findall(text)]


def match_people(body, crm_names, cap=20):
    """CRM-matched wikilinks. Title Case required to exclude non-person entries."""
    people = []
    for lnk in WIKILINK_RE.findall(body):
        basename = os.path.basename(lnk.strip())
        if basename and basename[0].isupper() and basename in crm_names and basename not in people:
            people.append(basename)
    return people[:cap]


def iso_date_from(raw):
    """Normalize any date-ish string to YYYY-MM-DD, or None."""
    if not raw:
        return None
    m = ISO_DATE_RE.match(str(raw).strip())
    return m.group(1) if m else None


# ── Extraction result helper ──────────────────────────────────────────

class ExtractionResult:
    """What an extractor returns: fields dict + field order for stable YAML."""
    def __init__(self, fields, field_order, auto_fields=None):
        self.fields = fields
        self.field_order = field_order
        # Full auto_fields list (for strip on --force). Defaults to field_order.
        self.auto_fields = tuple(auto_fields or field_order)

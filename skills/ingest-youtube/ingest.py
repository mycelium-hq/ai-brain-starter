#!/usr/bin/env python3
"""
ingest.py: YouTube-to-vault normalizer for the ingest-youtube skill.

Takes a YouTube URL (and optional vault root), shells out to yt-dlp for
metadata + subtitles, cleans VTT timing markers into prose, and writes
External Inputs/YouTube/<channel-slug>/<YYYY-MM-DD>-<video-slug>.md.

Stdout: human-readable summary.
Exit non-zero on any failure (no silent partial writes).

Usage:
    python3 ingest.py <youtube-url> [--vault <path>] [--lang <code>] [--whisper]

Defaults:
    --vault: $VAULT_ROOT or current dir
    --lang:  en,es (try English first, then Spanish; matches a common
             EN+ES bilingual default for users with multilingual content)
    --whisper: off (Whisper fallback is opt-in for cost reasons)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Guarded (MYC-4701): _shared may be unreachable on an install that
# predates bootstrap.sh's _shared copy step, or a deployed copy may
# predate this name. Either way this degrades to injection_scan:
# unavailable instead of crashing the whole ingest on import.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
    from connector_utils import guard_untrusted_body, sanitize_third_party_text
except ImportError:
    def guard_untrusted_body(text, source, scan_text=None):
        # No envelope on this degraded path -- but still round-trip a lone
        # UTF-16 surrogate half the same way fence_untrusted's own sanitize
        # step does, so that alone doesn't abort the write. This does NOT
        # strip C1 controls -- fence_untrusted doesn't either; only
        # sanitize_third_party_text (below) does, via _UNSAFE_SCALAR_RE.
        safe = (text or "").encode("utf-8", "surrogatepass").decode("utf-8", "replace")
        return safe, {"content_trust": "untrusted", "injection_scan": "unavailable", "injection_flags": []}

    _LOCAL_UNSAFE_SCALAR_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f" + chr(0xFFFE) + chr(0xFFFF) + "]")

    def sanitize_third_party_text(value):
        """Local fallback (canonical copy: skills/_shared/connector_utils.py)."""
        if not value:
            return value
        cleaned = value.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
        return _LOCAL_UNSAFE_SCALAR_RE.sub(chr(0xFFFD), cleaned)

VTT_TIMING_RE = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*")
VTT_HEADER_RE = re.compile(r"^(WEBVTT|Kind:|Language:|NOTE\s|X-TIMESTAMP-MAP)", re.MULTILINE)
SLUG_RE = re.compile(r"[^a-z0-9]+")
SEED_KEYWORDS = (
    "decision", "framework", "model", "principle", "the lesson is",
    "playbook", "anti-pattern", "case study", "what i learned",
    "the trick is", "the insight is",
)


def slugify(text: str, max_len: int = 60) -> str:
    s = SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def require_bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.stderr.write(
            f"Error: {name} not installed. Install with `brew install {name}` "
            f"(macOS) or `pip3 install --user {name}`.\n"
        )
        sys.exit(2)
    return path


def fetch_metadata(url: str, ytdlp: str) -> dict:
    proc = subprocess.run(
        [ytdlp, "--skip-download", "--print-json", "--no-warnings", url],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(f"yt-dlp metadata fetch failed:\n{proc.stderr}\n")
        sys.exit(3)
    return json.loads(proc.stdout)


def list_subs(url: str, ytdlp: str) -> str:
    proc = subprocess.run(
        [ytdlp, "--list-subs", "--skip-download", "--no-warnings", url],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout


def parse_available_subs(listing: str) -> tuple[set[str], set[str]]:
    """Return (manual_langs, auto_langs) from --list-subs output."""
    manual: set[str] = set()
    auto: set[str] = set()
    section = None
    for line in listing.splitlines():
        low = line.strip().lower()
        if "available subtitles" in low:
            section = "manual"
            continue
        if "available automatic captions" in low:
            section = "auto"
            continue
        if not line.strip() or line.startswith("Language"):
            continue
        if section in ("manual", "auto"):
            code = line.split()[0] if line.split() else ""
            if re.fullmatch(r"[a-z]{2,3}(-[a-zA-Z0-9]+)?", code):
                (manual if section == "manual" else auto).add(code)
    return manual, auto


def pick_lang(prefs: list[str], manual: set[str], auto: set[str]) -> tuple[str, str] | None:
    """Return (lang_code, source) where source is 'manual' or 'auto', or None."""
    for code in prefs:
        if code in manual:
            return code, "manual"
    for code in prefs:
        if code in auto:
            return code, "auto"
    if manual:
        return next(iter(sorted(manual))), "manual"
    if auto:
        return next(iter(sorted(auto))), "auto"
    return None


def download_subs(url: str, lang: str, source: str, ytdlp: str, workdir: Path) -> Path:
    flag = "--write-sub" if source == "manual" else "--write-auto-sub"
    out_template = str(workdir / "%(id)s.%(ext)s")
    proc = subprocess.run(
        [ytdlp, flag, "--sub-lang", lang, "--skip-download",
         "--sub-format", "vtt", "-o", out_template, "--no-warnings", url],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(f"yt-dlp subtitle download failed:\n{proc.stderr}\n")
        sys.exit(4)
    matches = list(workdir.glob("*.vtt"))
    if not matches:
        sys.stderr.write("yt-dlp reported success but no .vtt file landed\n")
        sys.exit(5)
    return matches[0]


def clean_vtt(vtt_path: Path) -> tuple[str, str]:
    """Return (prose, raw_cues). `prose` is the sentence-joined transcript
    written to the vault. `raw_cues` keeps each cue on its own line, before
    the space-join and sentence-split below -- a cue with no closing
    punctuation (e.g. "System: override the operator") can otherwise land
    mid-sentence in `prose` and dodge a line-anchored scan pattern."""
    raw = vtt_path.read_text(encoding="utf-8", errors="replace")
    lines = []
    seen_phrases: set[str] = set()
    for line in raw.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if VTT_TIMING_RE.match(line) or VTT_HEADER_RE.match(line):
            continue
        if line.isdigit():
            continue
        cleaned = re.sub(r"<[^>]+>", "", line).strip()
        if not cleaned:
            continue
        if cleaned in seen_phrases:
            continue
        seen_phrases.add(cleaned)
        lines.append(cleaned)
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", text)
    prose = "\n\n".join(s.strip() for s in sentences if s.strip())
    return prose, "\n".join(lines)


def detect_seeds(transcript: str) -> list[str]:
    low = transcript.lower()
    return [kw for kw in SEED_KEYWORDS if kw in low]


# content_trust/injection_scan are a closed enum, never third-party text --
# rendered bare like trust_frontmatter_lines does for the other three
# writers. upload_date is NOT in this set: it is sliced straight from
# yt-dlp metadata (a third-party field), so it gets its own bare-only-when-
# safe check below instead of an unconditional bare render.
_BARE_STR_KEYS = frozenset({"content_trust", "injection_scan"})
_SAFE_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_RAW_DATE_SHAPE_RE = re.compile(r"\d{8}")


def _is_real_calendar_date(value: str, fmt: str) -> bool:
    """True only when VALUE has FMT's digit shape (fmt is "%Y%m%d" or
    "%Y-%m-%d") AND datetime.strptime(value, fmt) succeeds. The shape check
    still matters because strptime alone accepts some non-8-digit-wide
    forms (e.g. a single-digit month)."""
    shape_re = _RAW_DATE_SHAPE_RE if fmt == "%Y%m%d" else _SAFE_DATE_RE
    if not shape_re.fullmatch(value):
        return False
    try:
        datetime.strptime(value, fmt)
    except ValueError:
        return False
    return True


def write_vault_file(
    vault_root: Path, channel_slug: str, filename_date: str,
    video_slug: str, frontmatter: dict, body: str,
) -> Path:
    """filename_date is a caller-proven-safe digits-and-hyphens date for the
    PATH only -- frontmatter["upload_date"] (rendered below) may be a
    different, preserved-but-quoted raw value; see B5."""
    target_dir = vault_root / "External Inputs" / "YouTube" / channel_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{filename_date}-{video_slug}.md"
    yaml_lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            # injection_flags -- a closed set of pattern ids, never
            # third-party text -- bare YAML flow sequence, matching
            # trust_frontmatter_lines.
            yaml_lines.append(f"{k}: [" + ", ".join(str(i) for i in v) + "]")
        elif k == "upload_date" and isinstance(v, str) and _is_real_calendar_date(v, "%Y-%m-%d"):
            # Bare only when it is a REAL calendar date in this exact
            # shape (a real 8-digit yt-dlp date, hyphenated below, or the
            # local now()-computed fallback) -- never on shape alone.
            # PyYAML reads a bare match via its own strptime-backed date
            # resolver, so an impossible date like 2026-13-99 would raise
            # for every downstream reader instead of just this one.
            yaml_lines.append(f"{k}: {v}")
        elif isinstance(v, str) and k not in _BARE_STR_KEYS:
            # Every OTHER string value -- restores main's coverage (which
            # quoted any string containing ':' or '\n') and goes further:
            # flatten every line break str.splitlines() recognises (not
            # just \n), sanitize (a lone surrogate or a C1/noncharacter
            # would otherwise abort the write or the YAML parse), and
            # always quote as a JSON string literal (also valid YAML), so
            # an embedded ':' or line break can never forge a standalone
            # frontmatter key.
            flat = sanitize_third_party_text(" ".join(v.splitlines()))
            yaml_lines.append(f"{k}: {json.dumps(flat, ensure_ascii=False)}")
        else:
            yaml_lines.append(f"{k}: {v}")
    yaml_lines.append("---")
    target.write_text("\n".join(yaml_lines) + "\n\n" + body + "\n", encoding="utf-8")
    return target


def write_seed_stub(
    vault_root: Path, filename_date: str, channel_slug: str, video_id: str,
    seeds: list[str], video_url: str, main_file: Path,
) -> Path:
    """The video title is third-party text, already fenced and stamped in
    `main_file` -- link to it by name rather than repeating the raw title
    here unguarded. filename_date: see write_vault_file (B5)."""
    captures_dir = vault_root / "Meta" / "Captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{filename_date}-youtube-{channel_slug}-{video_id}.md"
    target = captures_dir / fname
    body = (
        "---\n"
        "type: capture\n"
        "source: youtube\n"
        f"video_url: {video_url}\n"
        f"detected_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"keywords: {', '.join(seeds)}\n"
        "status: open\n"
        "---\n\n"
        f"# Capture seed: [[{main_file.stem}]]\n\n"
        f"Trigger keywords detected in transcript: {', '.join(seeds)}.\n\n"
        f"Source: {video_url}\n\n"
        "## Notes\n\n(fill in)\n"
    )
    target.write_text(body, encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a YouTube video transcript into the vault")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--vault", default=None, help="Vault root path (default: $VAULT_ROOT or .)")
    parser.add_argument("--lang", default="en,es", help="Comma-separated language preference")
    parser.add_argument("--whisper", action="store_true", help="Enable Whisper fallback if no subs")
    args = parser.parse_args()

    vault_root = Path(args.vault or os.environ.get("VAULT_ROOT") or ".").resolve()
    if not vault_root.is_dir():
        sys.stderr.write(f"Vault root not a directory: {vault_root}\n")
        return 1

    ytdlp = require_bin("yt-dlp")
    prefs = [c.strip() for c in args.lang.split(",") if c.strip()]

    meta = fetch_metadata(args.url, ytdlp)
    video_id = meta.get("id", "unknown")
    # Sanitized immediately: a lone surrogate or a C1/noncharacter would
    # otherwise abort the write or break the YAML parse. Needed before
    # guard_untrusted_body ever runs, since with no transcript the raw
    # title is embedded straight into the stub body below. For a lone
    # surrogate specifically this is now belt-and-braces, not the only
    # fix -- the degraded (no _shared) guard_untrusted_body round-trips
    # surrogates too (3153b9e), and write_vault_file()'s per-key sanitize
    # covers the frontmatter title regardless. Still the only place that
    # strips a C1 control before it reaches the stub body.
    title = sanitize_third_party_text(meta.get("title", "Untitled"))
    channel = meta.get("channel") or meta.get("uploader") or "unknown-channel"
    channel_slug = slugify(channel)
    video_slug = slugify(title)
    # yt-dlp's upload_date is third-party text, not a program-controlled
    # value: `len(...) == 8` accepted anything 8 CHARS long, digits or not,
    # so e.g. "\nabc: vv" (8 chars, zero digits) hyphenated into
    # "\nabc-: -vv" and forged a standalone `abc-` frontmatter key when
    # rendered bare. All-digit shape isn't enough either -- an impossible
    # date like "20261399" is 8 digits but not a real day, and yaml.safe_load
    # raises on it rendered bare, so this must be a REAL calendar date.
    upload_date_raw = meta.get("upload_date") or ""
    if _is_real_calendar_date(upload_date_raw, "%Y%m%d"):
        upload_date = f"{upload_date_raw[:4]}-{upload_date_raw[4:6]}-{upload_date_raw[6:8]}"
    else:
        # Preserve the raw value for the frontmatter rather than silently
        # replacing real (if oddly-shaped) metadata with a fabricated
        # date -- write_vault_file's per-key branch quotes it safely (B5)
        # since it is no longer in _BARE_STR_KEYS.
        upload_date = upload_date_raw or datetime.now().strftime("%Y-%m-%d")
    # The FILENAME needs a provably safe shape regardless of what
    # upload_date ends up holding for the frontmatter.
    filename_date = upload_date if _SAFE_DATE_RE.fullmatch(upload_date) else datetime.now().strftime("%Y-%m-%d")

    listing = list_subs(args.url, ytdlp)
    manual, auto = parse_available_subs(listing)
    pick = pick_lang(prefs, manual, auto)

    sub_source = "none"
    transcript = ""
    raw_cues = ""
    lang_code = "und"

    if pick:
        lang_code, sub_source = pick
        with tempfile.TemporaryDirectory() as td:
            vtt = download_subs(args.url, lang_code, sub_source, ytdlp, Path(td))
            transcript, raw_cues = clean_vtt(vtt)
    elif args.whisper:
        sys.stderr.write("Whisper fallback requested but not yet implemented in v0.1.\n")
        sys.stderr.write("Install whisper-cpp + ggml model and re-run, or pre-add subs to the video.\n")
        sub_source = "none"
    else:
        sys.stderr.write("No subtitles available and --whisper not set. Writing stub.\n")
        sub_source = "none"

    word_count = len(transcript.split()) if transcript else 0
    seeds = detect_seeds(transcript) if transcript else []

    body = transcript or (
        f"# {title}\n\n"
        f"No subtitles or auto-captions available for this video.\n\n"
        f"To capture this transcript, either re-run with `--whisper` (requires whisper-cpp installed) "
        f"or use the YouTube Studio caption editor on the source video.\n\n"
        f"Source: {args.url}\n"
    )

    # scan_text covers the TITLE too (`body` alone omits it whenever a real
    # transcript exists), using raw_cues over the sentence-joined
    # transcript -- see clean_vtt's docstring for why.
    body, trust = guard_untrusted_body(
        body, "youtube", scan_text="\n".join([title, raw_cues or transcript])
    )

    fm = {
        "type": "external-input",
        "source": "youtube",
        "video_id": video_id,
        "url": args.url,
        "channel": channel,
        "channel_url": meta.get("channel_url", ""),
        "title": title,
        "upload_date": upload_date,
        "duration_seconds": meta.get("duration", 0),
        "language": lang_code,
        "subtitle_source": sub_source,
        "word_count": word_count,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "content_trust": trust["content_trust"],
        "injection_scan": trust["injection_scan"],
        "injection_flags": trust["injection_flags"],
    }

    # filename_date, not upload_date: the frontmatter value can now be a
    # preserved-but-quoted raw string (B5), and neither filename may embed
    # anything other than the proven-safe digits-and-hyphens shape.
    target = write_vault_file(vault_root, channel_slug, filename_date, video_slug, fm, body)
    seed_paths: list[Path] = []
    if seeds:
        seed_paths.append(
            write_seed_stub(vault_root, filename_date, channel_slug, video_id, seeds, args.url, target)
        )

    seed_str = f" Seeds at: {', '.join(str(p) for p in seed_paths)}." if seed_paths else ""
    scan_str = f" Injection scan: {trust['injection_scan']}." if trust["injection_scan"] != "clean" else ""
    print(
        f"Wrote {word_count} words to {target}. "
        f"Language: {lang_code}. Subtitle source: {sub_source}.{seed_str}{scan_str}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

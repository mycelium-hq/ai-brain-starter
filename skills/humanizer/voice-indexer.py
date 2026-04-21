#!/usr/bin/env python3
"""
voice-indexer.py — Build a statistical voice fingerprint from journal entries.

Usage:
    python3 voice-indexer.py [journals_path]

    journals_path   Path to your journals directory. If omitted, falls back
                    to the VAULT_PATH environment variable + "/📓 Journals",
                    or prints an error.

Output: ~/.claude/voice-fingerprint.json

Re-run monthly or on demand. Zero external dependencies (stdlib only).
"""

import os
import re
import sys
import json
import statistics
from pathlib import Path
from collections import Counter

# Resolve journals path: CLI arg > $VAULT_PATH env > error.
# (Do not hardcode a personal vault path here — this script ships to anyone.)
_cli_path = sys.argv[1] if len(sys.argv) > 1 else None
_env_vault = os.environ.get("VAULT_PATH")
if _cli_path:
    JOURNALS_PATH = Path(_cli_path).expanduser()
elif _env_vault:
    JOURNALS_PATH = Path(_env_vault).expanduser() / "📓 Journals"
else:
    JOURNALS_PATH = None  # main() checks and exits with a helpful message
OUTPUT_PATH = Path.home() / ".claude" / "voice-fingerprint.json"

# High-frequency Spanish words unlikely to appear in English prose
SPANISH_MARKERS = {
    "que", "de", "en", "la", "el", "los", "las", "una", "un", "es", "son",
    "con", "por", "para", "pero", "como", "más", "muy", "también", "hay",
    "me", "se", "le", "mi", "tu", "su", "nos", "les", "del", "al",
    "fue", "era", "ser", "estar", "tener", "hacer", "decir", "ver",
    "cuando", "donde", "quien", "porque", "aunque", "sino", "siempre",
    "todo", "nada", "algo", "alguien", "nadie", "mucho", "poco",
    "ahora", "antes", "después", "aquí", "allí", "hoy", "ayer",
    "entonces", "así", "bien", "mal", "nunca", "ya", "aún",
    "vida", "mundo", "tiempo", "año", "día", "noche", "casa",
    "sé", "yo", "él", "ella", "ellos", "nosotros", "voy",
    "están", "tiene", "tienen", "había", "han", "he", "ha",
    "creo", "siento", "quiero", "puedo", "debo", "veo",
}

# English connectors to track frequency of
EN_CONNECTORS = [
    "but", "and", "so", "because", "when", "while", "though", "although",
    "however", "still", "yet", "also", "even", "just", "maybe", "somehow",
    "anyway", "sometimes", "always", "never", "often", "usually", "actually",
    "honestly", "really", "apparently", "clearly", "obviously", "basically",
    "essentially", "ultimately", "finally", "suddenly", "eventually",
    "instead", "otherwise", "meanwhile", "then", "now", "here", "there",
    "again", "already", "enough", "only", "both", "either", "neither",
    "whether", "until", "unless", "since", "once", "if", "like", "kind",
]


def strip_frontmatter(text):
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].strip()
    return text


def strip_code_blocks(text):
    return re.sub(r"```[\s\S]*?```", "", text)


def strip_markdown(text):
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)  # wikilinks
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)           # md links
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)           # headers
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)        # bullets
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)                  # bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)                      # italic
    text = re.sub(r"_([^_]+)_", r"\1", text)                        # underline
    return text


def split_sentences(text):
    # Split on .!? followed by whitespace + uppercase (handles EN and ES)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ\u00C0-\u024F])", text)
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def split_paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 20]


def word_count(text):
    return len(re.findall(r"\b\w+\b", text))


def spanish_ratio(text):
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0.0
    return sum(1 for w in words if w in SPANISH_MARKERS) / len(words)


def count_punctuation(text, sentences, words_total):
    sentences_n = max(len(sentences), 1)
    words_n = max(words_total, 1)
    return {
        "commas_per_sentence": round(text.count(",") / sentences_n, 3),
        "colons_per_100_words": round(text.count(":") / words_n * 100, 3),
        "semicolons_per_100_words": round(text.count(";") / words_n * 100, 3),
        "parentheticals_per_100_words": round(text.count("(") / words_n * 100, 3),
        "em_dashes_per_100_words": round((text.count("—") + text.count("--")) / words_n * 100, 3),
        "ellipses_per_100_words": round(text.count("...") / words_n * 100, 3),
    }


def process_file(filepath):
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    text = strip_frontmatter(text)
    text = strip_code_blocks(text)
    text = strip_markdown(text)
    text = text.strip()

    if len(text) < 100:
        return None

    sentences = split_sentences(text)
    paragraphs = split_paragraphs(text)

    if len(sentences) < 2:
        return None

    sent_lengths = [word_count(s) for s in sentences if word_count(s) > 0]
    para_lengths = [word_count(p) for p in paragraphs if word_count(p) > 0]
    words = re.findall(r"\b\w+\b", text.lower())
    total_words = len(words)

    if total_words < 30:
        return None

    # Vocabulary richness: type-token ratio on a 200-word window to normalize length
    sample = words[:200]
    ttr = round(len(set(sample)) / len(sample), 3) if len(sample) >= 50 else None

    # Opening words of each paragraph (first 5 words)
    openers = []
    for p in paragraphs:
        pw = re.findall(r"\b\w+\b", p)[:5]
        if pw:
            openers.append(" ".join(pw).lower())

    return {
        "sentence_lengths": sent_lengths,
        "paragraph_lengths": para_lengths,
        "words": words,
        "total_words": total_words,
        "spanish_ratio": spanish_ratio(text),
        "punctuation": count_punctuation(text, sentences, total_words),
        "openers": openers,
        "ttr": ttr,
    }


def percentile(sorted_list, pct):
    idx = int(len(sorted_list) * pct / 100)
    return sorted_list[min(idx, len(sorted_list) - 1)]


def build_fingerprint(journals_path):
    print(f"Indexing: {journals_path}")

    all_sent = []
    all_para = []
    all_words = []
    all_spanish = []
    all_punct = []
    all_openers = []
    all_ttr = []
    processed = 0
    skipped = 0

    for dirpath, dirnames, filenames in os.walk(str(journals_path), followlinks=True):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in sorted(filenames):
            if not fname.endswith(".md"):
                continue
            result = process_file(Path(dirpath) / fname)
            if result is None:
                skipped += 1
                continue
            all_sent.extend(result["sentence_lengths"])
            all_para.extend(result["paragraph_lengths"])
            all_words.extend(result["words"])
            all_spanish.append(result["spanish_ratio"])
            all_punct.append(result["punctuation"])
            all_openers.extend(result["openers"])
            if result["ttr"] is not None:
                all_ttr.append(result["ttr"])
            processed += 1
            if processed % 200 == 0:
                print(f"  {processed} files...")

    print(f"Done: {processed} processed, {skipped} skipped.")

    if not all_sent:
        print("ERROR: No usable content found.")
        return None

    sorted_sent = sorted(all_sent)

    # Sentence stats
    sent_stats = {
        "mean": round(statistics.mean(all_sent), 2),
        "std": round(statistics.stdev(all_sent), 2),
        "p25": percentile(sorted_sent, 25),
        "p50": percentile(sorted_sent, 50),
        "p75": percentile(sorted_sent, 75),
    }

    # Paragraph stats
    para_stats = {}
    if all_para:
        para_stats = {
            "mean": round(statistics.mean(all_para), 2),
            "std": round(statistics.stdev(all_para), 2) if len(all_para) > 1 else 0,
        }

    # Connector frequency (per 1000 words)
    total = len(all_words)
    freq = Counter(all_words)
    connector_freq = {
        c: round(freq.get(c, 0) / total * 1000, 2)
        for c in EN_CONNECTORS
    }
    top_connectors = dict(sorted(connector_freq.items(), key=lambda x: -x[1])[:20])

    # Vocabulary richness
    avg_ttr = round(statistics.mean(all_ttr), 3) if all_ttr else None

    # Punctuation averages
    avg_punct = {
        k: round(statistics.mean(d[k] for d in all_punct), 3)
        for k in all_punct[0]
    }

    # Opening word patterns
    opener_words = Counter(o.split()[0] for o in all_openers if o.split())
    top_openers = dict(opener_words.most_common(20))

    # Content vocabulary (non-function words, len > 3)
    function = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
        "but", "is", "are", "was", "were", "be", "been", "have", "has", "had",
        "do", "does", "did", "it", "its", "this", "that", "my", "your", "his",
        "her", "our", "their", "i", "you", "he", "she", "we", "they", "what",
        "who", "how", "why", "with", "from", "by", "as", "if", "not", "no",
        "so", "de", "la", "el", "los", "las", "un", "una", "que", "en",
        "con", "por", "para", "me", "se", "le", "mi",
    }
    content = {
        w: c for w, c in freq.items()
        if w not in function and len(w) > 3 and w.isalpha()
    }
    top_content = dict(sorted(content.items(), key=lambda x: -x[1])[:50])

    avg_spanish = round(statistics.mean(all_spanish), 3)

    return {
        "version": "1.0",
        "files_indexed": processed,
        "total_words": total,
        "sentence_length": sent_stats,
        "paragraph_length": para_stats,
        "spanish_ratio": {
            "mean": avg_spanish,
            "interpretation": (
                "bilingual" if avg_spanish > 0.15 else
                "mixed" if avg_spanish > 0.05 else
                "english-dominant"
            ),
        },
        "punctuation": avg_punct,
        "top_connectors_per_1000_words": top_connectors,
        "top_content_words": top_content,
        "top_opener_words": top_openers,
        "vocabulary_richness": {
            "avg_ttr": avg_ttr,
            "interpretation": (
                "rich" if (avg_ttr or 0) > 0.65 else
                "moderate" if (avg_ttr or 0) > 0.45 else
                "repetitive"
            ),
        },
    }


def main():
    journals = JOURNALS_PATH
    if journals is None:
        print(
            "ERROR: journals path not provided.\n"
            "  Pass it as an argument:   python3 voice-indexer.py /path/to/journals\n"
            "  Or set an env var:        export VAULT_PATH=\"$HOME/Desktop/MyVault\""
        )
        sys.exit(1)

    if not journals.exists():
        print(f"ERROR: Path not found: {journals}")
        sys.exit(1)

    fp = build_fingerprint(journals)
    if fp is None:
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(fp, indent=2, ensure_ascii=False))

    print(f"\nSaved: {OUTPUT_PATH}")
    print(f"Files:    {fp['files_indexed']:,}")
    print(f"Words:    {fp['total_words']:,}")
    s = fp["sentence_length"]
    print(f"Sentence: avg {s['mean']} words  σ={s['std']}  P50={s['p50']}")
    p = fp["paragraph_length"]
    print(f"Para:     avg {p.get('mean', '?')} words  σ={p.get('std', '?')}")
    sp = fp["spanish_ratio"]
    print(f"Spanish:  {sp['mean']} ({sp['interpretation']})")
    vr = fp["vocabulary_richness"]
    print(f"Vocab:    TTR={vr['avg_ttr']} ({vr['interpretation']})")
    print(f"\nTop 10 connectors (per 1000 words):")
    for c, v in list(fp["top_connectors_per_1000_words"].items())[:10]:
        print(f"  {c}: {v}")


if __name__ == "__main__":
    main()

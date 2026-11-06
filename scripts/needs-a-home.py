#!/usr/bin/env python3
"""Leave one thing the close could not place in the needs-a-home inbox.

At session close, something said in one workspace that belongs in another, or
whose workspace was unclear, is kept in the member's personal vault under
"Needs a home". This script ALSO drops it, as one small JSON file, in
~/.ai-brain/needs-a-home/, so a desktop app can ask the member where it goes
and file their answer. The vault keeps the durable copy; the inbox is the ask.

    python3 needs-a-home.py add --kind todo --text "Send the pricing page" \
        --for "Acme" --from "team-vault"

--for is the workspace it seems to belong to; leave it out when unsure.
The id is a hash of where it was said and its words, so adding the same thing
twice writes one file. Prints the file it wrote. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

LIMITS = {"todo": 300, "note": 2000}


def inbox() -> Path:
    return Path.home() / ".ai-brain" / "needs-a-home"


def add(kind: str, text: str, suggested: str | None, source: str) -> Path:
    text = " ".join(text.split()) if kind == "todo" else text.strip()
    if not text:
        raise ValueError("nothing to add: the text is empty")
    if len(text) > LIMITS[kind]:
        raise ValueError(f"a {kind} is at most {LIMITS[kind]} characters")
    item_id = hashlib.sha256(f"{source}\n{text}".encode("utf-8")).hexdigest()[:16]
    record = {"version": 1, "id": item_id, "kind": kind, "text": text,
              "from": source.strip()[:120], "created": date.today().isoformat()}
    if suggested and suggested.strip():
        record["for"] = suggested.strip()[:80]
    folder = inbox()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{item_id}.json"
    # Write then rename, so a reader never sees half a file.
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("add", help="leave one thing in the inbox")
    one.add_argument("--kind", choices=sorted(LIMITS), required=True)
    one.add_argument("--text", required=True)
    one.add_argument("--for", dest="suggested", default=None)
    one.add_argument("--from", dest="source", required=True)
    args = parser.parse_args(argv)
    try:
        print(add(args.kind, args.text, args.suggested, args.source))
    except (OSError, ValueError) as exc:
        print(f"needs-a-home: not added: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

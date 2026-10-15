#!/usr/bin/env python3
"""
journal-metadata-extract.py — backward-compat shim.

Delegates to the extractor dispatcher at `extractors/_dispatcher.py` with
--type journal. Preserves the old CLI (--dry-run, --force, --year=YYYY)
so existing hooks, scheduled tasks, and shell scripts keep working.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "extractors"))

# Translate legacy --year=YYYY into dispatcher's --year YYYY
argv_out = [sys.argv[0]]
for arg in sys.argv[1:]:
    if arg.startswith("--year="):
        argv_out.extend(["--year", arg.split("=", 1)[1]])
    else:
        argv_out.append(arg)

# Force journal-only scope for backward compat
if "--type" not in argv_out:
    argv_out.extend(["--type", "journal"])

sys.argv = argv_out

import _dispatcher  # noqa: E402

if __name__ == "__main__":
    _dispatcher.main()

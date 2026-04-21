#!/usr/bin/env python3
"""
vault-metadata-extract.py — thin launcher that invokes the extractor dispatcher.

The real logic lives in `extractors/_dispatcher.py`. Each doc type has its own
extractor module in `extractors/<type>.py`. This wrapper just sets the import
path and hands off.

Usage:
  python3 vault-metadata-extract.py                   # all types, all files
  python3 vault-metadata-extract.py --dry-run         # preview, no writes
  python3 vault-metadata-extract.py --sample          # preview 1 file per type (cold-start preview)
  python3 vault-metadata-extract.py --sample 3        # preview 3 files per type
  python3 vault-metadata-extract.py --type journal    # only journals
  python3 vault-metadata-extract.py --force           # re-process tagged files
  python3 vault-metadata-extract.py --year 2026       # path filter
  python3 vault-metadata-extract.py --limit 20        # stop after N files
  python3 vault-metadata-extract.py --progress-every 100  # heartbeat every N files
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "extractors"))

import _dispatcher  # noqa: E402

if __name__ == "__main__":
    sys.exit(_dispatcher.main() or 0)

#!/usr/bin/env bash
# Negative-control test for check-sync-folder-machinery.py (the "machinery inside
# a cloud-synced folder" detector). A guard earns trust only by failing on the
# thing it catches: --self-test asserts it FLAGS a .git inside a synced root, an
# oversized synced dir, AND a Google Drive Mirror root (sync_type=1) that holds
# .git; and stays SILENT for a clean docs tree, a clean Mirror tree, and a
# non-Mirror (stream, sync_type!=1) root. MYC-705 added the Drive-Mirror-DB leg:
# Mirror roots live at a NATIVE path invisible to a ~/Library/CloudStorage walk,
# so the DriveFS roots DB is the only signal; read fail-open + immutable=1.
# Run: bash scripts/test-sync-folder-machinery-guard.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/../hooks/check-sync-folder-machinery.py" --self-test

#!/usr/bin/env bash
# CI integration wrapper — runs the cloud-sync detection negative-control suite
# (scripts/test-cloud-sync-guard.sh, incl. the iCloud Desktop & Documents
# realpath branch) as part of `scripts/ci.sh`. Thin: logic lives next to the
# script it exercises.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-cloud-sync-guard.sh"

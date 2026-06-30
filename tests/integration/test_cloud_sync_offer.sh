#!/usr/bin/env bash
# CI integration wrapper — runs the unconditional cloud-sync relocate-OFFER
# negative-control suite (scripts/test-cloud-sync-offer.sh, MYC-2360) as part of
# scripts/ci.sh. Thin: the logic lives next to the hook it exercises.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
exec bash "$ROOT/scripts/test-cloud-sync-offer.sh"

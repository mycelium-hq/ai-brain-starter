#!/usr/bin/env bash
# Negative-control test for Drive "Mirror" root detection in the SHARED
# detect_cloud_sync (MYC-1130). A guard earns trust only by failing on the thing
# it catches: a Google Drive for Desktop Mirror root (sync_type=1) sits at a
# NATIVE path invisible to the path markers, so the DriveFS roots DB is the only
# signal. This asserts (1) detect_cloud_sync flags a vault under a Mirror root,
# (2) a sync_type=2 (stream) root is NOT Mirror-flagged, (3) a missing DB
# fail-opens to None, and (4) the REAL SINK -- the INSTALL GUARD
# (scripts/check-cloud-sync.py) -- inherits it end-to-end via the
# WORKTREE_SAFETY_DRIVEFS_DB test seam. Pure stdlib (sqlite3 module, no CLI dep).
# Run: bash scripts/test-detect-cloud-sync-mirror.sh
set -u
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 - "$REPO_ROOT" <<'PY'
import os, sys, subprocess, sqlite3, tempfile
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "hooks"))
from _lib.worktree_safety import detect_cloud_sync

SCHEMA = (
    "CREATE TABLE roots (root_id INTEGER PRIMARY KEY, metadata BLOB, "
    "media_id TEXT NOT NULL, title TEXT NOT NULL, root_path TEXT NOT NULL, "
    "account_token TEXT NOT NULL, sync_type INTEGER NOT NULL, "
    "destination INTEGER NOT NULL, medium INTEGER NOT NULL, state INTEGER NOT NULL, "
    "one_shot BOOL NOT NULL, is_my_drive BOOL NOT NULL, doc_id TEXT NOT NULL, "
    "last_seen_absolute_path TEXT NOT NULL)"
)
INS = ("INSERT INTO roots (media_id,title,root_path,account_token,sync_type,"
       "destination,medium,state,one_shot,is_my_drive,doc_id,last_seen_absolute_path) "
       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)")

fails = 0
def check(label, cond):
    global fails
    print(f"[mirror-test] {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails += 1

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    mirror_root = tmp / "MirrorDrive"
    vault = mirror_root / "Brain"
    vault.mkdir(parents=True)
    stream_root = tmp / "StreamDrive"
    stream_vault = stream_root / "Brain"
    stream_vault.mkdir(parents=True)
    db = tmp / "drivefs_roots.db"
    con = sqlite3.connect(db)
    con.execute(SCHEMA)
    con.execute(INS, ("m", "t", str(mirror_root), "a", 1, 0, 0, 0, 0, 1, "d", str(mirror_root)))
    con.execute(INS, ("m2", "t2", str(stream_root), "a", 2, 0, 0, 0, 0, 1, "d2", str(stream_root)))
    con.commit()
    con.close()

    # 1. function: a vault under a sync_type=1 Mirror root -> flagged
    check("detect_cloud_sync flags Mirror vault",
          detect_cloud_sync(vault, _drivefs_db=db) == "Google Drive (Mirror)")
    # 2. sync_type=2 (stream) root -> NOT a Mirror finding
    check("sync_type=2 stream not Mirror-flagged",
          detect_cloud_sync(stream_vault, _drivefs_db=db) is None)
    # 3. fail-open: a missing DB -> None
    check("missing DB -> fail-open None",
          detect_cloud_sync(vault, _drivefs_db=tmp / "nope.db") is None)

    # 4. REAL SINK: the install guard (check-cloud-sync.py) inherits it via env
    guard = repo / "scripts" / "check-cloud-sync.py"
    env = dict(os.environ, WORKTREE_SAFETY_DRIVEFS_DB=str(db))
    out = subprocess.run([sys.executable, str(guard), "--porcelain", str(vault)],
                         capture_output=True, text=True, env=env).stdout.strip()
    check(f"install guard flags Mirror vault (got {out!r})", out.startswith("CLOUD_SYNC_RISK"))
    out2 = subprocess.run([sys.executable, str(guard), "--porcelain", str(stream_vault)],
                          capture_output=True, text=True, env=env).stdout.strip()
    check(f"install guard OK for stream root (got {out2!r})", out2.startswith("OK_LOCAL"))

print("[mirror-test] PASS" if fails == 0 else f"[mirror-test] FAIL ({fails})")
sys.exit(0 if fails == 0 else 1)
PY

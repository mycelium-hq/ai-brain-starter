# Cloud sync = documents, not machinery

Consumer cloud-sync folders (iCloud Drive, iCloud "Desktop & Documents", OneDrive, Dropbox, Box, Google Drive) sync DOCUMENTS well and choke on MACHINERY.

**Machinery** = `.git`, `node_modules`, `.venv`/`venv`, build output (`dist`/`build`/`target`/`.next`/`.gradle`), caches (`.smart-env`, `.smart-connections`, `.codegraph`), any directory with thousands of files.

**Why it breaks:** machinery rewrites files constantly (git rewrites `.git/index.lock` + pack objects every operation). The sync daemon (macOS `fileproviderd`/`bird`) can never converge → retry storm at 70-130% CPU for hours + silent repo/vault corruption. The phantom-error backlog grows into the hundreds of thousands and survives even after you move the churn out — until the sync DB is rebuilt.

## Rules

- Vault + repos + machinery live at a LOCAL home-root path (`~/dev`, `~/code`, `~/<vault>`). NEVER inside a sync folder. On macOS that means NOT `~/Desktop` or `~/Documents` when iCloud "Desktop & Documents" is on (both are synced); on Windows NOT inside `OneDrive\`.
- Cloud sync is NOT a backup. Back up with a versioned git remote + an encrypted backup whose restore you have ACTUALLY tested. A backup you have never restored is a hope, not a backup.
- Already on a sync path? Move it out, leave a symlink behind (the daemon follows the few-byte symlink, not the contents). Back up and verify the restore BEFORE relocating.
- Don't put a `.git/` inside a cloud mirror. Mirror documents only; keep the repo's `.git` at the local home-root path.

## Detect

```bash
# audit ANY machine for machinery in ANY synced root (broader than the per-session vault check)
python3 ~/.claude/skills/ai-brain-starter/hooks/check-sync-folder-machinery.py
```

The per-session `worktree-footprint-signal.py` only checks whether THE VAULT sits in a sync folder. This audit walks every synced root for machinery anywhere — side repos, build trees, caches — and is the one to run on a machine that already feels broken.

## Cure (daemon already pegged)

See `docs/CLOUD_SYNC.md` § "Already melting? Rebuild the sync DB": confirm with `fileproviderctl dump | grep -c itemNotFound` → remove the cause (audit above) → `fileproviderctl repair` → if it errors `Code=65` and counts don't move, rebuild via iCloud Drive off ("Keep a Copy") → reboot → on. Measure before/after; never claim fixed without the number dropping.

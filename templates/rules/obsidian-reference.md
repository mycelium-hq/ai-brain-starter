# Obsidian Reference Details

## Auto-reprioritization

Every time Claude adds or completes a task in a to-do file, run a lightweight priority check:
- **On add:** evaluate against your priority framework, check if it outranks existing P1s
- **On complete:** scan for newly unblocked tasks or approaching deadlines, bump priority if warranted, check if any other task became irrelevant
- Full reprioritization only at sprint transitions / weekly reviews
- Never rearrange file sections (Dataview views handle sort order)

## Obsidian sort config

`fileSortOrder` in `app.json` is the declared preference but `workspace.json` stores per-pane sort state that silently wins at runtime. Editing `app.json` alone does nothing if `workspace.json` has a stale `"sortOrder": "alphabetical"` under the `file-explorer` leaf. Since Obsidian rewrites `workspace.json` constantly while running, the only durable fix for folder/file sort order is the `custom-sort` plugin (not config edits).

## macOS folder mtime

Obsidian's built-in `byModifiedTime` uses each folder's own filesystem mtime. On macOS/APFS, a folder's mtime only updates when files are directly added/removed from it. Editing a nested file does NOT propagate up. Folders end up sorted by creation order regardless of the setting.

Fix: `custom-sort` plugin (SebastianMC/obsidian-custom-sort) with `sortspec.md` at vault root containing `> advanced recursive modified`. This traverses the full folder tree and sorts by the newest note anywhere inside. Note: the plugin installs with `suspended: true` by default. Needs one manual toggle click (ribbon icon or Command Palette: "Toggle custom sort on/off") to activate. Persists after that.

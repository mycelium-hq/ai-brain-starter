# Obsidian Plugin Integration

Three community plugins that extend what Claude Code can do with the vault. All configuration is on the Claude Code side (hooks, scripts, rules). You just install the plugins and leave them running.

---

## Local REST API

**Plugin**: Local REST API by Adam Coddington
**What it gives Claude Code**: The ability to open notes in Obsidian's UI, trigger Obsidian commands, and search via Dataview queries, all over HTTP.

### How Claude Code uses it

After creating or editing a vault file, Claude Code can open it in Obsidian automatically:
```bash
curl -sk -H "Authorization: Bearer $OBSIDIAN_REST_API_KEY" \
  -X POST "https://127.0.0.1:27124/open/path/to/note.md"
```

Other operations:
- **Search**: `GET /search/simple/?query=...` for full-text search
- **Read active file**: `GET /active/` to see what you have open
- **Execute commands**: `POST /commands/{id}/` to trigger any command palette action (reload dataview, refresh graph view)
- **Read vault structure**: `GET /vault/` to list files and folders

### Configuration

Store the API key in your shell profile (e.g. `~/.zshrc` or `~/.bashrc`) as `OBSIDIAN_REST_API_KEY`.

The API runs on `https://127.0.0.1:27124/` (localhost only, self-signed HTTPS). Claude Code uses `-k` flag with curl to accept the self-signed cert.

---

## Smart Connections (optional — not enabled by default)

**Plugin**: Smart Connections by Brian Petro
**What it gives Claude Code**: Semantic search (meaning-based, not just keyword/link-based) over the vault.

> ⚠️ **Large-vault warning.** Smart Connections is a heavy indexer — it builds SQLite-backed embeddings of every note and holds them in Obsidian's single renderer process. On a vault beyond ~5K notes, enabling it (alongside other heavy indexers) can exhaust the renderer's memory and crash Obsidian on open: a hard `EXC_BREAKPOINT (SIGTRAP)` V8 fatal, CPU pinned. For that reason it is **not in the default install**. If you enable it, **scope it to a subset of folders, not the whole vault.** graphify already covers explicit relationships; if you run the paid Mycelium runtime, that runtime is your semantic retrieval layer and Smart Connections is redundant. See "Large-vault plugin posture" below.

### How it complements graphify

| Dimension | graphify (graph.json) | Smart Connections |
|---|---|---|
| Search type | Structural (explicit links, entity co-occurrence) | Semantic (meaning similarity) |
| Best for | "What is connected to X?" | "What else talks about themes like X?" |
| Updates | On-demand (run /graphify) | Continuous (re-embeds on file change) |

Use both: graphify for navigating explicit relationships, Smart Connections for discovering notes you forgot to link.

### Recommended settings (if you opt in)

- **Scope it: include only a subset of folders, not the whole vault.** On a large vault this is the difference between stable and a renderer crash. Point it at the few folders where semantic discovery helps (e.g. `📝 Notes/`, `📓 Journals/`) rather than embedding everything.
- **Excluded folders**: `⚙️ Meta/scripts/`, `⚙️ Meta/Sessions/`, `⚙️ Meta/logs/`, `⚙️ Meta/Worktree Snapshots/`, `Archive/`, `.obsidian/`, `graphify-out/`
- **Minimum file length**: 50 characters (skip stubs)
- **Embedding model**: Local model (default) to avoid API costs
- **Re-embed interval**: "On file change" (switch to "On vault open" if you notice lag)
- **Max results in sidebar**: 20

### Watch out for

- **Renderer crash on large vaults.** Past ~5K notes the embedding index can exhaust Obsidian's renderer heap and crash the app on open (`EXC_BREAKPOINT`). Scoping it to a few folders is the fix; full crash recovery is under "Large-vault plugin posture" below.
- Initial embedding of a large vault (thousands of files) takes 30-60 minutes and spikes CPU. Run overnight.
- Pause the plugin during bulk vault operations (auto-wikilink, graphify multi-stage) to avoid hundreds of queued re-embeddings.

---

## Large-vault plugin posture

Obsidian renders your entire vault in a single Electron renderer process with a bounded JavaScript heap. Every "indexer" plugin you enable builds and holds an in-memory index of your notes. On a small vault that is invisible. Past roughly **5,000 notes**, several heavy indexers loading at once can exhaust the renderer heap and crash Obsidian on open — a hard `EXC_BREAKPOINT (SIGTRAP)` V8 fatal, CPU pinned while it builds the index.

As your vault grows:

- **Keep Dataview.** It is the lightest indexer and the dashboards/queries depend on it. A vault with Dataview alone opens fine at 13K+ notes.
- **Scope or disable the heavy indexers.** Smart Connections (SQLite-backed embeddings of every note) is the heaviest; Tasks (full-vault scan for checkboxes) compounds it. Scope them to a subset of folders or turn them off.
- **Machine-generated folders are already excluded** from Obsidian's index by the installer (`userIgnoreFilters` in `.obsidian/app.json` — session stubs, logs, worktree snapshots). That bounds machinery churn; it does not bound a plugin that indexes your real notes.
- **graphify already covers explicit relationships**, and if you run the paid Mycelium runtime, that runtime is your semantic retrieval layer — so Smart Connections is redundant in that setup.

### Recover from a renderer crash (Obsidian won't open)

1. Fully quit Obsidian.
2. Edit `<vault>/.obsidian/community-plugins.json` and set its contents to `[]`. This is "restricted mode" — no community plugins load.
3. Reopen Obsidian. It should open cleanly with core features only.
4. Re-add **Dataview only**, reopen, confirm it is stable.
5. Add the other plugins back **one at a time**, reopening between each, watching CPU in Activity Monitor (macOS) or Task Manager (Windows). The plugin that pins "Obsidian Helper (Renderer)" at 100%+ and crashes on open is the culprit — leave it off or scope it to fewer folders.

**Crash reports (macOS):** `~/Library/Logs/DiagnosticReports/*Obsidian*Renderer*.ips`. An `EXC_BREAKPOINT (SIGTRAP)` in a `*Renderer*` report is the renderer running out of memory — the signature of the heavy-indexer-on-a-large-vault crash. Run `bash scripts/diagnose.sh` (section 13) to flag repeated such crashes and reprint this remedy.

---

## Visual Graph Exploration (optional)

### Neo4j Browser (standalone, Cypher queries)

For power-user graph analysis with Cypher queries, use Neo4j directly (not as an Obsidian plugin).

**Setup:**
- Install Neo4j Desktop (neo4j.com/download) or Docker: `docker run -d --name neo4j-obsidian -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/your-password neo4j:latest`
- Export graph data: `python3 "⚙️ Meta/scripts/graph-to-neo4j.py"`
- Copy CSVs from `graphify-out/neo4j/` to Neo4j's `import/` directory
- Run `neo4j-import.cypher` in Neo4j Browser

**Example queries:**
```cypher
-- Find all notes within 3 hops of a concept
MATCH path = (n:Node {label: "Fear"})-[*1..3]-(connected)
RETURN path

-- Find bridge nodes
MATCH (n:Node)
WHERE size((n)--()) > 10
RETURN n.label, size((n)--()) AS connections
ORDER BY connections DESC LIMIT 20

-- Explore a community cluster
MATCH (n:Node {community: 42})-[r]-(m)
RETURN n, r, m
```

---

## In-vault search routing

When to use which search tool:

| Need | Tool | Why |
|------|------|-----|
| Keyword/exact match | `obsidian search` or Grep | Fastest for known terms |
| Structural neighbors ("what links to X?") | graphify graph.json query | Explicit relationships, communities |
| Semantic similarity ("what else talks about themes like X?") | Smart Connections sidebar in Obsidian *(optional, opt-in — see warning above)* | Finds conceptually related notes even without shared links or keywords |
| Visual graph exploration | Neo4j Browser | Cypher queries, visual cluster browsing. Requires CSVs imported via `graph-to-neo4j.py` |

---

## Installation checklist

- [ ] Local REST API: install from Community Plugins, set API key in shell profile, test with `curl -sk -H "Authorization: Bearer $OBSIDIAN_REST_API_KEY" "https://127.0.0.1:27124/"`
- [ ] Smart Connections *(optional, not in the default set — only on vaults under ~5K notes, or scoped to a few folders)*: install from Community Plugins, **scope it to a subset of folders**, configure exclusions, wait for initial embedding
- [ ] Neo4j: install when you want Cypher query power (requires Neo4j Desktop or Docker)

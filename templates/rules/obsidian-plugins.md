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

## Smart Connections

**Plugin**: Smart Connections by Brian Petro
**What it gives Claude Code**: Semantic search (meaning-based, not just keyword/link-based) over the entire vault.

### How it complements graphify

| Dimension | graphify (graph.json) | Smart Connections |
|---|---|---|
| Search type | Structural (explicit links, entity co-occurrence) | Semantic (meaning similarity) |
| Best for | "What is connected to X?" | "What else talks about themes like X?" |
| Updates | On-demand (run /graphify) | Continuous (re-embeds on file change) |

Use both: graphify for navigating explicit relationships, Smart Connections for discovering notes you forgot to link.

### Recommended settings

- **Excluded folders**: `⚙️ Meta/scripts/`, `Archive/`, `.obsidian/`, `graphify-out/`
- **Minimum file length**: 50 characters (skip stubs)
- **Embedding model**: Local model (default) to avoid API costs
- **Re-embed interval**: "On file change" (switch to "On vault open" if you notice lag)
- **Max results in sidebar**: 20

### Watch out for

- Initial embedding of a large vault (thousands of files) takes 30-60 minutes and spikes CPU. Run overnight.
- Pause the plugin during bulk vault operations (auto-wikilink, graphify multi-stage) to avoid hundreds of queued re-embeddings.

---

## Visual Graph Exploration (optional)

Two options for visually browsing the knowledge graph:

### Option A: Juggl (in-Obsidian, no external dependencies)

**Plugin**: Juggl by Emile van Krieken (successor to the deprecated Neo4j Graph View)

Juggl renders an interactive graph inside Obsidian using the vault's native link data. No Neo4j required. Good for browsing neighborhoods and exploring connections visually. Install from Community Plugins when you want it.

### Option B: Neo4j Browser (standalone, Cypher queries)

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
| Semantic similarity ("what else talks about themes like X?") | Smart Connections sidebar in Obsidian | Finds conceptually related notes even without shared links or keywords |
| Visual graph exploration | Neo4j Browser or Juggl in Obsidian | Cypher queries, visual cluster browsing. Neo4j requires CSVs imported via `graph-to-neo4j.py` |

---

## Installation checklist

- [ ] Local REST API: install from Community Plugins, set API key in shell profile, test with `curl -sk -H "Authorization: Bearer $OBSIDIAN_REST_API_KEY" "https://127.0.0.1:27124/"`
- [ ] Smart Connections: install from Community Plugins, configure exclusions, wait for initial embedding
- [ ] Juggl: install when you want visual graph browsing (no external dependencies)
- [ ] Neo4j: install when you want Cypher query power (requires Neo4j Desktop or Docker)

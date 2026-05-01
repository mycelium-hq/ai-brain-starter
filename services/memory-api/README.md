# memory-api

Read-only REST mirror of the graph-query MCP tools. Loads NetworkX knowledge
graphs from JSON files once at startup, then serves search, neighbor, path,
community, and subgraph queries over HTTP.

## Why this exists

The `graph-query` MCP server gives Claude Code direct access to your knowledge
graph. But anything that does not speak MCP (a workflow engine, a custom
dashboard, an LLM runtime that only speaks HTTP, a teammate's app) is locked
out of the same data. This service closes that gap with a thin REST surface
that mirrors the MCP tool set 1-to-1.

It is intentionally minimal:

- Read-only. No ingestion endpoints. The graph is built by the graphify
  pipeline; this service only serves it.
- In-memory NetworkX. No database, no Redis, no rate limiter, no multi-user.
- Single bearer token for all writes-of-nothing.
- Two scopes: `personal` and `team`. Both are optional at startup.

## Setup

```bash
cd services/memory-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env, set MEMORY_API_TOKEN and the graph paths
```

## Env vars

| Var | Required | Notes |
|---|---|---|
| `MEMORY_API_TOKEN` | yes | Bearer token clients send in `Authorization: Bearer ...`. Service returns 503 on every authed endpoint if unset. |
| `GRAPH_JSON_PATH_PERSONAL` | optional | Path to your personal graph.json. If missing, `scope=personal` returns 404. |
| `GRAPH_JSON_PATH_TEAM` | optional | Path to a team graph.json. Map this to whatever team vault you sync from (an Obsidian team vault, a Drive-shared vault, anything that produces a graph.json in NetworkX node-link format). |
| `MEMORY_API_PORT` | optional | Defaults to 8765 in the example. Pass to uvicorn explicitly. |

## Run

```bash
source .venv/bin/activate
set -a; source .env; set +a
uvicorn app:app --host 127.0.0.1 --port "${MEMORY_API_PORT:-8765}"
```

OpenAPI lives at `http://127.0.0.1:8765/openapi.json`. Interactive docs at
`http://127.0.0.1:8765/docs`.

## Endpoints

All scope-aware endpoints accept `?scope=personal` (default) or `?scope=team`.
All endpoints except `/healthz` require `Authorization: Bearer ${MEMORY_API_TOKEN}`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness check + which scopes loaded |
| GET | `/search?query=X&scope=&limit=20` | Substring match on node id and name |
| GET | `/node/{node_id}?scope=` | Full attributes + top neighbors |
| GET | `/neighbors/{node_id}?max_hops=1&limit=30&scope=` | BFS within max_hops |
| GET | `/path?source=X&target=Y&scope=` | Shortest path between two nodes |
| GET | `/community/{node_id}?limit=30&scope=` | Other nodes sharing the community attribute |
| POST | `/subgraph` | JSON body: concepts, max_hops, limit, scope |
| GET | `/top-nodes?n=20&scope=` | Most-connected nodes by degree |

## Curl examples

Health (no auth):

```bash
curl -sS http://127.0.0.1:8765/healthz
```

Search:

```bash
curl -sS -H "Authorization: Bearer $MEMORY_API_TOKEN" \
  "http://127.0.0.1:8765/search?query=fear&scope=personal&limit=10"
```

Node info:

```bash
curl -sS -H "Authorization: Bearer $MEMORY_API_TOKEN" \
  "http://127.0.0.1:8765/node/c_fear?scope=personal"
```

Neighbors at 2 hops:

```bash
curl -sS -H "Authorization: Bearer $MEMORY_API_TOKEN" \
  "http://127.0.0.1:8765/neighbors/c_fear?max_hops=2&limit=20&scope=personal"
```

Path between two concepts:

```bash
curl -sS -H "Authorization: Bearer $MEMORY_API_TOKEN" \
  "http://127.0.0.1:8765/path?source=c_fear&target=c_courage&scope=personal"
```

Subgraph from a list of seeds:

```bash
curl -sS -H "Authorization: Bearer $MEMORY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"concepts": ["c_fear", "c_courage"], "max_hops": 1, "limit": 40, "scope": "personal"}' \
  http://127.0.0.1:8765/subgraph
```

## Graph file format

The service expects NetworkX node-link JSON. Nodes have an `id` field
(prefixed `c_` by convention, e.g. `c_fear`); edges live under the `links`
key, not `edges`. This matches what `graphify` produces and what
`networkx.node_link_data` writes. If you generate graphs another way, run
them through `nx.node_link_data(graph)` before serializing.

## Failure modes

- Missing or wrong token → 401.
- Token not configured on the server → 503.
- Unknown scope name → 400.
- Scope path missing or unparseable at startup → that scope responds 404 at
  request time. The other scope still works.
- Unknown node id → 404.
- No path between source and target → 200 with `path: []` and `length: null`.

#!/usr/bin/env python3
"""Graph Query MCP: surgical queries against a NetworkX knowledge graph.

Loads graph.json (NetworkX node-link format, output of the /graphify skill)
once at startup. Answers targeted queries without requiring Claude to read the
full GRAPH_REPORT.md summary. Supports two scopes (e.g. personal vault and a
work/team vault) via the 'scope' parameter on every tool.

Setup:
  1. Copy to ~/.claude/graph-query-mcp/server.py
  2. Set env vars (or edit defaults below):
       GRAPH_JSON_PATH       path to primary graph.json
       SECOND_GRAPH_JSON_PATH  path to secondary graph.json (optional)
  3. Register in .mcp.json:
       "graph-query": {
         "type": "stdio",
         "command": "fastmcp",
         "args": ["run", "~/.claude/graph-query-mcp/server.py"]
       }
  4. Restart Claude Code.

Tools:
  search_nodes          - find nodes by name (fuzzy)
  get_neighbors         - get connected nodes up to N hops
  find_path             - shortest path between two concepts
  get_top_nodes         - most connected nodes by degree
  query_subgraph        - subgraph around a list of concepts
  get_node_info         - all metadata + top neighbors for a node
  get_community_members - all nodes in the same community as a given node

Note: node IDs may use a prefix (e.g. "c_fear") depending on how graphify
was run. Use search_nodes("fear") to discover the exact ID.
"""

import json
import os
from pathlib import Path
from typing import Optional

import networkx as nx
from fastmcp import FastMCP

# --- CONFIG (override via env vars) ------------------------------------------
PRIMARY_GRAPH = Path(
    os.environ.get("GRAPH_JSON_PATH", str(Path.home() / "vault" / "graphify-out" / "graph.json"))
)
SECONDARY_GRAPH = Path(
    os.environ.get("SECOND_GRAPH_JSON_PATH", str(Path.home() / "vault" / "work" / "graphify-out" / "graph.json"))
)

# Scope names: 'primary' (default) and 'secondary'
SCOPE_PATHS = {"primary": PRIMARY_GRAPH, "secondary": SECONDARY_GRAPH}

# --- GRAPH LOADING (cached at startup) ----------------------------------------
_graphs: dict = {}


def _load_graph(path: Path, name: str) -> Optional[nx.Graph]:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return nx.node_link_graph(data, edges="links")
    except Exception as e:
        print(f"[graph-query-mcp] Failed to load {name}: {e}")
        return None


def _get_graph(scope: str):
    """Return (graph, error_str). scope: 'primary' or 'secondary'."""
    if scope not in _graphs:
        path = SCOPE_PATHS.get(scope, PRIMARY_GRAPH)
        g = _load_graph(path, scope)
        if g is None:
            return None, f"Graph '{scope}' not found at {path}. Set GRAPH_JSON_PATH env var."
        _graphs[scope] = g
    return _graphs[scope], ""


def _fuzzy_match(G: nx.Graph, query: str, limit: int) -> list:
    q = query.lower()
    exact, starts, contains = [], [], []
    for n in G.nodes():
        nl = str(n).lower()
        if nl == q:
            exact.append(n)
        elif nl.startswith(q):
            starts.append(n)
        elif q in nl:
            contains.append(n)
    return (exact + starts + contains)[:limit]


def _node_summary(G: nx.Graph, node_id: str) -> dict:
    data = dict(G.nodes[node_id]) if node_id in G.nodes else {}
    degree = G.degree(node_id) if node_id in G.nodes else 0
    neighbors = list(G.neighbors(node_id)) if node_id in G.nodes else []
    return {
        "id": node_id,
        "degree": degree,
        "top_neighbors": sorted(neighbors, key=lambda n: G.degree(n), reverse=True)[:10],
        "metadata": {k: v for k, v in data.items() if k != "id"},
    }


# --- MCP SERVER ---------------------------------------------------------------
mcp = FastMCP("graph-query")


@mcp.tool()
def search_nodes(query: str, scope: str = "primary", limit: int = 20) -> str:
    """Find nodes by name (fuzzy match). scope: 'primary' or 'secondary'."""
    G, err = _get_graph(scope)
    if err:
        return err
    matches = _fuzzy_match(G, query, limit)
    if not matches:
        return f"No nodes found matching '{query}' in {scope} graph."
    rows = [f"{n} (degree={G.degree(n)})" for n in matches]
    return f"Found {len(matches)} match(es) for '{query}' in {scope} graph:\n" + "\n".join(rows)


@mcp.tool()
def get_neighbors(node_id: str, scope: str = "primary", max_hops: int = 1, limit: int = 30) -> str:
    """Get nodes connected to node_id within max_hops, sorted by degree."""
    G, err = _get_graph(scope)
    if err:
        return err
    if node_id not in G.nodes:
        matches = _fuzzy_match(G, node_id, 1)
        if not matches:
            return f"Node '{node_id}' not found in {scope} graph."
        node_id = matches[0]
    if max_hops == 1:
        neighbors = list(G.neighbors(node_id))
    else:
        ego = nx.ego_graph(G, node_id, radius=max_hops)
        neighbors = [n for n in ego.nodes() if n != node_id]
    top = sorted(neighbors, key=lambda n: G.degree(n), reverse=True)[:limit]
    rows = [f"{n} (degree={G.degree(n)})" for n in top]
    return (
        f"Node '{node_id}' (degree={G.degree(node_id)}) -- {len(neighbors)} neighbor(s) "
        f"within {max_hops} hop(s).\nTop {len(top)}:\n" + "\n".join(rows)
    )


@mcp.tool()
def find_path(source: str, target: str, scope: str = "primary") -> str:
    """Find shortest path between two concepts. Auto-fuzzy-matches node names."""
    G, err = _get_graph(scope)
    if err:
        return err
    s_matches = _fuzzy_match(G, source, 1)
    t_matches = _fuzzy_match(G, target, 1)
    if not s_matches:
        return f"Source '{source}' not found."
    if not t_matches:
        return f"Target '{target}' not found."
    s, t = s_matches[0], t_matches[0]
    try:
        path = nx.shortest_path(G, s, t)
        return f"Path from '{s}' to '{t}' ({len(path)-1} hops):\n" + " -> ".join(path)
    except nx.NetworkXNoPath:
        return f"No path between '{s}' and '{t}'."
    except nx.NodeNotFound as e:
        return f"Node not found: {e}"


@mcp.tool()
def get_top_nodes(scope: str = "primary", n: int = 20) -> str:
    """Get the most connected nodes by degree."""
    G, err = _get_graph(scope)
    if err:
        return err
    top = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:n]
    rows = [f"{i+1}. {node} (degree={deg})" for i, (node, deg) in enumerate(top)]
    return f"Top {n} nodes in {scope} graph ({G.number_of_nodes()} total):\n" + "\n".join(rows)


@mcp.tool()
def query_subgraph(concepts: list, scope: str = "primary", max_hops: int = 1, limit: int = 40) -> str:
    """Get the subgraph connecting a list of concepts."""
    G, err = _get_graph(scope)
    if err:
        return err
    resolved = []
    for c in concepts:
        matches = _fuzzy_match(G, c, 1)
        resolved.append(matches[0] if matches else c)
    subgraph_nodes = set()
    for node in resolved:
        if node in G.nodes:
            ego = nx.ego_graph(G, node, radius=max_hops)
            subgraph_nodes.update(ego.nodes())
    if not subgraph_nodes:
        return f"None of the concepts found in {scope} graph: {concepts}"
    sub = G.subgraph(subgraph_nodes)
    top_nodes = sorted(sub.degree(), key=lambda x: x[1], reverse=True)[:limit]
    rows = [f"{node} (degree={deg})" for node, deg in top_nodes]
    return (
        f"Subgraph for {resolved} ({max_hops} hop radius): "
        f"{sub.number_of_nodes()} nodes, {sub.number_of_edges()} edges.\n"
        f"Top connected nodes:\n" + "\n".join(rows)
    )


@mcp.tool()
def get_node_info(node_id: str, scope: str = "primary") -> str:
    """Get full metadata and top neighbors for a specific node."""
    G, err = _get_graph(scope)
    if err:
        return err
    matches = _fuzzy_match(G, node_id, 3)
    if not matches:
        return f"Node '{node_id}' not found in {scope} graph."
    node_id = matches[0]
    info = _node_summary(G, node_id)
    lines = [
        f"Node: {info['id']}",
        f"Degree: {info['degree']}",
        f"Top neighbors: {', '.join(info['top_neighbors'])}",
    ]
    if info["metadata"]:
        lines.append(f"Metadata: {json.dumps(info['metadata'], indent=2)}")
    if len(matches) > 1:
        lines.append(f"Also matched: {', '.join(matches[1:])}")
    return "\n".join(lines)


@mcp.tool()
def get_community_members(node_id: str, scope: str = "primary", limit: int = 30) -> str:
    """Get all nodes in the same community as the given node, sorted by degree."""
    G, err = _get_graph(scope)
    if err:
        return err
    matches = _fuzzy_match(G, node_id, 1)
    if not matches:
        return f"Node '{node_id}' not found in {scope} graph."
    node_id = matches[0]
    node_data = dict(G.nodes[node_id])
    community_id = node_data.get("community")
    if community_id is None:
        return f"Node '{node_id}' has no community attribute."
    members = [n for n in G.nodes() if G.nodes[n].get("community") == community_id]
    top = sorted(members, key=lambda n: G.degree(n), reverse=True)[:limit]
    rows = [f"{n} (degree={G.degree(n)})" for n in top]
    return (
        f"Community {community_id}: {len(members)} members. '{node_id}' is here.\n"
        f"Top {len(top)} by degree:\n" + "\n".join(rows)
    )


if __name__ == "__main__":
    for scope, path in SCOPE_PATHS.items():
        if path.exists():
            g = _load_graph(path, scope)
            if g:
                _graphs[scope] = g
                print(f"[graph-query-mcp] Loaded {scope}: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    mcp.run()

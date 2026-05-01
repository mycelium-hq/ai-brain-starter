"""Graph loader and query functions for memory-api.

Loads node-link JSON graph files into NetworkX once at startup. All query
functions take a scope name and return data structured for the REST endpoints.

Graph file convention (NetworkX node_link convention):
- Nodes carry an "id" with prefix c_ (e.g. c_fear).
- Edges live under the "links" key (NetworkX to_json default), not "edges".

Scopes are defined by env vars:
- GRAPH_JSON_PATH_PERSONAL → personal scope
- GRAPH_JSON_PATH_TEAM     → team scope

If a path is unset or the file is missing, the scope is simply not loaded;
endpoints respond 404 for that scope at request time.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import networkx as nx

logger = logging.getLogger("memory_api.graph_store")


SCOPE_ENV = {
    "personal": "GRAPH_JSON_PATH_PERSONAL",
    "team": "GRAPH_JSON_PATH_TEAM",
}

ALLOWED_SCOPES = tuple(SCOPE_ENV.keys())


# Module-level registry: scope name -> loaded graph (or None if not loaded).
_graphs: dict[str, nx.Graph | None] = {scope: None for scope in ALLOWED_SCOPES}


def _load_one(scope: str, path_str: str | None) -> nx.Graph | None:
    """Load a single graph file. Returns None on any failure."""
    if not path_str:
        logger.warning(
            "scope %s has no env var set (%s), skipping", scope, SCOPE_ENV[scope]
        )
        return None

    path = Path(path_str).expanduser()
    if not path.exists():
        logger.warning("scope %s graph file not found at %s, skipping", scope, path)
        return None

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("scope %s failed to parse %s: %s", scope, path, exc)
        return None

    # NetworkX 3.x node_link_graph defaults to edges="links" already, but be
    # explicit so we never depend on the default flipping under us.
    try:
        graph = nx.node_link_graph(data, edges="links")
    except (KeyError, TypeError) as exc:
        logger.warning("scope %s node_link_graph failed: %s", scope, exc)
        return None

    logger.info(
        "scope %s loaded from %s: %d nodes, %d edges",
        scope,
        path,
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )
    return graph


def load_graphs() -> list[str]:
    """Load all scopes from env. Returns the list of scope names that loaded."""
    loaded: list[str] = []
    for scope, env_name in SCOPE_ENV.items():
        path_str = os.environ.get(env_name)
        graph = _load_one(scope, path_str)
        _graphs[scope] = graph
        if graph is not None:
            loaded.append(scope)
    return loaded


def loaded_scopes() -> list[str]:
    """Return the list of scope names currently loaded."""
    return [scope for scope, graph in _graphs.items() if graph is not None]


def get_graph(scope: str) -> nx.Graph | None:
    """Return the loaded graph for a scope, or None if not loaded."""
    if scope not in ALLOWED_SCOPES:
        return None
    return _graphs.get(scope)


# Query helpers below. Each accepts a scope and returns plain Python primitives
# the FastAPI route can JSON-serialize. The route is responsible for the 404
# when the graph is not loaded; helpers raise LookupError or similar for
# node-not-found, the route turns those into 404s as well.


def _node_summary(graph: nx.Graph, node_id: str) -> dict[str, Any]:
    """Return a compact summary dict for a single node."""
    attrs = graph.nodes[node_id]
    return {
        "id": node_id,
        "name": attrs.get("name", node_id),
        "degree": graph.degree(node_id),
        "community": attrs.get("community"),
    }


def search(scope: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Substring match on lower-cased node id and name fields."""
    graph = get_graph(scope)
    if graph is None:
        raise LookupError(f"scope {scope} not loaded")

    if not query:
        return []

    needle = query.lower()
    hits: list[dict[str, Any]] = []
    for node_id, attrs in graph.nodes(data=True):
        nid_l = str(node_id).lower()
        name_l = str(attrs.get("name", "")).lower()
        if needle in nid_l or needle in name_l:
            hits.append(_node_summary(graph, node_id))
        if len(hits) >= limit:
            break
    # Sort the matches we collected by degree desc for determinism.
    hits.sort(key=lambda r: r["degree"], reverse=True)
    return hits


def get_node_info(scope: str, node_id: str, top_n: int = 10) -> dict[str, Any]:
    """Full metadata for a node plus its top neighbors by degree."""
    graph = get_graph(scope)
    if graph is None:
        raise LookupError(f"scope {scope} not loaded")
    if node_id not in graph:
        raise LookupError(f"node {node_id} not in scope {scope}")

    attrs = dict(graph.nodes[node_id])
    neighbors_raw = list(graph.neighbors(node_id))
    neighbors_summary = [_node_summary(graph, n) for n in neighbors_raw]
    neighbors_summary.sort(key=lambda r: r["degree"], reverse=True)
    return {
        "id": node_id,
        "attributes": attrs,
        "degree": graph.degree(node_id),
        "top_neighbors": neighbors_summary[:top_n],
    }


def get_neighbors(
    scope: str, node_id: str, max_hops: int = 1, limit: int = 30
) -> list[dict[str, Any]]:
    """Return nodes within max_hops of node_id, sorted by degree desc."""
    graph = get_graph(scope)
    if graph is None:
        raise LookupError(f"scope {scope} not loaded")
    if node_id not in graph:
        raise LookupError(f"node {node_id} not in scope {scope}")

    if max_hops < 1:
        max_hops = 1

    # BFS bounded by max_hops; exclude the seed itself.
    seen: dict[str, int] = {node_id: 0}
    frontier: list[str] = [node_id]
    for hop in range(1, max_hops + 1):
        next_frontier: list[str] = []
        for current in frontier:
            for neighbor in graph.neighbors(current):
                if neighbor in seen:
                    continue
                seen[neighbor] = hop
                next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    out: list[dict[str, Any]] = []
    for nid, hops in seen.items():
        if nid == node_id:
            continue
        summary = _node_summary(graph, nid)
        summary["hops"] = hops
        out.append(summary)
    out.sort(key=lambda r: r["degree"], reverse=True)
    return out[:limit]


def find_path(scope: str, source: str, target: str) -> dict[str, Any]:
    """Shortest path between source and target. Returns the node id list."""
    graph = get_graph(scope)
    if graph is None:
        raise LookupError(f"scope {scope} not loaded")
    if source not in graph:
        raise LookupError(f"node {source} not in scope {scope}")
    if target not in graph:
        raise LookupError(f"node {target} not in scope {scope}")

    try:
        path = nx.shortest_path(graph, source=source, target=target)
    except nx.NetworkXNoPath:
        return {"source": source, "target": target, "path": [], "length": None}

    nodes = [_node_summary(graph, nid) for nid in path]
    return {
        "source": source,
        "target": target,
        "path": nodes,
        "length": len(path) - 1,
    }


def get_community(scope: str, node_id: str, limit: int = 30) -> list[dict[str, Any]]:
    """Return all nodes sharing the same community attribute, sorted by degree."""
    graph = get_graph(scope)
    if graph is None:
        raise LookupError(f"scope {scope} not loaded")
    if node_id not in graph:
        raise LookupError(f"node {node_id} not in scope {scope}")

    community = graph.nodes[node_id].get("community")
    if community is None:
        return []

    members: list[dict[str, Any]] = []
    for nid, attrs in graph.nodes(data=True):
        if attrs.get("community") == community:
            members.append(_node_summary(graph, nid))
    members.sort(key=lambda r: r["degree"], reverse=True)
    return members[:limit]


def query_subgraph(
    scope: str, concepts: list[str], max_hops: int = 1, limit: int = 40
) -> dict[str, Any]:
    """Return the subgraph spanning the given concepts plus their neighborhoods."""
    graph = get_graph(scope)
    if graph is None:
        raise LookupError(f"scope {scope} not loaded")

    if max_hops < 1:
        max_hops = 1

    # Resolve concepts: keep only those present in the graph.
    seeds = [c for c in concepts if c in graph]
    missing = [c for c in concepts if c not in graph]

    seen: set[str] = set(seeds)
    frontier = list(seeds)
    for _ in range(max_hops):
        next_frontier: list[str] = []
        for current in frontier:
            for neighbor in graph.neighbors(current):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                next_frontier.append(neighbor)
                if len(seen) >= limit:
                    break
            if len(seen) >= limit:
                break
        frontier = next_frontier
        if not frontier or len(seen) >= limit:
            break

    sub = graph.subgraph(seen)
    nodes = [_node_summary(graph, nid) for nid in sub.nodes()]
    nodes.sort(key=lambda r: r["degree"], reverse=True)
    edges = [{"source": u, "target": v} for u, v in sub.edges()]
    return {
        "seeds": seeds,
        "missing": missing,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def get_top_nodes(scope: str, n: int = 20) -> list[dict[str, Any]]:
    """Return the n most-connected nodes in the graph, by degree desc."""
    graph = get_graph(scope)
    if graph is None:
        raise LookupError(f"scope {scope} not loaded")

    ranked = sorted(graph.degree(), key=lambda pair: pair[1], reverse=True)
    return [_node_summary(graph, nid) for nid, _ in ranked[:n]]

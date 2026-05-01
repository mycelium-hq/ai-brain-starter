"""memory-api: read-only REST mirror of the graph-query MCP tools.

Exposes a small FastAPI surface so external apps (a workflow engine, an LLM
runtime that does not speak MCP, a custom dashboard) can query the same
NetworkX-loaded knowledge graphs that the local MCP server uses. Read-only by
design. No ingestion endpoints.

Scopes:
- personal (default)
- team

Each scope is loaded from a JSON file pointed at by an env var
(GRAPH_JSON_PATH_PERSONAL, GRAPH_JSON_PATH_TEAM). If the file is missing the
service still starts cleanly; requests for that scope return 404.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from auth import require_bearer
import graph_store

logger = logging.getLogger("memory_api")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


app = FastAPI(
    title="memory-api",
    version="0.1.0",
    description=(
        "Read-only REST mirror of the graph-query MCP tools. Loads NetworkX "
        "graphs once at startup and serves search, neighbor, path, community, "
        "and subgraph queries over HTTP. Bearer-token auth on every endpoint "
        "except /healthz."
    ),
)


@app.on_event("startup")
def _startup_load_graphs() -> None:
    loaded = graph_store.load_graphs()
    logger.info("startup complete, loaded scopes: %s", loaded)


def _validate_scope(scope: str) -> str:
    if scope not in graph_store.ALLOWED_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"scope must be one of {list(graph_store.ALLOWED_SCOPES)}",
        )
    if graph_store.get_graph(scope) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scope {scope} not loaded",
        )
    return scope


def _lookup_to_404(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# Response and request models. Kept loose (Any) on attribute fields because
# graph node payloads vary by extractor.


class NodeSummary(BaseModel):
    id: str
    name: str
    degree: int
    community: Any | None = None


class NodeSummaryWithHops(NodeSummary):
    hops: int


class NodeInfo(BaseModel):
    id: str
    attributes: dict[str, Any]
    degree: int
    top_neighbors: list[NodeSummary]


class PathResult(BaseModel):
    source: str
    target: str
    path: list[NodeSummary]
    length: int | None


class SubgraphRequest(BaseModel):
    concepts: list[str] = Field(..., min_length=1)
    max_hops: int = Field(default=1, ge=1, le=4)
    limit: int = Field(default=40, ge=1, le=500)
    scope: str = "personal"


class SubgraphResult(BaseModel):
    seeds: list[str]
    missing: list[str]
    nodes: list[NodeSummary]
    edges: list[dict[str, str]]
    node_count: int
    edge_count: int


class HealthResponse(BaseModel):
    status: str
    graphs_loaded: list[str]


# Public health check. No auth, no scope validation.
@app.get("/healthz", response_model=HealthResponse, tags=["meta"])
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", graphs_loaded=graph_store.loaded_scopes())


@app.get("/search", response_model=list[NodeSummary], tags=["query"])
def search(
    query: str = Query(..., min_length=1),
    scope: str = Query("personal"),
    limit: int = Query(20, ge=1, le=200),
    _token: str = Depends(require_bearer),
) -> list[NodeSummary]:
    scope = _validate_scope(scope)
    try:
        rows = graph_store.search(scope, query, limit=limit)
    except LookupError as exc:
        raise _lookup_to_404(exc) from exc
    return [NodeSummary(**row) for row in rows]


@app.get("/node/{node_id}", response_model=NodeInfo, tags=["query"])
def node_info(
    node_id: str,
    scope: str = Query("personal"),
    _token: str = Depends(require_bearer),
) -> NodeInfo:
    scope = _validate_scope(scope)
    try:
        info = graph_store.get_node_info(scope, node_id)
    except LookupError as exc:
        raise _lookup_to_404(exc) from exc
    return NodeInfo(**info)


@app.get("/neighbors/{node_id}", response_model=list[NodeSummaryWithHops], tags=["query"])
def neighbors(
    node_id: str,
    scope: str = Query("personal"),
    max_hops: int = Query(1, ge=1, le=4),
    limit: int = Query(30, ge=1, le=500),
    _token: str = Depends(require_bearer),
) -> list[NodeSummaryWithHops]:
    scope = _validate_scope(scope)
    try:
        rows = graph_store.get_neighbors(scope, node_id, max_hops=max_hops, limit=limit)
    except LookupError as exc:
        raise _lookup_to_404(exc) from exc
    return [NodeSummaryWithHops(**row) for row in rows]


@app.get("/path", response_model=PathResult, tags=["query"])
def path(
    source: str = Query(...),
    target: str = Query(...),
    scope: str = Query("personal"),
    _token: str = Depends(require_bearer),
) -> PathResult:
    scope = _validate_scope(scope)
    try:
        result = graph_store.find_path(scope, source, target)
    except LookupError as exc:
        raise _lookup_to_404(exc) from exc
    return PathResult(**result)


@app.get("/community/{node_id}", response_model=list[NodeSummary], tags=["query"])
def community(
    node_id: str,
    scope: str = Query("personal"),
    limit: int = Query(30, ge=1, le=500),
    _token: str = Depends(require_bearer),
) -> list[NodeSummary]:
    scope = _validate_scope(scope)
    try:
        rows = graph_store.get_community(scope, node_id, limit=limit)
    except LookupError as exc:
        raise _lookup_to_404(exc) from exc
    return [NodeSummary(**row) for row in rows]


@app.post("/subgraph", response_model=SubgraphResult, tags=["query"])
def subgraph(
    body: SubgraphRequest,
    _token: str = Depends(require_bearer),
) -> SubgraphResult:
    scope = _validate_scope(body.scope)
    try:
        result = graph_store.query_subgraph(
            scope, body.concepts, max_hops=body.max_hops, limit=body.limit
        )
    except LookupError as exc:
        raise _lookup_to_404(exc) from exc
    return SubgraphResult(**result)


@app.get("/top-nodes", response_model=list[NodeSummary], tags=["query"])
def top_nodes(
    n: int = Query(20, ge=1, le=500),
    scope: str = Query("personal"),
    _token: str = Depends(require_bearer),
) -> list[NodeSummary]:
    scope = _validate_scope(scope)
    try:
        rows = graph_store.get_top_nodes(scope, n=n)
    except LookupError as exc:
        raise _lookup_to_404(exc) from exc
    return [NodeSummary(**row) for row in rows]

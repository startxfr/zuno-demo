"""Zuno RAG service: pgvector + PostgreSQL full-text hybrid search over the
`document_embeddings` table. See README.md for the API contract and the
schema assumption.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app import db, ogx_provider
from app.bindings import KnowledgeBindingRegistry
from app.schemas import SearchRequest, SearchResponse
from app.search import hybrid_search
from app.telemetry import init_telemetry, search_span

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("rag_service")

init_telemetry("rag-service")  # ADR-0029: traces/metrics to the shared OTel Collector

# ADR-0204 (WP-21): loaded once at import time, same as mcp-gateway's
# module-level PolicyStore/BindingRegistry - a load failure is recorded
# (load_error) and surfaced via /readyz, never raised here.
_knowledge_bindings = KnowledgeBindingRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eager per-domain connect: every domain the registry resolves gets a
    # connection attempt, but one domain's failure never blocks another's
    # (see app/db.py:connect_all) - do not crash-loop the pod just because
    # one domain's database/ExternalSecret isn't ready yet.
    await db.connect_all(_knowledge_bindings)
    yield
    await db.disconnect_all()


app = FastAPI(
    title="Zuno RAG Service",
    version="0.1.0",
    description="pgvector + full-text hybrid search supporting the Tekos agent's retrieve step (ADR-0018).",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    # ADR-0204: ready as soon as any one domain can serve a query - a
    # domain still waiting on its schema-apply/ExternalSecret must not
    # take rag-service out of rotation for every other domain that's fine.
    if await db.ping_any():
        return JSONResponse({"status": "ready", "domains": db.ready_domains()})
    return JSONResponse(
        {"status": "not-ready", "reason": "no domain database reachable", "domains": db.ready_domains()},
        status_code=503,
    )


@app.post("/v1/search", response_model=SearchResponse)
async def search(payload: SearchRequest) -> SearchResponse:
    # ADR-0322: RAG_PROVIDER=ogx is the only way this branch is ever taken
    # (see app/ogx_provider.py's module docstring) - the pgvector+full-text
    # provider below is untouched and remains the default. A database pool
    # is only required by the pgvector path - and only a service-wide 503
    # here (no domain at all is reachable); a specific requested domain
    # being down while others are up surfaces as hybrid_search's own
    # RuntimeError below (500, not 503 - this service IS ready, that one
    # domain just is not).
    use_ogx = ogx_provider.should_use_ogx()
    if not use_ogx and not db.any_ready():
        raise HTTPException(status_code=503, detail="no domain database connected")
    with search_span(payload.query, payload.top_k) as call:
        call.provider = "ogx" if use_ogx else "pgvector"
        try:
            if use_ogx:
                result = await ogx_provider.ogx_search(
                    payload.query,
                    payload.top_k,
                    product=payload.product,
                    version=payload.version,
                    language=payload.language,
                    caller_groups=payload.caller_groups,
                    domains=payload.domains,
                    technology=payload.technology,
                )
            else:
                result = await hybrid_search(
                    payload.query,
                    payload.top_k,
                    product=payload.product,
                    version=payload.version,
                    language=payload.language,
                    caller_groups=payload.caller_groups,
                    domains=payload.domains,
                    technology=payload.technology,
                )
        except Exception as exc:
            logger.error("search failed for query=%r (provider=%s): %s", payload.query, call.provider, exc)
            raise HTTPException(status_code=500, detail=f"search failed: {exc}") from exc
        call.result_count = len(result.get("results", []))
    return SearchResponse(**result)

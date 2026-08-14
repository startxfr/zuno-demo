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
from app.schemas import SearchRequest, SearchResponse
from app.search import hybrid_search
from app.telemetry import init_telemetry, search_span

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("rag_service")

init_telemetry("rag-service")  # ADR-0029: traces/metrics to the shared OTel Collector


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await db.connect()
    except Exception as exc:
        # Do not crash-loop the pod: /readyz will report not-ready and
        # /v1/search will return a clear 503 until the database is reachable.
        logger.error("startup: database connection failed, will report not-ready: %s", exc)
    yield
    await db.disconnect()


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
    if await db.ping():
        return JSONResponse({"status": "ready"})
    return JSONResponse({"status": "not-ready", "reason": "database unreachable"}, status_code=503)


@app.post("/v1/search", response_model=SearchResponse)
async def search(payload: SearchRequest) -> SearchResponse:
    # ADR-0322: RAG_PROVIDER=ogx is the only way this branch is ever taken
    # (see app/ogx_provider.py's module docstring) - the pgvector+full-text
    # provider below is untouched and remains the default. The database
    # pool is only required by the pgvector path.
    use_ogx = ogx_provider.should_use_ogx()
    if not use_ogx and db.get_pool() is None:
        raise HTTPException(status_code=503, detail="database not connected")
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
                )
            else:
                result = await hybrid_search(
                    payload.query,
                    payload.top_k,
                    product=payload.product,
                    version=payload.version,
                    language=payload.language,
                    caller_groups=payload.caller_groups,
                )
        except Exception as exc:
            logger.error("search failed for query=%r (provider=%s): %s", payload.query, call.provider, exc)
            raise HTTPException(status_code=500, detail=f"search failed: {exc}") from exc
        call.result_count = len(result.get("results", []))
    return SearchResponse(**result)

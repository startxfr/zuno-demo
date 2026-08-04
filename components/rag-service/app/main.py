"""Zuno RAG service: pgvector + PostgreSQL full-text hybrid search over the
`document_embeddings` table. See README.md for the API contract and the
schema assumption.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app import db
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
    if db.get_pool() is None:
        raise HTTPException(status_code=503, detail="database not connected")
    with search_span(payload.query, payload.top_k) as call:
        try:
            result = await hybrid_search(payload.query, payload.top_k)
        except Exception as exc:
            logger.error("search failed for query=%r: %s", payload.query, exc)
            raise HTTPException(status_code=500, detail=f"search failed: {exc}") from exc
        call.result_count = len(result.get("results", []))
    return SearchResponse(**result)

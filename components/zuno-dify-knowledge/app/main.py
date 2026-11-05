"""zuno-dify-knowledge: Dify External Knowledge API over the mcp-gateway (ADR-0599, WP-205).

    POST /retrieval   Dify's contract: {knowledge_id, query, retrieval_setting:{top_k, score_threshold}}
                      -> {"records": [{content, score, title, metadata}]}
    /healthz /readyz /metrics

The adapter holds no store and no copy. A retrieval is one ``tools/call knowledge.tech.search (alias search_technical_docs)`` through
the zuno-token-proxy, so the caller of the mcp-gateway is the ``dify`` experience client and the
group ACL (ADR-0568), the classification marking (ADR-0594) and the audit are the gateway's.
Dify sends only a static bearer: anything else is refused (Dify error codes 1001/1002). The probe
Dify makes when the API is registered (empty id and query) is answered ``200 {"records": []}``.
"""

from __future__ import annotations

import hmac
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app import metrics
from app.config import Settings

logger = logging.getLogger("zuno_dify_knowledge")

_CLASSIFICATION_WHEN_MISSING = "C2"  # as the gateway: fail closed


def _error(status: int, code: int, message: str) -> JSONResponse:
    return JSONResponse({"error_code": code, "error_msg": message}, status_code=status)


def _authorized(header: Optional[str], key: str) -> Optional[JSONResponse]:
    if not header or not header.lower().startswith("bearer ") or not header[7:].strip():
        return _error(403, 1001, "Invalid Authorization header format. Expected 'Bearer <api-key>' format.")
    if not hmac.compare_digest(header[7:].strip().encode(), key.encode()):
        return _error(403, 1002, "Authorization failed. Please check your API key.")
    return None


def _sse_json(body: str) -> Optional[Dict[str, Any]]:
    """The last JSON-RPC message of a ``text/event-stream`` body."""
    message = None
    for line in body.splitlines():
        if line.startswith("data:") and line[5:].strip():
            try:
                message = json.loads(line[5:].strip())
            except ValueError:
                continue
    return message


def _results(rpc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The tool's result rows, or ValueError with a reason that is safe to log."""
    if "error" in rpc:
        raise ValueError(f"json-rpc error: {rpc['error'].get('message', rpc['error'])}")
    result = rpc.get("result") or {}
    if result.get("isError"):
        text = " ".join(c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))
        raise ValueError(f"tool error: {text[:200]}")
    payload = result.get("structuredContent")
    if payload is None:
        # A gateway that only sends the text rendering. The text may carry the ADR-0594 marker, so parse leniently.
        for block in result.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    payload = json.loads(block["text"])
                    break
                except ValueError:
                    continue
    if not isinstance(payload, dict):
        # The gateway answers a plain sentence when nothing matched ("No result: ...").
        return []
    if "error" in payload:
        raise ValueError(f"tool error: {str(payload['error'])[:200]}")
    rows = payload.get("results") or []
    return [r for r in rows if isinstance(r, dict)]


def _record(row: Dict[str, Any]) -> Dict[str, Any]:
    classification = str(row.get("classification") or "").strip().upper() or _CLASSIFICATION_WHEN_MISSING
    return {
        "content": row.get("snippet") or "",
        "score": float(row.get("score") or 0.0),
        "title": row.get("title") or "",
        "metadata": {"source": row.get("source") or "", "classification": classification, "id": row.get("id") or ""},
    }


def create_app(settings: Settings, transport: Optional[httpx.AsyncBaseTransport] = None) -> FastAPI:
    client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(settings.upstream_timeout_s, connect=5.0))
    bases = settings.knowledge_bases or {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()

    app = FastAPI(title="zuno-dify-knowledge", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    async def search(query: str, top_k: int) -> List[Dict[str, Any]]:
        message = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": settings.tool_name, "arguments": {"query": query, "top_k": top_k}},
        }
        response = await client.post(
            settings.mcp_url, json=message,
            headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        )
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            rpc = _sse_json(response.text)
        else:
            rpc = response.json()
        if not isinstance(rpc, dict):
            raise ValueError("no json-rpc message in the answer")
        return _results(rpc)

    @app.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> Dict[str, str]:
        return {"status": "ready"}

    @app.get("/metrics")
    async def prometheus() -> Response:
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    @app.post("/retrieval")
    async def retrieval(request: Request) -> Response:
        refused = _authorized(request.headers.get("authorization"), settings.api_key)
        if refused is not None:
            metrics.inc("zuno_dify_knowledge_requests_total", code="403")
            return refused
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            metrics.inc("zuno_dify_knowledge_requests_total", code="400")
            return _error(400, 400, "The body must be a JSON object.")

        knowledge_id = str(body.get("knowledge_id") or "").strip()
        query = str(body.get("query") or "").strip()
        setting = body.get("retrieval_setting") if isinstance(body.get("retrieval_setting"), dict) else {}
        try:
            top_k = max(1, min(int(setting.get("top_k") or 5), settings.max_top_k))
            threshold = float(setting.get("score_threshold") or 0.0)
        except (TypeError, ValueError):
            metrics.inc("zuno_dify_knowledge_requests_total", code="400")
            return _error(400, 400, "retrieval_setting.top_k and score_threshold must be numbers.")

        # Dify's registration probe sends an empty id and an empty query: nothing to search, nothing wrong.
        if not knowledge_id and not query:
            metrics.inc("zuno_dify_knowledge_requests_total", code="200")
            return JSONResponse({"records": []})
        if knowledge_id not in bases:
            metrics.inc("zuno_dify_knowledge_requests_total", code="404")
            return _error(404, 2001, "The knowledge does not exist.")
        if not query:
            metrics.inc("zuno_dify_knowledge_requests_total", code="200")
            return JSONResponse({"records": []})

        try:
            rows = await search(query, top_k)
        except (httpx.HTTPError, ValueError) as exc:
            # Never a partial or an empty success: Dify would show "no knowledge" for an outage.
            logger.warning("search failed: %s", exc)
            metrics.inc("zuno_dify_knowledge_requests_total", code="502")
            return _error(502, 502, "The knowledge search is unavailable.")

        records = [r for r in (_record(row) for row in rows) if r["score"] >= threshold][:top_k]
        metrics.inc("zuno_dify_knowledge_requests_total", code="200")
        return JSONResponse({"records": records})

    return app


def get_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app(Settings.from_env())

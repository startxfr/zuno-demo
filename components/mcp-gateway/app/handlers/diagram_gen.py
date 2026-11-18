"""In-process handler for the ``generate_diagram`` MCP tool (ADR-0516,
capability ``diagram.generation.create``).

Renders Mermaid source into an SVG via ``components/diagram-render``, a
small in-cluster service (headless Chromium + `@mermaid-js/mermaid-cli`) -
never an external SaaS call, unlike ``image_gen.py``'s call to ai-gateway/
OVHcloud (ADR-0415). This was a deliberate choice: a free public rendering
API (mermaid.ink) was considered and rejected specifically because it
would send diagram *content* (which can describe internal system
topology, deal-specific details, etc.) outside the cluster with no
data-classification gate - inconsistent with how every other
externally-reaching call in this codebase treats that as a deliberate,
gated decision, not a default.

No classification override: unlike image_gen.py's fixed C2 ceiling (a
scoped exception letting C3 agents reach one specific external SaaS
boundary, ADR-0415 decision 3), rendering never leaves the cluster, so
there is no SaaS boundary to gate here at all - policies/tools/
tool-policy.yaml's own `min_classification: C1` for this tool is the
correct, permissive default, not a copy-pasted C2.

No identity forwarding to the render service: unlike ai-gateway (which
needs the caller's bearer token for identity/audit against an external
boundary), diagram-render has no per-caller decision to make - it just
renders text. The real authorization already happened one layer up (MCP
Gateway's own ADR-0011 policy.evaluate() against generate_diagram before
this handler ever runs); reaching diagram-render at all is already gated
by its own NetworkPolicy (ingress from mcp-gateway only).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from app import call_assertion

logger = logging.getLogger("mcp_gateway.handlers.diagram_gen")

DIAGRAM_RENDER_URL = os.getenv("DIAGRAM_RENDER_URL", "http://diagram-render.zuno-ai-run.svc:8080")
DIAGRAM_RENDER_TIMEOUT_SECONDS = float(os.getenv("DIAGRAM_RENDER_TIMEOUT_SECONDS", "35"))
# WP-250 lot 2: diagram-render verifies the gateway's Vault-Transit-signed call assertion
# (components/diagram-render/assertion.js), the same trust anchor as the MCP servers; the
# shared workload token is retired. NetworkPolicy stays the first layer.
DIAGRAM_RENDER_AUDIENCE = "diagram-render"
DIAGRAM_RENDER_TOOL = "render"


async def handle(
    arguments: Dict[str, Any],
    caller_sub: str,
    delegated_token: Optional[str] = None,
    bearer_token: str = "",
    caller_groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    mermaid_source = str(arguments.get("mermaid_source", "")).strip()
    if not mermaid_source:
        return {"error": "mermaid_source is required"}

    try:
        # In a thread: with the Vault Transit signer this is a network call.
        assertion = await asyncio.to_thread(
            call_assertion.mint, audience=DIAGRAM_RENDER_AUDIENCE, sub=caller_sub, tool=DIAGRAM_RENDER_TOOL,
        )
    except call_assertion.AssertionUnavailable as exc:
        logger.error("no call assertion for diagram-render: %s", exc)
        return {"error": "diagram generation failed: the gateway cannot sign the call assertion"}

    try:
        async with httpx.AsyncClient(timeout=DIAGRAM_RENDER_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{DIAGRAM_RENDER_URL}/render",
                json={"mermaid_source": mermaid_source},
                headers={"Authorization": f"Bearer {assertion}"},
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        # diagram-render's own 422 body carries a specific, actionable
        # reason (components/diagram-render/server.js's findRenderIssue -
        # e.g. "Mermaid could not parse this diagram (syntax error in the
        # mermaid_source)."). agent-runtime's _resolve_diagram_generation_
        # call makes one retry call offering the model this exact detail so
        # it can self-correct its mermaid_source - swallowing it into the
        # generic httpx exception string below silently broke that retry's
        # only feedback signal. Fall back to the generic message only if
        # the body isn't the JSON shape we expect.
        detail = None
        try:
            detail = exc.response.json().get("error")
        except (ValueError, AttributeError):
            pass
        logger.warning("diagram render call failed: %s", exc)
        return {"error": detail or f"diagram generation failed: {exc}"}
    except httpx.HTTPError as exc:
        logger.warning("diagram render call failed: %s", exc)
        return {"error": f"diagram generation failed: {exc}"}

    data_base64 = body["data_base64"]
    base64.b64decode(data_base64, validate=True)
    return {
        "data_base64": data_base64,
        "mime_type": body.get("mime_type", "image/svg+xml"),
        "alt": arguments.get("alt") or "Generated diagram",
        "provider": "mermaid-cli",
    }

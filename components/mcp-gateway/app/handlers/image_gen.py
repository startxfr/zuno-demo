"""In-process handler for the ``generate_image`` MCP tool (ADR-0415,
capability ``image.generation.create``).

Unlike every other handler in this package, this one is NOT a demo-mode
stub: ``components/ai-gateway`` (the platform's real, already-deployed
model gateway, ADR-0009) is reachable in-cluster, so this calls its real
``POST /v1/images/generations`` endpoint rather than returning synthetic
data.

Identity propagation (ADR-0013/ADR-0032/ADR-0033): forwards the caller's
own bearer token as Authorization, exactly like app/downstream.py's
_invoke_streamable_http does for streamable-http backends - ai-gateway's
own auth.validate_token expects the same Keycloak-issued JWT the end user
already has, not a service credential.

Classification override (ADR-0415 decision 3): this call ALWAYS declares
``X-Zuno-Data-Classification: C2``, regardless of the calling agent's own
ambient classification (arkos/cognos are C3 for everything else). This is
the one place that scoped override is enforced - nowhere else in the
generate_image call path inspects or forwards the caller's real
classification, so a future caller cannot accidentally widen it by passing
a different value through `arguments`.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("mcp_gateway.handlers.image_gen")

AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc:8080")
IMAGE_GENERATION_TIMEOUT_SECONDS = float(os.getenv("IMAGE_GENERATION_TIMEOUT_SECONDS", "60"))


async def handle(
    arguments: Dict[str, Any],
    caller_sub: str,
    delegated_token: Optional[str] = None,
    bearer_token: str = "",
) -> Dict[str, Any]:
    prompt = str(arguments.get("prompt", "")).strip()
    if not prompt:
        return {"error": "prompt is required"}
    negative_prompt = arguments.get("negative_prompt")

    try:
        async with httpx.AsyncClient(timeout=IMAGE_GENERATION_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{AI_GATEWAY_URL}/v1/images/generations",
                json={
                    "model": "stable-diffusion-xl",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                },
                headers={
                    "Authorization": f"Bearer {bearer_token}",
                    # ADR-0415: fixed ceiling for this one call type - see
                    # module docstring.
                    "X-Zuno-Data-Classification": "C2",
                },
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        logger.warning("image generation call to ai-gateway failed: %s", exc)
        return {"error": f"image generation failed: {exc}"}

    b64_json = body["data"][0]["b64_json"]
    base64.b64decode(b64_json, validate=True)
    return {
        "data_base64": b64_json,
        "mime_type": "image/png",
        "alt": prompt,
        "provider": body.get("zuno_provider", "ovhcloud-sdxl"),
    }

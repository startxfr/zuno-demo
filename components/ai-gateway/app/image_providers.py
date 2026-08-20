"""Image-generation provider factory (ADR-0415). Mirrors app/providers.py's
chat_model_for shape (a candidate + its config in, a client call out) but
calls OVHcloud's OpenAI-compatible images endpoint via the plain `openai`
SDK's Images API instead of building a LangChain BaseChatModel - image
generation is a single request/response call, not a chat turn, so there is
no LangGraph streaming/message-history concern to satisfy here the way
app/providers.py's factory has to.

Like app/providers.py, this module never sees a hardcoded key: it only
reads `os.environ` variable *names* declared in the routing file, never a
literal secret value (ADR-0024).
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict

from openai import OpenAI

from app.image_routing import ImageProviderCandidate

logger = logging.getLogger("ai_gateway.image_providers")


class ImageProviderFactoryError(RuntimeError):
    pass


@dataclass
class GeneratedImage:
    data_base64: str
    mime_type: str


def generate_image(
    candidate: ImageProviderCandidate,
    cfg: Dict[str, Any],
    prompt: str,
    negative_prompt: str | None = None,
) -> GeneratedImage:
    if candidate.name != "ovhcloud-sdxl":
        raise ImageProviderFactoryError(f"no image provider factory registered for '{candidate.name}'")

    # OVHcloud's OpenAI-compatible images endpoint does not support
    # negative_prompt (see docs/adr/0415-*.md) - folded into the prompt
    # itself rather than silently dropped, so a caller's intent still has
    # some effect instead of vanishing.
    effective_prompt = prompt if not negative_prompt else f"{prompt}\n(avoid: {negative_prompt})"

    client = OpenAI(
        base_url=cfg.get("endpoint", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"),
        api_key=os.getenv(cfg.get("api_key_env", "OVHCLOUD_API_KEY")),
        timeout=cfg.get("timeout_seconds", 60),
    )
    response = client.images.generate(
        model=cfg.get("model", "stable-diffusion-xl"),
        prompt=effective_prompt,
        size=cfg.get("size", "1024x1024"),
    )
    b64_json = response.data[0].b64_json
    # Sanity-decode rather than trust the field name blindly; a malformed
    # response should fail here, not silently reach the frontend as a
    # broken <img> src.
    base64.b64decode(b64_json, validate=True)
    return GeneratedImage(data_base64=b64_json, mime_type="image/png")

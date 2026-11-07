"""Readiness of the local models, as their controller reports it (ADR-0591).

With a model's pods gone, its llm-d router-scheduler keeps accepting requests
and holds them: measured on demo333 2026-11-02, every `*-maas` candidate of a
`Ready=False` LLMInferenceService waited its full 180 s timeout, never a 503.
The controller already knows: the `Ready` condition of the LLMInferenceService.

This module polls the LLMInferenceService list of the gateway's namespace with
the pod's ServiceAccount (read-only Role) and caches `Ready` per name. A local
provider names its model with `inference_service:` in provider-routing.yaml;
both members of a pair (direct and `*-maas`) name the same object.

Fail open, always (decision 2): no successful poll yet, a poll older than
`STALE_AFTER` polls, an object this cache has never seen, or a provider without
`inference_service` all mean "ready" - today's behaviour. The readiness source
can only remove a candidate it positively knows is not ready; it can never be
the reason a request is refused.

A poll, not a watch: one GET every few seconds is enough for a signal that
changes over minutes, and it needs no reconnect logic.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict, Optional

logger = logging.getLogger("ai_gateway.model_readiness")

API_SERVER = os.getenv("KUBERNETES_API_URL", "https://kubernetes.default.svc")
TOKEN_PATH = os.getenv("MODEL_READINESS_TOKEN_PATH", "/var/run/secrets/maas/token")
CA_PATH = os.getenv("MODEL_READINESS_CA_PATH", "/etc/kube-root-ca/ca.crt")
API_PATH = "/apis/serving.kserve.io/v1alpha2/namespaces/{ns}/llminferenceservices"
STALE_AFTER = 3  # polls


def _enabled() -> bool:
    return os.getenv("MODEL_READINESS_ENABLED", "false").strip().lower() == "true"


def _interval() -> float:
    return float(os.getenv("MODEL_READINESS_POLL_SECONDS", "10"))


def _namespace() -> str:
    return os.getenv("MODEL_READINESS_NAMESPACE", "zuno-ai-run")


def ready_from_status(obj: dict) -> Optional[bool]:
    """`Ready` condition of one LLMInferenceService; None when absent."""
    for cond in ((obj or {}).get("status") or {}).get("conditions") or []:
        if cond.get("type") == "Ready":
            return str(cond.get("status")) == "True"
    return None


class ModelReadiness:
    def __init__(self) -> None:
        self._ready: Dict[str, bool] = {}
        self._last_success: float = 0.0

    def update(self, items: list, now: Optional[float] = None) -> None:
        ready: Dict[str, bool] = {}
        for obj in items or []:
            name = ((obj or {}).get("metadata") or {}).get("name")
            state = ready_from_status(obj)
            if name and state is not None:
                ready[name] = state
        self._ready = ready
        self._last_success = time.monotonic() if now is None else now

    def is_ready(self, inference_service: Optional[str], now: Optional[float] = None) -> bool:
        if not inference_service or not _enabled():
            return True
        now = time.monotonic() if now is None else now
        if not self._last_success or now - self._last_success > STALE_AFTER * _interval():
            return True  # never polled, or the source went silent: fail open
        return self._ready.get(inference_service, True)

    def snapshot(self) -> Dict[str, bool]:
        return dict(self._ready)

    async def poll_once(self) -> None:
        import httpx

        with open(TOKEN_PATH) as fh:  # kubelet rotates it in place: read per poll
            token = fh.read().strip()
        from app.tls import verify_for

        verify = verify_for(CA_PATH) if os.path.exists(CA_PATH) else True
        async with httpx.AsyncClient(verify=verify, timeout=5.0) as client:
            resp = await client.get(
                API_SERVER + API_PATH.format(ns=_namespace()),
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            self.update(resp.json().get("items") or [])

    async def run(self) -> None:
        """Background loop. A failed poll is logged and leaves the cache to go
        stale, which fails open; it never raises."""
        failing = False
        while True:
            try:
                await self.poll_once()
                if failing:
                    logger.info("model readiness: polls recovered: %s", self.snapshot())
                failing = False
            except Exception as exc:  # noqa: BLE001 - never take the gateway down
                if not failing:
                    logger.warning(
                        "model readiness poll failed (%s: %s); treating models as ready",
                        type(exc).__name__, exc,
                    )
                failing = True
            await asyncio.sleep(_interval())


readiness = ModelReadiness()

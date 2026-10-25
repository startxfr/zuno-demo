"""Reload the provider routing files when their mounted copy changes.

provider-routing.yaml and image-provider-routing.yaml reach the pod as a
ConfigMap volume owned by another Argo CD Application (zuno-llm-d1), so a
change to them never rolls this Deployment. The kubelet does update the
mounted files, but the tables only read them at startup. On 2026-10-25,
gpt-oss-20b went to 131072 tokens while the gateway kept refusing prompts
above the old 32768 until /admin/reload-routing was called by hand.

RoutingWatcher compares each file's sha256 every
ROUTING_RELOAD_INTERVAL_SECONDS (default 30, 0 disables) and reloads the
table whose file changed. A file that cannot be read or parsed keeps the
table as it is: the tables fall back to an empty, local-only config on a
parse error, which is right at startup and wrong mid-flight.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Callable, Dict, List, Optional

import yaml

logger = logging.getLogger("ai_gateway.routing_watch")

ROUTING_RELOAD_INTERVAL_SECONDS = float(os.getenv("ROUTING_RELOAD_INTERVAL_SECONDS", "30"))


def _digest(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


class RoutingWatcher:
    """Watches files and calls each one's reload callable when its content changes."""

    def __init__(self, reloaders: Dict[str, Callable[[], None]]):
        self._reloaders = reloaders
        self._digests = {path: _digest(path) for path in reloaders}

    def check_once(self) -> List[str]:
        """Reload every file whose content changed and still parses; return the reloaded paths."""
        reloaded = []
        for path, reload in self._reloaders.items():
            digest = _digest(path)
            if digest is None or digest == self._digests[path]:
                continue
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    doc = yaml.safe_load(fh)
                if not isinstance(doc, dict):
                    raise ValueError("top level is not a mapping")
            except Exception as exc:  # noqa: BLE001
                logger.error("routing file %s changed but is invalid, keeping the loaded table: %s", path, exc)
                self._digests[path] = digest  # do not log the same bad content every tick
                continue
            reload()
            self._digests[path] = digest
            reloaded.append(path)
            logger.info("routing reloaded from %s (sha256 %s)", path, digest[:12])
        return reloaded

    async def run(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                self.check_once()
            except Exception:  # noqa: BLE001 - the watcher must never die
                logger.exception("routing watch tick failed")

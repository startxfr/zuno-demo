"""Generic pattern-matching action for the zuno observe-only rails.

ADR-0540/WP-120. This file deliberately contains NO policy: every pattern
comes from config.yaml's custom_data.zuno_patterns. Adding, removing or
tuning a detection class is a YAML edit that ArgoCD syncs - it never
touches this code, and never rebuilds an image.

The action returns the list of matched detection names. It cannot block:
the calling flow in rails.co only records, and the client
(components/agent-runtime/app/clients/guardrails_client.py) is
fire-and-forget after the response has already been delivered. Observe-only
is enforced in three independent places on purpose - ADR-0534 makes the
observe-to-block transition a separate, later decision.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from nemoguardrails.actions import action

log = logging.getLogger(__name__)

# Compiled once per process, keyed by the pattern string so a config
# reload picks up edits without a restart leaking the old set.
_COMPILED: Dict[str, "re.Pattern[str]"] = {}


def _compile(pattern: str) -> "re.Pattern[str] | None":
    cached = _COMPILED.get(pattern)
    if cached is not None:
        return cached
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        # A bad pattern must degrade to "this class never fires", never
        # take the whole rail down: one malformed YAML entry would
        # otherwise silently disable every detection after it.
        log.warning("zuno rails: skipping uncompilable pattern %r: %s", pattern, exc)
        return None
    _COMPILED[pattern] = compiled
    return compiled


@action(name="zuno_scan")
async def zuno_scan(text: str = "", config: Any = None) -> List[str]:
    """Return the names of every pattern matching `text`.

    `config` is the RailsConfig NeMo injects; custom_data carries the
    policy. An empty or missing policy returns [] rather than raising -
    a misconfigured ConfigMap must not break the exchange.
    """
    if not text:
        return []
    custom = getattr(config, "custom_data", None) or {}
    patterns = custom.get("zuno_patterns") or []
    hits: List[str] = []
    for entry in patterns:
        name = (entry or {}).get("name")
        pattern = (entry or {}).get("pattern")
        if not name or not pattern:
            continue
        compiled = _compile(pattern)
        if compiled is not None and compiled.search(text):
            hits.append(name)
    return hits

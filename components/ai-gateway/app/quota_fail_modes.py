"""Per-class quota fail modes (ADR-0511, ADR-0570 clause 7, WP-157 D6).

Reads app/quota_fail_modes.yaml - GENERATED from the release's
policies/quotas/quota-policy.yaml by platform/okf/generate_quota_enforcement.py,
so the policy file stays the only source of fail modes once
app/quota_budgets.yaml and app/quota.py are gone.

Used only when QUOTA_FAIL_MODES_ENFORCED=true (chart value
maasAdapter.failModes.enabled, default false); with it off, app/main.py
behaves exactly as before. With it on:

- ADR-0570 clause 7: the direct-Service sibling of a via_maas local
  candidate (same model, reached without MaaS) bypasses MaaS's quota, so it
  serves only classes whose fail_mode is `open` (today `standard`); for a
  `closed` class it is skipped.
- A token-budget config fault in app/quota.py (its class lookup denies every
  class, `standard` included - the WP-157 inventory's finding 2, contrary to
  quota.py's own docstring) lets an `open` class through. quota.py itself is
  left untouched; it goes with the ledger.

A class missing from the file, or a file that cannot be read, is `closed`:
ADR-0511's default.
"""
from __future__ import annotations

import logging
import os
import pathlib
from typing import Dict, Optional

import yaml

logger = logging.getLogger("zuno.ai-gateway.quota_fail_modes")

FAIL_MODES_PATH = pathlib.Path(__file__).resolve().parent / "quota_fail_modes.yaml"


def enforced() -> bool:
    """Read per call, so a test (or a restart with the env set) flips it."""
    return os.getenv("QUOTA_FAIL_MODES_ENFORCED", "false").strip().lower() == "true"


class FailModes:
    def __init__(self, modes: Optional[Dict[str, str]] = None, path: pathlib.Path = FAIL_MODES_PATH):
        self.error: Optional[str] = None
        if modes is None:
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                modes = {str(k): str(v) for k, v in (doc.get("classes") or {}).items()}
            except Exception as exc:  # noqa: BLE001 - unreadable = every class closed
                logger.error("quota fail modes unreadable (%s) - every class is closed", exc)
                self.error = str(exc)
                modes = {}
        self._modes = modes

    def fail_open(self, quota_class: str) -> bool:
        """Whether a class rides through an enforcement fault (ADR-0511:
        default closed; `open` only when the policy file says so)."""
        return self._modes.get(quota_class) == "open"


fail_modes = FailModes()

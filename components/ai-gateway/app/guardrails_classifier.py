"""ADR-0602 clause 8 (WP-225 lot A): a model-based classifier next to the regular expressions.

Off by default. The regular expressions of app/guardrails.py catch the phrases
they name and nothing else; a classifier model (a prompt-injection or a hate,
abuse and profanity detector) catches paraphrases. No model is wired here: the
gateway calls whatever detector the chart names, through one interface.

The interface is `Classifier.classify(contents) -> detections`, one call for a
list of texts, returning detections in the shape app/guardrails.py already
uses (`content_index`, `detection`, `detection_type`, `score`). It raises on an
outage; app/guardrails.py turns that into the `unavailable` outcome, so a
classifier outage is treated exactly like a detector outage (fail closed in
`block` from GUARDRAILS_FAIL_CLOSED_FROM up, open below).

Shipped implementation, `detectors-api`: the FMS Guardrails detector API that
TrustyAI's Hugging Face detector runtime serves (`POST /api/v1/text/contents`,
header `detector-id`, body `{"contents": [...], "detector_params": {}}`, reply one
list of `{start, end, text, detection, detection_type, score}` per content). Any
model served that way plugs in by URL and detector id. A detection below
GUARDRAILS_CLASSIFIER_THRESHOLD is dropped; matched text is never kept.

Configuration (chart `guardrails.classifier`), read per call:
    GUARDRAILS_CLASSIFIER            "" (off) or "detectors-api"
    GUARDRAILS_CLASSIFIER_URL        base URL of the detector Service
    GUARDRAILS_CLASSIFIER_DETECTOR_ID  the `detector-id` header value
    GUARDRAILS_CLASSIFIER_THRESHOLD  minimum score kept (default 0.5)

The classifier joins an evaluation; it does not open one: with no regex/NeMo
backend URL the guardrail mode is `off` and the classifier is not called.

Another implementation (an in-process model, a different API) registers itself
with `register("name", factory)` and is selected by GUARDRAILS_CLASSIFIER=name.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Protocol

import httpx

logger = logging.getLogger("ai_gateway.guardrails_classifier")


class Classifier(Protocol):
    name: str

    async def classify(self, contents: List[str]) -> List[Dict[str, Any]]:
        """Detections for `contents` (index into that list). Raises on an outage."""
        ...


def _threshold() -> float:
    raw = os.getenv("GUARDRAILS_CLASSIFIER_THRESHOLD", "0.5")
    try:
        return float(raw)
    except ValueError:
        logger.error("GUARDRAILS_CLASSIFIER_THRESHOLD=%r is not a number; using 0.5", raw)
        return 0.5


class DetectorsApiClassifier:
    """A classifier model behind the FMS Guardrails detector API."""

    name = "detectors-api"

    def __init__(self, url: str, detector_id: str, threshold: float, timeout: float):
        self.url = url.rstrip("/")
        self.detector_id = detector_id
        self.threshold = threshold
        self.timeout = timeout

    async def classify(self, contents: List[str]) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.url}/api/v1/text/contents",
                json={"contents": contents, "detector_params": {}},
                headers={"detector-id": self.detector_id},
            )
        resp.raise_for_status()
        out: List[Dict[str, Any]] = []
        for index, dets in enumerate(resp.json()):
            for d in dets if isinstance(dets, list) else []:
                score = d.get("score")
                if isinstance(score, (int, float)) and score < self.threshold:
                    continue
                out.append({
                    "content_index": index,
                    # Prefixed so the detection names of the regexes and of the
                    # model stay apart on the zuno_guardrails_detections series.
                    "detection": f"classifier:{d.get('detection') or self.detector_id}",
                    "detection_type": d.get("detection_type") or "classifier",
                    "score": score,
                })
        return out


class MisconfiguredClassifier:
    """Stands for a classifier that was asked for but cannot run (a missing URL or
    detector id, an unknown type). Every call raises, so the evaluation counts as
    unavailable: `block` fails closed from GUARDRAILS_FAIL_CLOSED_FROM up instead of
    silently running without the classifier the deployment asked for."""

    def __init__(self, reason: str):
        self.name = "misconfigured"
        self.reason = reason

    async def classify(self, contents: List[str]) -> List[Dict[str, Any]]:
        raise RuntimeError(f"guardrails classifier misconfigured: {self.reason}")


def _detectors_api() -> Optional[Classifier]:
    url = os.getenv("GUARDRAILS_CLASSIFIER_URL", "").strip()
    detector_id = os.getenv("GUARDRAILS_CLASSIFIER_DETECTOR_ID", "").strip()
    if not url or not detector_id:
        logger.error("GUARDRAILS_CLASSIFIER=detectors-api needs GUARDRAILS_CLASSIFIER_URL and "
                     "GUARDRAILS_CLASSIFIER_DETECTOR_ID; every evaluation counts as unavailable")
        return MisconfiguredClassifier("detectors-api needs a URL and a detector id")
    timeout = float(os.getenv("GUARDRAILS_TIMEOUT_SECONDS", "10"))
    return DetectorsApiClassifier(url, detector_id, _threshold(), timeout)


_FACTORIES: Dict[str, Callable[[], Optional[Classifier]]] = {"detectors-api": _detectors_api}


def register(name: str, factory: Callable[[], Optional[Classifier]]) -> None:
    """Add an implementation, selected by GUARDRAILS_CLASSIFIER=<name>."""
    _FACTORIES[name] = factory


def active() -> Optional[Classifier]:
    """The configured classifier; None when off (the default); a
    MisconfiguredClassifier (which raises) when asked for but unusable."""
    name = os.getenv("GUARDRAILS_CLASSIFIER", "").strip().lower()
    if not name or name == "off":
        return None
    factory = _FACTORIES.get(name)
    if factory is None:
        logger.error("unknown GUARDRAILS_CLASSIFIER=%r; every evaluation counts as unavailable", name)
        return MisconfiguredClassifier(f"unknown type {name!r}")
    return factory()

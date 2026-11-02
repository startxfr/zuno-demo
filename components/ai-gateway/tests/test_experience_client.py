"""ADR-0587 (WP-179): the experience client (the token's `azp`) reaches the
`model_call` span and the model and guardrails counters as a bounded `client`
label, so one dashboard compares UnifAI, Open WebUI and OpenClaw on the same
users, models and guardrails.

Run from this directory:

    python3 tests/test_experience_client.py
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from app import telemetry  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402

_CLIENTS = {"EXPERIENCE_CLIENTS": "unifai, open-webui, openclaw-*"}


class _Recorder:
    """Stands in for an OTel counter or histogram: keeps the attributes."""

    def __init__(self):
        self.points = []

    def add(self, value, attrs):
        self.points.append(dict(attrs))

    record = add


def _identity(azp):
    claims = {"sub": "u-1"}
    if azp is not None:
        claims["azp"] = azp
    return CallerIdentity(sub="u-1", groups=["sales"], raw_claims=claims, token="t")


def test_client_label_is_bounded_by_the_declared_clients() -> None:
    with mock.patch.dict(os.environ, _CLIENTS):
        assert telemetry.client_label("unifai") == "unifai"
        assert telemetry.client_label("open-webui") == "open-webui"
        assert telemetry.client_label("openclaw-sales-01") == "openclaw-sales-01"
        assert telemetry.client_label("some-other-client") == "other"
        assert telemetry.client_label("open-webui-2") == "other"
        assert telemetry.client_label("") == ""
        assert telemetry.client_label(None) == ""


def test_without_declared_clients_every_client_is_other() -> None:
    with mock.patch.dict(os.environ, {"EXPERIENCE_CLIENTS": ""}):
        assert telemetry.client_label("unifai") == "other"


def test_identity_client_is_the_azp_claim() -> None:
    assert _identity("open-webui").client == "open-webui"
    assert _identity(None).client == ""


def _span_and_counters(azp):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    calls, durations = _Recorder(), _Recorder()
    token = telemetry._caller_client.set("")
    try:
        with mock.patch.dict(os.environ, _CLIENTS), \
             mock.patch.object(telemetry, "_tracer", provider.get_tracer("test")), \
             mock.patch.object(telemetry, "_model_call_counter", calls), \
             mock.patch.object(telemetry, "_model_call_duration_histogram", durations):
            telemetry.set_caller_client(azp)
            with telemetry.model_call_span("local", "qwen3.5-9b", "C1", caller_sub="u-1", groups=["sales"]):
                pass
    finally:
        telemetry._caller_client.reset(token)
    spans = exporter.get_finished_spans()
    assert len(spans) == 1, spans
    return spans[0], calls.points, durations.points


def test_model_call_carries_the_client_on_span_and_counters() -> None:
    span, calls, durations = _span_and_counters("openclaw-sales-01")
    assert span.attributes.get("zuno.client") == "openclaw-sales-01"
    assert [p["client"] for p in calls] == ["openclaw-sales-01"]
    assert [p["client"] for p in durations] == ["openclaw-sales-01"]


def test_an_undeclared_client_is_counted_as_other() -> None:
    span, calls, _ = _span_and_counters("rogue-ui")
    assert span.attributes.get("zuno.client") == "other"
    assert calls[0]["client"] == "other"


def test_without_a_client_the_label_is_empty_and_the_span_attribute_absent() -> None:
    span, calls, _ = _span_and_counters(None)
    assert "zuno.client" not in span.attributes
    assert calls[0]["client"] == ""


def test_guardrails_counters_carry_the_client() -> None:
    evals, detections = _Recorder(), _Recorder()
    token = telemetry._caller_client.set("")
    try:
        with mock.patch.dict(os.environ, _CLIENTS), \
             mock.patch.object(telemetry, "_guardrails_eval_counter", evals), \
             mock.patch.object(telemetry, "_guardrails_detection_counter", detections):
            telemetry.set_caller_client("open-webui")
            telemetry.record_guardrails_evaluation("open-webui", "detected", ["pii"])
    finally:
        telemetry._caller_client.reset(token)
    assert evals.points == [{"agent": "open-webui", "outcome": "detected", "client": "open-webui"}]
    assert detections.points == [{"agent": "open-webui", "detection": "pii", "client": "open-webui"}]


def test_the_client_set_in_a_handler_reaches_the_span() -> None:
    """The handler sets the client after `validate_token` (a sync dependency,
    run in a worker thread, could not); only a request through FastAPI proves
    the ContextVar reaches model_call_span."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    api = FastAPI()

    @api.post("/probe")
    async def probe():
        telemetry.set_caller_client(_identity("open-webui").client)
        with telemetry.model_call_span("local", "qwen3.5-9b", "C1"):
            return {"ok": True}

    with mock.patch.dict(os.environ, _CLIENTS), \
         mock.patch.object(telemetry, "_tracer", provider.get_tracer("test")):
        assert TestClient(api).post("/probe").status_code == 200
    spans = exporter.get_finished_spans()
    assert len(spans) == 1, spans
    assert spans[0].attributes.get("zuno.client") == "open-webui"


TESTS = [
    test_client_label_is_bounded_by_the_declared_clients,
    test_without_declared_clients_every_client_is_other,
    test_identity_client_is_the_azp_claim,
    test_model_call_carries_the_client_on_span_and_counters,
    test_an_undeclared_client_is_counted_as_other,
    test_without_a_client_the_label_is_empty_and_the_span_attribute_absent,
    test_guardrails_counters_carry_the_client,
    test_the_client_set_in_a_handler_reaches_the_span,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

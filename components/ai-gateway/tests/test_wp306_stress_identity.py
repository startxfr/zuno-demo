"""WP-306 (ADR-0624 clause 5): stress traffic has its own identity, so it never spends the shared MaaS budget.

  * a quota class with a dedicated MaaS credential (MAAS_CLASS_TOKEN_PATHS) sends that credential, never the ai-gateway
    ServiceAccount's, and never falls back to it when the file is missing;
  * members of QUOTA_LOADTEST_GROUP run under the `loadtest` class once the budgets define it;
  * X-Zuno-Traffic: stresstest is a span attribute (zuno.traffic) on the model_call and guardrails spans, never a metric
    label, and any other value is dropped.

No network. Run from this directory with the pinned requirements installed (the OTel SDK enabled, the exporter pointed at
a closed port so an export fails fast):

    OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:9 python3 tests/test_wp306_stress_identity.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from app import main as app_main  # noqa: E402
from app import maas_adapter, telemetry  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402

_CLASS_ENV_KEYS = ("MAAS_CLASS_TOKEN_PATHS", "MAAS_SA_TOKEN_PATH", "MAAS_GATEWAY_IDENTITY", "MAAS_GATEWAY_API_KEY_ENV")


def _token_file(text: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as fh:
        fh.write(text)
        return fh.name


class _env:
    """A clean MaaS environment plus `overrides`. MAAS_SA_TOKEN_PATH is read once at import by the adapter, so the
    module attribute is patched too, as the other adapter tests do."""

    def __init__(self, **overrides):
        self.overrides = overrides

    def __enter__(self):
        cleaned = {k: v for k, v in os.environ.items() if k not in _CLASS_ENV_KEYS}
        cleaned.update(self.overrides)
        self._env = mock.patch.dict(os.environ, cleaned, clear=True)
        self._attr = mock.patch.object(maas_adapter, "MAAS_SA_TOKEN_PATH", self.overrides.get("MAAS_SA_TOKEN_PATH", ""))
        self._env.__enter__()
        self._attr.__enter__()
        return self

    def __exit__(self, *exc):
        self._attr.__exit__(*exc)
        return self._env.__exit__(*exc)


# -- the credential by quota class ------------------------------------------------------------------------------


def test_a_mapped_class_sends_its_own_credential_not_the_gateways() -> None:
    stress, shared = _token_file("stress-sa-token\n"), _token_file("ai-gateway-sa-token\n")
    try:
        with _env(MAAS_CLASS_TOKEN_PATHS='{"loadtest": "%s", "stresstest": "%s"}' % (stress, stress),
                  MAAS_SA_TOKEN_PATH=shared, MAAS_GATEWAY_IDENTITY="true"):
            assert maas_adapter._maas_bearer_token("caller-token", "loadtest") == "stress-sa-token"
            assert maas_adapter._maas_bearer_token("caller-token", "stresstest") == "stress-sa-token"
            # the other classes keep their behaviour: the pod's identity, then the caller's token
            assert maas_adapter._maas_bearer_token("caller-token", "standard") == "ai-gateway-sa-token"
            assert maas_adapter._maas_bearer_token("caller-token") == "ai-gateway-sa-token"
    finally:
        os.unlink(stress)
        os.unlink(shared)


def test_a_mapped_class_wins_even_with_the_gateway_identity_off() -> None:
    stress = _token_file("stress-sa-token")
    try:
        with _env(MAAS_CLASS_TOKEN_PATHS='{"loadtest": "%s"}' % stress):
            assert maas_adapter._maas_bearer_token("caller-token", "loadtest") == "stress-sa-token"
            assert maas_adapter._maas_bearer_token("caller-token", "standard") == "caller-token"
    finally:
        os.unlink(stress)


def test_a_mapped_class_with_a_missing_or_empty_file_raises_and_never_falls_back() -> None:
    shared = _token_file("ai-gateway-sa-token")
    empty = _token_file("  \n")
    try:
        for path in ("/nonexistent/stress-token", empty):
            with _env(MAAS_CLASS_TOKEN_PATHS='{"loadtest": "%s"}' % path, MAAS_SA_TOKEN_PATH=shared):
                try:
                    maas_adapter._maas_bearer_token("caller-token", "loadtest")
                except maas_adapter.MaasAdapterError as exc:
                    assert "loadtest" in str(exc) and "never spend" in str(exc), exc
                else:
                    raise AssertionError("expected MaasAdapterError: the shared credential must not be used")
    finally:
        os.unlink(shared)
        os.unlink(empty)


def test_no_mapping_changes_nothing() -> None:
    shared = _token_file("ai-gateway-sa-token")
    try:
        with _env(MAAS_SA_TOKEN_PATH=shared, MAAS_GATEWAY_IDENTITY="true"):
            assert maas_adapter.class_token_path("loadtest") == ""
            assert maas_adapter._maas_bearer_token("caller-token", "loadtest") == "ai-gateway-sa-token"
    finally:
        os.unlink(shared)


def test_a_broken_mapping_is_an_error_not_a_guess() -> None:
    for raw in ("not json", '["loadtest"]'):
        with _env(MAAS_CLASS_TOKEN_PATHS=raw):
            try:
                maas_adapter._maas_bearer_token("caller-token", "loadtest")
            except maas_adapter.MaasAdapterError:
                continue
            raise AssertionError(f"expected MaasAdapterError for {raw!r}")


def test_the_metered_path_sends_the_class_credential_and_the_attested_class() -> None:
    stress = _token_file("stress-sa-token")
    identity = CallerIdentity(sub="u", groups=["test-stress"], raw_claims={}, token="caller-token")
    try:
        with _env(MAAS_CLASS_TOKEN_PATHS='{"loadtest": "%s"}' % stress, MAAS_GATEWAY_IDENTITY="true", MAAS_SA_TOKEN_PATH="/nonexistent"):
            headers = app_main._metered_upstream_headers({"via_maas": True}, identity, "rid-1", "loadtest", None, {})
        assert headers["Authorization"] == "Bearer stress-sa-token", headers
        assert headers["X-Zuno-Quota-Class"] == "loadtest", headers
    finally:
        os.unlink(stress)


# -- the loadtest group ------------------------------------------------------------------------------------------


def _classes(*names):
    classes = dict(getattr(app_main.quota.ledger, "_classes", None) or {})
    for name in names:
        classes.setdefault(name, {"fail_mode": "closed", "tokens": {}})
    return mock.patch.object(app_main.quota.ledger, "_classes", classes)


def _who(*groups):
    return CallerIdentity(sub="test-stress-load-01", groups=list(groups), raw_claims={"azp": "zuno-stresstest"}, token="t")


def test_a_loadtest_group_member_runs_under_loadtest_when_the_class_exists() -> None:
    with _classes("loadtest", "stresstest", "evaluation"), mock.patch.dict(os.environ, {"QUOTA_LOADTEST_GROUP": "test-stress"}):
        assert app_main._default_quota_class(_who("sales", "test-eval", "test-stress")) == "loadtest"
        assert app_main._default_quota_class(_who("sales", "test-eval")) == "evaluation"


def test_the_loadtest_group_wins_over_the_stresstest_group() -> None:
    env = {"QUOTA_LOADTEST_GROUP": "test-stress", "QUOTA_STRESSTEST_GROUP": "zuno-quota-stresstest"}
    with _classes("loadtest", "stresstest"), mock.patch.dict(os.environ, env):
        assert app_main._default_quota_class(_who("zuno-quota-stresstest", "test-stress")) == "loadtest"
        assert app_main._default_quota_class(_who("zuno-quota-stresstest")) == "stresstest"


def test_without_the_class_in_the_budgets_the_group_changes_nothing() -> None:
    """An image older than the policy that adds `loadtest` keeps the member on the next rule instead of denying it."""
    classes = {"standard": {"fail_mode": "open", "tokens": {}}, "evaluation": {"fail_mode": "open", "tokens": {}}}
    with mock.patch.object(app_main.quota.ledger, "_classes", classes), mock.patch.dict(os.environ, {"QUOTA_LOADTEST_GROUP": "test-stress"}):
        assert app_main._default_quota_class(_who("test-eval", "test-stress")) == "evaluation"


def test_the_group_is_off_by_default() -> None:
    with _classes("loadtest"), _env():
        assert app_main._default_quota_class(_who("test-stress")) == "standard"


# -- the traffic tag ---------------------------------------------------------------------------------------------


def _spans(run_fn):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    saved = telemetry._tracer
    telemetry._tracer = provider.get_tracer("test")
    try:
        run_fn()
    finally:
        telemetry._tracer = saved
    return exporter.get_finished_spans()


class _Request:
    def __init__(self, headers):
        self.headers = headers


def _tagged(value, work):
    """Run `work` after the dependency saw the header, in ONE context, as FastAPI does for a handler."""
    headers = {} if value is None else {"x-zuno-traffic": value}

    async def go():
        await telemetry.adopt_incoming_trace_context(_Request(headers))
        work()

    asyncio.run(go())


def test_the_traffic_tag_is_on_the_model_call_and_guardrails_spans() -> None:
    def work():
        with telemetry.model_call_span("local", "qwen3.5-9b", "C1", run_id="r1"):
            pass
        with telemetry.guardrails_observe_span("r1", "tekos", "nemo"):
            pass

    spans = _spans(lambda: _tagged("stresstest", work))
    assert {s.name for s in spans} == {"model_call", "guardrails_observe"}, spans
    for span in spans:
        assert span.attributes.get("zuno.traffic") == "stresstest", (span.name, dict(span.attributes))


def test_an_unknown_or_missing_tag_leaves_no_attribute() -> None:
    for value in ("production", "<script>", "", None, "STRESSTEST "):
        def work():
            with telemetry.model_call_span("local", "qwen3.5-9b", "C1"):
                pass

        (span,) = _spans(lambda: _tagged(value, work))
        expected = "stresstest" if (value or "").strip().lower() == "stresstest" else None
        assert span.attributes.get("zuno.traffic") == expected, (value, dict(span.attributes))


def test_each_request_resets_the_tag() -> None:
    def work():
        with telemetry.model_call_span("local", "qwen3.5-9b", "C1"):
            pass

    async def two_requests():
        # the second request of the same context carries no header: the tag of the first must not leak
        await telemetry.adopt_incoming_trace_context(_Request({"x-zuno-traffic": "stresstest"}))
        await telemetry.adopt_incoming_trace_context(_Request({}))
        work()

    (span,) = _spans(lambda: asyncio.run(two_requests()))
    assert "zuno.traffic" not in span.attributes, dict(span.attributes)


def test_the_tag_is_never_a_metric_label() -> None:
    import inspect

    source = inspect.getsource(telemetry)
    assert "zuno.traffic" in source
    for line in source.splitlines():
        if "traffic" in line and ("add(1" in line or "record(" in line or '"outcome"' in line):
            raise AssertionError(f"the traffic tag reached a metric call: {line.strip()}")


TESTS = [obj for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc!r}")
        else:
            print(f"PASS {test.__name__}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

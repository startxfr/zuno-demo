"""WP-157 (ADR-0570) preparatory switches, each default off:

- MAAS_QUOTA_429_PASSTHROUGH: a 429 from a via_maas candidate stops the
  fallback loop and becomes the gateway's own 429 (WP-148 contract), on the
  non-streaming and the streaming path; a 429 from a direct SaaS provider
  still falls back; with the flag off nothing changes.
- MAAS_GATEWAY_IDENTITY (D5): the ServiceAccount token replaces the caller's
  token towards MaaS and the attested headers are attached; their names
  match the generated TokenRateLimitPolicy.
- QUOTA_FAIL_MODES_ENFORCED (D6, ADR-0570 clause 7): a direct sibling serves
  only `open` classes; a budget-config fault lets `open` classes through.

No network: providers are fakes. Run from this directory:

    python3 tests/test_wp157_maas_switches.py
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
import openai  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessageChunk  # noqa: E402

from app import maas_adapter, quota, quota_fail_modes  # noqa: E402
from app import main as app_main  # noqa: E402
from app.auth import CallerIdentity, validate_token  # noqa: E402
from app.routing import ProviderCandidate, RoutingTable  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_IDENTITY = CallerIdentity(sub="alice", groups=["/sales", "/agent_tekos"], raw_claims={}, token="caller-bearer")

_CFGS = {
    "local-maas": {"kind": "local", "model": "qwen", "via_maas": True, "endpoint": "https://maas/zuno-ai-run/qwen/v1"},
    "local": {"kind": "local", "model": "qwen"},
    "openai": {"kind": "saas", "model": "gpt-4o-mini"},
}
_CANDIDATES = [
    ProviderCandidate(name="local-maas", kind="local"),
    ProviderCandidate(name="local", kind="local"),
    ProviderCandidate(name="openai", kind="saas"),
]
_BODY = {"model": "x", "messages": [{"role": "user", "content": "hi"}]}


def _rate_limit_error(retry_after: str = "42") -> openai.RateLimitError:
    request = httpx.Request("POST", "https://maas/zuno-ai-run/qwen/v1/chat/completions")
    response = httpx.Response(429, headers={"retry-after": retry_after}, request=request)
    return openai.RateLimitError("Too Many Requests", response=response, body=None)


class _Model:
    def __init__(self, name, fail=None):
        self.name, self.fail = name, fail

    async def ainvoke(self, _messages):
        if self.fail:
            raise self.fail

        class _R:
            content = f"answer from {self.name}"
            usage_metadata = {"input_tokens": 1, "output_tokens": 1}
        return _R()

    async def astream(self, _messages):
        if self.fail:
            raise self.fail
        yield AIMessageChunk(content=f"answer from {self.name}")


class _Env:
    """Gateway with three candidates; `failures` maps a candidate to the
    exception its model raises. Records which candidates were built."""

    def __init__(self, failures, env=None, candidates=None):
        self.built = []
        failures = failures or {}

        def fake_chat_model_for(candidate, cfg, **kwargs):
            self.built.append(candidate.name)
            return _Model(candidate.name, failures.get(candidate.name))

        async def no_publish(*_a, **_k):
            return None

        self.patches = [
            mock.patch.dict(os.environ, env or {}),
            mock.patch.object(maas_adapter, "MAAS_ADAPTER_ENABLED", True),
            mock.patch.object(app_main, "chat_model_for", fake_chat_model_for),
            mock.patch.object(app_main.routing_table, "provider_config", side_effect=lambda n: _CFGS[n]),
            mock.patch.object(app_main.routing_table, "candidates_for", return_value=list(candidates or _CANDIDATES)),
            mock.patch.object(app_main.routing_table, "direct_sibling_names", return_value={"local"}),
            mock.patch.object(app_main.routing_decisions, "set_routing_decision", no_publish),
        ]

    def __enter__(self):
        for p in self.patches:
            p.start()
        app_main.app.dependency_overrides[validate_token] = lambda: _IDENTITY
        return self

    def __exit__(self, *exc):
        app_main.app.dependency_overrides.pop(validate_token, None)
        for p in reversed(self.patches):
            p.stop()


def _post(stream=False, headers=None):
    body = dict(_BODY, stream=stream)
    return TestClient(app_main.app).post("/v1/chat/completions", json=body, headers=headers or {})


_ON = {"MAAS_QUOTA_429_PASSTHROUGH": "true"}


# -- defaults ----------------------------------------------------------------

def test_every_switch_defaults_off() -> None:
    with mock.patch.dict(os.environ, {}, clear=False):
        for name in ("MAAS_QUOTA_429_PASSTHROUGH", "MAAS_GATEWAY_IDENTITY", "QUOTA_FAIL_MODES_ENFORCED"):
            os.environ.pop(name, None)
        assert maas_adapter.quota_429_passthrough_enabled() is False
        assert maas_adapter.gateway_identity_enabled() is False
        assert quota_fail_modes.enforced() is False
        assert app_main._maas_call_kwargs("alice", ["g"], "standard", None) == {}


# -- 429 pass-through --------------------------------------------------------

def test_flag_off_a_maas_429_falls_back_as_today() -> None:
    with _Env({"local-maas": _rate_limit_error()}) as env:
        r = _post()
    assert r.status_code == 200, r.text
    assert r.json()["zuno_provider"] == "local"
    assert env.built == ["local-maas", "local"]


def test_flag_on_a_maas_429_is_returned_without_fallback() -> None:
    with _Env({"local-maas": _rate_limit_error("42")}, env=_ON) as env:
        r = _post()
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after") == "42"
    body = r.json()
    assert body["error"] == "quota_exceeded" and body["quota_class"] == "standard"
    assert body["provider"] == "local-maas"
    assert env.built == ["local-maas"], "the direct sibling or SaaS was tried after a MaaS 429"


def test_flag_on_streaming_maas_429_is_an_http_429() -> None:
    with _Env({"local-maas": _rate_limit_error("7")}, env=_ON) as env:
        r = _post(stream=True)
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after") == "7"
    assert r.json()["error"] == "quota_exceeded"
    assert env.built == ["local-maas"]


def test_flag_on_streaming_success_is_unchanged() -> None:
    with _Env({}, env=_ON) as env:
        r = _post(stream=True)
    assert r.status_code == 200
    assert "answer from local-maas" in r.text and r.text.rstrip().endswith("data: [DONE]")
    assert env.built == ["local-maas"]


def test_flag_on_a_direct_saas_429_still_falls_back() -> None:
    candidates = [ProviderCandidate(name="openai", kind="saas"), ProviderCandidate(name="local", kind="local")]
    with _Env({"openai": _rate_limit_error()}, env=_ON, candidates=candidates) as env:
        r = _post()
    assert r.status_code == 200, r.text
    assert env.built == ["openai", "local"]


def test_flag_on_a_maas_5xx_still_falls_back() -> None:
    request = httpx.Request("POST", "https://maas/v1/chat/completions")
    err = openai.InternalServerError("boom", response=httpx.Response(503, request=request), body=None)
    with _Env({"local-maas": err}, env=_ON) as env:
        r = _post()
    assert r.status_code == 200
    assert env.built == ["local-maas", "local"]


def test_quota_exceeded_from_reads_status_and_retry_after() -> None:
    denial = maas_adapter.quota_exceeded_from(_rate_limit_error("12"), "p")
    assert denial is not None and denial.retry_after == 12 and denial.provider == "p"
    assert maas_adapter.quota_exceeded_from(_rate_limit_error("Wed, 21 Oct 2026 07:28:00 GMT"), "p").retry_after is None
    assert maas_adapter.quota_exceeded_from(RuntimeError("x"), "p") is None


# -- D5 gateway identity -----------------------------------------------------

def _via_maas_kwargs(env, context=None, caller="caller-bearer"):
    with mock.patch.dict(os.environ, env), mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        maas_adapter.chat_model_via_maas(
            {"endpoint": "https://maas/v1", "model": "qwen"}, request_id="req-1",
            caller_bearer_token=caller, context=context,
        )
    return chat_openai.call_args.kwargs


def test_identity_off_forwards_the_caller_token_and_no_quota_headers() -> None:
    os.environ.pop("MAAS_GATEWAY_IDENTITY", None)
    os.environ.pop("MAAS_QUOTA_429_PASSTHROUGH", None)
    ctx = maas_adapter.MaasCallContext(sub="alice", groups=("/sales",))
    kwargs = _via_maas_kwargs({}, ctx)
    assert kwargs["api_key"] == "caller-bearer"
    assert kwargs["default_headers"] == {"X-Zuno-Request-Id": "req-1"}
    assert "max_retries" not in kwargs


def test_identity_on_uses_the_sa_token_and_attests_the_context() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".token", delete=False) as fh:
        fh.write("sa-token\n")
    try:
        ctx = maas_adapter.MaasCallContext(
            sub="alice", groups=("/sales", "/agent_tekos"), quota_class="standard", project_id="p-1",
        )
        with mock.patch.object(maas_adapter, "MAAS_SA_TOKEN_PATH", fh.name):
            kwargs = _via_maas_kwargs({"MAAS_GATEWAY_IDENTITY": "true"}, ctx)
    finally:
        os.unlink(fh.name)
    assert kwargs["api_key"] == "sa-token", "the caller token must never reach MaaS in gateway-identity mode"
    assert kwargs["default_headers"] == {
        "X-Zuno-Request-Id": "req-1",
        "X-Zuno-User-Sub": "alice",
        "X-Zuno-Groups": "/agent_tekos|/sales",
        "X-Zuno-Quota-Class": "standard",
        "X-Zuno-Project-Id": "p-1",
    }


def test_identity_on_without_a_sa_token_refuses_the_call() -> None:
    ctx = maas_adapter.MaasCallContext(sub="alice")
    with mock.patch.object(maas_adapter, "MAAS_SA_TOKEN_PATH", "/nonexistent/token"):
        try:
            _via_maas_kwargs({"MAAS_GATEWAY_IDENTITY": "true"}, ctx)
        except maas_adapter.MaasAdapterError:
            return
    raise AssertionError("expected MaasAdapterError without a ServiceAccount token")


def test_identity_on_without_context_refuses_the_call() -> None:
    with tempfile.NamedTemporaryFile("w", delete=False) as fh:
        fh.write("sa-token")
    try:
        with mock.patch.object(maas_adapter, "MAAS_SA_TOKEN_PATH", fh.name):
            try:
                _via_maas_kwargs({"MAAS_GATEWAY_IDENTITY": "true"}, None)
            except maas_adapter.MaasAdapterError:
                return
    finally:
        os.unlink(fh.name)
    raise AssertionError("expected MaasAdapterError without a request context")


def test_attested_values_are_header_safe_and_groupless_is_none() -> None:
    headers = maas_adapter.attested_headers(maas_adapter.MaasCallContext(sub="é\r\nx", groups=()))
    assert headers["X-Zuno-Groups"] == "(none)"
    assert headers["X-Zuno-User-Sub"] == "%C3%A9%0D%0Ax"
    assert "X-Zuno-Project-Id" not in headers


def test_passthrough_on_disables_sdk_retries_on_maas_calls() -> None:
    os.environ.pop("MAAS_GATEWAY_IDENTITY", None)
    kwargs = _via_maas_kwargs({"MAAS_QUOTA_429_PASSTHROUGH": "true"})
    assert kwargs["max_retries"] == 0


def test_main_passes_the_context_only_with_identity_on() -> None:
    seen = []

    def spy(candidate, cfg, **kwargs):
        seen.append(kwargs.get("maas_context"))
        return _Model(candidate.name)

    for env, expect_ctx in (({"MAAS_GATEWAY_IDENTITY": "false"}, False), ({"MAAS_GATEWAY_IDENTITY": "true"}, True)):
        seen.clear()
        with _Env({}, env=env):
            with mock.patch.object(app_main, "chat_model_for", spy):
                r = _post(headers={"X-Zuno-Project-Id": "p-9"})
        assert r.status_code == 200
        if expect_ctx:
            ctx = seen[0]
            assert ctx == maas_adapter.MaasCallContext(
                sub="alice", groups=("/sales", "/agent_tekos"), quota_class="standard", project_id="p-9",
            )
        else:
            assert seen == [None]


def test_attested_header_names_match_the_generated_policy() -> None:
    """One place names the headers (maas_adapter.ATTESTED_HEADERS); the
    generated TokenRateLimitPolicy must count on exactly those."""
    template = (_REPO_ROOT / "gitops" / "charts" / "connectivity-link" / "templates"
                / "quota-tokenratelimitpolicies.yaml").read_text(encoding="utf-8")
    used = set(re.findall(r"request\.headers\['([a-z0-9-]+)'\]", template))
    declared = {name.lower() for name in maas_adapter.ATTESTED_HEADERS.values()}
    assert used == declared, f"policy reads {sorted(used)}, gateway attests {sorted(declared)}"


# -- fail modes ----------------------------------------------------------------

def test_generated_fail_modes_load() -> None:
    modes = quota_fail_modes.FailModes()
    assert modes.error is None
    assert modes.fail_open("standard") is True
    assert modes.fail_open("intensive") is False
    assert modes.fail_open("no-such-class") is False
    assert quota_fail_modes.FailModes(path=pathlib.Path("/nonexistent")).fail_open("standard") is False


def test_direct_sibling_names_are_derived_from_via_maas_twins() -> None:
    table = RoutingTable.__new__(RoutingTable)
    table._config = {"providers": [
        {"name": "local-maas", "kind": "local", "model": "qwen", "via_maas": True},
        {"name": "local", "kind": "local", "model": "qwen"},
        {"name": "local-other", "kind": "local", "model": "other"},
        {"name": "openai", "kind": "saas", "model": "qwen"},
    ]}
    assert table.direct_sibling_names() == {"local"}


def test_fail_modes_off_closed_class_still_reaches_the_sibling() -> None:
    os.environ.pop("QUOTA_FAIL_MODES_ENFORCED", None)
    with _Env({"local-maas": RuntimeError("maas down")}) as env:
        r = _post(headers={"X-Zuno-Quota-Class": "intensive"})
    assert r.status_code == 200 and env.built == ["local-maas", "local"]


def test_fail_modes_on_closed_class_skips_the_sibling() -> None:
    with _Env({"local-maas": RuntimeError("maas down")}, env={"QUOTA_FAIL_MODES_ENFORCED": "true"}) as env:
        r = _post(headers={"X-Zuno-Quota-Class": "intensive"})
    assert r.status_code == 200
    assert env.built == ["local-maas", "openai"], env.built


def test_fail_modes_on_open_class_keeps_the_sibling() -> None:
    with _Env({"local-maas": RuntimeError("maas down")}, env={"QUOTA_FAIL_MODES_ENFORCED": "true"}) as env:
        r = _post()
    assert r.status_code == 200 and env.built == ["local-maas", "local"]


def test_budget_config_fault_denies_standard_unless_fail_modes_on() -> None:
    broken = quota.TokenBudgetLedger(config={})
    broken._config_error = "unreadable"
    with mock.patch.object(quota, "ledger", broken):
        os.environ.pop("QUOTA_FAIL_MODES_ENFORCED", None)
        with _Env({}) as env:
            r = _post()
        assert r.status_code == 429 and env.built == [], "today's behaviour: every class denied"
        with _Env({}, env={"QUOTA_FAIL_MODES_ENFORCED": "true"}) as env:
            r = _post()
            assert r.status_code == 200, r.text
            r = _post(headers={"X-Zuno-Quota-Class": "intensive"})
            assert r.status_code == 429, "a closed class stays denied on a config fault"


TESTS = [obj for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

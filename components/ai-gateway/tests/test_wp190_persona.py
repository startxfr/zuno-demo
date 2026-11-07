"""ADR-0593 (WP-190 phase 1): the per-user budget, the quota windows, the MaaS
attestation and the zuno.persona span attribute are keyed by persona, so one person
has one budget across Open WebUI, UnifAI and OpenClaw. The `user` metric label was
dropped by WP-225 lot B (ADR-0603 M15).

Found in the WP-184 shared-quota proof (2026-11-03): OpenClaw's token belongs to the
service account of client `openclaw-<persona>`, so its `sub` differs from the
person's and it spent a budget of its own.

Run from this directory:

    python3 tests/test_wp190_persona.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402

from app import main as app_main  # noqa: E402
from app import quota, telemetry  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402
from app.schemas import ChatMessage  # noqa: E402

_PERSON_SUB = "6f1c0d3e-0000-4000-8000-000000000001"
_SA_SUB = "6f1c0d3e-0000-4000-8000-000000000002"


def _person(azp="open-webui", username="sale-01", sub=_PERSON_SUB, **extra):
    claims = {"sub": sub, "azp": azp, "preferred_username": username, **extra}
    return CallerIdentity(sub=sub, groups=["sales"], raw_claims=claims, token="t")


def _openclaw_sa(persona="sale-01", azp="openclaw-sale-01", sub=_SA_SUB):
    claims = {"sub": sub, "azp": azp, "preferred_username": f"service-account-{azp}", "persona": persona}
    return CallerIdentity(sub=sub, groups=["sales"], raw_claims=claims, token="t")


# -- persona derivation ----------------------------------------------------------

def test_a_person_is_its_username() -> None:
    assert _person().persona == "sale-01"
    assert _person(azp="unifai").persona == "sale-01"


def test_an_openclaw_token_is_its_persona_claim() -> None:
    assert _openclaw_sa().persona == "sale-01"
    assert _openclaw_sa(persona="consultant-02", azp="openclaw-consultant-02").persona == "consultant-02"


def test_a_persona_claim_from_another_client_is_ignored() -> None:
    """Only the OpenClaw clients may name a persona: a claim on any other
    client's token never redirects whose budget is spent."""
    assert _person(azp="open-webui", persona="board-01").persona == "sale-01"
    assert _person(azp="unifai", persona="board-01").persona == "sale-01"
    assert _person(azp="openclaw", persona="board-01").persona == "sale-01"  # the bare prefix is no client


def test_a_service_account_username_is_never_a_persona() -> None:
    sa = CallerIdentity(sub=_SA_SUB, groups=[], token="t", raw_claims={
        "sub": _SA_SUB, "azp": "zuno-evaluations", "preferred_username": "service-account-zuno-evaluations"})
    assert sa.persona == _SA_SUB
    no_claim = CallerIdentity(sub=_SA_SUB, groups=[], token="t", raw_claims={
        "sub": _SA_SUB, "azp": "openclaw-sale-01", "preferred_username": "service-account-openclaw-sale-01"})
    assert no_claim.persona == _SA_SUB  # an OpenClaw token without the claim keeps its own sub


def test_without_username_or_claim_the_persona_is_the_sub() -> None:
    bare = CallerIdentity(sub=_PERSON_SUB, groups=[], token="t", raw_claims={"sub": _PERSON_SUB})
    assert bare.persona == _PERSON_SUB
    blank = CallerIdentity(sub=_PERSON_SUB, groups=[], token="t",
                           raw_claims={"sub": _PERSON_SUB, "azp": "openclaw-x", "persona": "  ", "preferred_username": ""})
    assert blank.persona == _PERSON_SUB


def test_the_claim_clients_are_configurable() -> None:
    with mock.patch.dict(os.environ, {"PERSONA_CLAIM_CLIENTS": "assistant-a"}):
        assert _openclaw_sa().persona == _SA_SUB
        assert _openclaw_sa(azp="assistant-a").persona == "sale-01"
    with mock.patch.dict(os.environ, {"PERSONA_CLAIM_CLIENTS": ""}):
        assert _openclaw_sa().persona == _SA_SUB


# -- one budget ------------------------------------------------------------------

_BUDGETS = {"classes": {"tight": {"fail_mode": "open", "tokens": {
    "user": {"budget": 100, "window": "5m"},
    "group": {"budget": 100000, "window": "5m"},
    "project": {"budget": 100000, "window": "5m"},
}}}, "precedence": {"default": ["user", "group"], "in_project_context": ["project", "user", "group"]}}


def test_two_subs_of_one_persona_share_one_budget() -> None:
    ledger = quota.TokenBudgetLedger(config=_BUDGETS)
    person, assistant = _person(), _openclaw_sa()
    assert person.sub != assistant.sub
    ledger.consume("tight", person.persona, person.groups, None, 120, now=1000.0)
    denial = ledger.check("tight", assistant.persona, assistant.groups, None, now=1001.0)
    assert denial is not None and denial.dimension == "user", denial
    other = _person(username="sale-02", sub="another-sub")
    assert ledger.check("tight", other.persona, other.groups, None, now=1001.0) is None


def test_the_sub_alone_would_have_kept_two_budgets() -> None:
    """The WP-184 finding, kept as a guard on the test above."""
    ledger = quota.TokenBudgetLedger(config=_BUDGETS)
    ledger.consume("tight", _PERSON_SUB, ["sales"], None, 120, now=1000.0)
    assert ledger.check("tight", _SA_SUB, ["sales"], None, now=1001.0) is None


# -- the candidate loop spends the persona's budget --------------------------------

class _FakeModel:
    async def ainvoke(self, _messages):
        class _Result:
            content = "ok"
            usage_metadata = {"input_tokens": 30, "output_tokens": 20}
        return _Result()


def test_the_non_streaming_path_consumes_under_the_persona() -> None:
    consumed, attested = [], []
    with mock.patch.object(app_main, "chat_model_for", return_value=_FakeModel()), \
         mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "gpt-4o-mini"}), \
         mock.patch.object(app_main, "_maas_call_kwargs", side_effect=lambda sub, *a: attested.append(sub) or {}), \
         mock.patch.object(app_main.quota.ledger, "consume", side_effect=lambda *a, **k: consumed.append(a)):
        asyncio.run(app_main._invoke_with_fallback(
            [ProviderCandidate(name="openai", kind="saas")], "C1", [{"role": "user", "content": "hi"}],
            caller_sub=_SA_SUB, quota_subject="sale-01", local_only=False, task_id="", requested_model="auto",
            raw_messages=[ChatMessage(role="user", content="hi")], request_id="req-1",
        ))
    assert attested == ["sale-01"], attested
    assert consumed and consumed[0][1] == "sale-01" and consumed[0][4] == 50, consumed


def test_without_a_quota_subject_the_sub_is_used() -> None:
    consumed = []
    with mock.patch.object(app_main, "chat_model_for", return_value=_FakeModel()), \
         mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "gpt-4o-mini"}), \
         mock.patch.object(app_main, "_maas_call_kwargs", return_value={}), \
         mock.patch.object(app_main.quota.ledger, "consume", side_effect=lambda *a, **k: consumed.append(a)):
        asyncio.run(app_main._invoke_with_fallback(
            [ProviderCandidate(name="openai", kind="saas")], "C1", [{"role": "user", "content": "hi"}],
            caller_sub="u-1", local_only=False, task_id="", requested_model="auto",
            raw_messages=[ChatMessage(role="user", content="hi")], request_id="req-2",
        ))
    assert consumed and consumed[0][1] == "u-1", consumed


# -- telemetry ---------------------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.points = []

    def add(self, value, attrs):
        self.points.append(dict(attrs))

    record = add


def test_no_user_label_the_span_keeps_the_persona_and_the_sub() -> None:
    """WP-225 lot B (ADR-0603 M15): the counters carry no per-user label; the
    persona and the sub stay on the span."""
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    calls = _Recorder()
    t1, t2 = telemetry._caller_persona.set(""), telemetry._caller_client.set("")
    try:
        with mock.patch.object(telemetry, "_tracer", provider.get_tracer("test")), \
             mock.patch.object(telemetry, "_model_call_counter", calls), \
             mock.patch.object(telemetry, "_model_call_duration_histogram", _Recorder()):
            telemetry.set_caller_persona(_openclaw_sa().persona)
            with telemetry.model_call_span("openai", "gpt-4o-mini", "C1", caller_sub=_SA_SUB, groups=["sales"]):
                pass
    finally:
        telemetry._caller_persona.reset(t1)
        telemetry._caller_client.reset(t2)
    assert calls.points and "user" not in calls.points[0], calls.points
    assert calls.points[0]["client"] == "", calls.points
    span = exporter.get_finished_spans()[0]
    assert span.attributes["zuno.user_sub"] == _SA_SUB
    assert span.attributes["zuno.persona"] == "sale-01"


def test_without_a_persona_there_is_still_no_user_label() -> None:
    calls = _Recorder()
    token = telemetry._caller_persona.set("")
    try:
        with mock.patch.object(telemetry, "_tracer", TracerProvider().get_tracer("test")), \
             mock.patch.object(telemetry, "_model_call_counter", calls), \
             mock.patch.object(telemetry, "_model_call_duration_histogram", _Recorder()):
            with telemetry.model_call_span("openai", "gpt-4o-mini", "C1", caller_sub="u-1"):
                pass
    finally:
        telemetry._caller_persona.reset(token)
    assert "user" not in calls.points[0], calls.points


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


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

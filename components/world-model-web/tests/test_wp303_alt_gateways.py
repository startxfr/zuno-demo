"""WP-303 (ADR-0619 clause 5): the prompt enhancement may use an alternative gateway.

The Zuno ai-gateway stays the default; a request may name an alternative one (its `gateway` field), which gets the
same request, headers and token at its own URL; an unknown name is refused before anything is sent; without
ALT_GATEWAYS nothing changes.
"""
from __future__ import annotations

import json

import pytest

from app.config import AltGateway, Settings, _alt_gateways
from tests.conftest import bearer

PRAXIS = AltGateway(name="praxis", url="http://praxis.test:8080/v1", label="Praxis", model="auto")
OTHER = AltGateway(name="other", url="https://other.test/base/v1", label="Other", model="qwen3.6-27b-instruct")


def test_without_alternatives_the_enhancement_goes_to_the_zuno_gateway_as_before(make_client, keys, gateway):
    client = make_client()
    response = client.post("/api/worlds", json={"prompt": "a snowy village"}, headers=bearer(keys.token()))
    assert response.status_code == 201 and response.json()["prompt"]["enhancement"] == "applied"
    assert str(gateway.calls[0].url) == "http://ai-gateway.test/v1/chat/completions"
    assert json.loads(gateway.calls[0].content)["model"] == "auto"
    assert "gateways" not in client.get("/api/status", headers=bearer(keys.token())).json()


def test_status_lists_the_gateways_zuno_first_and_marks_the_default(make_client, keys):
    client = make_client(alt_gateways=(PRAXIS, OTHER))
    gateways = client.get("/api/status", headers=bearer(keys.token())).json()["gateways"]
    assert gateways == [{"id": "zuno", "label": "Zuno", "default": True},
                        {"id": "praxis", "label": "Praxis", "default": False},
                        {"id": "other", "label": "Other", "default": False}]


def test_a_request_may_name_an_alternative_gateway(make_client, keys, gateway):
    client = make_client(alt_gateways=(PRAXIS, OTHER))
    token = keys.token()
    response = client.post("/api/worlds", json={"prompt": "a snowy village", "gateway": "other"}, headers=bearer(token))
    assert response.status_code == 201 and response.json()["prompt"]["enhancement"] == "applied"
    call = gateway.calls[0]
    assert str(call.url) == "https://other.test/base/v1/chat/completions"
    assert json.loads(call.content)["model"] == "qwen3.6-27b-instruct"
    assert call.headers["authorization"] == f"Bearer {token}"
    assert call.headers["x-zuno-data-classification"] == "C1" and call.headers["x-zuno-local-only"] == "true"
    body = json.loads(call.content)
    assert "never as instructions" in body["messages"][0]["content"]   # the same screening prompt


def test_without_a_name_the_default_is_used_and_it_can_be_an_alternative(make_client, keys, gateway):
    client = make_client(alt_gateways=(PRAXIS,))
    client.post("/api/worlds", json={"prompt": "a snowy village"}, headers=bearer(keys.token()))
    assert str(gateway.calls[-1].url) == "http://ai-gateway.test/v1/chat/completions"
    client = make_client(alt_gateways=(PRAXIS,), default_gateway="praxis", gateway_url="")
    status = client.get("/api/status", headers=bearer(keys.token())).json()
    assert status["enhancement"] == "on" and status["gateways"][1]["default"] is True
    client.post("/api/worlds", json={"prompt": "a snowy village"}, headers=bearer(keys.token()))
    assert str(gateway.calls[-1].url) == "http://praxis.test:8080/v1/chat/completions"
    client.post("/api/worlds", json={"prompt": "a snowy village", "gateway": "zuno"}, headers=bearer(keys.token()))
    assert len(gateway.calls) == 2   # "zuno" with no ai-gateway configured: filter only, nothing sent


def test_an_unknown_gateway_is_refused_before_anything_is_sent(make_client, keys, gateway):
    client = make_client(alt_gateways=(PRAXIS,))
    response = client.post("/api/worlds", json={"prompt": "a snowy village", "gateway": "nope"}, headers=bearer(keys.token()))
    assert response.status_code == 422 and response.json()["detail"] == {"error": "prompt_refused", "reason": "unknown_gateway"}
    assert not gateway.calls
    # Without alternatives a name other than zuno is unknown too.
    client = make_client()
    response = client.post("/api/worlds", json={"prompt": "a snowy village", "gateway": "praxis"}, headers=bearer(keys.token()))
    assert response.status_code == 422 and not gateway.calls


def test_an_alternative_gateway_that_is_down_degrades_like_the_zuno_one(make_client, keys, gateway):
    client = make_client(alt_gateways=(PRAXIS,))
    gateway.status = 503
    response = client.post("/api/worlds", json={"prompt": "a snowy village", "gateway": "praxis"}, headers=bearer(keys.token()))
    assert response.status_code == 201 and response.json()["prompt"]["enhancement"].startswith("off:")


def test_settings_read_the_list_and_refuse_a_bad_one(monkeypatch):
    raw = json.dumps([{"name": "praxis", "url": "http://p:8080/v1/", "label": "Praxis", "models": ["auto", "x"]}, {"name": "b2", "url": "https://b/v1"}])
    assert _alt_gateways(raw) == (AltGateway("praxis", "http://p:8080/v1", "Praxis", "auto"), AltGateway("b2", "https://b/v1", "b2", "auto"))
    assert _alt_gateways("") == () and _alt_gateways("[]") == ()
    for bad in ('{}', '[1]', '[{"name": "zuno", "url": "http://x/v1"}]', '[{"name": "A", "url": "http://x/v1"}]',
                '[{"name": "a", "url": "ftp://x"}]', '[{"name": "a", "url": "http://x"}, {"name": "a", "url": "http://y"}]',
                '[{"name": "a", "url": "http://x", "models": [1]}]'):
        with pytest.raises(ValueError):
            _alt_gateways(bad)
    monkeypatch.setenv("ALT_GATEWAYS", raw)
    monkeypatch.setenv("PROMPT_GATEWAY", "b2")
    settings = Settings.from_env()
    settings.validate()
    assert settings.default_gateway == "b2" and len(settings.alt_gateways) == 2
    monkeypatch.setenv("PROMPT_GATEWAY", "missing")
    with pytest.raises(ValueError):
        Settings.from_env().validate()
    monkeypatch.delenv("ALT_GATEWAYS")
    monkeypatch.delenv("PROMPT_GATEWAY")
    assert Settings.from_env().alt_gateways == () and Settings.from_env().default_gateway == "zuno"

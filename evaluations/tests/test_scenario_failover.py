#!/usr/bin/env python3
"""WP-156: offline tests for the GPU failover drill's probe and verifier on the
UnifAI target. No network: a fake target and monkeypatched helpers.

    cd evaluations && python3 -m pytest tests/test_scenario_failover.py -q
"""
from __future__ import annotations

import pathlib
import sys

EVAL = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL))

import scenario_failover_probe as probe  # noqa: E402
import scenario_failover_verify as verify  # noqa: E402
from unifai_target import UnifaiRun  # noqa: E402

ROUTING = {"provider": "local-qwen35", "model": "qwen3.5-9b", "kind": "local", "classification": "C2", "fallback_used": True, "fallback_from": "local-wesh"}


class FakeTarget:
    def __init__(self, run):
        self._run = run
        self.cleaned = 0

    def run(self, persona, message, timeout=90):
        if isinstance(self._run, Exception):
            raise self._run
        return self._run

    def cleanup(self):
        self.cleaned += 1
        return (1, 0)


def test_probe_reports_the_routing_decision_and_cleans_up():
    t = FakeTarget(UnifaiRun("s-1", 200, "voici le point", 1.0, {"routing": ROUTING}))
    r = probe.probe("sale-01", "q", target=t)
    assert r["ok"] and r["provider"] == "local-qwen35" and r["routing"] == ROUTING and r["session_id"] == "s-1"
    assert t.cleaned == 1


def test_probe_without_routing_is_still_ok_with_a_null_provider():
    r = probe.probe("sale-01", "q", target=FakeTarget(UnifaiRun("s-1", 200, "ok", 1.0, {"routing": None})))
    assert r["ok"] and r["provider"] is None and "no routing decision" in r["detail"]


def test_probe_failures_are_reported_in_the_body():
    assert not probe.probe("sale-01", "q", target=FakeTarget(UnifaiRun("s", 599, "", 1.0, {"error": "x"})))["ok"]
    assert not probe.probe("sale-01", "q", target=FakeTarget(UnifaiRun("s", 200, "", 1.0, {})))["ok"]
    r = probe.probe("sale-01", "q", target=FakeTarget(RuntimeError("sign-in failed")))
    assert not r["ok"] and r["detail"] == "sign-in failed"


def test_verify_prefers_the_routing_metadata_without_polling(monkeypatch):
    monkeypatch.setattr(verify, "_query_provider_counts", lambda agent: (_ for _ in ()).throw(RuntimeError("no prom")))
    monkeypatch.setattr(verify, "_run_probe", lambda a, p, m: {"ok": True, "routing": ROUTING, "session_id": "s"})
    r = verify.verify_one_agent("comage", "sale-01", "q", "failover")
    assert r["ok"] and r["provider"] == "local-qwen35" and r["source"] == "routing-metadata"


def test_verify_falls_back_to_the_counter_delta(monkeypatch):
    counts = iter([{"local-wesh": 3.0}, {"local-wesh": 3.0, "local-qwen35": 1.0}])
    monkeypatch.setattr(verify, "_query_provider_counts", lambda agent: next(counts))
    monkeypatch.setattr(verify, "_run_probe", lambda a, p, m: {"ok": True, "routing": None})
    monkeypatch.setattr(verify.time, "sleep", lambda s: None)
    r = verify.verify_one_agent("comage", "sale-01", "q", "failover")
    assert r["ok"] and r["provider"] == "local-qwen35" and r["source"] == "prometheus"


def test_verify_without_routing_or_prometheus_fails_loudly(monkeypatch):
    monkeypatch.setattr(verify, "_query_provider_counts", lambda agent: (_ for _ in ()).throw(RuntimeError("no prom")))
    monkeypatch.setattr(verify, "_run_probe", lambda a, p, m: {"ok": True, "routing": None})
    r = verify.verify_one_agent("tekos", "consultant-01", "q", "baseline")
    assert not r["ok"] and r["provider"] is None and "Prometheus" in r["detail"]


def test_each_probe_subprocess_targets_its_agents_team(monkeypatch):
    seen = {}

    class Done:
        stdout = '{"ok": true}\n'
        stderr = ""

    def fake_run(cmd, env, **kw):
        seen.update(agent=env["AGENT"], team=env["UNIFAI_TEAM_NAME"], cmd=cmd)
        return Done()

    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    assert verify._run_probe("comage", "sale-01", "q") == {"ok": True}
    assert seen["agent"] == "comage" and seen["team"] == "agent-comage" and "--session-id" not in seen["cmd"]

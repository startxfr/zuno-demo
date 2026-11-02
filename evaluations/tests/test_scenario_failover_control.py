#!/usr/bin/env python3
"""WP-105 / zuno-demo WP-187: the tekos control of the GPU failover drill (evaluations/scenario_failover_verify.py).

Tekos's chat task reads Confluence, so it is local only since agents v0.8.1. The control must pass when the turn is
answered locally or refused cleanly with no external attempt, and fail when an external provider was reached or the
outcome cannot be established. The probe and Prometheus are faked; nothing touches a cluster.

Run directly:

    cd evaluations && python3 tests/test_scenario_failover_control.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

try:
    import httpx  # noqa: F401  (the script under test imports it)
except ImportError:  # the CI step installs httpx; keep a bare run readable
    sys.modules["httpx"] = mock.MagicMock()

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import scenario_failover_verify as sfv  # noqa: E402

REFUSAL = 'status=503 body={"detail":"no eligible provider is available for classification C2: local-gpt-oss-maas: not ready"}'


def _control(probe, counters=None, phase="failover"):
    """Runs the control with a fake probe result and a sequence of Prometheus snapshots (before, then after)."""
    snapshots = list(counters) if counters is not None else None

    def counts(agent, successes_only=True):
        if snapshots is None:
            raise RuntimeError("prometheus unreadable")
        return snapshots.pop(0) if len(snapshots) > 1 else snapshots[0]

    with mock.patch.object(sfv, "_run_probe", return_value=probe), \
            mock.patch.object(sfv, "_query_provider_counts", side_effect=counts), \
            mock.patch.object(sfv, "POLL_TIMEOUT_SECONDS", 0), \
            mock.patch.object(sfv.time, "sleep"):
        return sfv.verify_local_only_control("tekos", "consultant-01", "hello", phase)


class LocalOnlyControl(unittest.TestCase):
    def test_a_local_answer_passes(self):
        got = _control({"ok": True, "routing": {"provider": "local-gpt-oss-maas"}}, [{}])
        self.assertTrue(got["ok"])
        self.assertEqual((got["outcome"], got["provider"]), ("answered-local", "local-gpt-oss-maas"))

    def test_an_external_answer_fails(self):
        got = _control({"ok": True, "routing": {"provider": "ovhcloud-gpt-oss-120b"}}, [{}])
        self.assertFalse(got["ok"])
        self.assertEqual(got["outcome"], "external")

    def test_without_routing_metadata_the_counters_decide(self):
        local = _control({"ok": True}, [{"local-gpt-oss-maas": 1}, {"local-gpt-oss-maas": 2}])
        self.assertEqual((local["ok"], local["outcome"]), (True, "answered-local"))
        external = _control({"ok": True}, [{"openai": 1}, {"openai": 2, "local-gpt-oss-maas": 1}])
        self.assertEqual((external["ok"], external["outcome"]), (False, "external"))

    def test_no_signal_at_all_is_unknown_never_a_pass(self):
        got = _control({"ok": True}, [{"local-gpt-oss-maas": 1}])
        self.assertEqual((got["ok"], got["outcome"]), (False, "unknown"))

    def test_a_clean_refusal_with_no_external_attempt_passes(self):
        got = _control({"ok": False, "detail": REFUSAL}, [{"local-gpt-oss-maas": 5}, {"local-gpt-oss-maas": 5}])
        self.assertEqual((got["ok"], got["outcome"]), (True, "refused"))

    def test_a_refusal_followed_by_an_external_attempt_fails(self):
        got = _control({"ok": False, "detail": REFUSAL}, [{"ovhcloud-gpt-oss-120b": 1}, {"ovhcloud-gpt-oss-120b": 2}])
        self.assertEqual((got["ok"], got["outcome"]), (False, "external"))

    def test_a_refusal_cannot_be_proved_without_prometheus(self):
        got = _control({"ok": False, "detail": REFUSAL}, None)
        self.assertEqual((got["ok"], got["outcome"]), (False, "unknown"))

    def test_a_failure_that_is_not_the_gateways_refusal_is_unknown(self):
        got = _control({"ok": False, "detail": "sign-in failed: connection reset"}, [{}])
        self.assertEqual((got["ok"], got["outcome"]), (False, "unknown"))

    def test_the_local_provider_names(self):
        for name in ("local", "local-maas", "local-gpt-oss-maas", "local-qwen35"):
            self.assertTrue(sfv._is_local(name), name)
        for name in ("ovhcloud-gpt-oss-120b", "openai", "mistral-codestral", "localhost-proxy"):
            self.assertFalse(sfv._is_local(name), name)

    def test_the_agents_table_marks_only_tekos_as_the_control(self):
        controls = {spec["agent"] for spec in sfv._AGENTS if spec.get("control") == "local-only"}
        self.assertEqual(controls, {"tekos"})


if __name__ == "__main__":
    unittest.main()

"""WP-313 step 5: the tool-invocation counter's known label sets exist at 0 from startup, bounded by the tool policy.

Run from the component directory (exporter at a closed port so it fails fast):

    cd components/mcp-gateway && OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:9 python3 tests/test_zero_init.py
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402

from app import telemetry  # noqa: E402

TOOLS = [("search_confluence", "confluence.page.search", "confluence"), ("git.read", "git.repo.read", "git-forge")]


def primed(env=None):
    reader = InMemoryMetricReader()
    counter = MeterProvider(metric_readers=[reader]).get_meter("t").create_counter("zuno.tool_invocations")
    with mock.patch.dict(os.environ, env or {}), mock.patch.object(telemetry, "_invoke_counter", counter):
        n = telemetry.prime_zero_counters(TOOLS)
    data = reader.get_metrics_data()
    points = [(dict(p.attributes), p.value) for rm in (data.resource_metrics if data else []) for sm in rm.scope_metrics
              for m in sm.metrics for p in m.data.data_points]
    return n, points


class ZeroInit(unittest.TestCase):
    def test_each_tool_gets_every_outcome_at_zero(self):
        n, points = primed()
        self.assertEqual((n, len(points)), (6, 6))
        self.assertTrue(all(v == 0 for _, v in points))
        self.assertIn({"tool": "search_confluence", "capability": "confluence.page.search", "mcp_server": "confluence",
                       "outcome": "allowed"}, [labels for labels, _ in points])

    def test_nothing_beyond_the_policy_and_the_outcomes(self):
        _, points = primed()
        self.assertEqual({labels["outcome"] for labels, _ in points}, set(telemetry.INVOKE_OUTCOMES))
        self.assertEqual({labels["tool"] for labels, _ in points}, {t for t, _, _ in TOOLS})

    def test_the_switch_turns_it_off_and_a_missing_counter_is_fine(self):
        self.assertEqual(primed({"TELEMETRY_ZERO_INIT": "0"}), (0, []))
        with mock.patch.object(telemetry, "_invoke_counter", None):
            self.assertEqual(telemetry.prime_zero_counters(TOOLS), 0)

    def test_the_gateway_primes_the_real_policy(self):
        from app import main  # noqa: F401  (import primes against the mounted policy; must not raise)

        self.assertTrue(main._primed_tools() is not None)


if __name__ == "__main__":
    unittest.main()

"""WP-313 step 5: the model counters' known label sets exist at 0 from startup, bounded, and switchable.

Run from this directory:

    python3 tests/test_telemetry_zero_init.py
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry import metrics  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402

from app import telemetry  # noqa: E402
from app.routing import RoutingTable  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROUTING = os.path.join(REPO, "platform", "ai-gateway", "provider-routing.yaml")
CLIENTS = "unifai,open-webui,openclaw-*,zuno-stresstest"


def counters_on(reader):
    """Creates the telemetry module's counters on a private meter provider (no OTLP exporter)."""
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")
    names = {"_model_call_counter": "zuno.model_calls", "_token_counter": "zuno.model_tokens", "_cost_counter": "zuno.model_cost_usd",
             "_model_call_by_group_counter": "zuno.model_calls_by_group", "_token_by_group_counter": "zuno.model_tokens_by_group",
             "_cache_lookup_counter": "zuno.semantic_cache_lookups", "_guardrails_eval_counter": "zuno.guardrails_evaluations",
             "_candidates_skipped_counter": "zuno.model_candidates_skipped", "_empty_response_counter": "zuno.model_empty_responses"}
    return {attr: meter.create_counter(name) for attr, name in names.items()}


class ZeroInit(unittest.TestCase):
    def setUp(self):
        self.routing = RoutingTable(ROUTING)
        self.provider_models = self.routing.provider_models()

    def points(self, reader):
        out = {}
        data = reader.get_metrics_data()
        for rm in data.resource_metrics if data else []:
            for sm in rm.scope_metrics:
                for m in sm.metrics:
                    out[m.name] = [(dict(p.attributes), p.value) for p in m.data.data_points]
        return out

    def prime(self, env=None):
        reader = InMemoryMetricReader()
        patches = {f"app.telemetry.{k}": v for k, v in counters_on(reader).items()}
        with mock.patch.dict(os.environ, {"EXPERIENCE_CLIENTS": CLIENTS, **(env or {})}), \
                mock.patch.multiple("app.telemetry", **{k.split(".")[-1]: v for k, v in patches.items()}):
            n = telemetry.prime_zero_counters(self.provider_models)
        return n, self.points(reader)

    def test_the_providers_come_from_the_routing_file(self):
        names = [p for p, _ in self.provider_models]
        self.assertIn("local-maas", names)
        self.assertEqual(len(names), len(set(names)))

    def test_every_primed_series_is_zero_and_the_count_matches_the_label_sets(self):
        n, points = self.prime()
        self.assertGreater(n, 0)
        self.assertEqual(sum(len(v) for v in points.values()), n)
        self.assertTrue(all(value == 0 for series in points.values() for _, value in series))

    def test_the_first_real_call_of_an_experience_client_finds_its_series(self):
        _, points = self.prime()
        provider, model = self.provider_models[0]
        want = {"provider": provider, "model": model, "outcome": "success", "agent": "", "client": "open-webui"}
        self.assertIn(want, [labels for labels, _ in points["zuno.model_calls"]])
        self.assertIn({**want, "kind": "completion"}, [labels for labels, _ in points["zuno.model_tokens"]])

    def test_cardinality_is_bounded_by_the_known_sets(self):
        n, points = self.prime()
        clients = {labels["client"] for series in points.values() for labels, _ in series if "client" in labels}
        self.assertEqual(clients, {"unifai", "open-webui", "zuno-stresstest", "other", ""})  # openclaw-* is per persona: not primed
        for series in points.values():
            for labels, _ in series:
                self.assertNotIn("user", labels)
                self.assertIn(labels.get("agent", ""), ("",))
                self.assertIn(labels.get("group", ""), ("",))
        self.assertLess(n, 4000)

    def test_the_switch_turns_it_off(self):
        n, points = self.prime({"TELEMETRY_ZERO_INIT": "0"})
        self.assertEqual((n, points), (0, {}))

    def test_a_missing_counter_is_skipped_not_fatal(self):
        with mock.patch.multiple("app.telemetry", _model_call_counter=None, _token_counter=None):
            self.assertEqual(telemetry.prime_zero_counters(self.provider_models), 0)


if __name__ == "__main__":
    unittest.main()

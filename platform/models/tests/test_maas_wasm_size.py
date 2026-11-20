"""maas_wasm_size: the estimate of the Kuadrant wasm EnvoyFilter of the MaaS gateway, on fixture YAML (no cluster, no helm).

Run from the repository root:
    python3 platform/models/tests/test_maas_wasm_size.py
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import maas_wasm_size as w  # noqa: E402


def model(name: str, matches: int = 15, gateway: str = "maas-default-gateway") -> dict:
    rules = [{"matches": [{"path": {"type": "PathPrefix", "value": f"/{name}/{i}"}}]} for i in range(matches)]
    return {"kind": "LLMInferenceService", "metadata": {"name": name},
            "spec": {"router": {"route": {"http": {"spec": {"parentRefs": [{"name": gateway}], "rules": rules}}}}}}


def subscription(name: str, models: list) -> dict:
    return {"kind": "MaaSSubscription", "metadata": {"name": name}, "spec": {"modelRefs": [{"name": m} for m in models]}}


def today() -> list:
    """The live inputs of 2026-11-20: 15 matches per model, limits gpt-oss 9, qwen35-9b 6, wesh 5, qwen36-27b 6."""
    docs = [model("gpt-oss-20b"), model("qwen35-9b"), model("qwen35-9b-wesh"), model("qwen36-27b-instruct")]
    for model_name, n in (("gpt-oss-20b", 9), ("qwen35-9b", 6), ("qwen35-9b-wesh", 5), ("qwen36-27b-instruct", 6)):
        docs += [subscription(f"{model_name}-{i}", [model_name]) for i in range(n)]
    return docs


class Estimate(unittest.TestCase):
    def test_todays_inputs_give_3_92_mb(self):
        result = w.estimate(today(), listeners=2)
        self.assertEqual(round(result["total_bytes"] / 1e6, 2), 3.92)

    def test_one_listener_halves_it(self):
        self.assertAlmostEqual(w.estimate(today(), 1)["total_bytes"] * 2, w.estimate(today(), 2)["total_bytes"], delta=4)

    def test_the_formula_on_one_route(self):
        self.assertEqual(round(w.route_bytes(15, 9, 2)), round(1.06 * 2 * 15 * (3609 + 3940 * 9)))

    def test_vendor_routes_are_constants(self):
        rows = {r["name"]: r for r in w.estimate([], 1)["routes"]}
        self.assertEqual({n: (r["matches"], r["limits"]) for n, r in rows.items()},
                         {"external-model-route-1": (4, 1), "external-model-route-2": (4, 1), "maas-api-route": (5, 1)})
        self.assertEqual(w.estimate([], 1)["total_bytes"], sum(r["bytes"] for r in rows.values()))

    def test_matches_are_summed_over_rules(self):
        doc = model("m", matches=0)
        doc["spec"]["router"]["route"]["http"]["spec"]["rules"] = [{"matches": [{}, {}]}, {"matches": [{}]}, {}]
        self.assertEqual(w.model_routes([doc])[0]["matches"], 3)

    def test_limits_count_the_subscriptions_that_name_the_model(self):
        docs = [model("a"), model("b"), subscription("s1", ["a"]), subscription("s2", ["a", "b"]), subscription("s3", ["c"])]
        self.assertEqual({r["name"]: r["limits"] for r in w.model_routes(docs)}, {"a": 2, "b": 1})

    def test_only_routes_on_the_maas_gateway_count(self):
        docs = [model("kept"), model("other", gateway="another-gateway"), {"kind": "ConfigMap", "metadata": {"name": "x"}}]
        self.assertEqual([r["name"] for r in w.model_routes(docs)], ["kept"])


class Listeners(unittest.TestCase):
    def values(self, text):
        path = pathlib.Path(tempfile.mkdtemp()) / "values.yaml"
        path.write_text(text)
        return path

    def test_the_external_hostname_listener_makes_two(self):
        on = self.values("maasGateway:\n  externalHostnameListener:\n    enabled: true\n")
        off = self.values("maasGateway:\n  externalHostnameListener:\n    enabled: false\n")
        self.assertEqual((w.listeners_from_values([on]), w.listeners_from_values([off])), (2, 1))

    def test_the_later_file_wins_and_a_silent_file_changes_nothing(self):
        on = self.values("maasGateway:\n  externalHostnameListener:\n    enabled: true\n")
        off = self.values("maasGateway:\n  externalHostnameListener:\n    enabled: false\n")
        silent = self.values("other: 1\n")
        self.assertEqual(w.listeners_from_values([off, on, silent]), 2)
        self.assertEqual(w.listeners_from_values([on, off]), 1)

    def test_the_chart_default_is_one_listener(self):
        self.assertEqual(w.listeners_from_values([w.OPENSHIFT_AI_VALUES]), 1)


class Cli(unittest.TestCase):
    def run_cli(self, docs, *args):
        path = pathlib.Path(tempfile.mkdtemp()) / "r.yaml"
        path.write_text(yaml.safe_dump_all(docs))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = w.main([str(path), *args])
        return code, out.getvalue(), err.getvalue()

    def test_the_table_lists_each_route_and_the_total(self):
        code, out, _ = self.run_cli(today(), "--listeners", "2")
        self.assertEqual(code, 0)
        for name in ("gpt-oss-20b", "qwen36-27b-instruct", "maas-api-route", "TOTAL", "3.92 MB"):
            self.assertIn(name, out)

    def test_max_bytes_fails_above_and_passes_below(self):
        self.assertEqual(self.run_cli(today(), "--listeners", "2", "--max-bytes", "1400000")[0], 1)
        self.assertIn("TOO BIG", self.run_cli(today(), "--listeners", "2", "--max-bytes", "1400000")[2])
        self.assertEqual(self.run_cli(today(), "--listeners", "2", "--max-bytes", "4000000")[0], 0)

    def test_json_output(self):
        code, out, _ = self.run_cli(today(), "--listeners", "2", "--json", "--max-bytes", "5000000")
        data = json.loads(out)
        self.assertEqual((code, data["listeners"], data["ok"]), (0, 2, True))
        self.assertEqual(len(data["routes"]), 7)

    def test_the_default_render_of_the_models_chart_is_below_the_ci_limit(self):
        # the numbers the CI step relies on: 4 models, 1 listener (chart default), 1.4 MB
        docs = [model("a"), model("b"), model("c"), model("d")] + [subscription(f"s{i}", ["a"]) for i in range(6)]
        self.assertEqual(self.run_cli(docs, "--listeners", "1", "--max-bytes", "1400000")[0], 0)


@unittest.skipUnless(shutil.which("helm"), "helm not on PATH")
class RealChart(unittest.TestCase):
    """The models chart rendered the way demo333 runs it (second listener, Praxis, stress) must keep the wasm config small enough."""

    def test_the_demo333_shape_stays_under_the_limit(self):
        chart = w.REPO / "gitops" / "charts" / "models"
        rendered = subprocess.run(
            ["helm", "template", "m", str(chart), "-f", str(chart / "values.agents.generated.yaml"),
             "--set", "altGatewayPeers.praxis.enabled=true", "--set", "altGatewayPeers.stress.enabled=true",
             "--set", "maas.saasSubscriptions.gatewayOnly=true"], capture_output=True, text=True, check=True).stdout
        docs = [d for d in yaml.safe_load_all(rendered) if isinstance(d, dict)]
        models = w.model_routes(docs)
        self.assertGreaterEqual(len(models), 4)
        result = w.estimate(docs, listeners=2)
        self.assertLess(result["total_bytes"], 1_400_000,
                        f"the MaaS wasm EnvoyFilter would be {result['total_bytes']:,} bytes: Kuadrant stops updating it above ~1.4 MB, "
                        f"and the limits it cannot hold are silently NOT USED. Per route: {[(r['name'], r['matches'], r['limits']) for r in models]}")


if __name__ == "__main__":
    unittest.main()

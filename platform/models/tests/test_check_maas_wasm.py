"""check_maas_wasm: the read-only live check of the MaaS wasm EnvoyFilter, with a fake `oc` and small fixtures.

Run from the repository root:
    python3 platform/models/tests/test_check_maas_wasm.py
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check_maas_wasm as c  # noqa: E402

KEY_A, KEY_B, KEY_C = "limit.alpha__0123abcd", "limit.beta__89abcdef", "limit.gamma__aaaabbbb"


def envoyfilter(configuration: str, generation: int = 7) -> dict:
    return {"metadata": {"name": "kuadrant-maas-default-gateway", "generation": generation, "managedFields": [{"x": "y" * 500}]},
            "spec": {"configPatches": [{"patch": {"value": {"typed_config": {"value": {"config": {"configuration": {"value": configuration}}}}}}}]}}


def limitador(*limits: dict) -> dict:
    return {"spec": {"limits": list(limits)}}


def limit(namespace: str, keys: list, max_value: int = 1000, seconds: int = 3600, name: str = "") -> dict:
    return {"namespace": namespace, "name": name, "max_value": max_value, "seconds": seconds,
            "conditions": [f"descriptors[0][\"{k}\"] == \"1\"" for k in keys]}


def named(envoy: dict, name: str) -> dict:
    out = json.loads(json.dumps(envoy))
    out["metadata"]["name"] = name
    return out


def fake_oc(envoy, lim: dict, log: str = "", log_error: bool = False):
    """`envoy` is one EnvoyFilter (named kuadrant-maas-default-gateway) or a list of them; a non-kuadrant one is ignored by the check."""
    filters = envoy if isinstance(envoy, list) else [envoy]

    def run(args):
        if args[:2] == ["get", "envoyfilter"]:
            assert "-n" in args and args[args.index("-n") + 1] == "openshift-ingress"
            return json.dumps({"items": filters})
        if args[:2] == ["get", "limitador"]:
            return json.dumps(lim)
        if "logs" in args:
            if log_error:
                raise c.OcError("logs unavailable")
            return log
        raise AssertionError(f"unexpected oc call {args}")
    return run


CONFIG = json.dumps({"actionSets": [{"name": "a", "keys": [KEY_A]}, {"name": "b", "keys": [KEY_B]}]})


class Collect(unittest.TestCase):
    def test_every_limit_counted_and_no_failed_update_is_ok(self):
        result = c.collect(fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A]), limit("ns/b", [KEY_B]))))
        self.assertTrue(result["ok"])
        self.assertEqual([(o["name"], o["generation"], o["action_sets"]) for o in result["envoyfilters"]],
                         [("kuadrant-maas-default-gateway", 7, 2)])
        self.assertEqual([r["status"] for r in result["limits"]], ["COUNTED", "COUNTED"])
        self.assertEqual(result["failed_update_lines_last_30m"], 0)

    def test_a_limit_whose_key_is_missing_from_the_configuration_is_not_used(self):
        result = c.collect(fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A]), limit("ns/c", [KEY_C]))))
        self.assertFalse(result["ok"])
        self.assertEqual([r["status"] for r in result["limits"]], ["COUNTED", "NOT USED"])

    def test_all_keys_of_a_limit_must_appear(self):
        result = c.collect(fake_oc(envoyfilter(CONFIG), limitador(limit("ns/ab", [KEY_A, KEY_C]))))
        self.assertEqual(result["limits"][0]["status"], "NOT USED")

    def test_failed_updates_are_counted_and_the_lines_never_kept(self):
        log = ("ok\n" + 'ERROR failed to update envoyfilter object {"huge": "object"}\n' * 3 + "ok\n")
        result = c.collect(fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A])), log))
        self.assertEqual(result["failed_update_lines_last_30m"], 3)
        self.assertFalse(result["ok"])
        self.assertNotIn("huge", json.dumps(result))
        self.assertNotIn("huge", c.render(result))

    def test_an_unreadable_log_is_said_so_and_is_not_ok(self):
        result = c.collect(fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A])), log_error=True))
        self.assertIsNone(result["failed_update_lines_last_30m"])
        self.assertFalse(result["ok"])
        self.assertIn("could not be read", c.render(result))

    def test_the_size_leaves_managed_fields_out(self):
        envoy = envoyfilter(CONFIG)
        size = c.collect(fake_oc(envoy, limitador()))["envoyfilters"][0]["bytes"]
        envoy["metadata"]["managedFields"] = [{"x": "y" * 5000}]
        self.assertEqual(c.collect(fake_oc(envoy, limitador()))["envoyfilters"][0]["bytes"], size)

    def test_an_unexpected_configuration_gives_none_not_a_crash(self):
        self.assertIsNone(c.action_sets("not json"))
        self.assertIsNone(c.action_sets('{"other": []}'))
        self.assertEqual(c.wasm_configuration({"spec": {}}), "")

    def test_a_limit_with_no_descriptor_key_is_a_warning_not_a_failure(self):
        result = c.collect(fake_oc(envoyfilter(CONFIG), limitador({"namespace": "ns/none", "max_value": 1, "seconds": 1, "conditions": ["x == 1"]})))
        self.assertEqual((result["limits"][0]["status"], result["limits"][0]["keys"]), ("NO-KEY", 0))
        self.assertTrue(result["ok"])
        self.assertIn("1 without a key (warning)", c.render(result))

    def test_a_limit_is_counted_when_its_keys_appear_in_any_kuadrant_envoyfilter(self):
        other = json.dumps({"actionSets": [{"keys": [KEY_C]}]})
        filters = [named(envoyfilter(CONFIG), "kuadrant-maas-default-gateway"), named(envoyfilter(other), "kuadrant-zuno-agent-gateway")]
        result = c.collect(fake_oc(filters, limitador(limit("ns/a", [KEY_A]), limit("ns/c", [KEY_C]))))
        self.assertEqual([r["status"] for r in result["limits"]], ["COUNTED", "COUNTED"])
        self.assertEqual([o["name"] for o in result["envoyfilters"]], ["kuadrant-maas-default-gateway", "kuadrant-zuno-agent-gateway"])
        self.assertTrue(result["ok"])

    def test_the_keys_of_one_limit_must_all_sit_in_the_same_object(self):
        filters = [named(envoyfilter(json.dumps({"k": KEY_A})), "kuadrant-one"), named(envoyfilter(json.dumps({"k": KEY_B})), "kuadrant-two")]
        result = c.collect(fake_oc(filters, limitador(limit("ns/ab", [KEY_A, KEY_B]))))
        self.assertEqual(result["limits"][0]["status"], "NOT USED")

    def test_only_kuadrant_envoyfilters_are_read(self):
        filters = [named(envoyfilter(CONFIG), "kuadrant-maas-default-gateway"), named(envoyfilter(json.dumps({"k": KEY_C})), "istio-something")]
        result = c.collect(fake_oc(filters, limitador(limit("ns/c", [KEY_C]))))
        self.assertEqual([o["name"] for o in result["envoyfilters"]], ["kuadrant-maas-default-gateway"])
        self.assertEqual(result["limits"][0]["status"], "NOT USED")

    def test_an_envoyfilter_above_the_threshold_is_a_problem_per_object(self):
        filters = [named(envoyfilter(CONFIG), "kuadrant-small"), named(envoyfilter("x" * 5000), "kuadrant-big")]
        result = c.collect(fake_oc(filters, limitador(limit("ns/a", [KEY_A]))), max_bytes=3000)
        self.assertEqual({o["name"]: o["too_big"] for o in result["envoyfilters"]}, {"kuadrant-small": False, "kuadrant-big": True})
        self.assertFalse(result["ok"])
        self.assertIn("TOO BIG", c.render(result))
        self.assertTrue(c.collect(fake_oc(filters, limitador(limit("ns/a", [KEY_A]))), max_bytes=1_400_000)["ok"])

    def test_no_kuadrant_envoyfilter_at_all_is_a_problem(self):
        result = c.collect(fake_oc([], limitador(limit("ns/a", [KEY_A]))))
        self.assertFalse(result["ok"])
        self.assertIn("no EnvoyFilter named kuadrant-*", c.render(result))


class Cli(unittest.TestCase):
    def run_cli(self, run, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = c.main(list(args), run=run)
        return code, out.getvalue(), err.getvalue()

    def test_exit_codes(self):
        good = fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A])))
        bad = fake_oc(envoyfilter(CONFIG), limitador(limit("ns/c", [KEY_C])))
        self.assertEqual(self.run_cli(good)[0], 0)
        self.assertEqual(self.run_cli(bad)[0], 1)

    def test_the_text_report_has_one_line_per_limit_with_its_status(self):
        code, out, _ = self.run_cli(fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A], 5, 60), limit("ns/c", [KEY_C]))))
        self.assertIn("kuadrant-maas-default-gateway: generation 7", out)
        self.assertIn("action sets 2", out)
        self.assertIn("ns/a", out)
        self.assertIn("5/60s  COUNTED", out)
        self.assertIn("NOT USED", out)

    def test_max_bytes_flag(self):
        run = fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A])))
        self.assertEqual(self.run_cli(run, "--max-bytes", "100")[0], 1)
        self.assertEqual(self.run_cli(run, "--max-bytes", "1400000")[0], 0)

    def test_json_output(self):
        code, out, _ = self.run_cli(fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A]))), "--json")
        self.assertEqual((code, json.loads(out)["ok"]), (0, True))

    def test_an_oc_failure_is_exit_2_with_a_message(self):
        def broken(args):
            raise c.OcError("no cluster")
        code, _, err = self.run_cli(broken)
        self.assertEqual(code, 2)
        self.assertIn("no cluster", err)

    def test_only_get_and_logs_are_ever_asked_of_oc(self):
        seen = []

        def spy(args):
            seen.append(args)
            return fake_oc(envoyfilter(CONFIG), limitador(limit("ns/a", [KEY_A])))(args)
        self.run_cli(spy)
        for args in seen:
            self.assertTrue(args[0] == "get" or "logs" in args, args)


if __name__ == "__main__":
    unittest.main()

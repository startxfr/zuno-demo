"""The three mutating stress drivers and what they need (WP-310 batch 2, ADR-0624), offline.

Run from the repository root:
    python3 evaluations/tests/test_stress_mutating.py
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

import httpx
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
STRESS_DIR = REPO / "evaluations" / "stress"
sys.path.insert(0, str(REPO / "platform" / "testing"))
sys.path.insert(0, str(REPO / "evaluations"))

import stress_runner as sr  # noqa: E402

sr.load_drivers(STRESS_DIR)

import driver_mutating as mut  # noqa: E402

ENV = {"KEYCLOAK_URL": "https://kc", "DEMO_PERSONA_PASSWORD": "pw", "CLUSTER_BASE_DOMAIN": "apps.test", "UNIFAI_URL": "https://ui"}
IDS = ("delegation-approval", "unifai-live-rag", "image-signing-refusal")


def ctx_of(handler=None, env=None):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler or (lambda r: httpx.Response(404))))
    return sr.Ctx(env=dict(ENV, **(env or {})), run_id="mut-20261119", client=client, personas=["test-stress-load-01"])


class Registration(unittest.TestCase):
    def test_all_three_are_mutating_and_in_their_own_family(self):
        for i in IDS:
            d = sr.REGISTRY[i]
            self.assertTrue(d.mutating, i)
            self.assertEqual(d.family, "mutating", i)

    def test_a_profile_without_allow_mutating_skips_them(self):
        profile = {"families": ["mutating"], "defaults": {"iterations": 1}}
        chosen, warnings = sr.select_drivers(profile, {}, sr.REGISTRY) if hasattr(sr, "select_drivers") else (None, None)
        if chosen is None:
            plans, warnings = sr.build_plan(profile, {}, sr.REGISTRY)
            chosen = [p.driver for p in plans]
        self.assertEqual([d.id for d in chosen if d.id in IDS], [])
        self.assertTrue(any("allow_mutating" in w for w in warnings))

    def test_only_the_mutating_profile_allows_them(self):
        flags = {}
        for path in sorted(STRESS_DIR.glob("profile_*.yaml")):
            profile = yaml.safe_load(path.read_text())
            flags[profile["name"]] = (bool(profile.get("allow_mutating")), "mutating" in (profile.get("families") or []))
        self.assertEqual({n: f for n, f in flags.items() if any(f)}, {"mutating": (True, True)})

    def test_the_mutating_profile_selects_exactly_the_three(self):
        plans, _ = sr.build_plan(sr.load_profile("mutating", STRESS_DIR), {}, sr.REGISTRY)
        self.assertEqual(sorted(p.driver.id for p in plans), sorted(IDS))
        self.assertTrue(all(p.concurrency == 1 and p.iterations == 1 for p in plans))

    def test_the_persona_is_a_constant_never_the_workers(self):
        self.assertEqual(mut.MUTATE_PERSONA, "test-stress-mutate-01")
        source = (STRESS_DIR / "driver_mutating.py").read_text()
        self.assertNotIn("ctx.persona", source.replace("never `ctx.persona`", ""))
        values = yaml.safe_load((REPO / "gitops/charts/keycloak/values.yaml").read_text())
        entry = next(p for p in values["evalPersonas"] if p["username"] == "test-stress-mutate-01")
        self.assertEqual(entry["copyOf"], "consultant-01")
        self.assertEqual(entry.get("extraGroups"), ["/test-stress"])  # ADR-0630: the marker group of its type, so the loadtest class


class FakeStream:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        return iter(self.lines)


class FakeClient:
    def __init__(self, scripted, log):
        self.scripted, self.log = scripted, log

    def stream(self, method, url, **kw):
        return FakeStream(self.scripted["stream"])

    def post(self, url, json=None, **kw):
        self.log.append(("POST", url.rsplit("/", 1)[-1], dict(json or {})))
        if url.endswith("session.approval"):
            rid = json["requestId"]
            pending = self.scripted.get("pending")
            if rid == pending:
                self.scripted["pending"] = None  # answered once: a second answer is stale (409)
            return SimpleNamespace(status_code=200 if rid == pending else 409, text="")
        return SimpleNamespace(status_code=200, text="")

    def get(self, url, **kw):
        return SimpleNamespace(status_code=200, text='"CANCELLED"')


class FakeTarget:
    instances = []

    def __init__(self, password, ui_url=None, agent="tekos", team_id=None, team_name=None, scripted=None):
        self.ui_url = ui_url
        self.log, self.personas, self.cleaned = [], [], 0
        self.scripted = FakeTarget.scripted
        FakeTarget.instances.append(self)

    scripted = {}

    def client(self, persona):
        self.personas.append(persona)
        return FakeClient(self.scripted, self.log)

    def workflow_id(self, persona, name=None):
        self.personas.append(persona)
        return "wf"

    def create(self, persona, blueprint_id, tags=None):
        self.personas.append(persona)
        return "sid-1"

    def _team_body(self):
        return {}

    def cleanup(self):
        self.cleaned += 1
        return (1, 0)


@contextmanager
def fake_unifai(scripted):
    FakeTarget.instances.clear()
    FakeTarget.scripted = scripted
    with mock.patch.object(mut.ut, "UnifaiTarget", FakeTarget):
        yield FakeTarget.instances


class Approval(unittest.TestCase):
    EVENT = '{"type": "approval_required", "request_id": "req-1", "tool_name": "aap.cluster.audit"}'

    def test_the_judge(self):
        ok = {"asked": True, "answer": 200, "stale": 409, "unknown": 409, "seconds": 12.0, "final": "CANCELLED"}
        self.assertTrue(mut.judge_approval(ok)[0])
        self.assertFalse(mut.judge_approval({"asked": False, "types": ["x"]})[0])
        self.assertFalse(mut.judge_approval(dict(ok, stale=500))[0])
        self.assertFalse(mut.judge_approval(dict(ok, unknown=200))[0])
        self.assertFalse(mut.judge_approval(dict(ok, answer=404))[0])

    def test_a_request_is_rejected_never_approved_and_everything_is_cleaned(self):
        with fake_unifai({"stream": [self.EVENT], "pending": "req-1"}) as made:
            result = mut.approval_turn(ctx_of(), wait=5, sleep=lambda s: None)
        self.assertEqual((result["asked"], result["answer"], result["stale"], result["unknown"]), (True, 200, 409, 409))
        target = made[0]
        decisions = [(b["requestId"], b["decision"]) for m, path, b in target.log if path == "session.approval"]
        self.assertEqual(decisions[0], ("req-1", "reject"))
        self.assertEqual({d for r, d in decisions if r == "req-1"} - {"reject"}, {"approve"})  # only the stale probe says approve
        self.assertIn("session.cancel", [p for _, p, _ in target.log])
        self.assertEqual(target.cleaned, 1)
        self.assertEqual(set(target.personas), {"test-stress-mutate-01"})

    def test_no_request_still_cancels_and_deletes_the_session(self):
        with fake_unifai({"stream": []}) as made:
            result = mut.approval_turn(ctx_of(), wait=0, sleep=lambda s: None)
        self.assertFalse(result["asked"])
        self.assertIn("session.cancel", [p for _, p, _ in made[0].log])
        self.assertEqual(made[0].cleaned, 1)

    def test_the_driver_gives_one_row(self):
        done = {"asked": True, "answer": 200, "stale": 409, "unknown": 409, "seconds": 1, "final": "CANCELLED"}
        with mock.patch.object(mut, "approval_turn", lambda ctx: done):
            rows = asyncio.run(sr.REGISTRY["delegation-approval"].run(ctx_of().for_worker(0), 0))
        self.assertEqual([(r.id, r.passed) for r in rows], [("reject-and-stale", True)])


class Rag(unittest.TestCase):
    def test_names_are_bare_and_unique(self):
        a, b = mut.doc_name("run-1", 0), mut.doc_name("run-1", 0)
        self.assertNotEqual(a, b)
        for n in (a, b, mut.doc_name("a/b ../c", 1)):
            self.assertEqual(mut.lib.check_name(n), n)
            self.assertTrue(n.startswith("stress-rag-") and n.endswith(".md"))

    def test_the_judge_separates_indexing_from_cleanup(self):
        good = [{"action": "upload", "ok": True}, {"action": "wait", "ok": True, "seconds": 41.0},
                {"action": "delete", "ok": True}, {"action": "verify-gone", "ok": True}]
        self.assertEqual([(i, ok) for i, ok, _ in mut.judge_rag(good)], [("upload-indexed", True), ("cleanup", True)])
        left = good[:3] + [{"action": "verify-gone", "ok": False, "result": "STILL PRESENT"}]
        self.assertEqual([(i, ok) for i, ok, _ in mut.judge_rag(left)], [("upload-indexed", True), ("cleanup", False)])
        slow = [{"action": "upload", "ok": True}, {"action": "wait", "ok": False, "result": "PENDING"}] + good[2:]
        self.assertEqual([(i, ok) for i, ok, _ in mut.judge_rag(slow)], [("upload-indexed", False), ("cleanup", True)])

    def test_the_document_is_deleted_even_when_indexing_fails(self):
        calls = []
        lib = mut.lib
        with fake_unifai({}), mock.patch.object(lib, "upload_files", lambda c, a, p: calls.append("upload") or [{"action": "upload", "ok": True}]), \
                mock.patch.object(lib, "wait_done", lambda c, a, n, timeout=0: (_ for _ in ()).throw(RuntimeError("pipeline down"))), \
                mock.patch.object(lib, "delete_named", lambda c, a, n: calls.append("delete") or [{"action": "delete", "ok": True}]), \
                mock.patch.object(lib, "list_sources", lambda c, a: []):
            with self.assertRaises(RuntimeError):
                mut.rag_cycle(ctx_of(), 0)
        self.assertEqual(calls, ["upload", "delete"])

    def test_a_clean_cycle_uploads_waits_deletes_and_verifies(self):
        order = []
        lib = mut.lib
        with fake_unifai({}) as made, mock.patch.object(lib, "upload_files", lambda c, a, p: order.append(("upload", p[0].name)) or [{"action": "upload", "ok": True}]), \
                mock.patch.object(lib, "wait_done", lambda c, a, n, timeout=0: order.append(("wait", n[0])) or [{"action": "wait", "ok": True, "seconds": 3}]), \
                mock.patch.object(lib, "delete_named", lambda c, a, n: order.append(("delete", n[0])) or [{"action": "delete", "ok": True}]), \
                mock.patch.object(lib, "list_sources", lambda c, a: []):
            results = mut.rag_cycle(ctx_of(), 2)
        self.assertEqual([k for k, _ in order], ["upload", "wait", "delete"])
        self.assertEqual(len({n for _, n in order}), 1)
        self.assertTrue(all(r["ok"] for r in results))
        self.assertEqual(set(made[0].personas), {"test-stress-mutate-01"})


class Admission(unittest.TestCase):
    def test_the_judge(self):
        self.assertTrue(mut.judge_admission(400, 'admission webhook "policy.sigstore.dev" denied: must be referenced by digest')[0])
        self.assertTrue(mut.judge_admission(403, "denied by clusterimagepolicy: signature validation failed")[0])
        self.assertFalse(mut.judge_admission(201, "{}")[0])
        self.assertIn("ADMITTED", mut.judge_admission(201, "{}")[1])
        self.assertIn("does not exist", mut.judge_admission(404, "")[1])
        self.assertIn("stressImageProof", mut.judge_admission(403, 'pods is forbidden: User cannot create resource "pods"')[1])
        self.assertFalse(mut.judge_admission(422, "spec.containers invalid")[0])

    def test_the_pod_is_a_tag_referenced_restricted_pod_in_the_dedicated_namespace(self):
        pod = mut.unsigned_pod()
        image = pod["spec"]["containers"][0]["image"]
        self.assertNotIn("@sha256:", image)
        self.assertEqual(pod["spec"]["securityContext"]["runAsNonRoot"], True)
        self.assertEqual(mut.ADMISSION_NAMESPACE, "zuno-stress-admission")

    def test_the_driver_sends_a_dry_run_to_the_dedicated_namespace_only(self):
        seen = []

        def handler(request):
            seen.append((request.method, request.url.path, request.url.params.get("dryRun")))
            return httpx.Response(400, text="admission webhook denied the request: image must be referenced by digest")

        ctx = ctx_of(env={"KUBE_TOKEN": "t", "KUBE_URL": "https://api"})
        import driver_state as ds
        with mock.patch.object(ds, "_client", lambda c: httpx.AsyncClient(transport=httpx.MockTransport(handler))):
            rows = asyncio.run(sr.REGISTRY["image-signing-refusal"].run(ctx.for_worker(0), 0))
        self.assertEqual(seen, [("POST", "/api/v1/namespaces/zuno-stress-admission/pods", "All")])
        self.assertTrue(rows[0].passed, rows[0].detail)


class Grant(unittest.TestCase):
    CHART = str(REPO / "gitops/charts/namespaces")

    def render(self, *sets):
        args = ["helm", "template", "n", self.CHART, "--set", "policy.enabled=true", "--set", "clusterBaseDomain=apps.test"]
        for s in sets:
            args += ["--set", s]
        return subprocess.run(args, capture_output=True, text=True, check=True).stdout

    @unittest.skipUnless(shutil.which("helm"), "helm not on PATH")
    def test_off_by_default_and_needs_the_reader(self):
        self.assertNotIn("stress-image-proof", self.render())
        self.assertNotIn("stress-image-proof", self.render("stressReader.enabled=true"))
        self.assertNotIn("stress-image-proof", self.render("stressImageProof.enabled=true"))

    @unittest.skipUnless(shutil.which("helm"), "helm not on PATH")
    def test_the_grant_is_one_verb_on_pods_in_one_namespace(self):
        docs = [d for d in yaml.safe_load_all(self.render("stressReader.enabled=true", "stressImageProof.enabled=true")) if d]
        mine = [d for d in docs if "stress-image-proof" in str(d.get("metadata", {}).get("name", "")) or d.get("metadata", {}).get("name") == "zuno-stress-admission"]
        self.assertEqual(sorted(d["kind"] for d in mine), ["Namespace", "Role", "RoleBinding"])
        role = next(d for d in mine if d["kind"] == "Role")
        self.assertEqual(role["rules"], [{"apiGroups": [""], "resources": ["pods"], "verbs": ["create"]}])
        self.assertEqual(role["metadata"]["namespace"], "zuno-stress-admission")
        namespace = next(d for d in mine if d["kind"] == "Namespace")
        self.assertEqual(namespace["metadata"]["labels"]["policy.rhtas.com/include"], "true")
        binding = next(d for d in mine if d["kind"] == "RoleBinding")
        self.assertEqual([(s["kind"], s["name"]) for s in binding["subjects"]], [("ServiceAccount", "zuno-stress-reader")])
        self.assertFalse([d for d in docs if d["kind"] in ("ClusterRole", "ClusterRoleBinding") and "image-proof" in d["metadata"]["name"]])

    def test_the_ansible_switch_defaults_off(self):
        text = (REPO / "ansible/roles/namespaces/tasks/install_d1.yml").read_text()
        self.assertIn("zuno_stress_image_proof_enabled | default(false)", text)
        values = yaml.safe_load((REPO / "gitops/charts/namespaces/values.yaml").read_text())
        self.assertIs(values["stressImageProof"]["enabled"], False)


if __name__ == "__main__":
    unittest.main()

"""Tests for platform/supply-chain/admit_okf_bundle.py (WP-160).

The signature path is exercised live against quay.io (WP-160 brief); these
tests cover what needs no registry: validation against the platform
bindings, the promotion diff, the lock file and archive extraction.

Run from the repository root:
    python3 platform/supply-chain/tests/test_admit_okf_bundle.py
"""
from __future__ import annotations

import gzip
import io
import pathlib
import shutil
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import admit_okf_bundle as admit  # noqa: E402

AGENT = """---
okf_version: v0.2
type: agent
title: Demo
zuno:
  name: demo
  tasks: [ask]
  access: {groups: [agent_demo]}
  model: {preferred_classification: C1}
---
"""
TASK = """---
okf_version: v0.2
type: task
title: Ask
zuno:
  allowed_tools: [search_docs]
  allowed_knowledge: [knowledge.tech]
---
"""


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class AdmitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.release = self.tmp / "release"
        write(self.release / "agents/demo/agent.okf.md", AGENT)
        write(self.release / "agents/demo/tasks/ask.md", TASK)
        write(self.release / "policies/tools/tool-policy.yaml",
              "tools:\n  - tool: search_docs\n    capability: knowledge.tech.search\n")
        write(self.release / "policies/models/model-catalog.yaml",
              "models:\n  - {name: local, kind: local}\n  - {name: spare, kind: local}\n")
        write(self.release / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [local]}\n")
        platform = self.tmp / "platform"
        write(platform / "provider-routing.yaml", "providers:\n  - {name: local}\n")
        write(platform / "tool-bindings.yaml", "bindings:\n  - capability: knowledge.tech.search\n")
        write(platform / "unifai-values.yaml", "ragSources: []\n")
        write(platform / "redhat-docs.yaml",
              "sources:\n  - {name: rh-x, tags: [knowledge.tech, product:x]}\n")
        self.saved = (admit.PROVIDER_ROUTING_PATH, admit.TOOL_BINDINGS_PATH, admit.UNIFAI_RAG_SOURCE_FILES)
        admit.PROVIDER_ROUTING_PATH = platform / "provider-routing.yaml"
        admit.TOOL_BINDINGS_PATH = platform / "tool-bindings.yaml"
        admit.UNIFAI_RAG_SOURCE_FILES = ((platform / "unifai-values.yaml", "ragSources"),
                                         (platform / "redhat-docs.yaml", "sources"))

    def tearDown(self) -> None:
        admit.PROVIDER_ROUTING_PATH, admit.TOOL_BINDINGS_PATH, admit.UNIFAI_RAG_SOURCE_FILES = self.saved
        shutil.rmtree(self.tmp)

    def copy(self) -> pathlib.Path:
        other = self.tmp / "other"
        shutil.copytree(self.release, other)
        return other


class ValidateTest(AdmitTestCase):
    def test_servable_release(self) -> None:
        errors, warnings = admit.validate(self.release)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, ["model catalog names 'spare', which provider-routing.yaml does not bind"])

    def test_unbound_model(self) -> None:
        write(self.release / "policies/models/model-catalog.yaml", "models:\n  - {name: local}\n  - {name: big}\n")
        write(self.release / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [big]}\n")
        self.assertIn("not bound in provider-routing.yaml", admit.validate(self.release)[0][0])

    def test_model_outside_the_catalog(self) -> None:
        write(self.release / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, prefer: [ghost]}\n")
        self.assertIn("absent from the release's model catalog", admit.validate(self.release)[0][0])

    def test_tool_without_binding(self) -> None:
        write(self.release / "policies/tools/tool-policy.yaml",
              "tools:\n  - tool: search_docs\n    capability: nowhere.do\n")
        self.assertIn("no backend binding", admit.validate(self.release)[0][0])

    def test_tool_absent_from_policy(self) -> None:
        write(self.release / "policies/tools/tool-policy.yaml", "tools: []\n")
        self.assertIn("absent from the release's tool policy", admit.validate(self.release)[0][0])

    def test_tool_bound_by_alias(self) -> None:
        write(self.release / "policies/tools/tool-policy.yaml",
              "tools:\n  - tool: search_docs\n    capability: other.cap\n")
        write(admit.TOOL_BINDINGS_PATH, "bindings:\n  - capability: x.y.z\n    aliases: [search_docs]\n")
        self.assertEqual(admit.validate(self.release)[0], [])

    def test_v03_widening_is_refused_at_admission(self) -> None:
        # ADR-0579 clause 5, re-checked here after the agents repository's CI.
        write(self.release / "agents/demo/agent.okf.md",
              AGENT.replace("okf_version: v0.2", "okf_version: v0.3")
                   .replace("  model: {preferred_classification: C1}\n",
                            "  model: {preferred_classification: C1}\n  limits: {max_tokens: 99999}\n"))
        write(self.release / "policies/limits/limits-policy.yaml", "max_tokens: 8192\n")
        errors = admit.validate(self.release)[0]
        self.assertEqual(len(errors), 1)
        self.assertIn("exceeds the corp ceiling 8192", errors[0])

    def _v03_demo(self, extra: str) -> None:
        write(self.release / "agents/demo/agent.okf.md",
              AGENT.replace("okf_version: v0.2", "okf_version: v0.3")
                   .replace("  model: {preferred_classification: C1}\n",
                            "  model: {preferred_classification: C1}\n" + extra))
        write(self.release / "policies/limits/limits-policy.yaml", "max_delegation_depth: 2\n")

    def test_delegation_depth_above_the_corp_ceiling_is_refused_at_admission(self) -> None:
        # ADR-0406: the ceiling is checked here too, after the agents repository's CI.
        self._v03_demo("  limits: {delegation: {max_depth: 3}}\n")
        errors = admit.validate(self.release)[0]
        self.assertEqual(len(errors), 1)
        self.assertIn("delegation max_depth 3 exceeds the corp ceiling 2", errors[0])

    def test_a_delegation_target_must_exist_and_not_be_the_agent_itself(self) -> None:
        self._v03_demo("  delegation: {targets: [{agent: ghost, task: ask}]}\n")
        self.assertIn("target agent 'ghost' is not in the release", admit.validate(self.release)[0][0])
        self._v03_demo("  delegation: {targets: [{agent: demo, task: ask}]}\n")
        self.assertIn("is the agent itself", admit.validate(self.release)[0][0])

    def test_delegation_in_a_v02_bundle_is_refused(self) -> None:
        write(self.release / "agents/demo/agent.okf.md",
              AGENT.replace("  model: {preferred_classification: C1}\n",
                            "  model: {preferred_classification: C1}\n  delegation: {targets: [{agent: demo, task: ask}]}\n"))
        self.assertIn("delegation is an OKF v0.3 field", admit.validate(self.release)[0][0])

    # ADR-0615 clauses 5 and 6: profile 1.0 (okf_version "0.2" + zuno.profile "1.0").

    def _profile10_demo(self, extra: str = "") -> None:
        write(self.release / "agents/demo/agent.okf.md",
              AGENT.replace("okf_version: v0.2", 'okf_version: "0.2"')
                   .replace("  name: demo\n", '  profile: "1.0"\n  name: demo\n')
                   .replace("  model: {preferred_classification: C1}\n",
                            "  model: {preferred_classification: C1}\n" + extra))
        write(self.release / "agents/demo/tasks/ask.md",
              TASK.replace("okf_version: v0.2", 'okf_version: "0.2"')
                  .replace("  allowed_tools:", '  profile: "1.0"\n  allowed_tools:'))
        # The bundle-root index.md of profile bundles: okf_version only, no type, no zuno.profile.
        # No reader opens it; were one to, the dispatch rule would refuse it.
        write(self.release / "agents/demo/index.md", '---\nokf_version: "0.2"\n---\n\n# Demo\n')

    def test_a_profile10_release_is_admitted(self) -> None:
        self._profile10_demo()
        self.assertEqual(admit.validate(self.release)[0], [])
        self.assertEqual(admit.agents_view(self.release)["demo"]["tasks"],
                         {"ask": {"tools": ["search_docs"], "knowledge": ["knowledge.tech"], "quota_class": "standard"}})

    def test_a_profile10_widening_is_refused_at_admission(self) -> None:
        # ADR-0615 clause 6 (F11): the v0.3 rules apply from v0.3 up, profile 1.0 included.
        # A gate testing `okf_version == "v0.3"` would skip this bundle in silence.
        self._profile10_demo("  limits: {max_tokens: 99999, delegation: {max_depth: 3}}\n")
        write(self.release / "policies/limits/limits-policy.yaml", "max_tokens: 8192\nmax_delegation_depth: 2\n")
        errors = admit.validate(self.release)[0]
        self.assertEqual(len(errors), 2, errors)
        self.assertIn("max_tokens 99999 exceeds the corp ceiling 8192", errors[0])
        self.assertIn("delegation max_depth 3 exceeds the corp ceiling 2", errors[1])

    def test_a_profile10_skill_the_task_does_not_cover_is_refused(self) -> None:
        self._profile10_demo()
        write(self.release / "agents/demo/tasks/ask.md",
              TASK.replace("okf_version: v0.2", 'okf_version: "0.2"')
                  .replace("  allowed_tools:", '  profile: "1.0"\n  skills: [cite]\n  allowed_tools:'))
        write(self.release / "agents/demo/skills/cite.md",
              '---\nokf_version: "0.2"\ntype: skill\nzuno:\n  profile: "1.0"\n  allowed_tools: [send_email]\n---\n')
        self.assertIn("skill 'cite' needs tool 'send_email'", admit.validate(self.release)[0][0])

    def test_the_narrowing_level_orders_the_versions(self) -> None:
        import okf_narrowing

        self.assertEqual([okf_narrowing.at_least_v03(v) for v in ("v0.2", "v0.3", "1.0")], [False, True, True])
        self.assertFalse(okf_narrowing.at_least_v03("v0.9"))

    def test_the_narrowing_rule_fails_closed_on_an_unsupported_version(self) -> None:
        import okf_narrowing

        for front, needle in (('okf_version: "0.2"', "unsupported zuno.profile None"),
                              ("okf_version: 0.2", "unsupported okf_version 0.2"),
                              ("okf_version: v0.9", "unsupported okf_version 'v0.9'")):
            with self.subTest(front=front):
                write(self.release / "agents/demo/agent.okf.md", AGENT.replace("okf_version: v0.2", front))
                findings = okf_narrowing.check_release(self.release)
                self.assertEqual(len(findings), 1, findings)
                self.assertIn(needle, findings[0])

    def test_profile_and_version_refusals_are_named(self) -> None:
        for agent, needle in (
                (AGENT.replace("okf_version: v0.2", 'okf_version: "0.2"'), "unsupported zuno.profile None"),
                (AGENT.replace("okf_version: v0.2", 'okf_version: "0.2"')
                      .replace("  name: demo\n", '  profile: "2.0"\n  name: demo\n'),
                 "unsupported zuno.profile '2.0'"),
                (AGENT.replace("okf_version: v0.2", "okf_version: 0.2")
                      .replace("  name: demo\n", '  profile: "1.0"\n  name: demo\n'),
                 "unsupported okf_version 0.2"),
                (AGENT.replace("  name: demo\n", '  profile: "1.0"\n  name: demo\n'),
                 'zuno.profile is only valid with okf_version "0.2"')):
            with self.subTest(needle=needle):
                write(self.release / "agents/demo/agent.okf.md", agent)
                with self.assertRaises(ValueError) as caught:
                    admit.validate(self.release)
                self.assertIn(needle, str(caught.exception))
                self.assertIn("agents/demo/agent.okf.md", str(caught.exception))

    def test_unserved_knowledge_domain_is_a_warning(self) -> None:
        # WP-168: nothing serves the domain (no UnifAI source tagged with it).
        # Allowing it grants no access, so the release stays servable.
        write(admit.UNIFAI_RAG_SOURCE_FILES[1][0], "sources:\n  - {name: rh-x, tags: [product:x]}\n")
        errors, warnings = admit.validate(self.release)
        self.assertEqual(errors, [])
        self.assertTrue(any("which no UnifAI RAG source serves" in w for w in warnings), warnings)

    def test_knowledge_domain_served_by_a_rag_source_in_the_chart_values(self) -> None:
        write(admit.UNIFAI_RAG_SOURCE_FILES[1][0], "sources: []\n")
        write(admit.UNIFAI_RAG_SOURCE_FILES[0][0],
              "ragSources:\n  - {name: tech-satellite, tags: [knowledge.tech], type: confluence}\n")
        errors, warnings = admit.validate(self.release)
        self.assertEqual(errors, [])
        self.assertFalse(any("knowledge.tech" in w for w in warnings), warnings)


class ExperienceClientValidateTest(AdmitTestCase):
    """ADR-0592: an experience client's tools must be served, and its name is
    never an agent's."""

    def client(self, name: str, tool: str) -> None:
        write(self.release / f"experience-clients/{name}/client.okf.md",
              "---\nokf_version: v0.3\ntype: experience-client\nzuno:\n  name: " + name
              + "\n  tasks: [chat]\n  access: {groups: [sales]}\n---\n")
        write(self.release / f"experience-clients/{name}/tasks/chat.md",
              "---\nokf_version: v0.3\ntype: task\nzuno:\n  allowed_tools: [" + tool + "]\n---\n")

    def test_a_served_client_is_admitted(self) -> None:
        self.client("chat-ui", "search_docs")
        self.assertEqual(admit.validate(self.release)[0], [])
        self.assertEqual(admit.clients_view(self.release),
                         {"chat-ui": {"groups": ["sales"], "tasks": {"chat": ["search_docs"]}}})

    def test_a_client_tool_absent_from_the_policy_is_refused(self) -> None:
        self.client("chat-ui", "ghost")
        self.assertIn("(experience client) allows tool 'ghost', absent", admit.validate(self.release)[0][0])

    def test_a_client_named_like_an_agent_is_refused(self) -> None:
        self.client("demo", "search_docs")
        self.assertIn("has the name of an agent", " ".join(admit.validate(self.release)[0]))


class DiffTest(AdmitTestCase):
    def test_first_admission_lists_agents(self) -> None:
        self.assertIn("**demo** added", admit.diff(None, self.release))

    def test_no_change(self) -> None:
        self.assertEqual(admit.diff(self.release, self.copy()), "- no change in agents, routing or corp policies")

    def test_task_tools_groups_and_routing(self) -> None:
        new = self.copy()
        write(new / "agents/demo/agent.okf.md", AGENT.replace("[agent_demo]", "[agent_demo, board]"))
        write(new / "agents/demo/tasks/ask.md", TASK.replace("[search_docs]", "[search_docs, web_search]"))
        write(new / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [spare, local]}\n")
        text = admit.diff(self.release, new)
        self.assertIn("groups +board", text)
        self.assertIn("ask tools +web_search", text)
        self.assertIn("model routing `demo/ask`: models +spare", text)

    def test_reorder_only(self) -> None:
        write(self.release / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [local, spare]}\n")
        new = self.copy()
        write(new / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [spare, local]}\n")
        self.assertIn("order now spare, local", admit.diff(self.release, new))

    def test_corp_policy_added_and_changed(self) -> None:
        new = self.copy()
        write(new / "policies/quotas/quota-policy.yaml", "classes: {}\n")
        write(new / "policies/tools/tool-policy.yaml", "tools: []\n")
        text = admit.diff(self.release, new)
        self.assertIn("corp policy `quotas/quota-policy.yaml` added", text)
        self.assertIn("corp policy `tools/tool-policy.yaml` changed", text)


class LockAndArchiveTest(unittest.TestCase):
    def test_lock_round_trip_and_digest_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = pathlib.Path(tmp) / "agents.lock"
            self.assertIsNone(admit.read_lock(lock))
            ref = "quay.io/zuno/okf-corp@sha256:" + "a" * 64
            admit.write_lock(ref, "v0.1.1", lock)
            self.assertEqual(admit.read_lock(lock), ref)
            with self.assertRaises(admit.AdmissionError):
                admit.write_lock("quay.io/zuno/okf-corp:v0.1.1", "v0.1.1", lock)

    def test_archive_escape_is_refused(self) -> None:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz, tarfile.open(fileobj=gz, mode="w") as tar:
            info = tarfile.TarInfo("../escape.txt")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(admit.AdmissionError):
                admit._untar(buf.getvalue(), pathlib.Path(tmp) / "out")


class ConformanceLayerExtractTest(unittest.TestCase):
    """ADR-0508: extract() unpacks the optional conformance layer of a release."""

    def _tar(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def _extract(self, layers: list, clients: list = ()):
        index = {"agents": []}
        blobs = {"sha256:p": self._tar({"tools/x.yaml": b"a: 1\n"})}
        manifest_layers = [{"mediaType": "application/vnd.zuno.okf.policies.v1.tar+gzip", "digest": "sha256:p"}]
        for i, files in enumerate(layers):
            blobs[f"sha256:c{i}"] = self._tar(files)
            manifest_layers.append({"mediaType": admit.CONFORMANCE_MEDIA_TYPE, "digest": f"sha256:c{i}"})
        for i, files in enumerate(clients):
            blobs[f"sha256:x{i}"] = self._tar(files)
            manifest_layers.append({"mediaType": admit.CLIENTS_MEDIA_TYPE, "digest": f"sha256:x{i}"})
        saved = (admit.verify, admit.manifest, admit.fetch_blob)
        admit.verify = lambda reference, dev=False: index
        admit.manifest = lambda reference: {"layers": manifest_layers}
        admit.fetch_blob = lambda repository, digest: blobs[digest]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = pathlib.Path(tmp) / "release"
                admit.extract("r/okf-corp@sha256:1", out)
                return sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
        finally:
            admit.verify, admit.manifest, admit.fetch_blob = saved

    def test_the_cases_land_under_conformance(self) -> None:
        files = self._extract([{"cases/valid-x/expected.json": b"{}\n"}])
        self.assertIn("conformance/cases/valid-x/expected.json", files)

    def test_a_release_without_the_layer_still_extracts(self) -> None:
        files = self._extract([])
        self.assertEqual(files, ["okf-index.json", "policies/tools/x.yaml"])

    def test_the_clients_land_under_experience_clients(self) -> None:
        # ADR-0592: the optional clients layer of the corp artifact.
        files = self._extract([], clients=[{"open-webui/client.okf.md": b"---\n---\n",
                                            "open-webui/tasks/chat.md": b"---\n---\n"}])
        self.assertIn("experience-clients/open-webui/client.okf.md", files)
        self.assertIn("experience-clients/open-webui/tasks/chat.md", files)

    def test_two_conformance_layers_are_refused(self) -> None:
        with self.assertRaises(admit.AdmissionError):
            self._extract([{"cases/a": b"1"}, {"cases/b": b"2"}])


class MirrorTest(unittest.TestCase):
    """ADR-0611 / WP-246: the mirror copies by digest and is read back by digest."""

    CORP = "quay.io/zuno/okf-corp@sha256:" + "a" * 64
    AGENT = "quay.io/zuno/okf-tekos@sha256:" + "b" * 64
    MIRROR = "zot.example.svc:5000/okf"

    def test_reference_keeps_name_and_digest_and_changes_the_registry(self) -> None:
        self.assertEqual(admit.mirror_reference(self.AGENT, self.MIRROR + "/"),
                         "zot.example.svc:5000/okf/okf-tekos@sha256:" + "b" * 64)

    def test_reference_refuses_a_tag_and_a_bad_prefix(self) -> None:
        with self.assertRaises(admit.AdmissionError):
            admit.mirror_reference("quay.io/zuno/okf-corp:latest", self.MIRROR)
        for bad in ("", "/okf", "host@sha256:x", "host:"):
            with self.assertRaises(admit.AdmissionError):
                admit.mirror_reference(self.CORP, bad)

    def test_plain_http_is_only_for_the_mirror_host(self) -> None:
        admit.set_plain_http(self.MIRROR)
        try:
            self.assertEqual(admit._oras_http(self.MIRROR + "/okf-corp"), ["--plain-http"])
            self.assertEqual(admit._oras_http(self.CORP), [])
            self.assertEqual(admit._cosign_http(self.CORP), [])
            self.assertIn("--allow-http-registry", admit._cosign_http(self.MIRROR + "/x@sha256:1"))
        finally:
            admit.set_plain_http(None)

    def _run_mirror(self, fake_run, resolve_digest: str):
        calls = []
        saved = (admit.run, admit.require, admit.verify)
        verified = []
        admit.require = lambda b: b
        admit.run = lambda args, **k: fake_run(calls, args, resolve_digest)
        admit.verify = lambda ref, dev=False, mirror=None: (
            verified.append((ref, mirror)) or {"release": "0.0.1", "channel": "release",
                                               "agents": [{"name": "tekos", "version": "1", "reference": self.AGENT}]})
        try:
            return admit.mirror_release(self.CORP, self.MIRROR), calls, verified
        finally:
            admit.run, admit.require, admit.verify = saved

    @staticmethod
    def _resolve(args, resolve_digest):
        """What the mirror holds under the release tag: the pushed digest, unless the test says otherwise."""
        if resolve_digest != "same":
            return resolve_digest
        return "sha256:" + args[-1].rsplit("release-", 1)[1][:1] * 64

    def _ok(self, calls, args, resolve_digest):
        calls.append(args)
        return self._resolve(args, resolve_digest) if args[1] == "resolve" else ""

    def test_copies_every_artifact_with_its_sig_and_att_tags_and_verifies_from_the_mirror(self) -> None:
        index, calls, verified = self._run_mirror(self._ok, "same")
        copies = [c for c in calls if c[1] == "cp"]
        self.assertEqual(len(copies), 6)  # corp + agent, each: artifact, .sig, .att
        tags = [c[-1].rsplit(":", 1)[1] for c in copies]
        self.assertIn("sha256-" + "a" * 64 + ".sig", tags)
        self.assertIn("sha256-" + "b" * 64 + ".att", tags)
        self.assertTrue(all("-r" in c for c in copies))
        self.assertEqual(verified[0], (self.CORP, None))
        self.assertEqual(verified[1], ("zot.example.svc:5000/okf/okf-corp@sha256:" + "a" * 64, self.MIRROR))

    def test_a_digest_that_changed_on_the_way_is_refused(self) -> None:
        with self.assertRaises(admit.AdmissionError) as ctx:
            self._run_mirror(self._ok, "sha256:" + "c" * 64)
        self.assertIn("digest mismatch", str(ctx.exception))

    def test_a_missing_att_tag_is_skipped_but_other_failures_are_not(self) -> None:
        def missing(calls, args, resolve_digest):
            calls.append(args)
            if args[1] == "cp" and args[-1].endswith(".att"):
                raise admit.AdmissionError("oras cp failed: sha256-x.att: not found")
            return self._resolve(args, resolve_digest) if args[1] == "resolve" else ""

        index, calls, _ = self._run_mirror(missing, "same")
        self.assertEqual(index["release"], "0.0.1")

        def broken(calls, args, resolve_digest):
            calls.append(args)
            if args[1] == "cp" and args[-1].endswith(".sig"):
                raise admit.AdmissionError("oras cp failed: connection refused")
            return self._resolve(args, resolve_digest) if args[1] == "resolve" else ""

        with self.assertRaises(admit.AdmissionError):
            self._run_mirror(broken, "same")


class PruneTests(unittest.TestCase):
    """ADR-0611: the mirror keeps the last three locked releases and prunes the rest."""

    MIRROR = "zot.example.svc:5000/okf"
    CORP = {n: "a b c d".split()[n - 1] * 64 for n in (1, 2, 3, 4)}      # release n -> corp digest
    TEKOS = {n: "1 2 3 4".split()[n - 1] * 64 for n in (1, 2, 3, 4)}     # release n -> tekos digest

    def _src(self, n: int) -> str:
        return "quay.io/zuno/okf-corp@sha256:" + self.CORP[n]

    def _world(self, releases, missing_layer=()):
        """A fake mirror holding `releases`, with the commands prune issues through oras; returns (calls, restore)."""
        calls, deletes = [], []
        tags = {"okf/okf-corp": [], "okf/okf-tekos": []}
        digest_of = {}
        for n in releases:
            for repo, d in (("okf/okf-corp", self.CORP[n]), ("okf/okf-tekos", self.TEKOS[n])):
                tags[repo] += [f"release-{d[:12]}", f"sha256-{d}.sig", f"sha256-{d}.att"]
                digest_of[(repo, f"release-{d[:12]}")] = "sha256:" + d

        def fake_run(args, **_kw):
            calls.append(args)
            cmd = args[1:3]
            if cmd == ["repo", "ls"]:
                return "\n".join(tags) + "\nother/thing\n"
            if cmd == ["repo", "tags"]:
                return "\n".join(tags[args[-1].split("/", 1)[1]]) + "\n"
            if args[1] == "resolve":
                repo, tag = args[-1].split("/", 1)[1].rsplit(":", 1)
                return digest_of[(repo, tag)] + "\n"
            if args[1] == "discover":
                return "{}"
            if cmd == ["manifest", "delete"]:
                deletes.append(args[-1])
                return ""
            raise AssertionError(args)

        def fake_layer(reference, media_type):
            digest = reference.split("@sha256:")[1]
            n = next(k for k, v in self.CORP.items() if v == digest)
            if n in missing_layer or n not in releases:
                raise admit.AdmissionError("not found")
            return ('{"release": "0.0.%d", "agents": [{"name": "tekos", "reference": '
                    '"quay.io/zuno/okf-tekos@sha256:%s"}]}' % (n, self.TEKOS[n])).encode()

        saved = (admit.run, admit.require, admit._layer)
        admit.run, admit.require, admit._layer = fake_run, (lambda b: b), fake_layer
        self.addCleanup(lambda: setattr(admit, "run", saved[0]))
        self.addCleanup(lambda: setattr(admit, "require", saved[1]))
        self.addCleanup(lambda: setattr(admit, "_layer", saved[2]))
        return deletes

    def _history(self, *ns):
        return [self._src(n) for n in ns]

    def test_keeps_the_last_three_and_lists_the_oldest_in_a_dry_run(self) -> None:
        deletes = self._world([1, 2, 3, 4])
        result = admit.prune_mirror(self.MIRROR, 3, False, self._history(4, 3, 2))
        listed = [ref for _kind, ref in result["candidates"]]
        d1, t1 = self.CORP[1], self.TEKOS[1]
        self.assertEqual(
            sorted(listed),
            sorted([f"zot.example.svc:5000/okf/okf-corp@sha256:{d1}", f"zot.example.svc:5000/okf/okf-tekos@sha256:{t1}",
                    f"zot.example.svc:5000/okf/okf-corp:sha256-{d1}.sig", f"zot.example.svc:5000/okf/okf-corp:sha256-{d1}.att",
                    f"zot.example.svc:5000/okf/okf-tekos:sha256-{t1}.sig", f"zot.example.svc:5000/okf/okf-tekos:sha256-{t1}.att"]))
        self.assertEqual(deletes, [])  # a dry run deletes nothing
        self.assertFalse(result["applied"])

    def test_apply_deletes_exactly_what_the_dry_run_listed(self) -> None:
        deletes = self._world([1, 2, 3, 4])
        planned = admit.prune_mirror(self.MIRROR, 3, False, self._history(4, 3, 2))["candidates"]
        admit.prune_mirror(self.MIRROR, 3, True, self._history(4, 3, 2))
        self.assertEqual(sorted(deletes), sorted(ref for _k, ref in planned))

    def test_a_first_install_with_one_release_prunes_nothing(self) -> None:
        deletes = self._world([4])
        result = admit.prune_mirror(self.MIRROR, 3, True, self._history(4))
        self.assertEqual(result["candidates"], [])
        self.assertEqual(deletes, [])

    def test_a_kept_release_the_mirror_never_received_is_skipped(self) -> None:
        deletes = self._world([1, 2, 4])  # release 3 was promoted but never fed to the mirror
        result = admit.prune_mirror(self.MIRROR, 3, True, self._history(4, 3, 2))
        self.assertEqual(result["absent"], [self._src(3)])
        self.assertTrue(deletes)
        self.assertTrue(all(self.CORP[1] in d or self.TEKOS[1] in d for d in deletes))  # only release 1 goes

    def test_it_refuses_to_run_when_the_locked_release_is_not_on_the_mirror(self) -> None:
        self._world([1, 2, 3])  # the lock names release 4, never mirrored
        with self.assertRaises(admit.AdmissionError) as ctx:
            admit.prune_mirror(self.MIRROR, 3, True, self._history(4, 3, 2))
        self.assertIn("does not hold the locked release", str(ctx.exception))

    def test_the_history_is_the_last_distinct_digests_of_the_lock_newest_first(self) -> None:
        locks = {"h1": self._src(4), "h2": self._src(4), "h3": self._src(3), "h4": self._src(2), "h5": self._src(1)}

        def git(args):
            if args[0] == "log":
                return "\n".join(locks) + "\n"
            return "# release\n" + locks[args[1].split(":", 1)[0]] + "\n"

        self.assertEqual(admit.lock_history(3, git), self._history(4, 3, 2))
        self.assertEqual(admit.lock_history(5, git), self._history(4, 3, 2, 1))


class QuayPruneTests(unittest.TestCase):
    """ADR-0612: the same retention on Red Hat Quay, by tag deletion through its API."""

    MIRROR = "quay.example.svc/zuno"
    CORP = {1: "a" * 64, 2: "b" * 64, 3: "c" * 64, 4: "d" * 64}
    TEKOS = {1: "1" * 64, 2: "2" * 64, 3: "3" * 64, 4: "4" * 64}

    def _src(self, n: int) -> str:
        return "quay.io/zuno/okf-corp@sha256:" + self.CORP[n]

    def _world(self, releases, page_size=100):
        calls = []
        repos = {"okf-corp": self.CORP, "okf-tekos": self.TEKOS}

        def tags_of(name):
            out = []
            for n in releases:
                d = repos[name][n]
                out += [{"name": f"release-{d[:12]}", "manifest_digest": "sha256:" + d},
                        {"name": f"sha256-{d}", "manifest_digest": "sha256:" + "7" * 64},
                        {"name": f"sha256-{d}.sig", "manifest_digest": "sha256:" + "9" * 64},
                        {"name": f"sha256-{d}.att", "manifest_digest": "sha256:" + "8" * 64}]
            return out

        def http(method, url, token):
            calls.append((method, url, token))
            if method == "DELETE":
                return None
            if "/repository?namespace=zuno" in url:
                return {"repositories": [{"name": "okf-corp"}, {"name": "okf-tekos"}]}
            name = url.split("/zuno/")[1].split("/")[0]
            page = int(url.rsplit("page=", 1)[1])
            tags = tags_of(name)
            chunk = tags[(page - 1) * page_size: page * page_size]
            return {"tags": chunk, "has_additional": page * page_size < len(tags)}

        def fake_layer(reference, media_type):
            digest = reference.split("@sha256:")[1]
            n = next(k for k, v in self.CORP.items() if v == digest)
            if n not in releases:
                raise admit.AdmissionError("not found")
            return ('{"release": "0.0.%d", "agents": [{"name": "tekos", "reference": '
                    '"quay.io/zuno/okf-tekos@sha256:%s"}]}' % (n, self.TEKOS[n])).encode()

        saved = admit._layer
        admit._layer = fake_layer
        self.addCleanup(lambda: setattr(admit, "_layer", saved))
        return calls, http

    def _history(self, *ns):
        return [self._src(n) for n in ns]

    def test_a_dry_run_lists_the_oldest_release_tags_and_deletes_nothing(self) -> None:
        calls, http = self._world([1, 2, 3, 4])
        result = admit.prune_quay(self.MIRROR, "tok", 3, False, self._history(4, 3, 2), http)
        d1, t1 = self.CORP[1], self.TEKOS[1]
        self.assertEqual(sorted(ref for _k, ref in result["candidates"]), sorted([
            f"zuno/okf-corp:release-{d1[:12]}", f"zuno/okf-corp:sha256-{d1}", f"zuno/okf-corp:sha256-{d1}.sig",
            f"zuno/okf-corp:sha256-{d1}.att", f"zuno/okf-tekos:release-{t1[:12]}", f"zuno/okf-tekos:sha256-{t1}",
            f"zuno/okf-tekos:sha256-{t1}.sig", f"zuno/okf-tekos:sha256-{t1}.att"]))
        self.assertFalse([c for c in calls if c[0] == "DELETE"])

    def test_apply_deletes_exactly_the_listed_tags_with_the_token(self) -> None:
        calls, http = self._world([1, 2, 3, 4])
        planned = admit.prune_quay(self.MIRROR, "tok", 3, False, self._history(4, 3, 2), http)["candidates"]
        calls.clear()
        admit.prune_quay(self.MIRROR, "tok", 3, True, self._history(4, 3, 2), http)
        deletes = [c for c in calls if c[0] == "DELETE"]
        self.assertEqual(len(deletes), len(planned))
        self.assertTrue(all(c[2] == "tok" and c[1].startswith("https://quay.example.svc/api/v1/repository/zuno/") for c in deletes))
        self.assertIn(f"https://quay.example.svc/api/v1/repository/zuno/okf-corp/tag/release-{self.CORP[1][:12]}",
                      [c[1] for c in deletes])

    def test_every_page_of_tags_is_read(self) -> None:
        _calls, http = self._world([1, 2, 3, 4], page_size=4)
        result = admit.prune_quay(self.MIRROR, "tok", 3, False, self._history(4, 3, 2), http)
        self.assertEqual(len(result["candidates"]), 8)

    def test_it_refuses_when_the_locked_release_is_not_on_quay(self) -> None:
        _calls, http = self._world([1, 2, 3])
        with self.assertRaises(admit.AdmissionError):
            admit.prune_quay(self.MIRROR, "tok", 3, True, self._history(4, 3, 2), http)


if __name__ == "__main__":
    unittest.main()

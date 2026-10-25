"""Tests for platform/okf/generate_stack_config.py (WP-164).

Run from the repository root:
    python3 platform/okf/tests/test_generate_stack_config.py
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import generate_stack_config as gen  # noqa: E402
import yaml  # noqa: E402

AGENT = """---
okf_version: v0.2
type: agent
title: {name}
zuno:
  name: {name}
  tasks: [one, two]
  access: {{groups: [agent_{name}]}}
  model: {{preferred_classification: C2}}
---
"""
TASK = """---
okf_version: v0.2
type: task
title: t
zuno:
  allowed_tools: {tools}
  allowed_knowledge: {domains}
---
"""


class GenerateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp())
        for name in ("beta", "alpha"):
            agent = self.dir / "agents" / name
            (agent / "tasks").mkdir(parents=True)
            (agent / "agent.okf.md").write_text(AGENT.format(name=name))
            (agent / "tasks" / "one.md").write_text(TASK.format(tools="[web_search]", domains="[knowledge.tech]"))
            (agent / "tasks" / "two.md").write_text(TASK.format(tools="[search_confluence, web_search]",
                                                                domains="[]"))
        (self.dir / "okf-index.json").write_text(json.dumps({
            "release": "0.2.0", "channel": "release",
            "agents": [{"name": n, "version": "1.0.0", "okfVersion": "v0.2",
                        "reference": f"quay.io/zuno/okf-{n}@sha256:{c * 64}"}
                       for n, c in (("alpha", "a"), ("beta", "b"))],
        }))

    def tearDown(self) -> None:
        shutil.rmtree(self.dir)

    def test_derived_configuration(self) -> None:
        config = gen.build(self.dir, "quay.io/zuno/okf-corp@sha256:" + "c" * 64)
        self.assertEqual(config["release"], "0.2.0")
        self.assertEqual(config["keycloak"]["groups"], ["agent_alpha", "agent_beta"])
        alpha = config["agents"]["alpha"]
        self.assertEqual(alpha["toolCapabilities"], ["search_confluence", "web_search"])
        self.assertEqual(alpha["knowledgeDomains"], ["knowledge.tech"])
        self.assertEqual(alpha["tasks"], ["one", "two"])
        self.assertEqual([b["name"] for b in config["unifai"]["bundles"]], ["alpha", "beta"])
        bundle = config["unifai"]["bundles"][0]
        self.assertTrue(bundle["reference"].endswith("a" * 64))
        self.assertEqual(bundle["ceilings"], {"toolCapabilities": ["search_confluence", "web_search"],
                                              "knowledgeDomains": ["knowledge.tech"],
                                              "minClassification": "C2"})

    def test_render_is_stable_and_alias_free(self) -> None:
        text = gen.render(gen.build(self.dir, None))
        self.assertEqual(text, gen.render(gen.build(self.dir, None)))
        self.assertNotIn("&id", text)
        self.assertTrue(text.startswith("# GENERATED"))
        self.assertEqual(yaml.safe_load(text)["agents"]["beta"]["version"], "1.0.0")

    def test_no_release_pinned(self) -> None:
        config = gen.build(None, None)
        self.assertEqual(config["unifai"]["bundles"], [])
        self.assertIsNone(config["release"])
        self.assertIn("publish", config["unifai"]["verify"]["keyless"]["subjectRegExp"])

    def test_keyless_identity_comes_from_identity_yaml(self) -> None:
        keyless = gen.build(self.dir, None)["unifai"]["verify"]["keyless"]
        self.assertEqual(keyless["issuer"], "https://token.actions.githubusercontent.com")
        self.assertTrue(keyless["subjectRegExp"].endswith("publish\\.yml@refs/tags/v"))


CATALOG = """models:
- {name: local-big-maas, kind: local, role: quality, eligible_for: [C1, C2, C3]}
- {name: local-big, kind: local, role: quality, eligible_for: [C1, C2, C3]}
- {name: local-small-maas, kind: local, role: default, eligible_for: [C1, C2, C3]}
- {name: local-secret-maas, kind: local, role: reasoning, eligible_for: [C3]}
- {name: saas-one, kind: saas, role: general-external, eligible_for: [C1, C2]}
"""
ROUTING = {"providers": [
    {"name": "local-big-maas", "kind": "local", "model": "big", "via_maas": True,
     "endpoint": "https://maas.svc/zuno-ai-run/big-pub/v1"},
    {"name": "local-big", "kind": "local", "model": "big", "endpoint": "https://big.svc:8000/v1"},
    {"name": "local-small-maas", "kind": "local", "model": "small", "via_maas": True,
     "endpoint": "https://maas.svc/zuno-ai-run/small-pub/v1/"},
    {"name": "local-secret-maas", "kind": "local", "model": "secret", "via_maas": True,
     "endpoint": "https://maas.svc/zuno-ai-run/secret-pub/v1"},
    {"name": "saas-one", "kind": "saas", "model": "x"},
]}


class MaasSubscriptionsTest(unittest.TestCase):
    """ADR-0581 clause 2: groups x the local MaaS models each active agent can reach."""

    def setUp(self) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp())
        (self.dir / "policies" / "models").mkdir(parents=True)
        (self.dir / "policies" / "model-routing").mkdir(parents=True)
        (self.dir / "policies" / "models" / "model-catalog.yaml").write_text(CATALOG)
        (self.dir / "policies" / "model-routing" / "model-routing-policy.yaml").write_text("preferences: []\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.dir)

    def agent(self, name, groups, classification="C2", status="active", tasks=None, models=None):
        tasks = tasks or {"one": None}
        agent = self.dir / "agents" / name
        (agent / "tasks").mkdir(parents=True)
        z = {"name": name, "tasks": list(tasks), "access": {"groups": groups}, "status": status,
             "model": {"preferred_classification": classification}}
        if models:
            z["models"] = models
        (agent / "agent.okf.md").write_text("---\n" + yaml.safe_dump({"okf_version": "v0.3", "type": "agent",
                                                                     "title": name, "zuno": z}) + "---\n")
        for task, task_models in tasks.items():
            tz = {"allowed_tools": [], "allowed_knowledge": []}
            if task_models:
                tz["models"] = task_models
            (agent / "tasks" / f"{task}.md").write_text("---\n" + yaml.safe_dump(
                {"okf_version": "v0.3", "type": "task", "title": task, "zuno": tz}) + "---\n")

    def subs(self):
        return gen.maas_agent_subscriptions(self.dir, gen.admit.agents_view(self.dir), ROUTING)

    def test_published_models_follow_the_via_maas_endpoint(self) -> None:
        self.assertEqual(gen.published_models(ROUTING), {
            "local-big-maas": "big-pub", "local-big": "big-pub",
            "local-small-maas": "small-pub", "local-secret-maas": "secret-pub"})

    def test_active_agents_reach_every_eligible_local_model_saas_and_placeholders_never(self) -> None:
        self.agent("alpha", ["agent_alpha", "agent_alpha_preview"], classification="C1")
        self.agent("beta", ["agent_beta"], classification="C3")
        self.agent("ghost", ["agent_ghost"], status="placeholder")
        self.assertEqual(self.subs(), {
            "big-pub": {"agents": ["alpha", "beta"],
                        "groups": ["/agent_alpha", "/agent_alpha_preview", "/agent_beta"]},
            # eligible for C3 only: a C1 agent never sends data that may reach it
            "secret-pub": {"agents": ["beta"], "groups": ["/agent_beta"]},
            "small-pub": {"agents": ["alpha", "beta"],
                          "groups": ["/agent_alpha", "/agent_alpha_preview", "/agent_beta"]},
        })

    def test_strict_preference_narrows_and_plain_preference_does_not(self) -> None:
        (self.dir / "policies" / "model-routing" / "model-routing-policy.yaml").write_text(yaml.safe_dump({
            "preferences": [
                {"agent": "alpha", "task": "one", "prefer": ["local-small-maas"], "strict": True},
                {"agent": "beta", "task": "one", "preferred": ["local-small-maas"]},
            ]}))
        self.agent("alpha", ["agent_alpha"])
        self.agent("beta", ["agent_beta"])
        subs = self.subs()
        self.assertEqual(subs["small-pub"]["agents"], ["alpha", "beta"])
        self.assertEqual(subs["big-pub"]["agents"], ["beta"])

    def test_forbidden_roles_narrow_and_preferred_roles_only_reorder(self) -> None:
        self.agent("alpha", ["agent_alpha"], tasks={"one": {"forbidden": ["quality"]}})
        self.agent("beta", ["agent_beta"], models={"forbidden": ["default"]})
        self.agent("gamma", ["agent_gamma"], tasks={"one": {"preferred": ["default"]}})
        subs = self.subs()
        self.assertEqual(subs["big-pub"]["agents"], ["beta", "gamma"])
        self.assertEqual(subs["small-pub"]["agents"], ["alpha", "gamma"])

    def test_one_task_reaching_a_model_is_enough(self) -> None:
        self.agent("alpha", ["agent_alpha"], tasks={"one": {"forbidden": ["quality"]}, "two": None})
        self.assertEqual(self.subs()["big-pub"]["agents"], ["alpha"])

    def test_render_maas_golden(self) -> None:
        self.agent("alpha", ["agent_alpha"], classification="C1")
        config = {"maas": {"agentSubscriptions": self.subs()}}
        self.assertEqual(gen.render_maas(config), gen.MAAS_HEADER + """maas:
  agentSubscriptions:
    big-pub:
      agents:
      - alpha
      groups:
      - /agent_alpha
    small-pub:
      agents:
      - alpha
      groups:
      - /agent_alpha
""")

    def test_no_release_pinned_gives_no_subscription(self) -> None:
        self.assertEqual(gen.render_maas(gen.build(None, None)),
                         gen.MAAS_HEADER + "maas:\n  agentSubscriptions: {}\n")


class ModelRoutingTest(MaasSubscriptionsTest):
    """ADR-0581 amendment (WP-164 lot 2): the corp routing policy, reordered by roles, forbidden as exclude."""

    def corp(self, doc) -> None:
        (self.dir / "policies" / "model-routing" / "model-routing-policy.yaml").write_text(
            yaml.safe_dump(doc, sort_keys=False))

    def routing(self):
        return gen.model_routing(self.dir, gen.admit.agents_view(self.dir))

    def test_roles_in_corp_order_leave_the_entry_unchanged(self) -> None:
        entry = {"agent": "alpha", "task": "one", "preferred": ["local-big-maas", "local-small-maas"],
                 "fallback": ["saas-one"], "local_only_for": ["C2"]}
        self.corp({"adapters": [{"agent": "alpha", "task": "one", "adapter": "a-lora"}], "preferences": [entry]})
        self.agent("alpha", ["agent_alpha"], tasks={"one": {"preferred": ["quality", "default"]}})
        self.assertEqual(self.routing(), {"adapters": [{"agent": "alpha", "task": "one", "adapter": "a-lora"}],
                                          "preferences": [entry]})

    def test_task_roles_reorder_the_corp_candidates_and_keep_strict(self) -> None:
        self.corp({"preferences": [{"agent": "alpha", "task": "one", "strict": True,
                                    "prefer": ["local-big-maas", "local-small-maas", "saas-one"]}]})
        self.agent("alpha", ["agent_alpha"], tasks={"one": {"preferred": ["default"]}})
        self.assertEqual(self.routing()["preferences"], [
            {"agent": "alpha", "task": "one", "strict": True,
             "prefer": ["local-small-maas", "local-big-maas", "saas-one"]}])

    def test_agent_roles_apply_when_the_task_has_none_and_never_add_a_model(self) -> None:
        self.corp({"preferences": [{"agent": "alpha", "task": "one", "prefer": ["local-big", "saas-one"]}]})
        self.agent("alpha", ["agent_alpha"], models={"preferred": ["general-external", "reasoning"]})
        prefs = self.routing()["preferences"]
        self.assertEqual(prefs, [{"agent": "alpha", "task": "one", "prefer": ["saas-one", "local-big"]}])

    def test_forbidden_roles_of_agent_and_task_become_exclude(self) -> None:
        self.corp({"preferences": [{"agent": "alpha", "task": "one", "prefer": ["local-big-maas"]}]})
        self.agent("alpha", ["agent_alpha"], models={"forbidden": ["general-external"]},
                   tasks={"one": {"forbidden": ["quality"]}})
        self.assertEqual(self.routing()["preferences"], [
            {"agent": "alpha", "task": "one", "prefer": ["local-big-maas"],
             "exclude": ["local-big-maas", "local-big", "saas-one"]}])

    def test_task_without_a_corp_entry_gets_a_prefer_list_from_its_roles(self) -> None:
        self.corp({"preferences": [{"agent": "other", "task": "x", "prefer": ["saas-one"]}]})
        self.agent("alpha", ["agent_alpha"], tasks={"one": {"preferred": ["default", "quality"]},
                                                    "two": {"forbidden": ["reasoning"]}, "three": None})
        self.assertEqual(self.routing()["preferences"], [
            {"agent": "other", "task": "x", "prefer": ["saas-one"]},
            {"agent": "alpha", "task": "one", "prefer": ["local-small-maas", "local-big-maas", "local-big"]},
            {"agent": "alpha", "task": "two", "exclude": ["local-secret-maas"]},
        ])

    def test_render_model_routing_golden(self) -> None:
        self.corp({"adapters": [], "preferences": [{"agent": "alpha", "task": "one", "prefer": ["local-big"]}]})
        self.agent("alpha", ["agent_alpha"])
        self.assertEqual(gen.render_model_routing({"modelRouting": self.routing()}), gen.MODEL_ROUTING_HEADER + """adapters: []
preferences:
- agent: alpha
  task: one
  prefer:
  - local-big
""")

    def test_no_release_pinned_gives_an_empty_policy(self) -> None:
        self.assertEqual(gen.render_model_routing(gen.build(None, None)),
                         gen.MODEL_ROUTING_HEADER + "adapters: []\npreferences: []\n")


if __name__ == "__main__":
    unittest.main()

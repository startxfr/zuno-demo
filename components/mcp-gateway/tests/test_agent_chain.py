"""ADR-0401 / ADR-0403 / ADR-0406 (WP-172): the agent delegation chain.

Synthetic agents and a synthetic tool policy (so the test does not depend on the
admitted release carrying delegation or `access`), run through the real
`policy.evaluate` and, for the header handling, the real REST and /mcp endpoints.

  alpha  (active, C1)  delegates to beta/ask, max_depth 1
  beta   (active, C2)  declares confluence.page.search (read) and confluence.page.create (write)
  gamma  (active, C1)  delegates to alpha/ask (a chain of two)
  mid    (active, C1)  delegates to alpha/ask, default max_depth 1
  top    (active, C1)  delegates to gamma/ask with max_depth 3 (above the corp ceiling 2)
  idle   (placeholder) an inactive target

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_agent_chain.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("TOOL_BINDINGS_PATH", str(_REPO_ROOT / "platform/bindings/tools/tool-bindings.yaml"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from app.agent_chain import Chain, ChainError, DelegationLimits, Hop, parse_chain, verify_chain  # noqa: E402
from app.agent_declarations import AgentDeclarationStore  # noqa: E402
from app.policy import PolicyStore, evaluate  # noqa: E402

READ, WRITE = "confluence.page.search", "confluence.page.create"


def _md(front: dict) -> str:
    return "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\nbody\n"


def _agent(name, status="active", classification="C1", groups=None, tools=(), targets=(), depth=None):
    zuno = {"name": name, "status": status, "tasks": ["ask"], "model": {"preferred_classification": classification},
            "access": {"groups": groups if groups is not None else [f"agent_{name}"]}}
    if targets:
        zuno["delegation"] = {"targets": [{"agent": a, "task": t} for a, t in targets]}
    if depth:
        zuno["limits"] = {"delegation": {"max_depth": depth}}
    return (_md({"okf_version": "v0.3", "type": "agent", "title": name, "zuno": zuno}),
            _md({"okf_version": "v0.3", "type": "task", "title": "ask", "zuno": {"allowed_tools": list(tools)}}))


def _build() -> tuple:
    root = pathlib.Path(tempfile.mkdtemp())
    agents = {
        "alpha": _agent("alpha", targets=[("beta", "ask")]),
        "beta": _agent("beta", classification="C2", tools=[READ, WRITE]),
        "gamma": _agent("gamma", targets=[("alpha", "ask")], depth=3),
        "mid": _agent("mid", targets=[("alpha", "ask")]),
        "top": _agent("top", targets=[("gamma", "ask")], depth=3),
        "idle": _agent("idle", status="placeholder", targets=[]),
        "hasidle": _agent("hasidle", targets=[("idle", "ask")]),
        "highc": _agent("highc", classification="C3", targets=[("beta", "ask")]),
    }
    for name, (index, task) in agents.items():
        (root / "agents" / name / "tasks").mkdir(parents=True)
        (root / "agents" / name / "agent.okf.md").write_text(index)
        (root / "agents" / name / "tasks" / "ask.md").write_text(task)
    (root / "tool-policy.yaml").write_text(yaml.safe_dump({"tools": [
        {"tool": READ, "capability": READ, "mcp_server": "confluence", "min_classification": "C2",
         "allowed_groups": ["consultant"], "access": "read"},
        {"tool": WRITE, "capability": WRITE, "mcp_server": "confluence", "min_classification": "C2",
         "allowed_groups": ["consultant"], "access": "write"}]}))
    (root / "limits.yaml").write_text("max_delegation_depth: 2\ndelegation:\n  allow_write: false\n")
    return (AgentDeclarationStore(str(root / "agents")), PolicyStore(str(root / "tool-policy.yaml"), str(root / "none.yaml")),
            DelegationLimits(str(root / "limits.yaml")), root)


USER = ["consultant", "agent_alpha", "agent_beta", "agent_gamma", "agent_mid", "agent_top", "agent_hasidle", "agent_highc"]


class ParseChain(unittest.TestCase):
    def test_no_headers_is_a_direct_call(self):
        self.assertFalse(parse_chain("", ""))
        self.assertFalse(parse_chain(None, None))

    def test_a_valid_chain_round_trips(self):
        chain = parse_chain("alpha:ask,beta:ask", "2")
        self.assertEqual(chain.hops, (Hop("alpha", "ask"), Hop("beta", "ask")))
        self.assertEqual((chain.depth, chain.render()), (2, "alpha:ask,beta:ask"))

    def test_refusals_by_name(self):
        for by, depth, needle in (("alpha:ask", "", "must be sent together"), ("", "1", "must be sent together"),
                                  ("alpha", "1", "malformed"), ("Alpha:ask", "1", "malformed"),
                                  ("alpha:ask", "2", "does not match"), ("alpha:ask", "x", "does not match"),
                                  (",".join(["a:b"] * 9), "9", "more than")):
            with self.assertRaises(ChainError) as caught:
                parse_chain(by, depth)
            self.assertIn(needle, str(caught.exception), (by, depth))


class VerifyAndEvaluate(unittest.TestCase):
    def setUp(self):
        self.agents, self.store, self.limits, _ = _build()

    def decide(self, chain, agent="beta", tool=READ, groups=None, classification="C2"):
        return evaluate(self.store, self.agents, tool, agent, "ask", groups if groups is not None else USER,
                        classification, [tool], chain=parse_chain(*chain) if chain else None, limits=self.limits)

    def test_a_direct_call_is_unchanged(self):
        self.assertTrue(self.decide(None).allowed)
        self.assertTrue(self.decide(None, tool=WRITE).allowed, "no chain: a write is decided as before")

    def test_a_declared_delegation_of_a_read_tool_is_allowed(self):
        decision = self.decide(("alpha:ask", "1"))
        self.assertTrue(decision.allowed, decision.reason)

    def test_the_delegators_own_tools_are_not_intersected(self):
        # alpha declares no tool at all: delegating exists so beta can do what alpha cannot.
        self.assertEqual(self.agents.get("alpha").declared_tools(), [])
        self.assertTrue(self.decide(("alpha:ask", "1")).allowed)

    def test_an_undeclared_target_is_refused(self):
        decision = self.decide(("alpha:ask", "1"), agent="gamma")
        self.assertFalse(decision.allowed)
        self.assertIn("does not declare 'gamma/ask' as a delegation target", decision.reason)

    def test_a_target_the_user_is_not_entitled_to_is_refused(self):
        decision = self.decide(("alpha:ask", "1"), groups=["consultant", "agent_alpha"])
        self.assertFalse(decision.allowed)
        self.assertIn("not entitled to agent 'beta'", decision.reason)

    def test_an_inactive_target_is_refused(self):
        decision = self.decide(("hasidle:ask", "1"), agent="idle", groups=USER + ["agent_idle"])
        self.assertFalse(decision.allowed)
        self.assertIn("'placeholder', not active", decision.reason)

    def test_an_unknown_agent_in_the_chain_is_refused(self):
        decision = self.decide(("ghost:ask", "1"))
        self.assertFalse(decision.allowed)
        self.assertIn("unknown agent 'ghost'", decision.reason)

    def test_the_origin_agents_max_depth_bounds_the_chain(self):
        # gamma (max_depth 3, corp ceiling 2) -> alpha -> beta: two hops, allowed.
        self.assertTrue(self.decide(("gamma:ask,alpha:ask", "2")).allowed)
        # mid declares no max_depth (default 1): mid -> alpha -> beta is two hops, refused.
        refused = self.decide(("mid:ask,alpha:ask", "2"))
        self.assertFalse(refused.allowed)
        self.assertIn("exceeds the limit 1", refused.reason)

    def test_depth_above_the_corp_ceiling_is_refused_whatever_the_agent_asks(self):
        # top declares max_depth 3, but the corp ceiling is 2: top -> gamma -> alpha -> beta is three hops.
        refused = self.decide(("top:ask,gamma:ask,alpha:ask", "3"))
        self.assertFalse(refused.allowed)
        self.assertIn("corp ceiling 2", refused.reason)

    def test_a_cycle_is_refused(self):
        decision = self.decide(("gamma:ask,alpha:ask", "2"), agent="gamma")
        self.assertFalse(decision.allowed)
        self.assertIn("cycle", decision.reason)

    def test_a_delegated_write_is_refused_until_allowed(self):
        decision = self.decide(("alpha:ask", "1"), tool=WRITE)
        self.assertFalse(decision.allowed)
        self.assertIn("delegated writes are refused", decision.reason)
        self.limits.allow_write = True
        self.assertTrue(self.decide(("alpha:ask", "1"), tool=WRITE).allowed)

    def test_a_delegation_with_no_limits_object_is_refused_not_allowed(self):
        decision = evaluate(self.store, self.agents, READ, "beta", "ask", USER, "C2", [READ],
                            chain=parse_chain("alpha:ask", "1"), limits=None)
        self.assertFalse(decision.allowed)

    def test_the_classification_is_the_targets_own_header_never_derived(self):
        # ADR-0565: a run's level only rises, in the agents' runs. The gateway judges the header it receives:
        # a C1 header still cannot reach beta's C2 tools even when a C3 agent delegates ...
        low = self.decide(("highc:ask", "1"), classification="C1")
        self.assertFalse(low.allowed)
        self.assertIn("requires a request context cleared for at least C2", low.reason)
        # ... and a C3 header from the same chain is accepted (beta's tools need C2 at least).
        self.assertTrue(self.decide(("highc:ask", "1"), classification="C3").allowed)


class EndpointHeaders(unittest.TestCase):
    """The same chain through the real REST and /mcp endpoints."""

    @classmethod
    def setUpClass(cls):
        agents, store, limits, root = _build()
        os.environ.setdefault("TOOL_POLICY_PATH", str(root / "tool-policy.yaml"))
        os.environ.setdefault("AGENTS_DIR", str(root / "agents"))
        os.environ.setdefault("LIMITS_POLICY_PATH", str(root / "limits.yaml"))
        from fastapi.testclient import TestClient

        import app.main as gateway_main
        from app.auth import CallerIdentity, validate_token, validate_token_or_kubernetes

        cls.main, cls.TestClient = gateway_main, TestClient
        gateway_main.agent_declarations, gateway_main.policy_store = agents, store
        gateway_main.delegation_limits = limits
        cls.identity = CallerIdentity(sub="user-01", groups=USER, raw_claims={"iss": "zuno"}, token="jwt")
        gateway_main.app.dependency_overrides[validate_token] = lambda: cls.identity
        gateway_main.app.dependency_overrides[validate_token_or_kubernetes] = lambda: cls.identity

        async def fake_downstream(*args, **kwargs):
            return {"ok": True}

        gateway_main.invoke_downstream = fake_downstream
        cls.client = TestClient(gateway_main.app)

    @classmethod
    def tearDownClass(cls):
        cls.main.app.dependency_overrides.clear()

    def invoke(self, tool, **headers):
        base = {"X-Zuno-Agent": "beta", "X-Zuno-Task": "ask", "X-Zuno-Data-Classification": "C2"}
        return self.client.post(f"/v1/tools/{tool}/invoke", json={}, headers={**base, **headers})

    def test_rest_direct_delegated_read_and_refusals(self):
        self.assertEqual(self.invoke(READ).status_code, 200)
        self.assertEqual(self.invoke(WRITE).status_code, 200, "a direct write is unchanged")
        chain = {"X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "1"}
        self.assertEqual(self.invoke(READ, **chain).status_code, 200)
        refused = self.invoke(WRITE, **chain)
        self.assertEqual(refused.status_code, 403)
        self.assertIn("delegated writes are refused", refused.json()["detail"])

    def test_rest_malformed_or_half_a_chain_is_a_403(self):
        for headers in ({"X-Zuno-Delegated-By": "alpha:ask"}, {"X-Zuno-Delegation-Depth": "1"},
                        {"X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "2"}):
            resp = self.invoke(READ, **headers)
            self.assertEqual(resp.status_code, 403, headers)

    def test_rest_a_chain_without_an_agent_is_refused(self):
        resp = self.client.post(f"/v1/tools/{READ}/invoke", json={}, headers={
            "X-Zuno-Data-Classification": "C2", "X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "1"})
        self.assertEqual(resp.status_code, 403)

    def test_mcp_lists_and_calls_through_the_chain(self):
        headers = {"X-Zuno-Agent": "beta", "X-Zuno-Task": "ask", "X-Zuno-Data-Classification": "C2",
                   "X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "1"}
        listed = self.client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        names = {t["name"] for t in listed.json()["result"]["tools"]}
        self.assertEqual(names, {READ}, "the delegated surface lists only what the chain may call")
        bad = {**headers, "X-Zuno-Delegation-Depth": "2"}
        self.assertEqual(self.client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                          headers=bad).status_code, 403)

    def test_the_audit_line_carries_the_chain_and_the_user(self):
        with self.assertLogs("mcp_gateway", level="INFO") as logs:
            self.invoke(READ, **{"X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "1"})
        line = next(l for l in logs.output if "tool=" in l)
        self.assertIn("caller=user-01", line)
        self.assertIn("delegated_by=alpha:ask depth=1", line)


if __name__ == "__main__":
    unittest.main()

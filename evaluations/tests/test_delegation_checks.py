#!/usr/bin/env python3
"""ADR-0401 / ADR-0403 / ADR-0406 (WP-174): the delegation checks of evaluations/common/delegation_checks.py,
against a fake MCP gateway and synthetic releases. Proves each outcome: pass, a write tool leaking onto the
delegated surface, a refusal that does not happen, and the clean skip while the release declares nothing.

Run directly:

    cd evaluations && python3 tests/test_delegation_checks.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from dataclasses import dataclass
from unittest import mock

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))

import delegation_checks as dc  # noqa: E402

READ, WRITE = "confluence.page.search", "git.file.write"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    skipped: bool = False


def _md(front: dict) -> str:
    return "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\nbody\n"


def release(declared: bool, allow_write: bool = False, with_policy: bool = True) -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp())
    zuno = {"name": "arkos", "status": "active", "tasks": ["draft-architecture-testimonial"]}
    if declared:
        zuno["delegation"] = {"targets": [{"agent": "tekos", "task": "answer-technical-question"}]}
    (root / "agents" / "arkos").mkdir(parents=True)
    (root / "agents" / "arkos" / "agent.okf.md").write_text(_md({"okf_version": "v0.3", "type": "agent", "zuno": zuno}))
    if with_policy:
        (root / "policies" / "tools").mkdir(parents=True)
        (root / "policies" / "tools" / "tool-policy.yaml").write_text(yaml.safe_dump({"tools": [
            {"tool": READ, "capability": READ, "access": "read"}, {"tool": WRITE, "capability": WRITE, "access": "write"},
            {"tool": "legacy_unlabelled"}]}))
        (root / "policies" / "limits").mkdir()
        (root / "policies" / "limits" / "limits-policy.yaml").write_text(
            yaml.safe_dump({"max_delegation_depth": 2, "delegation": {"allow_write": allow_write}}))
    return root


class FakeGateway:
    """Answers /mcp tools/list: `direct` without delegation headers, `chained` with them; or a fixed status."""

    def __init__(self, direct=(READ, WRITE), chained=(READ,), chained_status=200, direct_status=200):
        self.direct, self.chained = list(direct), list(chained)
        self.chained_status, self.direct_status = chained_status, direct_status
        self.calls = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append(dict(headers))
        chained = "X-Zuno-Delegated-By" in headers or "X-Zuno-Delegation-Depth" in headers
        status = self.chained_status if chained else self.direct_status
        names = self.chained if chained else self.direct
        body = {"result": {"tools": [{"name": n} for n in names]}} if status == 200 else {"detail": "refused"}
        return mock.Mock(status_code=status, json=lambda: body)


def run(check, gateway):
    with mock.patch.object(dc.httpx, "post", gateway):
        return check()


def surface(root, **kw):
    return dc.delegation_surface(
        CheckResult, root=root, mcp_gateway_url="http://gw", auth_headers=lambda p: {"Authorization": f"Bearer {p}"},
        persona="eval-consultant-01", delegator="arkos", delegator_task="draft-architecture-testimonial",
        target="tekos", target_task="answer-technical-question", **kw)


def refusal(root, **kw):
    base = dict(name="delegation_refused_x", root=root, mcp_gateway_url="http://gw",
                auth_headers=lambda p: {"Authorization": f"Bearer {p}"}, persona="p", agent="tekos",
                task="answer-technical-question", hops=["arkos:draft-architecture-testimonial"])
    return dc.delegation_refused(CheckResult, **{**base, **kw})


class Surface(unittest.TestCase):
    def test_a_declared_delegation_with_reads_only_passes(self):
        gw = FakeGateway()
        result = run(surface(release(True)), gw)
        self.assertTrue(result.passed, result.detail)
        chained = [c for c in gw.calls if "X-Zuno-Delegated-By" in c][0]
        self.assertEqual((chained["X-Zuno-Agent"], chained["X-Zuno-Delegation-Depth"]), ("tekos", "1"))
        self.assertEqual(chained["X-Zuno-Delegated-By"], "arkos:draft-architecture-testimonial")

    def test_a_write_tool_on_the_delegated_surface_fails(self):
        result = run(surface(release(True)), FakeGateway(chained=(READ, WRITE)))
        self.assertFalse(result.passed)
        self.assertIn(WRITE, result.detail)

    def test_an_unlabelled_tool_counts_as_a_write_tool(self):
        result = run(surface(release(True)), FakeGateway(direct=(READ, "legacy_unlabelled"), chained=("legacy_unlabelled",)))
        self.assertFalse(result.passed)

    def test_a_vacuous_pass_is_refused(self):
        # the direct surface has no write tool: the absence on the delegated one proves nothing.
        self.assertFalse(run(surface(release(True)), FakeGateway(direct=(READ,), chained=(READ,))).passed)

    def test_an_empty_or_refused_delegated_surface_fails(self):
        self.assertFalse(run(surface(release(True)), FakeGateway(chained=())).passed)
        self.assertFalse(run(surface(release(True)), FakeGateway(chained_status=403)).passed)

    def test_the_delegated_surface_may_not_exceed_the_direct_one(self):
        self.assertFalse(run(surface(release(True)), FakeGateway(chained=(READ, "extra.tool"))).passed)

    def test_nothing_enabled_is_a_clean_skip_never_a_pass(self):
        result = run(surface(release(False)), FakeGateway())
        self.assertTrue(result.skipped)
        self.assertFalse(result.passed)
        self.assertIn("not enabled", result.detail)

    def test_allowed_delegated_writes_skip_the_no_write_check(self):
        result = run(surface(release(True, allow_write=True)), FakeGateway())
        self.assertTrue(result.skipped)
        self.assertIn("allow_write", result.detail)


class Refusals(unittest.TestCase):
    def test_a_403_passes_and_anything_else_fails(self):
        self.assertTrue(run(refusal(release(True)), FakeGateway(chained_status=403, direct_status=403)).passed)
        self.assertFalse(run(refusal(release(True)), FakeGateway(chained_status=200, direct_status=200)).passed)

    def test_malformed_headers_replace_the_chain_exactly(self):
        gw = FakeGateway(chained_status=403, direct_status=403)
        result = run(refusal(release(True), hops=[], malformed={"X-Zuno-Delegated-By": "arkos:t"}), gw)
        self.assertTrue(result.passed)
        self.assertEqual(gw.calls[0]["X-Zuno-Delegated-By"], "arkos:t")
        self.assertNotIn("X-Zuno-Delegation-Depth", gw.calls[0])

    def test_a_refusal_is_skipped_unless_the_delegation_is_declared(self):
        result = run(refusal(release(False), requires=("arkos", "tekos", "answer-technical-question")),
                     FakeGateway(chained_status=403, direct_status=403))
        self.assertTrue(result.skipped)


class Layouts(unittest.TestCase):
    def test_the_first_root_that_holds_the_agent_wins(self):
        empty = pathlib.Path(tempfile.mkdtemp())
        self.assertTrue(dc.declares_target([empty, release(True)], "arkos", "tekos", "answer-technical-question"))
        self.assertFalse(dc.declares_target([empty], "arkos", "tekos", "answer-technical-question"))

    def test_a_malformed_agent_bundle_is_not_a_declaration(self):
        root = release(True)
        (root / "agents" / "arkos" / "agent.okf.md").write_text("# no frontmatter\n")
        self.assertFalse(dc.declares_target(root, "arkos", "tekos", "answer-technical-question"))

    def test_policies_are_searched_across_roots_and_default_safe(self):
        empty = pathlib.Path(tempfile.mkdtemp())
        self.assertEqual(dc.write_tools([empty, release(True)]), {WRITE, "legacy_unlabelled"})
        self.assertFalse(dc.allows_delegated_writes(empty), "absent limits policy means the gateway's default: false")
        self.assertTrue(dc.allows_delegated_writes([empty, release(True, allow_write=True)]))


class ArkosToTekos(unittest.TestCase):
    def checks(self, root):
        return dc.arkos_to_tekos_checks(CheckResult, root=root, mcp_gateway_url="http://gw",
                                        auth_headers=lambda p: {})

    def test_seven_uniquely_named_checks(self):
        names = [c.__name__ for c in self.checks(release(True))]
        self.assertEqual(len(names), 7)
        self.assertEqual(len(set(names)), 7)

    def test_all_skip_while_nothing_is_declared(self):
        gw = FakeGateway()
        for check in self.checks(release(False)):
            result = run(check, gw)
            self.assertTrue(result.skipped, result.name)
        self.assertEqual(gw.calls, [], "a skipped check must not call the gateway")

    def test_every_refusal_scenario_sends_what_it_names(self):
        gw = FakeGateway(chained_status=403, direct_status=403)
        by_name = {c.__name__: run(c, gw) for c in self.checks(release(True)) if "refused" in c.__name__}
        self.assertEqual(len(by_name), 6)
        self.assertTrue(all(r.passed for r in by_name.values()), {n: r.detail for n, r in by_name.items()})
        # entitlement 1, undeclared target 1, beyond the limit 2, cycle 2, depth header disagrees 2, half a chain none.
        depths = sorted(c.get("X-Zuno-Delegation-Depth", "-") for c in gw.calls)
        self.assertEqual(depths, ["-", "1", "1", "2", "2", "2"], depths)


if __name__ == "__main__":
    unittest.main()

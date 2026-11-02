import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import a2a_delegation_check as check  # noqa: E402

MCP = (
    "2026-11-01 10:00:01,000 INFO mcp_gateway tool=confluence.page.search capability=confluence.page.search binding=confluence "
    "auth_mode=service-identity agent=tekos task=answer-technical-question caller=u-eval groups=['agent_tekos'] "
    "classification=C1 delegated_by=arkos:draft-architecture-testimonial depth=1 allowed=True reason=ok request_id=r1\n"
    "2026-11-01 10:00:02,000 INFO mcp_gateway tool=confluence.page.read capability=confluence.page.read binding=confluence "
    "auth_mode=service-identity agent=tekos task=answer-technical-question caller=u-eval groups=['agent_tekos'] "
    "classification=C1 delegated_by= depth=0 allowed=True reason=ok request_id=r2\n"
)
A2A = 'INFO:     10.0.0.1:1 - "POST /agents/tekos/ HTTP/1.1" 200 OK\nINFO:     10.0.0.1:2 - "POST /agents/tekos/ HTTP/1.1" 404 Not Found\n'


def test_a_delegated_call_that_ran_as_a_user_is_proven():
    ok, findings = check.evaluate(MCP, A2A, delegator="arkos", target="tekos")
    assert ok, findings
    assert any("1 x 200, 1 x 404" in f for f in findings)


def test_no_delegated_call_is_no_proof():
    ok, findings = check.evaluate("", A2A, delegator="arkos", target="tekos")
    assert not ok and any(f.startswith("no tool call") for f in findings)


def test_a_wrong_depth_or_missing_caller_fails():
    bad = MCP.replace("depth=1", "depth=2")
    ok, findings = check.evaluate(bad, A2A, delegator="arkos", target="tekos")
    assert not ok and any("depth=2" in f for f in findings)
    anon = MCP.replace("caller=u-eval", "caller=")
    assert not check.evaluate(anon, A2A, delegator="arkos", target="tekos")[0]


def test_the_unentitled_caller_must_not_appear_in_delegated_calls():
    ok, findings = check.evaluate(MCP, A2A, delegator="arkos", target="tekos", expect_denied_sub="u-eval")
    assert not ok and any("must be refused" in f for f in findings)
    ok, findings = check.evaluate(MCP, A2A, delegator="arkos", target="tekos", expect_denied_sub="u-other")
    assert ok and any("as expected" in f for f in findings)


def test_refused_chain_calls_are_reported():
    refused = MCP.replace("allowed=True reason=ok request_id=r1", "allowed=False reason=depth_exceeded request_id=r1")
    ok, findings = check.evaluate(refused, A2A, delegator="arkos", target="tekos")
    assert not ok and any("depth_exceeded" in f for f in findings)

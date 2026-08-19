#!/usr/bin/env python3
"""ADR-0119 policy-as-code check: every real MCP server under
`components/mcp-servers/*/server.py` must carry the platform's mandatory
shape (ADR-0037 gateway-token middleware, `/healthz`, DNS-rebinding
protection) and must be registered everywhere the existing per-component
checks require a server to be listed by name - `platform/security/
check_workload_hardening.py`'s chart lists and `.github/workflows/
lint.yml`'s python test job.

This is the guardrail ADR-0119 introduces after `check_workload_hardening.py`'s
own comment recorded a real, already-happened gap: "ADR-0117/WP-02 added
this chart without updating this list". Registration in
`platform/bindings/tools/tool-bindings.yaml`/`policies/tools/tool-policy.yaml`
is intentionally NOT checked here - a server can legitimately exist with
zero capabilities wired yet (early scaffold), so that omission is not a
conformance failure the way a missing gateway-token check or missing
hardening-list entry is.

No live cluster or `helm` needed - pure source/text inspection.

Run from the repository root:

    python3 platform/supply-chain/check_mcp_server_conformance.py
"""
from __future__ import annotations

import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import List

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MCP_SERVERS_DIR = REPO_ROOT / "components" / "mcp-servers"
HARDENING_CHECK_PATH = REPO_ROOT / "platform" / "security" / "check_workload_hardening.py"
LINT_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "lint.yml"

REQUIRED_SERVER_PY_SNIPPETS = {
    "GatewayTokenMiddleware": "ADR-0037 gateway-token middleware class",
    "/healthz": "a /healthz route",
    "TransportSecuritySettings(": "DNS-rebinding protection (transport_security)",
    "mcp_asgi_app.add_middleware(GatewayTokenMiddleware)": "the middleware actually wired onto the mounted MCP app",
}


@dataclass
class Findings:
    results: List[str] = field(default_factory=list)
    ok: int = 0

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.ok += 1
        else:
            self.results.append(description)


def _discover_servers() -> List[str]:
    if not MCP_SERVERS_DIR.is_dir():
        return []
    return sorted(
        p.parent.name for p in MCP_SERVERS_DIR.glob("*/server.py")
    )


def check_server_shape(name: str, findings: Findings) -> None:
    server_py = (MCP_SERVERS_DIR / name / "server.py").read_text()
    for snippet, description in REQUIRED_SERVER_PY_SNIPPETS.items():
        findings.check(f"{name}/server.py: has {description}", snippet in server_py)

    dockerfile = MCP_SERVERS_DIR / name / "Dockerfile"
    findings.check(f"{name}/Dockerfile exists", dockerfile.is_file())
    if dockerfile.is_file():
        findings.check(
            f"{name}/Dockerfile: uses the ARG BASE_IMAGE pattern (ADR-0115 CVE-patch step)",
            "ARG BASE_IMAGE" in dockerfile.read_text(),
        )

    requirements = MCP_SERVERS_DIR / name / "requirements.txt"
    findings.check(f"{name}/requirements.txt exists", requirements.is_file())
    if requirements.is_file():
        findings.check(
            f"{name}/requirements.txt: pins the mcp SDK",
            re.search(r"^mcp==", requirements.read_text(), re.MULTILINE) is not None,
        )

    tests = MCP_SERVERS_DIR / name / "tests" / "test_mcp_protocol.py"
    findings.check(f"{name}/tests/test_mcp_protocol.py exists", tests.is_file())


def _list_literal_source(source: str, variable: str) -> str:
    """Best-effort extraction of the raw text between `variable = [` and the
    matching closing `]`, or the empty string if not found - good enough
    for a membership substring check, not a full parser."""
    match = re.search(rf"{re.escape(variable)}\s*=\s*\[", source)
    if not match:
        return ""
    depth = 1
    i = match.end()
    start = i
    while i < len(source) and depth > 0:
        if source[i] == "[":
            depth += 1
        elif source[i] == "]":
            depth -= 1
        i += 1
    return source[start : i - 1]


def check_hardening_registration(name: str, findings: Findings) -> None:
    chart_name = f"mcp-{name}"
    source = HARDENING_CHECK_PATH.read_text()

    deployment_charts = _list_literal_source(source, "DEPLOYMENT_CHARTS")
    findings.check(
        f"{chart_name}: listed in check_workload_hardening.py's DEPLOYMENT_CHARTS",
        f'"{chart_name}"' in deployment_charts,
    )

    # The NetworkPolicy coverage list is an inline literal on the `for
    # chart in [...]:` line inside main(), not a module-level constant -
    # matched by its own distinctive call, check_networkpolicies(chart, ...).
    np_loop_match = re.search(r"for chart in (\[[^\]]*\]):\s*\n\s*check_networkpolicies\(chart, findings\)", source)
    np_list = np_loop_match.group(1) if np_loop_match else ""
    findings.check(
        f"{chart_name}: listed in check_workload_hardening.py's NetworkPolicy coverage loop",
        f'"{chart_name}"' in np_list,
    )


def check_ci_test_wiring(name: str, findings: Findings) -> None:
    if not (MCP_SERVERS_DIR / name / "tests" / "test_mcp_protocol.py").is_file():
        return
    source = LINT_WORKFLOW_PATH.read_text()
    findings.check(
        f"{name}: has a 'working-directory: components/mcp-servers/{name}' step in lint.yml's python job",
        f"working-directory: components/mcp-servers/{name}" in source,
    )


def main() -> int:
    servers = _discover_servers()
    findings = Findings()

    for name in servers:
        check_server_shape(name, findings)
        check_hardening_registration(name, findings)
        check_ci_test_wiring(name, findings)

    total = findings.ok + len(findings.results)
    print(f"Checked {len(servers)} MCP server(s) under {MCP_SERVERS_DIR.relative_to(REPO_ROOT)}: {servers}")
    print(f"{findings.ok}/{total} checks passed")

    if findings.results:
        print(f"\n{len(findings.results)} conformance issue(s) found:")
        for r in findings.results:
            print(f"  ✗ {r}")
        print("\nRESULT: FAIL")
        return 1

    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""ADR-0052 policy-as-code check: renders every chart this repo directly
controls via `helm template` and asserts the restricted workload baseline
(non-root, no privilege escalation, all capabilities dropped, seccomp
RuntimeDefault, no automounted service account token unless needed, and a
NetworkPolicy exists for every workload) is actually present in the
rendered manifests - not just claimed in a commit message.

No live cluster needed (this is `helm template`, not `helm install` or
`oc apply`) - runnable anywhere `helm` is on PATH, same style as
evaluations/tekos/security_checks.py's config-consistency checks. Exits
non-zero on any failure, so it's CI-usable once `.github/workflows/`
exists (currently none do, see `.github/README.md`).

Run from the repository root:

    python3 platform/security/check_workload_hardening.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Charts with a raw Deployment PodSpec this repo fully controls - every
# container in every one of these must meet the full baseline.
DEPLOYMENT_CHARTS = [
    "tekos",
    "agent-runtime",
    "ai-gateway",
    "mcp-gateway",
    "mcp-sales-db",
    "rag-service",
]

# Deployments where readOnlyRootFilesystem is not expected - none today;
# kept as an explicit, documented allow-list rather than a silent skip so
# a future exception is a visible one-line diff, not a quietly weakened
# check (ADR-0052 Security considerations: "Exceptions require an ADR or
# security waiver with compensating controls").
READONLY_ROOTFS_EXEMPT_CONTAINERS: Dict[str, str] = {}


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def _helm_template(chart: str) -> List[Dict[str, Any]]:
    proc = subprocess.run(
        ["helm", "template", "test", str(REPO_ROOT / "gitops" / "charts" / chart)],
        capture_output=True,
        text=True,
        check=True,
    )
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def _pod_spec_of(container_spec: Dict[str, Any]) -> Dict[str, Any]:
    return container_spec.get("spec", {}).get("template", {}).get("spec", {})


@dataclass
class Findings:
    results: List[CheckResult] = field(default_factory=list)

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.results.append(CheckResult(name, condition, detail))


def check_deployment_chart(chart: str, findings: Findings) -> None:
    docs = _helm_template(chart)
    deployments = [d for d in docs if d.get("kind") == "Deployment"]
    findings.check(f"{chart}: at least one Deployment rendered", len(deployments) > 0, f"found {len(deployments)}")

    for dep in deployments:
        dep_name = dep["metadata"]["name"]
        pod_spec = _pod_spec_of(dep)
        pod_sc = pod_spec.get("securityContext", {})

        findings.check(
            f"{chart}/{dep_name}: pod securityContext.runAsNonRoot",
            pod_sc.get("runAsNonRoot") is True,
        )
        findings.check(
            f"{chart}/{dep_name}: pod securityContext.seccompProfile.type RuntimeDefault",
            pod_sc.get("seccompProfile", {}).get("type") == "RuntimeDefault",
        )
        findings.check(
            f"{chart}/{dep_name}: automountServiceAccountToken is false",
            pod_spec.get("automountServiceAccountToken") is False,
        )
        findings.check(
            f"{chart}/{dep_name}: dedicated serviceAccountName set",
            bool(pod_spec.get("serviceAccountName")),
            f"got {pod_spec.get('serviceAccountName')!r}",
        )

        for container in pod_spec.get("containers", []):
            cname = container["name"]
            exempt = READONLY_ROOTFS_EXEMPT_CONTAINERS.get(f"{chart}/{dep_name}/{cname}")
            csc = container.get("securityContext", {})
            findings.check(
                f"{chart}/{dep_name}/{cname}: allowPrivilegeEscalation false",
                csc.get("allowPrivilegeEscalation") is False,
            )
            findings.check(
                f"{chart}/{dep_name}/{cname}: capabilities.drop == [ALL]",
                csc.get("capabilities", {}).get("drop") == ["ALL"],
            )
            if not exempt:
                findings.check(
                    f"{chart}/{dep_name}/{cname}: readOnlyRootFilesystem true",
                    csc.get("readOnlyRootFilesystem") is True,
                )


def check_networkpolicies(chart: str, findings: Findings) -> None:
    docs = _helm_template(chart)
    policies = [d for d in docs if d.get("kind") == "NetworkPolicy"]
    findings.check(f"{chart}: at least one NetworkPolicy rendered", len(policies) > 0, f"found {len(policies)}")


def check_keycloak_partial(findings: Findings) -> None:
    docs = _helm_template("keycloak")
    kc = next((d for d in docs if d.get("kind") == "Keycloak"), None)
    findings.check("keycloak: Keycloak CR rendered", kc is not None)
    if kc is None:
        return
    pod_spec = kc["spec"]["unsupported"]["podTemplate"]["spec"]
    findings.check(
        "keycloak: automountServiceAccountToken is false",
        pod_spec.get("automountServiceAccountToken") is False,
    )
    findings.check(
        "keycloak: pod securityContext.runAsNonRoot",
        pod_spec.get("securityContext", {}).get("runAsNonRoot") is True,
    )
    container = pod_spec["containers"][0]
    csc = container.get("securityContext", {})
    findings.check(
        "keycloak/keycloak: allowPrivilegeEscalation false",
        csc.get("allowPrivilegeEscalation") is False,
    )
    findings.check(
        "keycloak/keycloak: capabilities.drop == [ALL]",
        csc.get("capabilities", {}).get("drop") == ["ALL"],
    )


def check_models_partial(findings: Findings) -> None:
    docs = _helm_template("models")
    runtime = next((d for d in docs if d.get("kind") == "ServingRuntime"), None)
    findings.check("models: ServingRuntime rendered", runtime is not None)
    if runtime is None:
        return
    container = runtime["spec"]["containers"][0]
    csc = container.get("securityContext", {})
    findings.check(
        "models/kserve-container: allowPrivilegeEscalation false",
        csc.get("allowPrivilegeEscalation") is False,
    )
    findings.check(
        "models/kserve-container: capabilities.drop == [ALL]",
        csc.get("capabilities", {}).get("drop") == ["ALL"],
    )


def main() -> int:
    findings = Findings()

    for chart in DEPLOYMENT_CHARTS:
        check_deployment_chart(chart, findings)

    # NetworkPolicy coverage: every zuno-ai-run workload chart (no namespace
    # baseline covers them - ADR-0037) plus the platform-namespace-baseline
    # owner and rag-service's precise cross-namespace policy.
    for chart in ["agent-runtime", "ai-gateway", "mcp-gateway", "mcp-sales-db", "rag-service", "models", "namespaces"]:
        check_networkpolicies(chart, findings)

    check_keycloak_partial(findings)
    check_models_partial(findings)

    passed = [r for r in findings.results if r.passed]
    failed = [r for r in findings.results if not r.passed]

    print(f"{len(passed)}/{len(findings.results)} checks passed")
    for r in failed:
        print(f"FAIL  {r.name}" + (f" ({r.detail})" if r.detail else ""))

    if failed:
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

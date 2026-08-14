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
import re
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
    # ADR-0117/WP-02 added this chart without updating this list - a real
    # gap ADR-0111's own repo-wide audit found and closed: every workload
    # this repo directly controls must be checked, not just the ones this
    # list happened to be updated for at the time it was written.
    "mcp-confluence",
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


def _helm_template(chart: str, set_values: Dict[str, str] | None = None) -> List[Dict[str, Any]]:
    """`set_values` renders charts that gate their real content behind a
    top-level `enabled: false` default (namespaces' `policy.enabled`,
    keycloak's `keycloak.enabled` - same "both default false so `helm
    template` with no overrides renders nothing" pattern several charts in
    this repo use for their -d0/-d1 ArgoCD Application split). Without
    this, `check_networkpolicies("namespaces", ...)` and
    `check_keycloak_partial()` were structurally checking an always-empty
    render - a real bug this ADR-0111 pass found and fixed, not a
    loosened check: the baseline they assert was already correct, the gate
    checker just never actually looked at it (ADR-0052's own "Implemented"
    claim for these two was accurate; this fixes proving it in CI).
    """
    cmd = ["helm", "template", "test", str(REPO_ROOT / "gitops" / "charts" / chart)]
    for key, value in (set_values or {}).items():
        cmd.extend(["--set", f"{key}={value}"])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
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


# ADR-0111 first increment: ADR-0024/0041 already require every credential
# to come from an ExternalSecret-populated secretKeyRef, never a literal
# value committed to a chart - this is the first automated check for it,
# catching a regression a reviewer might otherwise miss. Env var names
# matching this pattern must never carry a literal `value:` field.
_SECRET_ENV_NAME_PATTERN = re.compile(r"(PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)", re.IGNORECASE)


def check_no_hardcoded_secret_values(chart: str, findings: Findings) -> None:
    docs = _helm_template(chart)
    for dep in [d for d in docs if d.get("kind") == "Deployment"]:
        dep_name = dep["metadata"]["name"]
        pod_spec = _pod_spec_of(dep)
        for container in pod_spec.get("containers", []):
            cname = container["name"]
            for env in container.get("env", []):
                name = env.get("name", "")
                if not _SECRET_ENV_NAME_PATTERN.search(name):
                    continue
                if name.endswith("_ENV"):
                    # Meta-variable naming *which other* env var holds a
                    # secret (e.g. MAAS_GATEWAY_API_KEY_ENV="MAAS_GATEWAY_
                    # API_KEY" - components/ai-gateway/app/maas_adapter.py's
                    # own indirection pattern) - its value is an env var
                    # name, never a credential itself.
                    continue
                has_literal_value = bool(env.get("value"))
                findings.check(
                    f"{chart}/{dep_name}/{cname}: {name} is not a hardcoded literal value",
                    not has_literal_value,
                    f"got value={env.get('value')!r} - secret-like env vars must use valueFrom.secretKeyRef",
                )


# ADR-0101 (roadmap WP-12): the four charts with a raw Deployment PodSpec
# whose availability shape (PodDisruptionBudget, topologySpreadConstraints,
# probes) this repo directly authors and controls. Deliberately a
# separate, narrower list than DEPLOYMENT_CHARTS above (which also covers
# mcp-sales-db/mcp-confluence/tekos/models) - WP-12's own authoritative
# scope list names only these four as "runtime/gateways"; the others were
# never given the mechanism and checking them here would just be a
# self-inflicted permanent failure, not a real regression.
AVAILABILITY_CHARTS = ["agent-runtime", "ai-gateway", "mcp-gateway", "rag-service"]


def check_availability(chart: str, findings: Findings) -> None:
    docs = _helm_template(chart)
    deployments = [d for d in docs if d.get("kind") == "Deployment"]
    pdbs = [d for d in docs if d.get("kind") == "PodDisruptionBudget"]

    findings.check(f"{chart}: PodDisruptionBudget rendered", len(pdbs) > 0, f"found {len(pdbs)}")

    for dep in deployments:
        dep_name = dep["metadata"]["name"]
        pod_spec = _pod_spec_of(dep)
        findings.check(
            f"{chart}/{dep_name}: topologySpreadConstraints present",
            len(pod_spec.get("topologySpreadConstraints", [])) > 0,
        )
        for container in pod_spec.get("containers", []):
            cname = container["name"]
            findings.check(
                f"{chart}/{dep_name}/{cname}: livenessProbe present",
                "livenessProbe" in container,
            )
            findings.check(
                f"{chart}/{dep_name}/{cname}: readinessProbe present",
                "readinessProbe" in container,
            )


def check_keycloak_availability(findings: Findings) -> None:
    """Separate from check_keycloak_partial below: the Keycloak Operator's
    CR has no raw Deployment PodSpec to inspect the way
    check_availability does - this checks the CR's own
    spec.scheduling.topologySpreadConstraints field and the hand-authored
    PodDisruptionBudget alongside it (ADR-0101/WP-12, see that chart's own
    templates for why the operator needs one authored rather than
    providing its own).
    """
    docs = _helm_template("keycloak", {"keycloak.enabled": "true"})
    kc = next((d for d in docs if d.get("kind") == "Keycloak"), None)
    pdbs = [d for d in docs if d.get("kind") == "PodDisruptionBudget"]
    findings.check("keycloak: PodDisruptionBudget rendered", len(pdbs) > 0, f"found {len(pdbs)}")
    if kc is not None:
        findings.check(
            "keycloak: spec.scheduling.topologySpreadConstraints present",
            len(kc.get("spec", {}).get("scheduling", {}).get("topologySpreadConstraints", [])) > 0,
        )


def check_postgresql_availability(findings: Findings) -> None:
    """PGO already auto-manages replicas>=2 and a PodDisruptionBudget for
    both the instance set and pgBouncer (confirmed live, 2026-08-14 - see
    templates/postgrescluster.yaml's own comments) - this only needed to
    confirm the one gap ADR-0101/WP-12 closed: topologySpreadConstraints
    on both.
    """
    docs = _helm_template("postgresql", {"postgresCluster.enabled": "true"})
    cluster = next((d for d in docs if d.get("kind") == "PostgresCluster"), None)
    findings.check("postgresql: PostgresCluster rendered", cluster is not None)
    if cluster is None:
        return
    instances = cluster.get("spec", {}).get("instances", [{}])[0]
    findings.check(
        "postgresql/instance1: topologySpreadConstraints present",
        len(instances.get("topologySpreadConstraints", [])) > 0,
    )
    pgbouncer = cluster.get("spec", {}).get("proxy", {}).get("pgBouncer", {})
    findings.check(
        "postgresql/pgBouncer: topologySpreadConstraints present",
        len(pgbouncer.get("topologySpreadConstraints", [])) > 0,
    )


def check_networkpolicies(chart: str, findings: Findings, set_values: Dict[str, str] | None = None) -> None:
    docs = _helm_template(chart, set_values)
    policies = [d for d in docs if d.get("kind") == "NetworkPolicy"]
    findings.check(f"{chart}: at least one NetworkPolicy rendered", len(policies) > 0, f"found {len(policies)}")


def check_keycloak_partial(findings: Findings) -> None:
    docs = _helm_template("keycloak", {"keycloak.enabled": "true"})
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
        check_no_hardcoded_secret_values(chart, findings)

    # NetworkPolicy coverage: every zuno-ai-run workload chart (no namespace
    # baseline covers them - ADR-0037) plus the platform-namespace-baseline
    # owner and rag-service's precise cross-namespace policy.
    for chart in ["agent-runtime", "ai-gateway", "mcp-gateway", "mcp-sales-db", "mcp-confluence", "rag-service", "models"]:
        check_networkpolicies(chart, findings)
    check_networkpolicies("namespaces", findings, {"policy.enabled": "true"})

    check_keycloak_partial(findings)
    check_models_partial(findings)

    # ADR-0101 (roadmap WP-12).
    for chart in AVAILABILITY_CHARTS:
        check_availability(chart, findings)
    check_keycloak_availability(findings)
    check_postgresql_availability(findings)

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

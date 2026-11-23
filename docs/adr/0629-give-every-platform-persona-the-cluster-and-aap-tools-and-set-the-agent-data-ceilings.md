# ADR-0629: Give every platform persona the cluster and AAP tools, and set the agent data ceilings

- **Status:** Proposed
- **Target:** v0.18
- **Date:** 2026-11-23
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0349](0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md) (the personas and the `ocp-*`
  groups), [ADR-0600](0600-govern-kubernetes-read-tools-in-the-mcp-gateway-and-admit-kagent-as-a-thin-operations-client.md) (the governed cluster
  reads, `ocp-ai-ops` only), [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md) (the ceiling is one level per agent),
  [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md) (the `aap_*` groups)

## Context

On 2026-11-23 the platform owner reviewed the personas of the demo and asked that the four platform personas
(`ai-dev-01`, `ai-ops-01`, `paas-dev-01`, `paas-ops-01`) all reach the AAP tools and read the cluster, with write rights
only for the admin group, and revised the data ceiling of five agents.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Only `ocp-ai-ops` passes the five `k8s.*` and `metrics.query` tools of Tekos. The other three platform personas hold `agent_tekos` and no business role, so they are refused. | `policies/tools/tool-policy.yaml` of zuno-demo-agents v1.2.4 |
| F2 | `ai-dev-01` and `ai-ops-01` hold no `aap_*` group, so AAP shows them no template. `paas-dev-01` holds `aap_ops` and `paas-ops-01` holds `aap_admin`. | `gitops/charts/keycloak/files/realm-zuno.json` |
| F3 | No tool in the policy writes to the cluster. The one write is `aap.cluster.audit`, which launches a Day 0 check through AAP. | `tool-policy.yaml` |
| F4 | The ceiling is one `preferred_classification` per agent. The gateway raises each call to it and never lowers it. C3 means local models only. | `components/ai-gateway/app/classification_floor.py` |

## Decision

1. **Read for the four platform groups.** `ocp-ai-dev`, `ocp-paas-dev` and `ocp-paas-ops` join `ocp-ai-ops` on
   `k8s.resource.read`, `k8s.resource.list`, `k8s.events.read`, `k8s.logs.read`, `metrics.query` and
   `aap.platform.audit`.
2. **Write stays with the admin groups.** `aap.cluster.audit` takes `ocp-paas-ops` on top of `ocp-ai-ops`. No new write
   tool is built: a change to the cluster goes through AAP.
3. **AAP groups.** `ai-dev-01` joins `aap_reader`, `ai-ops-01` joins `aap_ops`. `paas-dev-01` keeps `aap_ops` and
   `paas-ops-01` keeps `aap_admin`. The memberships are applied to the live realm by
   `ansible/tasks/keycloak_persona_memberships.yml` (the realm import is create-only).
4. **Ceilings** (zuno-demo-agents v1.2.5): Arkos C3 to C2 (`structure-demo` gets `local_only_for`, as its other tasks),
   Finage C2 to C3, Tekos C1 to C2, Soursage stays C2, Naveo C1, Comage and Advantage C2, Cognos C3.
5. **`service-account-kagent`** in the realm file is aligned with the live account (`/ocp-ai-ops` only).

## Alternatives considered

- **A new write tool for the cluster** (scale, restart, apply): rejected, a second path to change the cluster beside AAP,
  which already approves, logs and limits what runs.
- **Soursage at C1 or C3**: a ceiling is one level per agent; C2 fits recruiting and leaves the Workday tools (C3 minimum)
  to a caller that sends C3.

## Consequences

Arkos and Finage change their floor, so the gateway floors file, the sovereignty probe and the demo pages that name them
change with the promotion of v1.2.5. Tekos at C2 drops the C1-only SaaS models (`gemini`, `mistral`) for its
`check-my-drive-docs` and `write-code` tasks. Cluster logs may carry values an application printed, so they stay C2, and
the platform personas who read them do so through the same checks as `ai-ops-01`.

## Security considerations

`ocp-paas-dev` and `ocp-ai-dev` now read pod logs of the `zuno-*` namespaces through Tekos, while their own OpenShift
rights are `cluster-reader` and `edit`. The server's ServiceAccount does the read (`view`, no Secret, no ConfigMap data),
so the tool never shows more than it does for `ocp-ai-ops`.

## Operational considerations

Roll after the promotion of v1.2.5: `make d2 install mcp`, `make d2 install unifai`, `make d0 install keycloak` (applies
the memberships), `make d1 build ai-gateway`, then `make d2 check agents`.

## Work packages

[WP-332](../roadmap/work-packages/wp-332-platform-personas-tools-and-agent-data-ceilings.md).

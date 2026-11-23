# WP-332: Platform personas, tools and agent data ceilings

- **State:** Done (released as zuno-demo-agents v1.2.5, rolled on demo333 on 2026-11-23)
- **ADRs:** [ADR-0629](../../adr/0629-give-every-platform-persona-the-cluster-and-aap-tools-and-set-the-agent-data-ceilings.md)
- **Depends on:** none
- **Target:** v0.18
- **Estimated files touched:** ~25: the tool and routing policies and four bundles of zuno-demo-agents, `realm-zuno.json`, the keycloak role, one shared task, the demo pages that name a ceiling

## Goal

The four platform personas read the cluster and AAP through Tekos, write stays with the admin groups, and the agent data
ceilings are Arkos C2, Finage C3, Tekos C2, Soursage C2, Naveo C1, Comage and Advantage C2, Cognos C3.

## Work

1. zuno-demo-agents v1.2.5: `tool-policy.yaml`, `model-routing-policy.yaml`, the four bundles, the authorization matrices.
2. This repository: the AAP groups of `ai-dev-01` and `ai-ops-01` in the realm file and on the live realm, kagent aligned.
3. After the release: promote v1.2.5 (`agents.lock`, generated stack config and floors), update the pages and probes that
   name a ceiling, roll.

## Acceptance criteria

- A token for each platform persona reads pod logs and the AAP state through Tekos; only `ai-ops-01` and `paas-ops-01`
  launch the cluster audit.
- `classification-floors.generated.yaml` gives Arkos C2, Finage C3, Tekos C2; `make d2 check agents` and the golden path pass.

## Review evidence

2026-11-23, demo333: zuno-demo-agents v1.2.5 released (PR #94), promoted here (PR #74), mirrored and rolled (mcp, a2a, unifai, the
Keycloak memberships, ai-gateway image 64adab9f). `ai-dev-01` holds `aap_reader` and `ai-ops-01` holds `aap_ops`, read back from
Keycloak. The gateway floors give Arkos C2, Finage C3 and Tekos C2. `make d2 check agents`: 18/19 scenarios (scenario 11, the
Red Hat documentation citation, fails as before), 14/14 security checks, 5/5 gate checks. Not exercised: a token of each of the
four platform personas calling the cluster and AAP tools through Tekos.

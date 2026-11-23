# WP-332: Platform personas, tools and agent data ceilings

- **State:** Repo work in review (2026-11-23: the bundle changes are committed in zuno-demo-agents on a local branch, the realm and role changes here; nothing released, promoted or applied to a cluster)
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

None yet: nothing is rolled.

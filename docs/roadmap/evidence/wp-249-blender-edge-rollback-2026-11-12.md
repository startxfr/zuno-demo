# WP-249 row 3: the Blender workstation entry removed and restored on demo333 (2026-11-12)

Live test with the user's go, by session zuno-avancement. The window ran from 10:40 to 10:49 UTC and was announced to
zuno-main and zuno-demo.

## How the entry is switched

`workstationEntry.enabled` sits in the inline values of `gitops/apps/connectivity-link/application-d1.yaml`. The
Application manifest is applied by the role, not synced from git, so pushing the value does nothing on its own. The
switch is `make d1 install connectivity-link` with the value changed. For the test, the value was changed in the
session's worktree and never pushed; git kept `enabled: true` throughout. ArgoCD prunes or recreates the four objects.

## Steps

| UTC | Step | Result |
|---|---|---|
| 10:40 | baseline | 4 objects: Route `zuno-agent-gateway-workstation-ai-gateway` (openshift-ingress), HTTPRoute `ai-gateway-workstation`, AuthPolicy `ai-gateway-workstation-jwt`, RateLimitPolicy `ai-gateway-workstation` (zuno-ai-run); edge without a token 401; Blender moment PASS (eval-ai-dev-01 by device flow, bpy script checked) |
| 10:40-10:43 | `enabled: false`, `make d1 install connectivity-link` | exit 0; the 4 objects pruned |
| 10:43 | the edge `https://ai-gateway.apps.demo333.startx.fr/v1/models` | **503** three times (the router has no route); the Blender moment reports the entry as not installed |
| 10:43-10:46 | `enabled: true` (the git value), `make d1 install connectivity-link` | exit 0 |
| 10:46 | the edge, sampled every 15 s | 404 for one sample (objects back, AuthPolicy not yet `Enforced`), then 401 with the AuthPolicy `Enforced` |
| 10:46 | the Blender moment | PASS |
| 10:47-10:49 | full golden path | RESULT PASS, 14 moments, world model as roadmap |

## Findings

- **The rollback and its way back work.** It takes one command each way and 2 to 3 minutes. Nothing on the platform
  holds Blender data.
- **The removed edge answers 503, not 404.** `docs/demo/rollback.md` said 404 and said "push"; both are corrected.
- **During the restore, the AuthPolicy is enforced a few seconds after the route.** In that interval the sample saw
  404, not an unauthenticated 200. The route is not served until the policy attaches. That rests on one sample, so the
  probe to repeat on a later restore is a token-less request in a tight loop.
- **The Keycloak client `blender` was kept.** The row of the WP brief named it, but rollback.md's procedure does not
  touch it: without the edge it reaches nothing from outside the cluster. Removing it would be a realm change, and the
  realm import is create-only.

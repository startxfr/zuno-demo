# WP-235: World-model GitOps integration (delivers ADR-0604 D5, D6, §7, §8)

- **State:** Operator pending
- **ADRs:** ADR-0604
- **Depends on:** WP-229, WP-234
- **Blocks:** WP-236
- **Estimated files touched:** ~25

> Execute this brief as a standalone task from the repository root.

## Goal

`make d2 install world-model` deploys the experience when the switch is on and the GPU node exists, removes it when the
switch is off, and every registry and check of the repository knows the new component.

## ADR references

ADR-0604 D5 item 2, D6, §7.1, §7.2, §8.

## Repo changes

1. `gitops/charts/world-model/`:
   - runtime Deployment: `strategy: Recreate`, nodeSelector `zuno.io/gpu-workload: world-model`, toleration
     `zuno.io/gpu-world-model`, `nvidia.com/gpu: 1`, `NVIDIA_DRIVER_CAPABILITIES=compute,utility,video`, an init container
     that fills an `emptyDir` cache from S3 (`gitops/charts/models/templates/job-lmeval-cache-prefetch.yaml` pattern),
     readiness after warm-up, a liveness probe that tolerates slow steps;
   - web Deployment, Services, the oauth2-proxy front door and the one Route (`gitops/charts/kagent/templates/front-door.yaml`
     pattern) with a long WebSocket timeout (`haproxy.router.openshift.io/timeout`);
   - ExternalSecrets (Keycloak client, S3 read), NetworkPolicies (router to front door to web to runtime; egress DNS,
     Keycloak, ai-gateway, OTel, S3 only), EgressFirewall, ServiceMonitors in `monitoring.coreos.com/v1`, third-party
     images pinned by digest.
2. `gitops/apps/world-model/application-d1.yaml`.
3. `ansible/roles/world_model/`: `install.yml` (switch off: delete the Application if present and stop; switch on: fail
   fast without the GPU node, seed Vault, create or patch the Keycloak group, apply the Application, wait), `precheck.yml`
   (preflight: node, models loaded, warm-up done, encoder in use, auth probes, ai-gateway reachable), `uninstall.yml`,
   `seed_vault.yml`.
5. The world-model golden-path probe for ADR-0605 clause 1 (a real call, read-only, cleans up after itself): sign in as
   the presenter persona, create a world from a preset, receive and decode frames for a few seconds, apply one world edit,
   close the session. Registered in the golden-path check's table (ADR-0605) in place of the "added when ADR-0604 ships a
   probe" row; it reports "not in this demonstration" while `zuno_world_model_enabled` is off.
4. Registration: `Makefile` `DAY2_RUN_COMPONENTS` and `DAY2_BUILD_COMPONENTS`; `ansible/playbooks/day2_{install,check,
   uninstall,build}.yml`; `gitops/charts/aap-config/values.yaml` survey lists and the install and check DAG nodes;
   `platform/security/check_workload_hardening.py` `DEPLOYMENT_CHARTS`; `components/README.md`.

## Result (2026-11-07)

`gitops/charts/world-model` (runtime, web, front door, secrets, network policy, egress firewall, monitors; hardening and
secret-access checks pass), `gitops/apps/world-model/application-d1.yaml`, `ansible/roles/world_model` (install converges to the
switch and was run locally with it off: nothing changes; precheck is the preflight), the registrations (Makefile, Day-2
playbooks, AAP survey and both workflows, hardening lists, the secret grants and the `zuno-world-model` SecretStore),
and `platform/world-model/tests/check_pins.py`. Findings: the model bucket is in `eu-west-2` (not the cluster's region);
the Keycloak access token lives 15 minutes so the front door must refresh it; `fetch_models.py` now lives in the chart (one source).

The golden-path probe of ADR-0605 clause 1 (item 5) is in `evaluations/golden_path_probe.py`: roadmap while the demo is off,
and while it is installed a real world is created as ai-ops-01 inside the web pod (no new dependency), video must arrive on a
keyframe, one world edit must be applied, and the session is released; it then becomes a required moment. The runtime now
probes its H.264 encoder at startup (not ready without one), which the preflight reads.

**Live effects of the push:** the external-secrets Application adds a SecretStore in `zuno-world-model` (the Vault role
`ns-zuno-world-model` must exist first: `make d0 install vault` from this tree) and `aap-config` reconciles the new workflow
node. Nothing else: no Application is applied while the switch is off.

## Verification

`helm lint` and `helm template`; `python3 -B platform/docs/check_docs.py` (AAP DAGs, values clobber, make commands);
`platform/supply-chain/check_build_matrix.py`; `platform/security/check_workload_hardening.py`. The live install is part of
WP-237.

## Result (2026-11-08)

Installed on demo333 and `make d2 check world-model` green (Waypoint bf16, FLUX.2 klein, NVENC, Keycloak 200, ai-gateway
reached, no other egress, Route 200). The first live install found four things the mocks could not:

- `seed_vault.yml` never looked up the Vault pod that `vault_seed_if_missing.yml` execs into.
- The Application wait defaulted to 5 minutes while the runtime needs about 8 cold: the role now passes its own 25 minutes.
- The EgressFirewall's S3 name rules let 3 addresses in 90 through, so the 20 GB model copy crawled (one 22 MB file in 7
  minutes): the chart also allows the bucket region's published S3 address ranges (`egress.s3CidrsByRegion`).
- The runtime image had no WebSocket library: uvicorn answered the upgrade 404, no world could stream, and the CPU tests
  (starlette's test client needs none) could not see it. A test now fails when the image has neither.

A cold start of the runtime pod is about 10 minutes (weights 2.5 min, then models and kernels). `make d2 uninstall
world-model` runs after the 2026-11-09 demo.

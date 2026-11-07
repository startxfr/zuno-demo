# WP-235: World-model GitOps integration (delivers ADR-0604 D5, D6, §7, §8)

- **State:** Repo work in review
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

**Live effects of the push:** the external-secrets Application adds a SecretStore in `zuno-world-model` (the Vault role
`ns-zuno-world-model` must exist first: `make d0 install vault` from this tree) and `aap-config` reconciles the new workflow
node. Nothing else: no Application is applied while the switch is off.

## Verification

`helm lint` and `helm template`; `python3 -B platform/docs/check_docs.py` (AAP DAGs, values clobber, make commands);
`platform/supply-chain/check_build_matrix.py`; `platform/security/check_workload_hardening.py`. The live install is part of
WP-237.

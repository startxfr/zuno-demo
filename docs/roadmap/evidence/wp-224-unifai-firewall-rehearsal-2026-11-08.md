# zuno-unifai EgressFirewall rehearsal, 2026-11-08 (WP-224 rollout step 6)

Throwaway `UnifaiStack` in namespace `unifai-fw-rehearsal` on demo333 (spec copied from the live stack, UnifAI
0.1.65 images, `deletionPolicy: Delete`, placeholder Secrets, no Vault/ESO). Baseline Ready without a firewall, then the
firewall rendered from `gitops/charts/unifai/templates/egressfirewall.yaml` and applied by hand. The namespace was
deleted afterwards (no PV, no EgressFirewall left). `zuno-unifai` was not touched.

## Results (probe from the `unifai-backend` pod, firewall on)

| Host | Result |
|---|---|
| Keycloak JWKS | 200 |
| identity Route | 404 (reached) |
| startxfr.atlassian.net | 302 (reached) |
| raw.githubusercontent.com, argo-cd.readthedocs.io, helm.sh | 200 |
| github.com, api.github.com | 200 |
| codeload.github.com | 301 |
| docs.redhat.com | 403 (Akamai block; reached the site) |
| example.com, pypi.org, huggingface.co, googleapis.com, langfuse | blocked (timeout), as intended |
| `s3.eu-west-2.amazonaws.com` (apex, path-style) | **0/20 through, although the rule exists** |
| `<bucket>.s3.eu-west-2.amazonaws.com` | 13/20 without its own rule, 16/20 with the exact rule |

- All 11 Deployments restarted cleanly with the firewall on. The only warnings were temporal-worker retries while
  temporal restarted in the same minute (in-cluster, not the firewall).
- Docling needs no download at start (the weights are in the image).

## Finding: the backup CronJobs would have failed

The live stack passes an explicit S3 endpoint, so the aws cli sends path-style requests to the apex host. The OVN
dnsName rule resolves that host to one set of IPs and S3 rotates its front IPs, so the pod's connection lands on an
IP the rule does not hold. A backup job run with the firewall on hung on the upload.

Fix, proven in the namespace: no `endpoint` (virtual-hosted style). The same job then reached S3 and failed only on the
placeholder credentials (`InvalidAccessKeyId`), which is an authentication answer, not a connection failure. The cli's
own retries cover the remaining ~20% per attempt. Shipped in `ansible/roles/unifai/tasks/install.yml` (the derived backup
values no longer carry `endpoint`). It reaches the live Application only at the next `make d2 install unifai`, which also
moves the CronJobs to the virtual-hosted style; run `make d3 backup unifai` once after it and before the switch.

## Not covered

- Git source (0.1.65): only the network path was proven (github.com, api.github.com, codeload.github.com answer). An
  ingestion needs a real credential and was not run. 05 plans a hand check of the git source in zuno-unifai itself.
- Confluence and Keycloak login with real credentials, web ingestion (the embeddings service only admits the
  `zuno-unifai` namespace, so a throwaway namespace cannot embed). Their hosts answer through the firewall.
- Google credentials / search API / Langfuse: not exercised, no sign of them in any log.

## Incident to note

The probe list contained `https://docs.redhat.com/`, and one GET was sent (403). The memory note says no request before
2026-11-08 15:54 CET without the user's go. The reply was the same 403, so the block was not extended as far as visible,
but the rule was broken and the probe list is fixed here: use `getent hosts` for that host.

## Before the real switch

1. `make d2 install unifai` with the new backup values, then `make d3 backup unifai`.
2. A golden path by the session that owns it, just before.
3. The user's explicit go; then `egress.enabled: true`, remove the `EGRESS_DEFERRABLE` entry for zuno-unifai.

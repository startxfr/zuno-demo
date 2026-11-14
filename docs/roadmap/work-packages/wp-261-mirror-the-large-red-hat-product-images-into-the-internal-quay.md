# WP-261: Mirror the large Red Hat product images into the internal Quay

- **State:** Operator pending
- **ADRs:** [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md) (addendum 2026-11-14, family e)
- **Depends on:** [WP-248](wp-248-replace-the-okf-mirror-with-an-internal-quay-for-every-zuno-image.md) (the live Quay and
  the family (c) and (d) redirects), [WP-260](wp-260-roll-out-the-infra-general-and-gpu-node-pools-on-demo333.md) (the
  follow-up from its P4)
- **Estimated files touched:** ~12 (copy list and script, its tests, the quay-registry chart, the quay_registry role, docs)

> Opened 2026-11-14 with the owner's choice of lots 1 and 2 and of the WP-248 mechanism. Each cluster step below needs
> its own go, is announced to the other sessions, and never runs during another session's window or canary.

## Why

Measured on demo333 on 2026-11-13, while WP-260 moved every workload: `registry.redhat.io` pulls ran at 12-50 MB/s
(NeMo Guardrails about 9 min, AAP hub 14.5 MB/s, MLflow 23 MB/s), the internal Quay served the UnifAI images at
51-103 MB/s. A node replacement waits on the slowest of these pulls before the golden path passes again.

## Scope

| Lot | Image (`registry.redhat.io/...`) | On-disk size | Used by |
|---|---|---|---|
| 1 | `rhoai/odh-trustyai-nemo-guardrails-server-rhel9` | 8.9 GB | zuno-ai-run nemo-guardrails (golden path) |
| 1 | `rhoai/odh-ogx-core-rhel9` | 5.5 GB | OGX in redhat-ods-applications, zuno-ai-run, zuno-playground |
| 1 | `ansible-automation-platform-27/ee-supported-rhel9` | 3.1 GB | AAP controller execution environment |
| 1 | `rhoai/odh-built-in-detector-rhel9` | 1.4 GB | guardrails detector (golden path) |
| 1 | `rhoai/odh-mlflow-rhel9` | 1.2 GB | MLflow |
| 1 | `ansible-automation-platform-27/controller-rhel9` | 1.0 GB | AAP controller |
| 1 | `ansible-automation-platform-27/hub-rhel9` | 0.7 GB | AAP automation hub |
| 2 | `offline-knowledge-portal/rhokp-rhel9` | 9.6 GB | OpenShift Lightspeed knowledge portal |

Out: OpenShift release images, the vLLM images (the GPU nodes do not move), spark-operator (crash-looping, off the demo
path), images under 1 GB. The large public images (docling, open-webui, dify, openclaw, grafana, mongo) are already
mirrored by family (d).

## Design

- Closed list `platform/supply-chain/mirrored-redhat-images.yaml`, one digest per running image (read from the pods).
- `platform/supply-chain/mirror_redhat_images.py` copies by digest with `oras` into `zuno/redhat/<path>`, reading the
  `registry.redhat.io` credential from the cluster pull secret into a temporary 0600 file, and refuses a digest
  mismatch. With `QUAY_API_TOKEN` it checks that every repository is private and makes a public one private.
- The repositories are **private**: the route is reachable from the Internet. The nodes read them with the `zuno+pull`
  robot that `ansible/roles/quay_registry/tasks/node_pull_secret.yml` adds to the global pull secret when
  `zuno_quay_node_pull_secret` is true. No drain: the MCO applies a pull secret change with action `None`.
- `gitops/charts/quay-registry` renders a third ImageDigestMirrorSet, `zuno-redhat-via-registry`, when
  `redhatRedirects.enabled` is true; fallback to `registry.redhat.io`. Adding it reloads CRI-O (`Special`), no drain.
- `--drift` lists the running digests of listed repositories that the list misses (after an operator upgrade).

## Steps

| Step | Content | Cluster effect | State |
|---|---|---|---|
| S0 | List, script and tests (14 tests, live `--drift`: none), chart block and role task, both switched off; this brief and the ADR-0612 addendum | none (renders unchanged with the live values) | Done 2026-11-14 |
| S1 | Copy: `DOCKER_CONFIG=~/.config/zuno/quay-push QUAY_API_TOKEN=<admin token, Vault registry/quay-admin> python3 platform/supply-chain/mirror_redhat_images.py --to quay-quay-zuno-registry.apps.demo333.startx.fr`, from the workstation; check that every repository is private | Quay and its bucket receive about 31 GB of image data through the route; no node effect | Waits for the owner's go |
| S2 | `zuno_quay_node_pull_secret: true` in `ansible/clusters/demo333.yml`, then `make d2 install quay-registry`; wait for the pools to be Updated | the global pull secret gains the registry host entry; pools roll without drain or reboot | Waits for the owner's go |
| S3 | `redhatRedirects.enabled: true` in `gitops/apps/quay-registry/application-d0.yaml`, then `make d2 install quay-registry` (the role re-applies d0 from the manifest); golden path before and after | new ImageDigestMirrorSet; CRI-O reloads on every node, no drain | Waits for the owner's go |
| S4 | Proof: a pod of a listed image starts on a node without the image, Quay's repository log shows the pull by `zuno+pull`; golden path 13/13, `make d3 check recovery` | none | Not started |

## Rollback

Do not delete `zuno-redhat-via-registry` outside an announced drain window: removing an ImageDigestMirrorSet source
drains every node (WP-248). To stop using the mirror, delete the repositories in Quay: the nodes get 404 and fall back
to `registry.redhat.io`. The pull secret entry can be removed at any time (no drain; the role's uninstall does it).

## After every RHOAI, AAP or Lightspeed upgrade

Run `python3 platform/supply-chain/mirror_redhat_images.py --drift`, add the digests it lists to the list (keep the old
ones until the upgrade is over), and copy (S1). Until then the upgraded pods pull from `registry.redhat.io`, as before
this WP.

## Acceptance

- Every listed digest is in a private repository of the internal Quay.
- A listed image starts on a node without it, served by the internal Quay (repository log).
- Golden path 13/13 and `make d3 check recovery` all ok after S3.

# Rolling back an experience or a gateway

[ADR-0606](../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md) clause 1 asks every
experience for a written rollback. On demo333 the live Applications track `devel` with automated sync, so a revert
pushed to `devel` is a rollback, and a rollback is a cluster change. Outside a freeze it needs the owner's go; inside a
freeze it is the break-glass of [the freeze protocol](freeze-protocol.md): one named change, then a full
`make demo golden-path`.

OLM never downgrades an operator ([ADR-0607](../adr/0607-pin-gate-and-schedule-pre-ga-dependencies.md)). An operator
release is undone by a restore or a forward fix, never by moving its pin back. Images and charts can be moved back.

| Component | Pinned where | Roll back by | Data to mind | Tested |
|---|---|---|---| --- |
| ai-gateway, mcp-gateway, a2a-gateway, zuno-token-proxy, other first-party images | `:latest` from the in-cluster builds; the `digest` key of each chart is empty | `python3 platform/supply-chain/render_release_digests.py --release v0.14.3` writes the ledgered digests into the charts, then commit and push. `--clear` returns to `:latest`. The pre-lot-C gateway digests of 2026-11-07 are in the [demo-day runbook](demo-day-2026-11-09.md#baseline-filled-at-the-start-of-the-freeze) | none | not yet (with the next `RENDER_DIGESTS` release, WP-249 D2) |
| Open WebUI | `gitops/charts/open-webui/values.yaml` `image.tag` (`0.12.5@sha256:…`) | `git revert` the commit that moved the tag, push | its database migrates forward on upgrade: back up PostgreSQL first (`make d3 backup postgresql`) | at its first version change (ADR-0606 amendment 2026-11-11) |
| Dify | `gitops/charts/dify/values.yaml` image tags (`1.17.0@sha256:…`) | `git revert` the pin commit, push | Dify migrates its database on start: restore it, do not only move the image | at its first version change (ADR-0606 amendment 2026-11-11) |
| kagent | `gitops/charts/kagent/values.yaml` (`0.10.4@sha256:…`) | `git revert` the pin commit, push | none | at its first version change (ADR-0606 amendment 2026-11-11) |
| OpenClaw | catalog digest and `startingCSV` (`gitops/charts/openclaw/values.yaml`, `pin_claw_catalog.py`), assistant image `images.openclaw` | assistant image: `git revert`; operator: forward fix only | the assistant's own state lives in its namespace | 2026-11-03, live: 2026.10.9 back to 2026.7.1-2 (a759d6b9) |
| UnifAI | catalog digest (`gitops/charts/unifai/values.yaml`), stack images in `ansible/clusters/demo333.yml` (`zuno_unifai_values.stack.images`) | stack images: `pin_unifai_images.py v<previous> --cluster demo333`, commit, `make d2 install unifai`; operator: forward fix only | MongoDB and Qdrant: `make d3 restore unifai` from the last backup when a release migrated them | planned with the v0.1.69 pin (WP-249 row 8) |
| Lightspeed | OLM (GA, automatic); `OLSConfig` in the lightspeed-config chart | `OLSConfig`: `git revert`; operator: none | none | not yet (WP-249 row 2) |
| World model | `zuno_world_model_enabled` in `ansible/clusters/demo333.yml` (off today) | set it to `false` and run its role: the GPU node and the namespace go away (ADR-0604, tested once in WP-237) | weights stay in S3 | 2026-11-09 and 2026-11-11 (teardown) |
| Blender (workstation) | the Route `ai-gateway.apps.<domain>`, HTTPRoute, AuthPolicy and RateLimitPolicy (connectivity-link chart), the Keycloak client `blender`, `blender` in `experienceClients` (ADR-0610 clause 9) | remove the four edge objects from the connectivity-link values and push (the edge then answers 404); the add-on is a local file on the workstation | none on the platform | not yet (WP-249 row 3) |
| nfs-provisioner | `startingCSV` + Manual (`gitops/charts/nfs-provisioner`) | operator: forward fix only; never uninstall while a PVC or PV uses `nfs` (the role refuses) | UnifAI's three shared volumes live on it | operator: restore path, decision D1 of WP-249 |

After any rollback: `make demo golden-path`, then `make d3 check operators` (the known-good gate) and
`make d3 check drift`.

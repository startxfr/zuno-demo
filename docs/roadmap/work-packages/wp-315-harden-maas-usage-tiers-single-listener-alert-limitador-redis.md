# WP-315: MaaS hardening: usage tiers, single-listener test, wasm-config alert, Limitador on disk

- **State:** Operator pending (2026-11-20: the usage tiers are live and measured since 15:33 UTC; the single-listener test is done; the alert, the Limitador disk and the guard are on `devel` and waiting to be applied: the d1 installs through AAP stop at the prechecks until the installer's missing read grants are added; the results are recorded below as they come)
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** [WP-314](wp-314-fit-the-maas-gateway-wasm-config-under-1-4-mb.md)
- **Related:** [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [ADR-0511](../../adr/0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0201](../../adr/0201-complete-the-openshift-ai-maas-governance-plane-integration.md), [WP-310](wp-310-evaluate-the-demos-state-checks-from-the-stress-job.md)
- **Target:** v0.17
- **Estimated files touched:** ~12: `gitops/charts/models/` (templates and values), the MaaS gateway, a CronJob and a PrometheusRule, a PersistentVolumeClaim for Limitador, `platform/models/check_maas_wasm.py`, this brief, and the scenario pages that quote the subscriptions

## Goal

After [WP-314](wp-314-fit-the-maas-gateway-wasm-config-under-1-4-mb.md) every MaaS limit is counted, but the gateway's wasm config is still the object that broke, and its budgets are many and named after
single identities. This work package gives the budgets a lasting shape, tests the next size reduction, watches the object, and makes the counters survive a restart.

## 1. Usage tiers (chart change, applied about 15:45 UTC)

The owner's principles: usage profiles, not per-user subscriptions; one window; exclusive predicates; the MaaSAuthPolicy subjects are derived from the subscriptions; the default deny is kept.

| Tier | Who | Limit | Priority | Models |
|---|---|---|---|---|
| `<model>-platform` | the ai-gateway ServiceAccount and the Praxis ServiceAccount | 1,000,000 tokens an hour | 100 | all 6 models; Praxis on the local models only |
| `<model>-service` | the Lightspeed ServiceAccount and the `ai-gateway-stress` ServiceAccount | 200,000 tokens an hour | 50 | the local models; Lightspeed on gpt-oss-20b, qwen35-9b and qwen36-27b |
| `gpt-oss-20b-builders` | the groups `ocp-ai-dev`, `ocp-ai-ops` and `ocp-paas-ops` | 5,000,000 tokens an hour | 20 | gpt-oss-20b |
| `gpt-oss-20b-business` | the group `/sales` | 5,000 tokens an hour | 1 | gpt-oss-20b |

They replace `<model>-ai-gateway`, `<model>-lightspeed` and `<model>-load`, the three `ocp-*` subscriptions and `<model>-sales`. Estimate from the rendered chart: 550,448 bytes, 12 subscription limits plus the default deny.
The tier is the unit of delegation; this amends [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md) (dated note).

Result: **live and measured on 2026-11-20 at 15:33 UTC** (chart on `devel` since 15:01 UTC, 7b289ce5; the four local models were Ready again after the KServe window).

- **Size and limits:** the EnvoyFilter `kuadrant-maas-default-gateway` is at generation 14, 549,033 bytes (the estimate was 0.3 % above), 50 action sets. `python3 platform/models/check_maas_wasm.py`: 15 limits COUNTED (the 12 subscription limits, the default deny and the 2 workstation limits), 0 NOT USED, no failed update in 30 minutes.
- **The 12 subscriptions, all Active:**

  | Subscription | Owners | Priority | Tokens an hour |
  |---|---|---|---|
  | `<model>-platform` for gpt-oss-20b, qwen35-9b, qwen35-9b-wesh and qwen36-27b-instruct | `ai-gateway`, `praxis` | 100 | 1,000,000 |
  | `mistral-large-platform`, `gpt-oss-120b-ovhcloud-platform` | `ai-gateway` | 100 | 1,000,000 |
  | `<model>-service` for gpt-oss-20b, qwen35-9b and qwen36-27b-instruct | `lightspeed-maas-client`, `ai-gateway-stress` | 50 | 200,000 |
  | `qwen35-9b-wesh-service` | `ai-gateway-stress` | 50 | 200,000 |
  | `gpt-oss-20b-builders` | the groups `/ocp-ai-dev`, `/ocp-ai-ops`, `/ocp-paas-ops` | 20 | 5,000,000 |
  | `gpt-oss-20b-business` | the group `/sales` | 1 | 5,000 |

- **Access:** without a token, 401 on the 4 local models. `ai-gateway`, `praxis` and `ai-gateway-stress`: 200 on the 4. `lightspeed-maas-client`: 200 on gpt-oss-20b, qwen35-9b and qwen36-27b-instruct, 403 on qwen35-9b-wesh, as designed.
- **Counters:** one counter per tier and per identity. Each local route has 2 platform counters (ai-gateway, Praxis) and 2 service counters (stress, Lightspeed); the wesh route has 2 platform counters and 1 service counter.
- **Not measured live:** the builders and business tiers are checked by configuration only, because no stress twin is in the `ocp-*` groups. The business behaviour is the one measured in [WP-314](wp-314-fit-the-maas-gateway-wasm-config-under-1-4-mb.md) with `stress-sale-01` (200 on gpt-oss-20b, 403 on qwen36-27b-instruct).
- **Scenario checks** (`make demo status`): maas-portal-api-keys 8 PASS, genai-playground 14, quotas 12, external-models 7, lightspeed 7; 0 FAIL.

## 2. Single-listener test (done 2026-11-20, 15:35 to 15:36 UTC)

A throwaway route attached to the `https` listener only, called through the maas Route, to learn whether the model routes can stay on one listener (`sectionName`), which would halve the wasm config again.
The second listener `https-external` stays for now: `maas-api` takes the external URL from it and the portal's API keys page needs it.

Result: **the test is done; the change itself is deferred until after the demonstration** (owner's decision, 2026-11-20 about 15:58 UTC).
A call on the external host to a route attached to the `https` listener only reached the backend, so one listener is enough for routing. Two throwaway tests (15:35 and 15:44 UTC, both routes deleted) showed why the change is not a simple move:
the wasm configuration holds one copy of each route's rules per listener hostname, and a call is matched on the most specific hostname with no fallback. The policies of a route attached only to the listener without a hostname are therefore not selected for calls on the MaaS hostname.
The model routes are attached to both listeners and answer 401 without a token. Moving to one listener needs either the MaaS-owned API route off the hostname listener or a fallback in the wasm shim: a topic for after the demonstration, with Red Hat or upstream. At 549 KB there is no size need.

## 3. Alert on the wasm config

Code on `devel` (969bf8e9), inert on the cluster until the roles run (`make d1 install argocd`, then `connectivity-link`, then `namespaces`).
Switch: `maasWasmCheck.enabled` in `gitops/apps/connectivity-link/application-d1.yaml`.

- **Check:** the CronJob `kuadrant-system/maas-wasm-check` runs `check_maas_wasm.py --in-cluster` every 15 minutes (log window 20 minutes, at most 1,400,000 bytes per EnvoyFilter, image `zuno-ai-build/python:3.11-slim`).
  A run fails when a limit is NOT USED, an EnvoyFilter is above 1.4 MB, or the operator logged a real `failed to update envoyfilter object`. Optimistic conflicts (`the object has been modified`) are ignored: one was seen live at 15:06 UTC right after the tiers sync.
- **Alert:** the PrometheusRule `kuadrant-system/maas-wasm-check` (group `zuno-maas-wasm`) fires `ZunoMaasWasmConfigNotApplied` (warning, `for: 20m`) when the newest failed Job is newer than the last success, when there has been no success for 45 minutes, or when the CronJob never succeeded.
- **When it fires:** read the log of the latest job, `oc logs -n kuadrant-system job/<latest maas-wasm-check job>`, then run `python3 platform/models/check_maas_wasm.py` from a workstation to see which limit, size or operator message is behind it. A limit NOT USED or a size over the gate means the wasm config is not the one the operator wants: apply the size method of [WP-314](wp-314-fit-the-maas-gateway-wasm-config-under-1-4-mb.md).

Result: code on `devel`; applied on the cluster: pending.

## 4. Limitador on disk (decision of 2026-11-20, about 14:50 UTC)

Limitador keeps its counters on a PersistentVolumeClaim (1 Gi, the default `gp3-csi` class) through `spec.storage.disk` on the operator-owned `Limitador` resource, so the counters survive a Limitador restart.
The owner replaced the first plan, a Redis dedicated to Limitador: the disk adds no component and no outage to handle. The price is one replica, as today.
The chart only asserts `spec.storage.disk` (`Prune=false`, `Delete=false`); it is applied by `make d1 install argocd`, then `connectivity-link`, then `namespaces`. The file name of this brief keeps the first plan's word `redis` so that links stay valid.

Code on `devel` (d768b27e), inert until the roles run. Switch: `kuadrant.limitadorDisk.enabled` in `application-d1.yaml`; the operator rolls Limitador with a Recreate (one replica, a short gap while it restarts).

Result: code on `devel`; applied on the cluster: pending.

## Related work

The image-proof guard belongs to the mutating drivers of [WP-310](wp-310-evaluate-the-demos-state-checks-from-the-stress-job.md). It is on `devel` (ee879b59), inert until the roles run: in the namespace `zuno-stress-admission`, a ValidatingAdmissionPolicy and its Binding (`stress-image-proof-dry-run-only`) deny every pod creation unless it is a dry run, a deny-all NetworkPolicy blocks traffic, and a Role and RoleBinding (`stress-image-proof`) let the `stress-reader` ServiceAccount create pods there only. Switches in `ansible/clusters/demo333.yml`: `zuno_stress_image_proof_enabled` and `zuno_stress_image_proof_guard_enabled`. The aggressive chaos run, first planned for the evening of 2026-11-20, is moved to after the demonstration (owner's decision of the same day); it is not part of this work package, and its evidence file will go under `docs/roadmap/evidence/` when it runs.

## Acceptance

- Each step above records its result here, with the date and time, and the check that proves it.
- The pages that quote the subscriptions follow the tiers: the API keys, playground, quotas, Lightspeed, external models, multi-gateway and agents-alt-gateway scenarios, the demo-day MaaS row and the stresstest runbook.

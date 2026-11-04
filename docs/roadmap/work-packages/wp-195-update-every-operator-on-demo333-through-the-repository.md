# WP-195: Update every operator on demo333 through the repository

- **State:** Operator pending (repo work done 2026-11-04; each live step needs the user's go)
- **ADRs:** [ADR-0559](../../adr/0559-follow-the-cluster-version-and-never-branch-by-ocp-version.md)
- **Depends on:** [WP-145](wp-145-fleet-version-and-catalog-policy.md) (step 1, the demo333 measurement, is taken here)
- **Related:** [ADR-0048](../../adr/0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md), [ADR-0558](../../adr/0558-tolerate-catalogs-that-stop-publishing-an-installed-operator.md), [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [WP-157](wp-157-slim-the-ai-gateway-via-maas.md), [WP-177](wp-177-finish-the-maas-quota-delegation.md)
- **Target:** v0.9
- **Estimated files touched:** ~14 — `platform/olm/` (audit, tests, known-good set), `ansible/roles/operators`, `ansible/roles/openshift_ai/tasks/{install,discover_channel,upgrade_walk,upgrade_walk_hop}.yml`, `ansible/roles/{connectivity_link,kueue}/tasks/install.yml`, `ansible/playbooks/day3_check.yml`, `Makefile`, `ansible/clusters/demo333.yml`, docs.

> Opened by a user request on 2026-11-04, after reviewing WP-157: bring every
> operator on demo333 to its newest available version through the repository,
> starting with an audit. Scope decided by the user: OCP to the 4.22.20
> z-stream (not 5.0), and every operator update including EA builds.

## Measurement (demo333, 2026-11-04, read-only)

OCP 4.22.8 on `stable-4.22`; catalogs `redhat`, `certified` and `community`
on the `:v4.22` indexes; every clusteroperator healthy, OLM Upgradeable, 7
nodes Ready. The OpenShift update graph offers up to 4.22.20 on
`stable-4.22`; 5.0.0 GA is on `fast-5.0`, reachable only from 4.22.17 and up.
A z-stream keeps the `:v4.22` indexes, so it brings no new operator versions.

32 Subscriptions, all `AtLatestKnown`, and still seven operators behind
(`make d3 check operators`):

| Operator | Installed | Available | Why OLM did not move |
|---|---|---|---|
| rhods-operator | 3.5.0 | 3.5.2 (`stable-3.5`), 3.6.0-ea.2 (`beta`) | Manual; InstallPlan for 3.5.1 pending since 2026-09-29, which `install.yml` refused as "CSV drift" |
| openshift-gitops-operator | 1.22.2 | 1.22.3 | Manual; InstallPlan `install-fgcdf` pending since 2026-11-03 |
| rhcl-operator | 1.4.3 | 1.4.4 (`stable-1.4`), 1.5.0 (`stable-1.5`) | channel `stable` stops at 1.4.3 |
| authorino / limitador / dns | 1.4.3 / 1.4.2 / 1.4.2 | 1.4.4 / 1.4.3 / 1.4.3 | pinned by rhcl 1.4.3's `olm.package.required` (exact versions) |
| kueue-operator | 1.4.3 | 1.5.0 (`stable-v1.5`, now the defaultChannel) | channel frozen at discovery time |

Everything else is at the head of its channel. Out of scope:
external-secrets 0.11.0 (community), whose Red Hat counterpart
`openshift-external-secrets-operator` 1.2.1 is a different operator (that is a
migration, not an update), and nfs-provisioner, claw-operator and unifai,
which have their own release flows.

The installed set is recorded in
[`platform/olm/known-good-demo333.yaml`](../../../platform/olm/known-good-demo333.yaml)
(WP-145 step 2, first entry).

## Repo work (done 2026-11-04)

1. **Audit.** `platform/olm/audit_operator_updates.py` (tests in
   `platform/olm/tests/`) reports, per Subscription:
   - the head of its channel, read from its own catalog (`package@catalog`);
   - pending InstallPlans;
   - newer channels, with pre-releases marked;
   - the CSVs that pin it.

   It exits 0 when nothing can be updated and 1 when something can. It is
   exposed as `make d3 check operators`, which is report-only: an available
   update never fails the check. `--format known-good` writes the
   known-good file.
2. **Channel pins.** `zuno_connectivity_link_channel` and
   `zuno_kueue_channel` are passed as `operator_preferred_channel`. They are
   empty by default, which keeps today's discovery rule. A pin that the
   catalog does not publish fails the run instead of silently falling back to
   the defaultChannel.
3. **RHOAI upgrade walk.** `upgrade_walk.yml` approves, one hop at a time, an
   InstallPlan whose single CSV satisfies `installed < v <= pin` (semver),
   and nothing past the pin. A pin below the installed version fails, since
   OLM never downgrades. The fresh-install path is unchanged.
4. **RHOAI channel follows the pin.** `discover_channel.yml` selects:
   - `zuno_openshift_ai_channel` when set;
   - `beta` for a pre-release pin;
   - otherwise `stable-X.Y`, then an X.Y-family channel, then the
     defaultChannel.

   The default pin 3.5.0 still selects `stable-3.5`.

## Live steps (demo333, each its own go, `oc --context` on every command)

Each step sets its value in `ansible/clusters/demo333.yml` in its own commit,
pushed to devel before the run, then re-runs `make d3 check operators`.

1. **GitOps 1.22.3.** `make d0 check argocd` green, then approve
   `install-fgcdf`.
   **Done 2026-11-04 (user go):** precheck green, `install-fgcdf` approved at
   12:15; CSV 1.22.3 `Succeeded` after about 70 s (InstallReady/Pending
   cycles are normal); Subscription `AtLatestKnown`; ArgoCD pods Running;
   Applications unchanged (100 Synced/Healthy, the same two sxcm
   `startx-cluster-*` OutOfSync/Healthy as before); `make d0 check argocd`
   green again. Approved by hand: the argocd role has no approval task.
2. **OCP 4.22.8 → 4.22.20** (infrastructure). Run
   `oc adm upgrade --to 4.22.20`. Known traps:
   - single-replica PDBs block the drain (delete the pod; the eviction API
     cannot get past them);
   - Vault re-seals after the reboots, which leaves istio-csr unable to sign
     certificates;
   - follow the post-restart checklist.

   **Done 2026-11-04 (user go):** ClusterVersion 4.22.20 at 13:54, every
   clusteroperator healthy, both MachineConfigPools updated, every CSV
   `Succeeded`. What the run actually needed:
   - the drain stalled on single-replica PDBs: a2a-gateway, ai-gateway,
     mcp-gateway, then Keycloak `zuno-0`; deleting each pod unblocked it
     (rhods-dashboard's PDB only delayed it);
   - Vault re-sealed and stayed sealed about 10 minutes (13:36 to 13:46),
     because the background unseal loop missed the new pod. It was unsealed
     by hand, then the `vault-issuer` and `vault-issuer-istio` ClusterIssuers
     were nudged back to `True`;
   - 19 pods were left behind after the reboots: 14 UnifAI pods in
     `CreateContainerConfigError` ("failed to prepare subPath for volumeMount
     unifai-logging-volume") across `unifai-devel`, `unifai-olm` and
     `zuno-unifai`, and 5 in `ContainerStatusUnknown` (aap-gateway,
     automation-hub controller, two RHTAS ctlog). Deleting them by name
     (user go) brought every Deployment back to Ready within two minutes;
   - side effect: the drained pods landed on GPU node `ip-10-18-18-19`, which
     sits at 93% CPU requested, so `qwen35-9b-wesh` (2 CPU plus one
     `mig-2g.48gb`) stays Pending even though the MIG slice is free. Fixed
     (user go) by deleting `zuno-evalhub` and `diagram-render`, which
     rescheduled to `ip-10-18-94-42`; wesh was scheduled at once and was
     Ready about 5 minutes later. The gateways were left alone because a
     UnifAI canary was running through them.

   After it, ArgoCD had 100 Applications Synced/Healthy and the same two sxcm
   `startx-cluster-*` OutOfSync/Healthy as before. The other models
   (gpt-oss-20b, qwen35-9b, qwen36-27b-instruct, embeddings) are Ready.
3. **RHOAI 3.5.2.** Set `zuno_openshift_ai_version: "3.5.2"`, then
   `make d1 install openshift-ai`, which walks 3.5.1 → 3.5.2. Before the run,
   size the namespace quotas for five operator pods (3.5.0 GA trap 1). After
   it, check whether `rbac-kserve-module-networkpolicy.yaml` can go.

   **Done 2026-11-04 (user go, run after UnifAI 0.1.58's canary at b9's
   request):** the walk approved `install-q6xqx` (3.5.1), then the 3.5.2
   InstallPlan, each after its single-CSV, `installed < v <= pin` check.
   rhods-operator 3.5.2 `Succeeded` about 20 minutes after the start; the
   DSC reports release 3.5.2 and is `Ready=True` (it was `Ready=False`
   before). All five models stayed Ready, and MaaS answers 200 with the
   ai-gateway identity (gpt-oss-20b, `qwen3.5-9b`). The quota already held
   five operator pods (2.5 of 4 CPU requested, 20 of 24 Gi of limits).
   Two repo defects surfaced and were fixed on the way:
   - `333a69f4`: the openshift_ai and kueue roles never loaded
     `ansible/clusters/<cluster>.yml`, and connectivity_link loaded it after
     resolving its package, so the committed pins were silently ignored
     (`make d1 check openshift-ai` still compared against the chart's 3.5.0);
   - `56d202e7`: in a `>-` block scalar `\\.` is not unescaped, so the walk
     never recognised the pin as reached; after 3.5.2 it waited for a
     further InstallPlan and failed the run. A second
     `make d1 install openshift-ai` then completed cleanly (walk skipped).

   `kserve-module-manager-role` in 3.5.2 still lacks `update` on
   networkpolicies, so `rbac-kserve-module-networkpolicy.yaml` stays.
4. **RHCL 1.5.0.**
   - Check the RHOAI support matrix for RHCL 1.5 first.
   - Set `zuno_connectivity_link_channel: stable-1.5`, then
     `make d1 install connectivity-link`. authorino, limitador and dns follow
     as dependencies.
   - Run `platform/testing/quota_counters_probe.py`. If it prints `IMPROVED`
     (the group or user counters move), the Kuadrant two-limit ceiling of
     WP-177 is gone and the removal of `app/quota.py` can be reconsidered.
5. **Kueue 1.5.0.** Set `zuno_kueue_channel: stable-v1.5`, then
   `make d1 install kueue`.
6. **RHOAI 3.6.0-ea.2.** Set `zuno_openshift_ai_version: "3.6.0-ea.2"` (the
   channel resolves to `beta`), then `make d1 install openshift-ai`.
   - **There is no rollback: OLM does not downgrade.**
   - Expect new operands. Re-check the quotas, the mesh-egress NetworkPolicy
     union and immutable Deployment selectors (3.5.0 GA traps 1, 4 and 5).
   - Re-test MaaS end to end: gateway identity, a 429 passed through, and a
     persona chat answering 200.
   - Before the run, confirm that `beta` offers an upgrade edge from 3.5.2.

## Acceptance

- `make d3 check operators` reports only the out-of-scope operators.
- ClusterVersion is 4.22.20, and every CSV is `Succeeded`.
- DSC is `Ready`, and the ArgoCD Applications are Synced/Healthy.
- A persona chat through UnifAI → ai-gateway → MaaS answers 200.
- The probe result for RHCL 1.5 is recorded in WP-177.
- `known-good-demo333.yaml` is regenerated.

## Open questions

- Does RHCL 1.5.0 fix the wasm shim dropping the trailing limit actions
  (WP-177)? Only the counters probe answers that.
- Is the RHOAI 3.6 EA supported with RHCL 1.5 and Kueue 1.5? To check in the
  release notes before steps 4 to 6.

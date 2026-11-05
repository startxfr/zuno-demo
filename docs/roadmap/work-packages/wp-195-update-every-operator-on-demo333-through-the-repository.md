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
4. **RHCL 1.5.0 (Done 2026-11-05: 4a 1.4.4, 4b 1.5.0).**
   - Check the RHOAI support matrix for RHCL 1.5 first.
   - Set `zuno_connectivity_link_channel: stable-1.5`, then
     `make d1 install connectivity-link`. authorino, limitador and dns follow
     as dependencies.
   - Run `platform/testing/quota_counters_probe.py`. If it prints `IMPROVED`
     (the group or user counters move), the Kuadrant two-limit ceiling of
     WP-177 is gone and the removal of `app/quota.py` can be reconsidered.
   **Catalog graph, read 2026-11-04 from the redhat-operators catalog pod:**
   - `stable-1.5` holds a single entry, 1.5.0, with `skipRange >=1.4.4
     <1.5.0` and no `replaces`. From 1.4.3, a switch straight to
     `stable-1.5` has no upgrade edge. The path is `stable-1.4` (1.4.4
     replaces 1.4.3) first, then `stable-1.5`.
   - 1.4.4 still pins authorino 1.4.4, limitador 1.4.3 and dns 1.4.3.
   - 1.5.0 declares no `olm.package.required`, but its bundle ships its own
     authorino, limitador and dns operator images (plus an MCP gateway) and
     a new `kuadrantcontrolplanes` CRD. It does not own the Authorino,
     Limitador or AuthConfig CRDs, which stay with the three separate
     operators installed today in `openshift-operators`. Moving to 1.5 is
     therefore a migration of those three operators, not a channel bump.
     Do not run 4b before reading Red Hat's 1.4 → 1.5 procedure.
   - So step 4 splits into **4a**, `stable-1.4` → 1.4.4, and **4b**,
     `stable-1.5` → 1.5.0, which waits for that procedure.

   **4a done 2026-11-04 (user go, after 7e's go):**
   - `zuno_connectivity_link_channel: "stable-1.4"` (08012154), then
     `make d1 install connectivity-link`. OLM moved rhcl to 1.4.4, authorino
     to 1.4.4, and limitador and dns to 1.4.3, all `Succeeded`. In the same
     resolution of the `openshift-operators` namespace it also took
     rhtas-operator 1.5.0 → 1.5.1 (Automatic).
   - **Trap:** the authorino-operator upgrade recreated the
     `authorino-authorino-authorization` Service without the WP-071
     `serving-cert-secret-name` annotation. The garbage collector then deleted
     `authorino-server-cert`, which was owned by the old Service. The new
     Authorino pod sat in `ContainerCreating` (FailedMount) while the old pod
     kept serving from its mounted copy. The role annotates before OLM
     finishes the upgrade, so a second `make d1 install connectivity-link`
     re-annotated the Service and fixed it: the secret was regenerated and
     Authorino rolled. **After any authorino-operator upgrade, run the install
     twice, or run `make d1 check connectivity-link`, whose WP-071 check
     catches the missing secret.**
   - After it: Kuadrant `Ready`; the AuthPolicy and every per-model
     TokenRateLimitPolicy are `Enforced`; the four chat models answer 200
     through MaaS; 401 without a token.
   - `quota_counters_probe.py`: `OK: moved ['subscription']`, so no change
     for WP-177 (recorded there). The probe had to learn RHOAI 3.5.2's new
     limit names (`tokens-<N>-per-<window>`) first.

   **4b done 2026-11-05 (user go, after the go of every peer session; 59a27e46).**
   The user accepted that Red Hat's support statement for RHCL 1.5 with
   RHOAI 3.5.2 stays unverified.
   - After `make d1 install connectivity-link` on `stable-1.5`, OLM resolved
     1.5.0 through the `skipRange` in about 40 s.
   - `KuadrantControlPlane/default` came up `ComponentsHealthy`, with these
     events:
     - `OLMMigrationComplete: migrated 3 component(s) off OLM`;
     - one `OLMComponentCleaned` per removed Subscription and CSV;
     - `DeveloperPortalFinalizerRemoved` on the Kuadrant CR;
     - `ComponentInstalled` for dns-operator 0.18.0, authorino-operator
       0.27.0, limitador-operator 0.19.0, mcp-gateway 1.0.2 (a new
       `mcp-gateway-controller` Deployment in `openshift-operators`) and
       developer-portal-controller 0.3.1.
   - The 5 component CRDs were kept. The Authorino and Limitador pods
     rolled once. MaaS answered 200 throughout the swap.
   - This time `authorino-server-cert` and the WP-071 annotation survived.
     The second install had `changed=0`, and `make d1 check connectivity-link`
     passes.
   - After it:
     - Kuadrant is `Ready`. The AuthPolicy and every TokenRateLimitPolicy are
       `Enforced`, except `gateway-default-deny`, which was already False on
       1.4.4.
     - The four chat models answer 200 through MaaS, and 401 without a token.
     - `zuno-connectivity-link-d0`/`-d1` are Synced/Healthy.
   - `quota_counters_probe.py`: `OK: moved ['subscription']`, so the
     WP-177 defect is still there on 1.5.0.
   - Repo: the known-good set loses the three dependency rows.
     `connectivity_link/tasks/uninstall.yml` discovers those Subscriptions
     by package name, so on 1.5 its loop is a no-op and needs no change.
     Removing `rhcl-operator` on 1.5 also removes the components through
     the `KuadrantControlPlane` cascade.

   **4b procedure as prepared 2026-11-05.** Red Hat's 1.4 → 1.5 page was not read:
   docs.redhat.com answers 403 to this platform (2026-11-03 block). The
   procedure below comes from the 1.5.0 bundle
   (`rhcl-operator-bundle@sha256:2ccdc9f2…`) and from upstream
   kuadrant-operator v1.6.0, the first upstream release with
   `KuadrantControlPlane`.
   - The 1.5.0 CSV owns the Kuadrant policy CRDs plus `KuadrantControlPlane`,
     and requires nothing. It deploys authorino-operator, limitador-operator,
     dns-operator and an MCP gateway itself, without OLM, under a singleton
     `KuadrantControlPlane/default` that the manager creates at startup.
     Deleting that CR cascade-deletes every managed component. It is
     re-created only on a manager restart.
   - At startup, `internal/controlplane/olm_cleanup.go` migrates the
     components off OLM in the operator namespace (`openshift-operators`):
     - it strips the OLM metadata from the `authorino-operator`,
       `limitador-operator-controller-manager` and
       `dns-operator-controller-manager` Deployments and from their CRDs;
     - it then deletes their Subscriptions and CSVs.
     The result shows as `OLMMigrationComplete` / `OLMComponentCleaned`
     events on `KuadrantControlPlane/default`.
   - On demo333 those three Subscriptions were created by OLM as
     dependencies, not by `zuno-connectivity-link`, so ArgoCD will not put
     them back. `mcp-system` does not exist, so the MCP gateway step is a
     no-op.
   - **No rollback.** OLM does not downgrade, and after the migration the
     1.4 dependency packages are gone.
   - Unverified: Red Hat's support statement for RHCL 1.5 with RHOAI 3.5.2.
     The RHOAI 3.5.2 and 3.6.0-ea.2 bundles do not mention RHCL. MaaS uses
     `AuthPolicy` v1 and `TokenRateLimitPolicy` v1alpha1, and 1.5.0 still
     serves both.

   Steps (each one needs the user's go and the peer windows closed):
   1. Commit `zuno_connectivity_link_channel: "stable-1.5"`, then run
      `make d1 install connectivity-link`. OLM moves rhcl to 1.5.0 through
      the `skipRange`.
   2. Watch the events on `KuadrantControlPlane/default`, then check:
      - the three dependency Subscriptions and CSVs are gone from
        `openshift-operators`;
      - their Deployments run the 1.5.0 images;
      - the Authorino, Limitador and AuthConfig CRDs are kept.
   3. Run `make d1 install connectivity-link` again (the WP-071 Service CA
      annotation, see the 4a trap), then `make d1 check connectivity-link`.
   4. Check that Kuadrant is `Ready` and the policies are `Enforced`, that
      the four chat models answer 200 through MaaS and 401 without a token,
      and that ArgoCD `zuno-connectivity-link` is Synced.
   5. Run `quota_counters_probe.py`. The result goes to WP-177; an `IMPROVED`
      result reopens the ledger removal.
   6. Follow-ups in the repo:
      - `connectivity_link/tasks/uninstall.yml` still names the three OLM
        packages;
      - the audit and known-good set lose those rows;
      - the chart's `consolePlugin` copy must match what 1.5 creates.
5. **Kueue 1.5.0 (Done 2026-11-05).** Set `zuno_kueue_channel: stable-v1.5`, then
   `make d1 install kueue`.

   **Catalog graph, read 2026-11-04:** `stable-v1.5` holds only 1.5.0, with
   no `replaces`, `skips` or `skipRange`. A channel switch therefore does not
   upgrade 1.4.3. Reaching 1.5.0 means removing the 1.4.3 Subscription and
   CSV (keeping the CRDs and the `Kueue` CR), then installing 1.5.0, or
   waiting for a 1.5.z that declares an edge from 1.4.

   **Decision 2026-11-04 (user):** K1 first, which means staying on 1.4.3
   and re-auditing for a 1.5.z that has an edge from 1.4. K2, a controlled
   reinstall, is prepared below and runs only after the user validates it.

   **Done 2026-11-05 (K2, user go, 9cd092da).** Kueue 1.5.0 is `Succeeded`.
   The operand `kueue-controller-manager` rolled to the 1.5.0 image (2/2).
   The 13 CRDs and 159 Workloads are kept, the ClusterQueue `default` is
   Active, and the DSC reports `KueueReady=True`. `zuno-kueue-d0`/`-d1` are
   Synced/Healthy. A suspended test Job in `zuno-ai-run` was admitted by
   ClusterQueue `default` and completed. The audit reports kueue `ok`.
   **Deviation from the plan below:** deleting the CSV alone is not enough.
   The Subscription's `status.installPlanRef` still pointed at the 1.4.3
   InstallPlan, so OLM logged "skipping update: installplan already created"
   and left the Subscription in `UpgradePending`. Deleting the Subscription
   as well let ArgoCD's selfHeal recreate it on `stable-v1.5` with a clean
   status, and OLM then installed 1.5.0 within about 20 seconds. The new
   operator then waited about 90 seconds for the old leader lease before it
   rolled the operand. Admission kept working the whole time, because the
   operand is owned by the `Kueue` CR.

   **K2 plan (as prepared on 2026-11-04).** What it relies on, measured live:
   - The operand `kueue-controller-manager` (2 replicas, which serve the
     `kueue-*-webhook-configuration` webhooks with `failurePolicy: Fail`) is
     owned by `Kueue.kueue.openshift.io/cluster`, not by the CSV, so it keeps
     admitting while the operator is swapped.
   - The DSC's `default-kueue` is `Unmanaged`.
   - There are 159 Workloads, one ClusterQueue, LocalQueues in `zuno-ai-run`
     and `zuno-ai-build`, and two ResourceFlavors.
   - The Subscription belongs to the ArgoCD Application `zuno-kueue-d0`
     (selfHeal, prune), so a Subscription deleted by hand would come back on
     `stable-v1.4`.

   Steps:
   1. Commit `zuno_kueue_channel: stable-v1.5` and run
      `make d1 install kueue`. The Subscription moves to `stable-v1.5`, and
      OLM keeps 1.4.3 because there is no edge.
   2. Delete CSV `kueue-operator.v1.4.3` in `openshift-kueue-operator`, then
      the Subscription `kueue-operator` (ArgoCD recreates it; see the
      deviation above). OLM keeps the CRDs and CRs, and the operand keeps
      running.
   3. OLM re-resolves the Subscription to the channel head, 1.5.0
      (Automatic). Wait for CSV `Succeeded`, then for the operand Deployment
      to roll and the webhooks to answer.
   4. Check: the ClusterQueue and LocalQueues are Active, a test Job in
      `zuno-ai-run` is admitted, the DSC is `KueueReady=True`, and ArgoCD
      `zuno-kueue-d0`/`-d1` are Synced.

   Never use `make d1 uninstall kueue` for this: it deletes the queues, the
   Application and the owned CRDs, which would take every Workload with them.
   If 1.5.0 fails to install, recreate the 1.4.3 CSV by setting the channel
   back to `stable-v1.4` with `startingCSV: kueue-operator.v1.4.3`.
6. **RHOAI 3.6.0-ea.2.** Set `zuno_openshift_ai_version: "3.6.0-ea.2"` (the
   channel resolves to `beta`), then `make d1 install openshift-ai`.

   **Stopped before any change (2026-11-05, after the user's go).** The
   `beta` channel holds a single entry, `rhods-operator.3.6.0-ea.2`, with no
   `replaces`, `skips` or `skipRange`. So no OLM upgrade path leads from
   3.5.2, and setting the pin would only move the Subscription to `beta` while
   OLM keeps 3.5.2. The bundle declares no other constraint. The only way in
   would be the K2-style reinstall: delete the rhods-operator CSV and
   Subscription and let OLM install 3.6.0-ea.2 over a live 3.5.2 DSC. That is
   an unsupported path for an EA build with no rollback, and every MaaS model
   and peer session depends on that DSC.

   **EA notes read (user choice, 2026-11-05).**
   - Red Hat's 3.6 release notes did not answer. The one GET to
     docs.redhat.com returned HTTP 503.
   - Upstream opendatahub-operator documents no EA upgrade path.
   - It does document one change that matters for 3.6: MaaS moved from
     `kserve.modelsAsService` to `aigateway.modelsAsAService` in 3.5
     (`docs/migration-guides/maas-to-aigateway-3.5.md`). The old field is
     honoured "at least through 3.6".
   - demo333's v2 DSC still sets `kserve.modelsAsService: Managed`, next to
     `aigateway: Managed`. Moving the chart to the new field is a 3.6 GA
     prerequisite. Note that CEL rejects re-enabling the old field once it
     is `Removed`.
   - Nothing on the cluster changed.

   **Decision 2026-11-05 (user): force the EA install.** A model and MaaS
   outage is accepted, provided the peer sessions are coordinated.
   Procedure:
   1. Commit `zuno_openshift_ai_version: "3.6.0-ea.2"` and run
      `make d1 install openshift-ai`. The d0 Application moves the
      Subscription to `beta` with `startingCSV: rhods-operator.3.6.0-ea.2`.
      The upgrade walk then fails after about 5 minutes, because no hop
      exists. This failure is expected.
   2. Back up the DSC, the DSCI, the CSV and the Subscription. Then delete
      CSV `rhods-operator.3.5.2` and Subscription `rhods-operator`. ArgoCD
      (`zuno-openshift-ai-d0`) recreates the Subscription on `beta` with a
      clean status, and OLM creates a Manual InstallPlan for 3.6.0-ea.2.
      Operands owned by the DSC keep running while no operator is present.
   3. Re-run `make d1 install openshift-ai`. With no installedCSV the walk is
      skipped and the exact-match approval takes the 3.6.0-ea.2 InstallPlan;
      d1 (DSCI, DSC) is then applied.
   4. Check the DSC conditions and any new operands, against the 3.5.0 GA
      traps: quotas, the mesh-egress union, immutable selectors and RBAC
      verbs. Then check MaaS end to end and run the quota probe.

   **Run 2026-11-05 (window 12:20-12:52 UTC): RHOAI 3.6.0-ea.2 `Succeeded`.**
   The procedure worked: install 1 failed in the walk as planned; deleting
   the CSV and the Subscription gave InstallPlan `install-z52dv`; install 2
   approved it; the operator came up in about 2 minutes. Install 2 then
   timed out waiting for the DSC Ready, because of the defects below, all
   fixed live:
   1. **SECURITY: the MaaS gateway was open without authentication for
      about 20 minutes (about 12:25-12:45 UTC).** 3.6 defaults
      `aigateway.modelsAsAService` to `Removed`, even with
      `kserve.modelsAsService: Managed`. It tore MaaS down: maas-api,
      maas-controller, `maas-gateway-auth` and the per-model
      TokenRateLimitPolicies were all deleted. Meanwhile
      `maas-default-gateway` kept routing, and `/v1/models` and
      `/v1/chat/completions` answered 200 without a token. The models
      stayed up the whole time. The gateway has no access log, so who used
      it cannot be known. Fix: `aigateway.modelsAsAService: Managed` on the
      live DSC, and in the chart. maas-controller recreated the AuthPolicy
      at 12:45:33; no-token requests answered 401 from 12:45:52. maas-api now runs in
      `redhat-ai-gateway-infra`, no longer in `redhat-ods-applications`, and
      requests answered 500 for about a minute while it started.
      `gateway-default-deny` is now `Enforced`, where it was False before.
   2. **TrustyAI schema mismatch (vendor defect).** The DSC types
      `trustyai.eval.lmeval.permit*` as the string enum `allow`/`deny`. The
      3.6.0-ea.2 TrustyAI module CRD types them as boolean, and the operator
      copies the string, so provisioning stopped with "expected boolean,
      got deny". Upstream main has a string on both sides. Fix:
      - remove `eval` from the live DSC and from the chart, so the module
        CRD defaults false/false apply, which equals deny/deny;
      - delete `default-trustyai`: the stored 3.5 object could no longer be
        patched.
   3. **Immutable selectors** (trap 5 of the 3.5.0 GA again):
      `spark-operator-controller`, `spark-operator-webhook` and
      `kuberay-operator`. Remedy: `oc delete deploy`; the operator
      recreates them.
   4. **ServiceMonitor `data-science-pipelines-operator-service-monitor`**
      was still controlled by the 3.5 `DataSciencePipelines` CR, which
      blocked the new AIPipelines module. Remedy: delete the ServiceMonitor;
      AIPipelines recreated it.
   5. **512Mi managers OOMKilled** (`odh-observability`,
      `opendatahub-feast-operator`, `spark-operator-module-controller-manager`).
      Raised to 1536Mi by hand. The operator keeps the change, but only
      live: on a fresh install the three are 512Mi again.
   6. The DSC and `default-ray` controllers stopped reconciling after the
      errors, with `observedGeneration` stuck at 1. An annotation woke them.

   **State after the run:**
   - The four LLMInferenceServices are Ready the whole time. MaaS answers
     200 on the four chat models and 401 without a token.
   - The DSC lists only `trustyai`: three LMEvalJobs from before ("operand
     status is not yet available") and `zuno-guardrails-smoke` in `Error`.
     `ogx` is degraded, which the role already treats as benign.

   **Open:**
   - **Quota counting at MaaS stopped: FIXED 2026-11-05 (0338f9ed).** See
     "Quota counters" below.
   - TrustyAI not Ready (above).
   - ArgoCD `zuno-namespaces-d0` is OutOfSync: `zuno-ai-build` lost
     `kueue.openshift.io/managed=true`.
   - ArgoCD `zuno-mlops-d1` is OutOfSync: TrainingRuntime `mlops-lora`.
   - The repo copies of maas-api settings (namespace `redhat-ods-applications`
     in the openshift-ai, postgresql, namespaces, service-mesh and models
     charts, and in the maas_db_copy role) are now stale. MaaS works because
     maas-api in its new namespace uses its own built-in config, but they
     must be audited.
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

## Quota counters after RHOAI 3.6.0-ea.2 (2026-11-05)

- **Cause:** the kuadrant-operator could not update the EnvoyFilter
  `openshift-ingress/kuadrant-maas-default-gateway`: `etcdserver: request is
  too large`. RHOAI 3.6 gave each local model route 11 rules / 15 matches, and
  Kuadrant expands a gateway-level policy into one wasm action set per match
  (68 sets; upstream Kuadrant/kuadrant-operator #2353 and #2051, both open).
  The EnvoyFilter stayed at its first version (generation 1, 795 KB of wasm
  config), which held only the AuthPolicy and `zuno-token-quota`. The six
  `maas-trlp-*` route policies and `gateway-default-deny` never reached the
  shim, although all reported `Enforced=True`. The probe said `moved []`.
- **Fix:** `zuno_connectivity_link_token_rate_limits.enabled: false` in
  demo333.yml, then `make d1 install connectivity-link`. The EnvoyFilter went
  to generation 2 (1.27 MB as an object) and now carries all six `maas-trlp-*`
  policies and `gateway-default-deny`. The probe gives
  `OK: moved ['subscription']` (+29); the four models answer 200 and no token
  gives 401.
- **What is lost:** `zuno-token-quota` was the MaaS-level user and group
  budget of ADR-0511 (standard-user 3M/24h, standard-group 30M/24h, ai-gateway
  headers only). While it is off, the user and group ceilings are enforced
  only by the ai-gateway ledger (WP-177, Redis-backed), and MaaS enforces
  only the per-subscription limits, which apply to the ai-gateway ServiceAccount
  as a whole. In practice nothing changes: WP-177 measured that these two
  limits never counted next to the controller's limits on the local routes.
  Turn it back on only when the EnvoyFilter still fits (watch its size and
  the operator log for `request is too large`).
- **Still unexplained:** the gateway still logs a few `Task failed: "0"` from
  the wasm shim, about one per chat, while chats succeed and counters move.

## TrustyAI after RHOAI 3.6.0-ea.2 (2026-11-05)

- **LMEvalJobs (T1), root cause: vendor defect.** The three 2026-09-07 jobs were failed (`ErrImagePull`). They were deleted
  and ArgoCD recreated them; all three then `Succeeded` (MMLU abstract_algebra: qwen3.5-9b 0.67, qwen3.6-27b 0.70, run
  against the model workload services, not through MaaS). TrustyAI still said "LMES ... operand status is not yet available",
  so the 3.6.0-ea.2 module cannot read an LMEvalJob status at all (the CRD has `state`, no `phase` or `conditions`).
  Fix (user choice): `lmEval.enabled: false` in `gitops/charts/models/values.yaml` (7cc43a39). ArgoCD pruned the jobs and the
  TrustyAI message dropped the LMES part, which confirms the diagnosis. Re-enable when a 3.6 release reads the status.
- **Permit flags (T3): not a regression.** The ConfigMap `trustyai-service-operator-config` shows `lmes-allow-online=true`
  and `lmes-allow-code-execution=true` (the shipped defaults), but the operator logs
  "Read PermitOnline from DSC config: false" and the same for code execution, so the DSC value applies. The API server
  admits an LMEvalJob with `allowOnline: true` (server dry-run); the controller is what enforces the deny.
- **Guardrails smoke (T2), open.** `GuardrailsOrchestrator zuno-guardrails-smoke` keeps `phase=Error` with
  `ReconcileFailed: Built-in route reconciliation failed`, a condition stamped 2026-10-12. Its Deployment, Service and
  Route are fine (route Admitted), and an annotation nudge produced no operator log and no status change, so the
  condition looks stale. It is the last thing holding TrustyAI at Ready=False. Planned remedy: delete the CR so
  `zuno-trustyai-config` recreates it with a fresh status (backup in the session scratchpad).


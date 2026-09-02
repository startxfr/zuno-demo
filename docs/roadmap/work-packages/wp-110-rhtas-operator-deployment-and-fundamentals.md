# WP-110: Deploy the RHTAS operator and fundamentals

- **State:** Done (2026-09-02) - live-verified end to end on demo222:
  operator v1.4.3 installed, Securesign CR `Ready` (Fulcio/Rekor/CTLog/
  Trillian-on-shared-MariaDB/TUF, TSA deliberately omitted), `zuno-signer`
  token live-tested, and a real keyless sign+verify smoke test passed with
  a Rekor transparency-log entry (logIndex 0, logID `876f72444af5fee8...`).
  Five live findings, all fixed in-repo the same day:
  1. rhtas-operator's CSV is **AllNamespaces-only** - subscribed into
     `openshift-operators` (mariadb/postgresql Pattern B), not the
     dedicated-namespace/OperatorGroup shape this brief anticipated;
     `zuno-rhtas` holds only the operand.
  2. With `trillian.database.create: false` the operator **never creates
     Trillian's schema** (only its embedded DB image does) - the role now
     vendors that image's own `storage.sql` and applies it idempotently
     before the operand syncs (`ansible/roles/rhtas/files/`).
  3. Failed createtree jobs leave Rekor/CTlog CRs in a **terminal state
     the operator never retries** - delete the child CRs, the Securesign
     parent recreates them.
  4. rhtas-operator **calls back INTO its operand** (GET rekor-server
     `/api/v1/log/publicKey` from `openshift-operators`) - zuno-rhtas's
     default-deny left `RekorAvailable` at "Creating" forever with every
     pod green; `openshift-operators` added to `allowedFromNamespaces`.
  5. Keycloak service-account tokens carry **no `aud` claim** by default -
     Fulcio rejects them (`expected audience "zuno-signer" got []`); fixed
     with an `oidc-audience-mapper` on the client (same class as WP-103's
     AAP finding). Also hit live: client `description` > varchar(255)
     kills the reconcile hook's create with an opaque `[unknown_error]`,
     and the ADR-0530 reconcile hook does NOT re-fire on automated/
     selfHeal syncs (same class as the open zuno-postgresql-d1 hook bug) -
     an explicit `spec.operation` sync is required after every
     realm-zuno.json client change.
- **ADRs:** ADR-0535 (Decision - partial scope: operator install and
  fundamentals only; the cutover itself is WP-111).
- **Depends on:** `mariadb` (Day 1 - Trillian's storage backend),
  `keycloak` (Day 1 - the new `zuno-signer` OIDC client, reconciled via
  ADR-0530's `zuno-keycloak-client-reconcile` Sync-hook Job).
- **Unblocks:** WP-111.
- **Related:** mirrors `ansible/roles/lightspeed`/`gitops/charts/lightspeed`
  (Red-Hat-product operator install pattern); ADR-0315 (shared-instance
  storage precedent) and ADR-0530 (Keycloak machine-identity client
  precedent) are the two decisions this WP implements without
  re-litigating. Supersedes half of WP-104 (Cancelled).
- **Target:** v0.9.

> Execute this brief as a standalone task from the repository root. Read
> ADR-0535 in full first, including its "Design decisions" subsection -
> this WP implements those three decisions, it does not re-derive them.

## Goal

Deploy the RHTAS/Securesign operator and its fundamentals - namespace,
Trillian storage backend, and the Keycloak OIDC signing identity - as a
new Day 1 component (`rhtas`), and prove the resulting Fulcio/Rekor/
Trillian chain actually works end to end with a throwaway test signature.
Do **not** touch the Vault-Transit-based signing of the platform's 14 real
first-party images, the verification tooling, or the Policy Controller -
all of that is WP-111, gated on this WP being live first.

## ADR references

ADR-0535, Decision section ("Scope (this ADR)": "Deploying the operator
and fundamentals is WP-110") and the "Design decisions" subsection, which
this WP implements verbatim:

1. Namespace = RHTAS's own upstream default/CSV-fixed namespace, owned by
   `gitops/charts/namespaces` (`zuno-namespaces-d0`), not by the `rhtas`
   chart.
2. Trillian storage = the shared `mariadb` Day 1 operand, dedicated
   `Database`/`User`/`Grant`, with the Istio MySQL-sniffing workaround
   applied from the start.
3. Signing identity = a new Keycloak client `zuno-signer`
   (`serviceAccountsEnabled: true`, no `realm-management` roles),
   reconciled via the existing ADR-0530 Sync-hook Job.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0 on the current tree.
- Confirm the RHTAS 1.4+ channel is actually published in this cluster's
  OperatorHub catalog, and check its CSV's `installModes` (OwnNamespace
  vs AllNamespaces) before assuming the target namespace - against
  `platform/docs/platform_profile.yaml`'s declared `openshift.target`
  (`4.22`) and `openshift_ai.release_train` (`3.5 EA2`).
- Read `ansible/roles/lightspeed/tasks/install.yml` and
  `gitops/charts/lightspeed` (`application-d0.yaml`, `application-d1.yaml`,
  `values.yaml`) in full - the operator-install pattern to mirror
  (PackageManifest-channel discovery with a clear diagnostic on mismatch;
  `application-d0.yaml` for the operator, `application-d1.yaml` for the
  operand; namespace owned by `gitops/charts/namespaces`, not the
  component's own chart).
- Read `gitops/charts/mariadb/templates/database-mlops.yaml`,
  `mariadb.yaml`, and `destinationrule-mariadb.yaml` in full, plus
  `gitops/charts/postgresql/templates/postgrescluster.yaml` (~lines
  58-74) - the exact `Database`/`User`/`Grant` shape and the Istio
  MySQL-sniffing workaround (`excludeInboundPorts`/`excludeOutboundPorts`
  annotations + a `DestinationRule` disabling client-side mTLS) to mirror
  for Trillian's MySQL listener.
- Read `gitops/charts/keycloak/files/realm-zuno.json` (the `zuno-admin-api`
  client block) and `job-client-reconcile.yaml` in full, plus ADR-0530 -
  the exact client shape and the reconcile-Job mechanics to mirror for
  `zuno-signer`.

## Repo changes (step by step)

1. New chart `gitops/charts/rhtas`:
   - `application-d0.yaml` - operator only (Subscription/OperatorGroup/CSV
     wait), sync-wave chosen after the most recently added Day 0
     operator's wave (confirm the current lowest/last wave live before
     picking a number - e.g. after lightspeed's `-126`).
   - `application-d1.yaml` - the `Securesign` CR (Fulcio + Rekor + CTLog +
     Trillian), Trillian pointed at the new MariaDB-backed database, Fulcio's
     OIDC issuer pointed at the `zuno-signer` Keycloak client.
   - `values.yaml` following the lightspeed pattern: `project.enabled:
     false` (namespace owned elsewhere), operator subscription
     fields left for runtime discovery per ADR-0048.
2. New role `ansible/roles/rhtas/tasks/{install,precheck,uninstall}.yml`,
   mirroring `ansible/roles/lightspeed`'s channel-discovery-with-diagnostic
   pattern.
3. Namespace declared in `gitops/charts/namespaces/values.yaml`, owned
   there (not by the `rhtas` chart) - same reasoning as
   `openshift-lightspeed`/`redhat-ods-operator`.
4. MariaDB: new `gitops/charts/mariadb/templates/database-rhtas-trillian.yaml`
   (`Database`/`User`/`Grant`, BYO password), Vault seed added to
   `ansible/roles/vault/tasks/install.yml`. Apply the mesh-sniffing
   workaround to whichever MySQL listener Trillian actually exposes -
   confirm the real port live; it may not be MariaDB's `3306`.
5. Keycloak: `zuno-signer` client block added to `realm-zuno.json`,
   exercised through the existing `zuno-keycloak-client-reconcile` Sync
   hook. Confirm live that this hook re-fires on every sync (it should,
   per ADR-0530) rather than assuming it without checking.
6. Makefile: `rhtas` added to `DAY1_RUN_COMPONENTS`.
7. Smoke test: from an in-cluster Job, `cosign sign --identity-token`
   (using a `zuno-signer` service-account token) against a throwaway test
   image, then `cosign verify` it against the live Fulcio certificate and
   confirm a real Rekor transparency-log entry exists. This is the only
   signing activity in this WP - the 14 production images stay on Vault
   Transit until WP-111.

## What NOT to touch

- `platform/supply-chain/sign_in_cluster.py`, `verify_signatures.py`, or
  any of the 14 first-party images' actual signatures.
- The Vault Transit key `zuno-platform-signer` or
  `ansible/roles/supply_chain_signer_build` - untouched, stays the live
  signing path for real images until WP-111 confirms the cutover.
- The Sigstore Policy Controller - not deployed in this WP.
- Any RHOAI/model-serving component - out of scope here (WP-111, Part A).

## Acceptance checks (repo-side)

- `python3 platform/docs/check_docs.py` exits 0.
- `oc get applications.argoproj.io zuno-rhtas-d0 zuno-rhtas-d1` both
  `Synced`/`Healthy`.
- `Securesign` CR reports `Ready`.
- Live keyless sign+verify of the smoke-test artifact succeeds, with a
  real Rekor UUID returned by `cosign verify`'s output - not just a green
  Ansible run (ADR-0420's own implementation notes record more than one
  case where a green playbook run did not mean a real signature existed).
- The dedicated MariaDB database is reachable from the RHTAS namespace
  with the mesh workaround confirmed live via a labeled/unlabeled pod-pair
  test (the method already used elsewhere in this repo for Istio
  sidecar-bootstrap verification).
- `service-account-zuno-signer` obtains a real token from the live
  Keycloak realm (`kcadm` or a direct client-credentials grant check).

## Operator / human follow-up

- Confirming RHTAS's actual CSV `installModes` and any cert-manager
  issuer wiring its defaults expect, once the operator is installed and
  its CRDs are inspected (`oc explain` before authoring any CR, per this
  repo's standing WP-execution convention).

## Out of scope / deferred

- Cutover of the 14 first-party images from Vault Transit.
- The Sigstore Policy Controller (any mode).
- RHOAI integration assessment (WP-111, Part A).
- Retiring Vault Transit or `zuno-platform-signer`.

## Status updates

- On repository merge, before live confirmation: State -> "Repo work
  merged, live verification pending".
- After all Acceptance checks are live-confirmed: State -> "Done".
- ADR-0535 stays "Proposed" until WP-111 is also `Done`.

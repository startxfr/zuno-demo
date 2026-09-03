# WP-132: Convert every remaining cluster-specific value into an Ansible parameter

- **State:** Not started
- **ADRs:** [ADR-0547](../../adr/0547-parameterize-every-cluster-specific-value-in-ansible.md)
  (the execution of that decision),
  [ADR-0517](../../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md)
  (B11, and clause 3's follow-up mechanism)
- **Depends on:** [WP-118](wp-118-demo333-portability-blockers.md) (Done — established
  the two-step delivery order and the three `resolve_cluster_*.yml` tasks this WP extends)
- **Related:** [WP-130](wp-130-fresh-cluster-readiness-gate.md) (probe P7 verifies this
  WP's result by construction), [WP-131](wp-131-per-cluster-s3-bucket-convention.md)
  (the S3 family, split out because it depends on ADR-0546),
  [ADR-0211](../../adr/0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md)
  (the ACME track whose staged rollout B11 short-circuits)

## Goal

WP-118 removed the `demo222` literals an audit could find. This WP applies ADR-0547's
rule to what an audit could not: values that are cluster-specific by *meaning* rather
than by spelling. Nothing here shows up in a `git grep` for `demo222`, and all of it
breaks or corrupts a fresh cluster.

## Steps

Each step follows ADR-0547 clause 4's two-step order without exception: inject the real
value at the Application level, prove the render is byte-identical **with the
Application's own toggle on**, apply live on `demo222`, confirm ArgoCD has synced a
revision containing the change, and only then flip the chart default to a placeholder.

Ordered least- to most-risky.

### Step 1 — `zuno_cluster_name`

A new `ansible/tasks/resolve_cluster_name.yml`, mirroring
`resolve_cluster_base_domain.yml`: derive the name from the base domain
(`apps.demo222.startx.fr` → `demo222`), idempotent behind an `is not defined` guard, with
a `zuno_cluster_name` override for a cluster whose domain does not encode its name.

Nothing consumes it on day one. It is first because WP-130's probe P6 and WP-131's whole
bucket convention are expressed in terms of it, and because a derived value with an
override is the cheapest possible thing to get wrong in isolation.

### Step 2 — the RHOAI version pin (B9's residual manual step)

`gitops/charts/openshift-ai/values.yaml`'s
`cluster-ods.operator.subscription.version`/`.channel` become parameters. The human
decision stays — ADR-0517 is explicit that auto-approving whatever a catalog publishes is
how a platform stops being reproducible, and the hard refusal in
`openshift_ai/tasks/install.yml:90` is kept exactly as it is. What changes is that
recording the decision stops requiring a chart edit, which today is a live change to
every cluster rendering from `main`.

Note that `openshift_ai/tasks/precheck.yml` reads the pin **from the chart** precisely
because a fresh cluster has no Subscription. That read must follow the value to its new
home rather than being left pointing at a stale default.

### Step 3 — the ACME issuer and consumer flips (B11)

`gitops/apps/cert-manager/application-d1.yaml` ships `certificatesIssuer:
letsencrypt-route53` and both `consumers.routerDefaultCert`/`apiServerNamedCert` as
`true`. Those are `demo222`'s end state. On a fresh cluster the first sync patches
`IngressController/default.spec.defaultCertificate` to `router-wildcard-tls` — a Secret
that cannot exist yet — and adds an APIServer named certificate for the same absent
Secret, breaking Console and route serving before any Certificate could be issued. The
chart's own comment at `acme-cluster-patches.yaml:1-22` says these flip only after
`oc get certificate -A` shows Ready.

Convert to `zuno_certmanager_issuer` and `zuno_certmanager_consumers_enabled`, defaulting
to the safe first-install values ADR-0211 prescribes (staging issuer, consumers off), with
`demo222`'s live values supplied from configuration. Nothing changes on `demo222` — the
injected values are exactly what renders today — which is the whole point of the two-step
order.

This is also the step that makes ADR-0211's staged rollout reproducible instead of
implicit: staging rehearsal, then production issuer, then consumers.

### Step 4 — the rest of the `machines` chart's cluster shape

WP-118 step 2 parameterized the AWS *identity* (cluster id, region, AMI, security group,
AZ→subnet map) and deliberately left `machineSet.list` as the authoring surface, since
`machines/tasks/install.yml` reads it from `values.yaml` on every run and replaces only
the identity fields. The availability zones and instance types in that list are still
cluster-specific: `values.yaml` records that g7e exists only in `eu-west-2a` and
`eu-west-2c`, which is a fact about one region.

Parameterize the AZ set and instance types while keeping the chart as the place where a
taint or a MIG profile is authored.

**This step can prune live GPU MachineSets** if the enable toggles are dropped from the
dict. WP-118's three guards stay: build from `application-d0.yaml`'s own values so the
toggles come along by construction; assert all three toggles are true and the list still
has as many entries as the chart declares; and fail pre-flight if a declared AZ has no
installer MachineSet to read a subnet from.

### Step 5 — Vault for anything secret

Any value introduced above that is secret gets its own Vault path and its own consumer
identity, seeded through `ansible/tasks/vault_seed_if_missing.yml`. ADR-0345 is what makes
re-running the seed safe: it writes only missing paths and does not rotate existing
secrets, correcting the belief — true when `mariadb/README.md` was written on 2026-08-12,
false the next day — that a `make d0 install vault` re-run rotates everything.

Most of what this WP touches is *not* secret. A hosted zone ID is a published DNS fact and
an operator channel name is public; those belong in `confidential.yml`, not Vault. Putting
non-secrets in Vault buys nothing and adds a failure mode.

## What NOT to touch

Unchanged from WP-118: the Makefile, the Go operator, the Go/Python components,
`realm-zuno.json`, the persona addresses `dev+zuno-*@startx.fr` and vendor links. Demo
data is not cluster identity.

## Verification (operator steps — ask before running)

Per step, before the commit that flips the default:

- `helm template` of the chart with the role-built values, diffed against the render with
  the manifest values alone: **empty diff**. Run it with the Application's own toggle
  enabled — WP-118 step 3's first inertia test passed while comparing two *empty* renders,
  because several charts render nothing until their toggle is set.
- After the live apply: the resources are unchanged **and** `git merge-base
  --is-ancestor` confirms the Application has synced a revision containing the flip. An
  unchanged resource proves nothing while the old chart is still what renders.
- `python3 platform/docs/check_docs.py` passes.

Step 3 additionally: both Let's Encrypt ClusterIssuers stay `Ready` through the apply, and
the three Certificates stay `Ready` with their real chains. Step 4 additionally: the three
MachineSets match their pre-apply baseline byte-for-byte.

## Risks and known unknowns

- Step 3 touches the router's default certificate and the API server's named
  certificates. A wrong value there is a control-plane-visible outage, not a degraded
  feature. It is sequenced third rather than first for that reason, behind two steps that
  build confidence in the injection mechanism.
- Step 4 can prune live GPU MachineSets.
- The AMI is region- and OCP-version-scoped. Reading it from a live MachineSet is correct
  for a cluster that already has one and says nothing about an AZ where no installer
  MachineSet exists; an operator override path is expected.
- Nothing here is exercised against a genuinely fresh cluster until `demo333` exists. A
  byte-identical render on `demo222` proves the conversion is inert, not that the
  parameter is right for a different cluster.

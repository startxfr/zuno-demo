# WP-132: Convert every remaining cluster-specific value into an Ansible parameter

- **State:** Repo work in review
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

### Step 0 — the unwired parameter surface (B13) — **DONE 2026-09-04**

Found while reading `cert_manager` for step 2, and it had to jump the queue: it
was a live `demo222` defect, not a `demo333` one.

WP-118 B6 moved the ACME DNS-01 identity (`zuno_certmanager_email`,
`zuno_certmanager_route53_region`, `zuno_certmanager_route53_hosted_zone_id`) into
`ansible/confidential.yml` and flipped the chart defaults to `mycluster-*`
placeholders — but `ansible/roles/cert_manager/tasks/install.yml` never loaded the
file. This repo has no `vars_files` and no global `include_vars`; each role that
reads an operator variable loads it itself (mariadb, models, smtp, keycloak,
postgresql, vault, aap all do). So the three variables were permanently undefined
and `| default(_cm_chart_acme[...])` resolved to the placeholders.

The next `make d0 install cert-manager` would have written
`MYCLUSTERHOSTEDZONEID` / `mycluster-route53-region` /
`acme-contact@mycluster.example.com` into the live `zuno-cert-manager-d1`
Application. DNS-01 would stop solving, and with B11's consumer flips on, a
failed renewal eventually takes the router certificate with it.

**Why B6's own inertia proof missed it.** The `changed=0` was measured while the
chart still carried the real values, so the apply was inert *for the wrong
reason* — `changed=0` is equally consistent with "the parameter works" and with
"the parameter is dead and the old value is still there". Step two then removed
the real values and left the fallback pointing at placeholders. An inertia proof
has to state why nothing changed, not only that nothing changed.

Fixed by adding the `stat` + `include_vars` pair, and by making the class
mechanically impossible to reintroduce: `check_confidential_var_loaders` in
`platform/docs/check_docs.py` fails any role that reads a variable documented in
`confidential.example.yml` (commented-out entries included — an optional variable
is exactly where the fallback hides the gap) without loading the file. Verified
both ways: the check fires on the pre-fix file and passes on the fixed one, and a
sweep of all 59 roles found cert_manager was the only offender.

Verified read-only first: with the loader in place the identity resolves to
`dev+zuno-acme@startx.fr` / `eu-west-3` / `Z3HY376RT1N9S1`, byte-identical to what
`zuno-cert-manager-d1` carries live.

**Live-verified 2026-09-04** with `make d0 install cert-manager` (operator
approved): `changed=0`, both `zuno-cert-manager-d0` and `-d1` Synced/Healthy, and
their `spec.source.helm.values` byte-identical to the captured baseline with no
`mycluster` string anywhere. The ACME track is untouched — all five ClusterIssuers
Ready, `router-wildcard-tls` and `api-server-tls` Ready with renewal at
2026-11-01, the IngressController still on `router-wildcard-tls`, the APIServer
still serving `api.demo222.startx.fr` from `api-server-tls`, and
`letsencrypt-route53` still pointed at the production Let's Encrypt directory with
zone `Z3HY376RT1N9S1` / region `eu-west-3`.

**And this `changed=0` means something, unlike B6's.** The chart defaults are
placeholders *now*, so an absent loader would have rewritten the Application and
reported a change. It reported none and the values are real — that is positive
evidence the parameter surface is live, not merely evidence that nothing moved.
The general rule: an inertia proof is only worth as much as the answer to "what
would this have looked like if the mechanism were dead?"


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

**Corrected 2026-09-04 after reading the code.** The channel is already a
parameter: `ansible/roles/openshift_ai/tasks/discover_channel.yml` reads it from
the live PackageManifest per ADR-0048 and injects it through
`gitops_app_extra_helm_values`, and the chart default `stable-3.5` is
deliberately a real channel because `helm template` and a plain ArgoCD sync must
still render. Only `subscription.version` (the `3.5.0` pin, now the GA rather
than the `3.5.0-ea.2` the ADR text still describes in places) is a chart literal.

So the scope is one value: `subscription.version` becomes a parameter defaulting
to the chart file itself, the shape WP-118 B6 used for the ACME identity — one
source of truth, and the apply stays inert until an operator sets it. **With step
0's lesson applied**: the role must actually load `confidential.yml`, and the
inertia proof must show the resolved value equals the live one, not merely that
the apply reported `changed=0`.

The human decision stays — ADR-0517 is explicit that auto-approving whatever a catalog publishes is
how a platform stops being reproducible, and the hard refusal in
`openshift_ai/tasks/install.yml:90` is kept exactly as it is. What changes is that
recording the decision stops requiring a chart edit, which today is a live change to
every cluster rendering from `main`.

Note that `openshift_ai/tasks/precheck.yml` reads the pin **from the chart** precisely
because a fresh cluster has no Subscription. That read must follow the value to its new
home rather than being left pointing at a stale default — otherwise a `demo333` operator
who sets the parameter correctly still gets a DRIFTED report, which is B9's own failure
mode reintroduced one level up.

**DONE 2026-09-04, live-verified.**

New `ansible/roles/openshift_ai/tasks/resolve_version_pin.yml`, shared by
`install.yml` and `precheck.yml` exactly as `discover_channel.yml` is shared by
`install.yml` and `reconcile.yml`. It loads `confidential.yml` (step 0's lesson,
now enforced by `check_confidential_var_loaders`), resolves
`zuno_openshift_ai_version` with the chart file as its default, and fails hard on
an empty pin — `startingCSV` is built as `<csv>.<version>`, so an empty value
produces a Subscription OLM cannot resolve and a diagnostic naming neither this
repo nor the variable.

Injected into **both** d0 applies in `install.yml`. `apply_gitops_app.yml`
replaces `spec.source.helm.values` wholesale, so a key present in only one of
them is dropped by the other — the grafana trap WP-118 step 1 hit.

`precheck.yml` now builds `_oai_pinned_csv` from the effective pin instead of
reading the chart directly. Leaving it on the chart would have told a `demo333`
operator who correctly set the variable that they were still DRIFTED — B9's own
failure mode reintroduced inside the check that exists to prevent it.

**Deliberate deviation from ADR-0547 clause 3:** the chart default stays a real
version rather than a fail-loud placeholder. The RHOAI version is a *platform*
decision, not cluster identity — every cluster should run the same build unless
its catalog cannot serve it — and the chart states an explicit constraint that a
plain `helm template` or an Ansible-less ArgoCD sync must still render, which a
placeholder version would break by building `rhods-operator.mycluster-version`.

Inertia proof, read-only, before any apply: the resolver returns `3.5.0`, which
equals the live Subscription's `startingCSV` (`rhods-operator.3.5.0`) and the
installed CSV. `helm template` of the chart with the injected key added to the
live Application's own values is **byte-identical** to the render without it, 4
documents, `startingCSV: "rhods-operator.3.5.0"` either way. And per step 0's
rule — what would this look like if the mechanism were dead? — injecting `9.9.9`
renders `rhods-operator.9.9.9`, so the key really drives `startingCSV` rather
than being inert decoration. `make d1 check openshift-ai` run locally exercises
the new task and still reports ALIGNED with no finding.

**Live-verified 2026-09-04** with `make d1 install openshift-ai` (operator
approved, run through AAP so it exercised the pushed code): `changed=1`, and the
diff of `zuno-openshift-ai-d0`'s values against the pre-apply baseline is
**exactly one added line**, `version: 3.5.0`. `zuno-openshift-ai-d1`'s values are
byte-identical. The Subscription still reads `startingCSV=rhods-operator.3.5.0`,
`channel=stable-3.5`, `installPlanApproval=Manual`, `currentCSV=rhods-operator.3.5.0`;
the CSV is still `Succeeded`; no new InstallPlan was created; `default-dsci` and
`zuno-dsc` are both still `Ready`; both Applications Synced/Healthy.

Predicted delta, observed delta, nothing else — which is the standard step 0
set. `changed=1` was expected here (the Application genuinely gains a key), so
the count carries no information; the evidence is that the *content* of the
change is the single line the design calls for, and that everything downstream of
`startingCSV` is untouched.

#### A wrong-day defect found alongside it

`openshift-ai` is a Day 1 component, and both this WP's first draft and
ADR-0517/WP-118's own B9 prose said `make d0 check openshift-ai`, which the Day 0
dispatcher rejects outright. `discover_channel.yml`'s `fail` message said it too.
This is exactly ADR-0344's defect class — `make d0 reconcile openshift-ai` was
published as the authoritative remedy by nine findings and had never once worked.

`check_debug_make_commands` already validated `debug` messages; it now validates
`fail` messages too, which is the louder surface — the last thing printed before
a run stops is the message an operator is most likely to type verbatim. That
found five further live instances, all fixed here: four `make d0 install
openshift-oauth` (Day 1), one `make d0 check service-mesh` (Day 1), and one
`make d0 configure keycloak` (no such verb; the secrets come from `make d0
install keycloak`). This matters more on a fresh cluster than a running one,
where these messages fire constantly and every wrong instruction costs a cycle.

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

# ADR-0547: Parameterize every cluster-specific value in Ansible, and seed it through Vault when secret

- **Status:** Proposed
- **Target:** v0.8
- **Date:** 2026-09-03
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0517 set out to prove the Day 0–3 automation bootstraps a brand-new
cluster. Its bounded remediation, WP-118, closed nine blockers by finding and
removing `demo222` literals from chart defaults — an audit, then a
find-and-route-back-onto-the-token pass, then a live inertia proof per flip.

That worked, and it does not generalize. Audit pass 2 (recorded in ADR-0517)
re-ran the same search and found no further literals, yet the same pass turned
up three more blockers of the same *consequence* and none of the same *shape*:

- **B10** — four RHOAI dashboard feature flags set by hand on the live cluster,
  with no applier anywhere. A cluster-only mutation leaves nothing in the
  repository to grep for, so no audit of the tree could ever have found it.
- **B11** — `gitops/apps/cert-manager/application-d1.yaml` ships `demo222`'s
  *end state*: ACME enabled against the production issuer with both consumer
  flips `true`. Every value is correct for `demo222` and destructive on a fresh
  cluster, where it points the router at a Secret that cannot exist yet. There
  is no literal to find; the defect is that a per-cluster *state* is a chart
  default.
- **B12** — seven S3 buckets, none namespaced by cluster. A second cluster
  installed today writes its RAG corpus, backups, traces and MLflow artifacts
  into the first cluster's buckets. This one is architectural, and it is the
  only blocker that damages the *existing* cluster rather than the new one.

Three defects, three shapes, one cause: the repository has no rule about where
a cluster-specific value is allowed to live. WP-118 removed the instances it
could see. Nothing stops the next one, and two of the three above were
introduced *after* the audit that was supposed to bound the problem.

The mechanisms to do better already exist and are proven — the
`apps.mycluster.example.com` token substituted by
`ansible/tasks/apply_gitops_app.yml`, the three
`ansible/tasks/resolve_cluster_*.yml` discovery tasks, `ansible/confidential.yml`
for the undiscoverable, and Vault plus External Secrets for the secret. What is
missing is the statement that they are mandatory.

## Decision

1. **No chart default carries a cluster-specific value.** Any value that
   differs between two clusters of this platform — base domain, AWS
   infrastructure identity, StorageClass, Route53 zone/region/ACME contact, S3
   bucket names and regions, the cluster's own name, availability zones and
   instance types, the RHOAI version pin, and the ACME issuer and consumer
   flips — is an **Ansible parameter**, injected into the ArgoCD Application at
   apply time. `gitops/charts/*/values.yaml` and `gitops/apps/*/application-*.yaml`
   describe the platform, not the cluster it happens to run on.

2. **Three surfaces, one rule for choosing between them.**
   - *Discoverable from the cluster API* → a `ansible/tasks/resolve_cluster_*.yml`
     task, following `resolve_cluster_base_domain.yml`'s shape: idempotent
     behind an `is not defined` guard, an explicit override variable, and a
     hard failure rather than a guess when the answer is ambiguous. Discovery
     beats declaration because it cannot drift.
   - *Not discoverable, not secret* → `ansible/confidential.yml`, documented as
     an optional block in `confidential.example.yml` with its consequence when
     unset spelled out. B8 is the precedent for why the consequence matters: the
     five MariaDB backup variables were merely undocumented, and the effect was
     that no MariaDB backup schedule existed at all.
   - *Secret* → **Vault**, seeded by the `vault` role through
     `ansible/tasks/vault_seed_if_missing.yml` (ADR-0345, which is what makes a
     re-seed safe), consumed through an ExternalSecret, with **one Vault path
     and one identity per consumer**. WP-079 already paid for the alternative:
     the `zuno-sxa-corpus-s3` IAM user was reused for AAP Hub and RHOAI traces
     without the right `s3:ListBucket` grant.

3. **The chart default becomes a placeholder that fails loudly.** Not a
   plausible value — an invalid one. WP-118 B5 set the precedent deliberately:
   `mycluster-default-storageclass` cannot bind, so an Application that lost its
   injected value produces an unschedulable PVC instead of silently binding to
   the wrong storage. `storageClassName` is immutable once bound, and a
   plausible placeholder would have been unrecoverable. The same reasoning
   governs every placeholder introduced under this ADR: prefer a value that
   cannot work over one that might.

4. **Delivery order is not optional.** Every `gitops/apps/*/application-*.yaml`
   points at `targetRevision: main` with `selfHeal: true`, so ArgoCD renders
   each chart from git `main`, never from an operator's working copy — which
   makes changing a chart default a **live change to every cluster already
   running**. Each value moves in two steps: first pin the real value at the
   Application level and prove the render is byte-identical, then flip the chart
   default to the placeholder. The reverse order rewrites live Route hosts,
   which are effectively immutable.

   Two traps this ADR inherits from WP-118 and restates because both cost a
   rewrite. An inertia diff between two *empty* renders passes while testing
   nothing — several charts render no PVC until their Application's own toggle
   is set, so the comparison must be made with the toggle on. And "the resource
   is unchanged" proves nothing until ArgoCD has actually synced a revision
   containing the flip; verify with `git merge-base --is-ancestor` against the
   Application's synced revision, not by looking at the resource.

5. **Demo content is not cluster identity and does not move.** The persona
   addresses `dev+zuno-*@startx.fr`, vendor links and demo data stay exactly
   where they are, per WP-118's "What NOT to touch".

6. **Conformance is verified by a probe, not by review.** A cluster-cleanliness
   audit is a snapshot that decays; B11 and B12 both entered the tree after the
   audit that was meant to bound them. The `check_cluster_readiness` probe
   introduced by WP-130 asserts the rule at `make d0 check` time — including
   that no chart default still carries a `mycluster-*` placeholder that no
   parameter replaces — and blocks `make d0 install` on the subset that would
   fail or destroy something. Read-only and never-failing on the check path,
   per the precheck contract.

## Acceptance criteria

- Every value listed in Decision clause 1 is supplied by an Ansible parameter,
  and no `gitops/charts/*/values.yaml` or `gitops/apps/*/application-*.yaml`
  default names a specific cluster.
- Each conversion is landed in the two-step order of clause 4, with its inertia
  proof recorded — render byte-identical with the Application's toggle on, and
  the Application confirmed synced to a revision containing the flip.
- Every secret introduced by a conversion has its own Vault path and its own
  consumer identity; none is shared across consumers.
- `make d0 check` reports zero readiness findings on `demo222`, and a fresh
  cluster missing any parameter is told which one before Day 0 begins rather
  than by a mid-install failure.

## Implementation notes

*(empty — WP-132 carries the conversions, WP-130 the probe, WP-131 the S3
family; entries are added as each lands.)*

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Consequences, Security/Operational considerations, Migration/evolution and
Review evidence.

## Related ADRs

- [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md)
- [ADR-0345](0345-make-self-generated-vault-credentials-idempotent.md)
- [ADR-0517](0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md)
- [ADR-0546](0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md)

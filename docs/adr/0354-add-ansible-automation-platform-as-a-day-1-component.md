# ADR-0354: Add Ansible Automation Platform as a new Day 1 component

- **Status:** Proposed
- **Target:** v0.2
- **Date:** 2026-08-20
- **Amended:** 2026-08-24 (Day 0 → Day 1 placement, scope split into `aap`/
  `aap-config`, non-HA sizing, retargeted v0.3 → v0.2)
- **Decision owners:** Zuno Demo architecture team

## Context

Every Day 0/Day 1 install today runs from an operator's or CI runner's own
shell (`make day0|d0`/`day1|d1 <verb> [component]` → `ansible-playbook ...
ansible/playbooks/day{0,1}_$verb.yml`, ADR-0056). There is no central
execution history for these runs beyond git history and ArgoCD sync
history - who ran `make d1 install`, when, against which component, with
what result, lives only in that operator's terminal scrollback.

Ansible Automation Platform (AAP) already appears in this repository, but
only once, and not as infrastructure: `gitops/charts/rag-ingestion/
README.md` and ADR-0330 list it as one of 17 Red Hat products whose public
documentation the RAG demo corpus ingests. AAP has never been deployed here
and has no prior ADR.

The repository's operator-component pattern is uniform and well-established
(ADR-0056, ADR-0060, ADR-0310, ADR-0312, ADR-0314): one Ansible role
(`ansible/roles/<c>/tasks/{install,precheck,uninstall}.yml`), one Helm chart
(`gitops/charts/<c>`) whose `operator.enabled`/`<operand>.enabled` values
both default `false`, and two ArgoCD `Application` objects
(`gitops/apps/<c>/application-d0.yaml` for the OLM `Subscription`/
`OperatorGroup`, `application-d1.yaml` for the operand CR), applied by
Ansible (`ansible/tasks/apply_gitops_app.yml`) with `-d0` waited
Synced+Healthy before `-d1`. Every operator-backed component (`keycloak`,
`external-secrets`, `postgresql`, `mariadb`, `nfd`, `nvidia-gpu`,
`openshift-ai`, `cert-manager`, `connectivity-link`, `lws`,
`custom-metrics-autoscaler`, `jobset`, `kueue`, `kiali`, `mesh-monitoring`,
`observability`, `tempo`) vendors the generic startx `operator` (or
`cluster-xxx`) chart as a Helm dependency instead of hand-authoring the
`Subscription`/`OperatorGroup` manifests. This is the shape a new AAP
component should reuse rather than invent something new. Note that the
`-d0`/`-d1` Application naming is a per-component "operator vs. instance"
convention, independent of which day (0, 1, 2, 3) the owning role actually
runs under - ADR-0060 established this distinction when it moved
`keycloak`/`postgresql`/`mariadb`/`tempo`/`kueue`/`openshift-ai` from Day 0
into Day 1 while every component kept its own internal `-d0`/`-d1` Application
pair unchanged.

**This ADR was originally written assuming a Day 0 placement, sequenced
`postgresql → mariadb → tempo → keycloak → aap → machines`.** That sequence
no longer exists: ADR-0060 (2026-08-22, implemented after this ADR was
first drafted) moved `postgresql`, `mariadb`, `tempo` and `keycloak` out of
Day 0 into Day 1, and commit `f021c16` (2026-08-24) moved `openshift_oauth`
alongside `keycloak` into Day 1 for the identical reason this ADR already
argues for `aap`'s dependents: it needs Keycloak's Ingress/TLS Secret,
which Day 0 can never provide. `aap` needs the same three prerequisites
(PostgreSQL, Vault/External Secrets, Keycloak) `openshift_oauth` needs, so
it belongs in the same tier, for the same reason. This amendment corrects
the placement to Day 1 (clause 2) without changing anything else about the
Decision's technical shape.

One technical fact shapes this ADR's scope directly: the AAP Operator's own
CRDs cover only platform infrastructure - the unified `AnsibleAutomationPlatform`
custom resource (`aap.ansible.com/v1alpha1`, AAP 2.5+) provisions Gateway,
Controller, Hub and EDA together as Kubernetes-managed workloads. It does
**not** publish Kubernetes CRDs for objects that live inside Controller's own
database - Projects, Job Templates, Inventories, Credentials. Those are
Controller API objects, configured the same way this repository already
configures `infra.aap_configuration`-collection-style state: declaratively,
idempotently, from Ansible - not as raw `kind:` manifests, unless the
separate AAP *resource operator* (a distinct OLM package from the platform
operator this ADR installs) is also present and does publish CRDs for them.
Which of those two shapes actually applies is not yet known from outside a
live cluster and is resolved by clause 4 below, not assumed here.

## Decision

1. **`aap` becomes a new Day 1 component**, following the identical
   role + `-d0`/`-d1` ArgoCD `Application` pair + `gitops/charts/aap` chart
   shape every operator-backed component already uses. No new deployment
   mechanism is introduced for this repository.

2. **Placement: immediately after `openshift_oauth`, before
   `connectivity_link`.** `aap` is added to `day1_components` in
   `ansible/playbooks/day1_install.yml` and `day1_check.yml` (and to the
   reverse-order list in `day1_uninstall.yml`, where it is removed *before*
   `openshift_oauth`), and to `DAY1_RUN_COMPONENTS` in the root `Makefile`,
   at this exact position in the existing sequence:

   ```
   ... → keycloak → openshift_oauth → aap → connectivity_link → lws → ...
   ```

   By this point in the sequence, PostgreSQL (AAP Controller needs its own
   database, the same way Keycloak has a dedicated database per ADR-0315),
   Vault + External Secrets (AAP's own credentials, both Day 0), and
   Keycloak + `openshift_oauth` (AAP's SSO identity source, clause 6, and
   the cluster-wide CA trust `aap` reuses per ADR-0411) are already
   Synced+Healthy. `postgresql` stays a Day 1 component - it is not moved
   to Day 0 by this ADR, and no existing component's position changes.

   The Day 1 namespace `zuno-aap` that `aap`'s OperatorGroup/Subscription
   target must already exist by the time `aap` runs. It is declared as a
   new `platformNamespaces` entry in `gitops/charts/namespaces/values.yaml`
   (the same mechanism `zuno-auth`, `zuno-vault` and `zuno-data` already
   use - see clause 3), so it is created by the **Day 0** `namespaces`
   component, unchanged in position. This is the one place this ADR touches
   a Day 0 component, and it is additive (one more namespace entry), not a
   reordering.

3. **Full-platform scope, non-HA sizing, dedicated namespace with default-deny
   baseline.** `aap`'s `-d1` Application renders a single
   `AnsibleAutomationPlatform` custom resource, gated by `aap.enabled`,
   provisioning Gateway, Controller, Hub and EDA together - not Controller
   alone - each sized for a demo-scale, non-HA deployment (single replica
   per component, trimmed resource requests/limits; the exact CR knobs are
   confirmed against the live CRD schema when the operator is first
   installed, since the 2.5 CRD's replica/sizing fields are not otherwise
   documented in this repository). This follows the same
   one-operand-CR-per-chart shape as `Keycloak`/`PostgresCluster`/
   `DataScienceCluster`. `aap`'s `-d0` Application renders the operator
   `Subscription`/`OperatorGroup` via the vendored startx `operator` chart
   dependency (the same `Chart.yaml` pattern as `gitops/charts/keycloak`),
   with channel and catalog source left empty in checked-in values and
   discovered at deploy time by `ansible/roles/aap/tasks/install.yml`
   exactly as `keycloak`/`openshift_ai` already do (`PackageManifest`
   lookup, ADR-0048) - never hardcoded to a specific channel name.

   `aap` runs in its own namespace, `zuno-aap`, following the same
   platform-namespace pattern `zuno-auth` (Keycloak) already uses rather
   than the shared `openshift-operators` some Day 1 operators use: declared
   in `gitops/charts/namespaces/values.yaml`'s `platformNamespaces` list
   with an OwnNamespace `OperatorGroup`, `zuno.io/managed: "true"` (ADR-0320
   labeling convention), and deliberately **without** `istio-injection:
   enabled` - AAP's own workloads stay outside the mesh, consistent with
   how other heavy operator-backed components are handled. The chart's
   baseline `zuno-default-deny-other-namespaces` `NetworkPolicy` (same
   template every `platformNamespaces` entry gets) applies unchanged:
   same-namespace and router-ingress traffic only, `allowedFromNamespaces:
   []` for v0.2. Two cross-namespace ingress allowances are added to
   *other* namespaces' entries in the same file so `aap`'s own egress is
   admitted at its targets: `zuno-data` (AAP Controller reaching its
   dedicated PostgreSQL database, clause 5) and `zuno-auth` (any in-cluster
   JWKS/token-endpoint calls to Keycloak, clause 6) each gain `zuno-aap` in
   their `allowedFromNamespaces`. `zuno-aap` is not itself allow-listed
   into `zuno-mesh` (no sidecar injection, so this does not apply). v0.3's
   `mcp-aap` server (ADR-0355) is expected to add `zuno-ai-run` to `aap`'s
   own `allowedFromNamespaces` when it starts calling the Controller API
   in-cluster; that edit is deferred to ADR-0355, not made here.

4. **Repository loading and one Job Template, via a new `aap-config`
   component - mechanism decided from the live CRD inventory, not
   assumed.** A second Day 1 component, `aap-config`, placed immediately
   after `aap` (day0-neutral: it has no Day 0 half of its own), registers
   exactly two things once the `AnsibleAutomationPlatform` CR reports
   Ready:
   - one **Project** pointing at this repository
     (`https://github.com/startxfr/zuno-demo.git`, `main` - the same
     `repoURL`/`targetRevision` every ArgoCD `Application` in this repo
     already uses), with SCM auto-sync so a re-run picks up new playbooks
     without manual re-registration;
   - one **Job Template**, `zuno-day0-check`, running
     `ansible/playbooks/day0_check.yml` (chosen because it is read-mostly
     and never fails destructively - the same property that makes it
     `day0 reconcile`'s closest sibling in ADR-0418's risk-phased rollout).

   Unlike the original (pre-amendment) version of this ADR, this is
   **not** assumed to require hand-written Ansible against the
   `infra.aap_configuration` collection. The first implementation work
   package (WP-072) installs the operator and then inventories what it
   actually ships (`oc api-resources | grep -Ei 'ansible|aap|awx'`, `oc
   explain` on any `AnsibleJob`/`JobTemplate`/`AnsibleProject`-shaped
   types found) before `aap-config`'s own work package (WP-073) picks a
   mechanism:
   - **Path A (preferred if available):** the AAP *resource operator* (a
     separate OLM package from the platform operator this ADR installs)
     ships Kubernetes CRDs for `Project`/`JobTemplate`-shaped objects, and
     `aap-config` is a normal `gitops/charts/aap-config` chart rendering
     those CRs - no new deployment mechanism, identical to every other
     component in this repository.
   - **Path B (fallback):** no such CRDs exist, and `aap-config` is an
     Ansible role using the `infra.aap_configuration` collection (added to
     `ansible/requirements.yml`) with the same assert-or-seed idempotency
     shape `ansible/tasks/vault_seed_if_missing.yml` already uses -
     checking whether the Project/Job Template already exists before
     writing it, so a re-run never clobbers or duplicates state.

   Whichever path applies, `aap-config` runs on every Day 1 install/
   reconcile of the component - a no-op when nothing has changed, the same
   idempotency guarantee every other component's `install.yml` already
   provides. **Scope boundary, unchanged from the original ADR:** creating
   this one Project and one Job Template is the entire scope of this
   ADR - the seven other top-level playbooks the original (pre-amendment)
   clause 4 named as Job Templates are cut from scope; adding them back, if
   ever wanted, is a future ADR's decision, not this one's. Actually
   routing `make day0|d0`/`make day1|d1` execution through any Job
   Template - so that a launch, not a local shell invocation, becomes how
   these verbs run - stays explicitly deferred to the companion ADR-0418
   (v0.4). This ADR changes nothing about how operators run Day 0/Day 1
   today.

5. **Credentials flow through Vault, unchanged from every other
   component.** Controller's own admin credentials, its dedicated
   PostgreSQL role, and the Machine credential `aap-config` uses to reach
   this cluster are generated/seeded into Vault KV and delivered via
   ExternalSecrets, the same pattern every other component's secrets
   already follow (ADR-0024):
   - `zuno/aap/admin` - Controller/Gateway admin password, seeded the same
     way `keycloak/admin` already is (`_vault_generated_secrets` in
     `ansible/roles/vault/tasks/install.yml`).
   - `zuno/aap/postgresql-app` - the dedicated PostgreSQL role/password on
     the shared Crunchy cluster, following the exact ADR-0315 pattern
     already used for `keycloak/postgresql-app`: a new `aapDatabase` entry
     in `gitops/charts/postgresql/templates/postgrescluster.yaml`'s
     `spec.users[]` plus a matching block in `values.yaml`, and a
     consumer-side `ExternalSecret` in `gitops/charts/aap`. Whether AAP
     2.5's unified CR needs one shared database credential or one per
     sub-component (Gateway/Controller/Hub/EDA each commonly want their
     own database) is confirmed against the live CR schema alongside
     clause 3's sizing knobs, not assumed here; if more than one is
     needed, this same ADR-0315 pattern is repeated per sub-component
     rather than switching mechanisms.
   - `zuno/keycloak/aap-client` - the Keycloak OIDC client secret (clause
     6), seeded and consumed exactly like every other frontend's client
     secret already is.

   Nothing is hand-entered into the Controller UI or committed to git.

6. **Identity: Keycloak stays the one identity provider, registered the
   same declarative way every other client is.** An `aap` client is added
   to `gitops/charts/keycloak/files/realm-zuno.json`'s `clients[]` array
   with `"secret": "${vault.aap_client_secret}"` (the file-vault SPI
   pattern every existing client secret already uses - never a literal),
   a matching `ExternalSecret` (`gitops/charts/keycloak/templates/
   externalsecret-aap-client.yaml`) and a projected-volume entry in
   `gitops/charts/keycloak/templates/keycloak.yaml` mapping to file
   `zuno_aap__client__secret` (the vault-key underscore-escaping rule every
   existing client already follows). This Keycloak-side registration is
   fully declarative and has no open questions.

   The **AAP-side** half - configuring the 2.5 platform gateway's OIDC
   authenticator to point at that Keycloak client - is a separate, open
   question this ADR does not resolve: AAP 2.5 configures authentication
   through the Gateway's own API/UI, not through the
   `AnsibleAutomationPlatform` CR, so whether it can be driven
   declaratively (an authenticator CRD from the resource operator?
   `infra.aap_configuration`? one-time interactive setup with the seeded
   `zuno/aap/admin` credential as a documented gap?) is resolved by the
   same clause-4 CRD inventory and recorded in WP-073. Until resolved,
   Controller/Gateway is reachable with the Vault-seeded admin password.
   AAP does not stand up a separate local-user store as its long-term
   authentication source regardless of which mechanism wires the
   federation. If the Keycloak route's certificate is signed by the
   platform's Vault PKI root (rather than a publicly trusted one), `aap`'s
   namespace trusts it via `ansible/tasks/sync_keycloak_serving_ca.yml`
   (ADR-0411), the same mechanism `agents`' role already uses.

7. **Internal-only for v0.2.** This ADR does not classify `aap` under
   ADR-0352's Tier A/B/C internal/external-mode framework - ADR-0352 is
   itself still `Proposed`, not implemented. AAP is always self-installed
   by this repository for v0.2. Supporting a pre-existing,
   customer-managed AAP instance (external mode) is explicitly deferred to
   a future ADR once ADR-0352 itself lands.

8. **Naming.** The two components are named `aap` and `aap-config`
   consistently: `gitops/charts/aap`, `gitops/apps/aap/`,
   `ansible/roles/aap/`; `gitops/charts/aap-config` (if Path A applies),
   `gitops/apps/aap-config/`, `ansible/roles/aap_config/`; the `Makefile`'s
   `DAY1_RUN_COMPONENTS` entries `aap`/`aap-config`, and the matching
   `day1_components` entries. No abbreviation collision exists elsewhere in
   the current component list.

## Consequences

- Day 1 grows from 17 to 19 run components (`aap`, `aap-config`), plus one
  more PostgreSQL database/role (or several, per clause 5's open question),
  one more Vault KV path set, one more ExternalSecret set, and one more
  Keycloak OIDC client to operate and back up alongside the ones already
  tracked for `keycloak`/`postgresql`. Day 0 grows by exactly one namespace
  entry (`zuno-aap`) inside the existing `namespaces` component - no new
  Day 0 component.
- Total Day 1 install wall-clock time grows - Gateway+Controller+Hub+EDA
  starting together, even non-HA, is likely among the heaviest pod-starts
  in the whole sequence, on the order of what `openshift_ai`'s
  `DataScienceCluster` already costs.
- The repository's `day0_check` playbook becomes visible, and executable,
  as a single AAP Job Template - a narrow foundation ADR-0418 can build on
  to route more (and eventually all) verb execution through AAP, once this
  first template proves the pattern. This ADR alone changes nothing about
  how `make d0`/`make d1` behave today.
- AAP is a genuinely heavy new product surface for a demo-scale platform;
  operators should expect it to be among the largest single additions to
  cluster resource consumption since OpenShift AI itself, even trimmed to
  non-HA sizing.

## Security considerations

Controller becomes a new privileged actor capable of running arbitrary
Ansible against this cluster once its one Job Template is launched (not
yet possible until ADR-0418 wires up execution, but the capability exists
as soon as Controller and its Machine credential exist). That Machine
credential must be scoped no more broadly than the existing Ansible
bootstrap's own cluster-admin kubeconfig already requires - not a new,
separately-privileged identity. Controller's own launch-RBAC (who may run
the `zuno-day0-check` Job Template) is a new authorization surface this
ADR does not model; it is deferred to ADR-0418, which must define it
before the Job Template becomes reachable outside an interactive admin
login. Installing EDA as part of "full platform" is flagged explicitly as
the reason this choice widens blast radius slightly versus a
Controller-only install: EDA can react to external webhooks/events and
trigger automation without any interactive login at all, so its event
sources must be enumerated and access-controlled once anything beyond
installation depends on it. `zuno-aap`'s default-deny `NetworkPolicy`
baseline (clause 3) is the first layer of that containment - no namespace
other than the router and, for now, nothing else, can reach AAP's
workloads at all.

## Operational considerations

AAP's own backup/DR posture (Controller's database, Hub's content) becomes
a new operational surface alongside the Vault and PostgreSQL backups
already tracked by this repository. `make d1 check aap` must assert that
the `AnsibleAutomationPlatform` CR and its Gateway/Controller/Hub/EDA
sub-resources are Ready; `make d1 check aap-config` must assert the
Project's last SCM sync succeeded and the Job Template exists, mirroring
how `keycloak`'s check already asserts `KeycloakRealmImport/zuno-realm`
reached `Done`. No `day1_reconcile.yml` playbook exists in this repository
(only `day0_reconcile.yml` does) - both `aap` and `aap-config` roles must
therefore be safely idempotent under a plain repeated `install`.

## Acceptance criteria

- The implementation is merged through the normal repository review
  process.
- Relevant documentation and `MEMORY.md` are updated to describe the
  implemented state rather than the target state.
- `python3 platform/docs/check_docs.py` and component-specific `make d1
  check aap`/`make d1 check aap-config` demonstrate the behavior described
  in this ADR.
- Security-negative tests are included for the Controller RBAC/Machine
  credential scope introduced by clauses 5 and the Security considerations
  above.

## Implementation state

**To be implemented.** This ADR records an agreed architectural decision.
No chart, role, playbook or Makefile change is claimed by this ADR itself -
implementation lands via WP-072 (`aap`) and WP-073 (`aap-config`) under
`docs/roadmap/work-packages/`.

## Related ADRs

- [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md)
- [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0060](0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md)
- [ADR-0310](0310-manage-static-kubernetes-resources-as-per-role-kustomize-directories.md)
- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md)
- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md)
- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md)
- [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md)
- [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md)
- [ADR-0355](0355-expose-aap-audits-to-agents-through-an-mcp-aap-server.md) (companion, v0.3)
- [ADR-0411](0411-trust-the-vault-pki-root-for-the-tekos-frontend-oidc-client.md)
- [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md) (companion, v0.4)

See [Standard clauses](README.md#standard-clauses) for Alternatives and
Review evidence.

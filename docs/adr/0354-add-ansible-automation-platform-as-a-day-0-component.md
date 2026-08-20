# ADR-0354: Add Ansible Automation Platform as a new Day 0 component

- **Status:** Proposed
- **Target:** v0.3
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team

## Context

Every Day 0 install today runs from an operator's or CI runner's own shell
(`make day0|d0 <verb> [component]` → `ansible-playbook ... ansible/playbooks/
day0_$verb.yml`, ADR-0056). There is no central execution history for these
runs beyond git history and ArgoCD sync history - who ran `make d0 install`,
when, against which component, with what result, lives only in that
operator's terminal scrollback.

Ansible Automation Platform (AAP) already appears in this repository, but
only once, and not as infrastructure: `gitops/charts/rag-ingestion/
README.md` and ADR-0330 list it as one of 17 Red Hat products whose public
documentation the RAG demo corpus ingests. AAP has never been deployed here
and has no prior ADR.

The repository's Day 0 pattern is uniform and well-established (ADR-0056,
ADR-0310, ADR-0312, ADR-0314): one Ansible role
(`ansible/roles/<c>/tasks/{install,check,uninstall,reconcile}.yml`), one
Helm chart (`gitops/charts/<c>`) whose `operator.enabled`/`<operand>.enabled`
values both default `false`, and two ArgoCD `Application` objects
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
component should reuse rather than invent something new.

One technical fact shapes this ADR's scope directly: the AAP Operator's own
CRDs cover only platform infrastructure - the unified `AnsibleAutomationPlatform`
custom resource (`aap.ansible.com/v1alpha1`, AAP 2.5+) provisions Gateway,
Controller, Hub and EDA together as Kubernetes-managed workloads. It does
**not** publish Kubernetes CRDs for objects that live inside Controller's own
database - Projects, Job Templates, Inventories, Credentials. Those are
Controller API objects, configured the same way this repository already
configures `infra.aap_configuration`-collection-style state: declaratively,
idempotently, from Ansible - not as raw `kind:` manifests. This repo already
has a precedent for exactly that shape: `ansible/tasks/
vault_seed_if_missing.yml` checks whether a piece of state exists before
writing it, so a re-run never clobbers what a previous run already
established.

## Decision

1. **`aap` becomes a new Day 0 component**, following the identical
   role + `-d0`/`-d1` ArgoCD `Application` pair + `gitops/charts/aap` chart
   shape every operator-backed Day 0 component already uses. No new
   deployment mechanism is introduced for this repository.

2. **Placement: immediately after `keycloak`, before `machines`.** `aap` is
   added to `day0_components` in all four `ansible/playbooks/day0_*.yml`
   playbooks and to `DAY0_COMPONENTS` in the root `Makefile`, at this exact
   position in the existing sequence:

   ```
   ... → postgresql → mariadb → tempo → keycloak → aap → machines → nfd → ...
   ```

   By this point in the sequence, PostgreSQL (AAP Controller needs its own
   database, the same way Keycloak has a dedicated database per ADR-0315),
   Vault + External Secrets (AAP's own credentials), and Keycloak (AAP's SSO
   identity source, clause 6) are already Synced+Healthy. No existing
   component's position changes; nothing about today's Day 0 sequence is
   reordered.

3. **Full-platform scope.** `aap`'s `-d1` Application renders a single
   `AnsibleAutomationPlatform` custom resource, gated by `aap.enabled`,
   provisioning Gateway, Controller, Hub and EDA together - not Controller
   alone. This follows the same one-operand-CR-per-chart shape as
   `Keycloak`/`PostgresCluster`/`DataScienceCluster`. `aap`'s `-d0`
   Application renders the operator `Subscription`/`OperatorGroup` via the
   vendored startx `operator` chart dependency (the same `Chart.yaml`
   pattern as `gitops/charts/keycloak`), with channel and catalog source
   left empty in checked-in values and discovered at deploy time by
   `ansible/roles/aap/tasks/install.yml` exactly as `keycloak`/
   `openshift_ai` already do (`PackageManifest` lookup, ADR-0048) - never
   hardcoded to a specific channel name.

4. **Repository loading and Job Templates, via a declarative Ansible sync,
   not a raw CR.** Once the Controller CR reports Ready, a new idempotent
   task file, `ansible/tasks/aap_sync_job_templates.yml` (using the
   `infra.aap_configuration` collection, the same assert-or-seed shape as
   `ansible/tasks/vault_seed_if_missing.yml`), declares:
   - one **Project** pointing at this repository
     (`https://github.com/startxfr/zuno-demo.git`, `main` - the same
     `repoURL`/`targetRevision` every ArgoCD `Application` in this repo
     already uses), with SCM auto-sync so a re-run picks up new playbooks
     without manual re-registration;
   - one **Job Template** per top-level playbook under
     `ansible/playbooks/` (`day0_check`, `day0_install`, `day0_uninstall`,
     `day0_reconcile`, `day1_check`, `day1_build`, `day1_install`,
     `day1_uninstall`), each exposing a Survey prompt for
     `target_component` that mirrors the Makefile's own optional
     `[component]` argument.

   This task is committed, git-tracked, and re-run on every Day 0 install/
   reconcile of `aap` - a no-op when nothing has changed, the same
   idempotency guarantee every other Day 0 component's `install.yml`
   already provides. "Use only chart, ArgoCD and AAP CR" is read here as
   "use the same GitOps-driven, nothing-hand-run-once mechanism this
   repository already trusts for everything else," not as a literal
   requirement for zero non-CR automation - Controller has no native
   Project/Job-Template CRD to satisfy that literally. **Scope boundary:**
   creating these Job Template definitions is the entire scope of this
   ADR. Actually routing `make day0|d0`/`make day1|d1` execution through
   them - so that a Job Template launch, not a local shell invocation,
   becomes how these verbs run - is explicitly deferred to the companion
   ADR-0418 (v0.4). This ADR changes nothing about how operators run Day 0/
   Day 1 today.

5. **Credentials flow through Vault, unchanged from every other
   component.** Controller's own admin credentials and the Machine
   credential it uses to reach this cluster are generated/seeded into
   Vault KV `zuno/aap/...` and delivered via ExternalSecrets, the same
   pattern every other Day 0 component's secrets already follow
   (ADR-0024). Nothing is hand-entered into the Controller UI or committed
   to git.

6. **Identity: Keycloak stays the one identity provider.** Controller's
   login is wired to Keycloak as an OIDC client in the existing `zuno`
   realm (ADR-0012), consistent with every other admin-facing surface in
   this platform - AAP does not stand up a separate local-user store.

7. **Internal-only for v0.3.** This ADR does not classify `aap` under
   ADR-0352's Tier A/B/C internal/external-mode framework - ADR-0352 is
   itself still `Proposed`, not implemented. AAP is always self-installed
   by this repository for v0.3. Supporting a pre-existing,
   customer-managed AAP instance (external mode) is explicitly deferred to
   a future ADR once ADR-0352 itself lands.

8. **Naming.** The component is named `aap` consistently:
   `gitops/charts/aap`, `gitops/apps/aap/`, `ansible/roles/aap/`, the
   `Makefile`'s `DAY0_COMPONENTS` entry `aap`, and the `day0_components`
   entry `aap`. No abbreviation collision exists elsewhere in the current
   component list.

## Consequences

- Day 0 grows from 29 to 30 components, plus one more PostgreSQL database,
  Vault KV path, and ExternalSecret set to operate and back up alongside
  the ones already tracked for `keycloak`/`postgresql`.
- Total Day 0 install wall-clock time grows - Gateway+Controller+Hub+EDA
  starting together is likely the single heaviest pod-start in the whole
  sequence, on the order of what `openshift_ai`'s `DataScienceCluster`
  already costs.
- Every playbook this repository owns becomes visible, and
  executable-in-principle, as an AAP Job Template - the foundation
  ADR-0418 builds on to actually route tracked execution through it. This
  ADR alone changes nothing about how `make d0`/`make d1` behave today.
- AAP is a genuinely heavy new product surface for a demo-scale platform;
  operators should expect it to be among the largest single additions to
  cluster resource consumption since OpenShift AI itself.

## Security considerations

Controller becomes a new privileged actor capable of running arbitrary
Ansible against this cluster once a Job Template is launched (not yet
possible until ADR-0418 wires up execution, but the capability exists as
soon as Controller and its Machine credential exist). That Machine
credential must be scoped no more broadly than the existing Ansible
bootstrap's own cluster-admin kubeconfig already requires - not a new,
separately-privileged identity. Controller's own launch-RBAC (who may run
which Job Template) is a new authorization surface this ADR does not model;
it is deferred to ADR-0418, which must define it before any Job Template
becomes reachable outside an interactive admin login. Installing EDA as
part of "full platform" is flagged explicitly as the reason this choice
widens blast radius slightly versus a Controller-only install: EDA can
react to external webhooks/events and trigger automation without any
interactive login at all, so its event sources must be enumerated and
access-controlled once anything beyond installation depends on it.

## Operational considerations

AAP's own backup/DR posture (Controller's database, Hub's content) becomes
a new operational surface alongside the Vault and PostgreSQL backups
already tracked by this repository. `make d0 check aap` must assert that
the `AnsibleAutomationPlatform` CR and its Gateway/Controller/Hub/EDA
sub-resources are Ready, plus - once clause 4 is implemented - that the
Project's last SCM sync succeeded, mirroring how `keycloak`'s check already
asserts `KeycloakRealmImport/zuno-realm` reached `Done`.

## Acceptance criteria

- The implementation is merged through the normal repository review
  process.
- Relevant documentation and `MEMORY.md` are updated to describe the
  implemented state rather than the target state.
- `make check` and `platform/docs/check_docs.py` (ADR index) demonstrate
  the behavior described in this ADR.
- Security-negative tests are included for the Controller RBAC/Machine
  credential scope introduced by clauses 5 and the Security considerations
  above.

## Implementation state

**To be implemented.** This ADR records an agreed architectural decision.
No chart, role, playbook or Makefile change is claimed by this ADR itself -
implementation lands via a future work package under `docs/roadmap/`, the
same deferral this repository already uses for ADR-0352 (clause 9: "roadmap
briefs live under `docs/roadmap/`, not in this ADR").

## Related ADRs

- [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md)
- [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0310](0310-manage-static-kubernetes-resources-as-per-role-kustomize-directories.md)
- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md)
- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md)
- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md)
- [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md)
- [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md) (companion, v0.4)

See [Standard clauses](README.md#standard-clauses) for Alternatives and
Review evidence.

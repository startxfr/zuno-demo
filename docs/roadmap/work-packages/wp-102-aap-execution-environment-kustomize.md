# WP-102: Custom AAP execution environment carrying `kustomize`, `oc` and `cosign`

- **State:** Not started.
- **ADRs:** ADR-0418 (clause 6 - Workflow Template Day 2 live verification).
- **Depends on:** WP-095 (Workflow Templates registered and DAG-verified).
- **Unblocks:** a full green `zuno-day2-check-workflow` run (currently
  blocked on the `agents` node alone), and green `zuno-day1-build`/
  `zuno-day2-build`/`zuno-day3-sign` runs once launched via AAP.

> Execute this brief as a standalone task from the repository root.

## Goal

Every Job/Workflow Template in this repo runs under Controller's stock
`ee-supported-rhel9` execution environment (`registry.redhat.io/
ansible-automation-platform-27/ee-supported-rhel9`) - nothing in
`gitops/charts/aap-config` assigns a custom one. Day 2's `agents` check
task (`ansible/roles/agents/tasks/run_acceptance_gate.yml`'s
`apply_kustomize.yml` include, ADR-0053's acceptance gate) shells out to
the `kustomize` CLI binary, which that stock EE does not ship - confirmed
live 2026-08-30 running `zuno-day2-check-workflow` for real (job 335,
node `agents`/job 353: `/bin/sh: line 1: kustomize: command not found`,
`rc=127`). This is the first Day 2 AAP run to ever reach that task - it
would fail identically on any future Day 2 `check`/`install` launch
through AAP until fixed.

A follow-up audit of every `ansible.builtin.command`/`shell` task
actually reached on `localhost` (this repo runs `ansible_connection:
local` everywhere, so any such task executes **inside the EE container
itself**, not inside a target pod) found two more binaries of the exact
same class missing from the stock EE:

- **`oc`** - `ansible/tasks/apply_openshift_build.yml`'s `oc start-build
  ... --wait` (fires whenever `day1_verb`/`day2_verb == build`), and
  `mlops`/`rag_ingestion`'s install roles (`oc whoami -t`, minting a
  bearer token for KFP).
- **`cosign`** - `ansible/tasks/verify_okf_signatures.yml` shells
  `platform/supply-chain/sign_okf_bundle.py verify`, which itself invokes
  `cosign verify-blob` directly on localhost. Reached from
  `ansible/roles/agents/tasks/check.yml` and `ansible/playbooks/
  day3_sign.yml`.

**`vault` and `helm` were investigated and ruled out** - every `vault`
call in this repo runs *inside* the Vault pod via
`kubernetes.core.k8s_exec` (that pod already has its own `vault` binary,
nothing to bundle), and `helm` is never shelled to at all: its only
appearances are `spec.source.helm.values` fields on ArgoCD `Application`
objects, rendered/executed by ArgoCD's own repo-server, never by Ansible.

**Decision: one custom EE carrying all three binaries** (`kustomize` +
`oc` + `cosign`), rather than three separate images or per-template
workarounds.

## ADR references

ADR-0418 clause 6 - Day 2 Workflow Template live verification is complete
for the DAG/edges themselves (WP-095's own live pass confirmed the
`rag`/`rag-ingestion`/`mcp` parallel edge), but a full green end-to-end
run is blocked on this gap, which is outside the Job/Workflow Template
mechanism ADR-0418 itself decided.

## Scope (decided)

- **Build**: an `ansible-builder` execution-environment definition under
  `components/aap-execution-environment/` (`execution-environment.yml`),
  layering onto `ee-supported-rhel9` as base image: `openshift-clients`
  (`oc`) via `dnf` (this cluster's RHN subscription auto-attach already
  makes this RPM available, proven for the `aap` role), plus pinned-
  version `kustomize` and `cosign` release binaries downloaded and
  checksum-verified. The `Dockerfile` committed alongside it is
  `ansible-builder create`'s generated output, matching every other
  component's `components/<name>/{Dockerfile|Containerfile}` convention
  - the BuildConfig here uses a plain `Docker` strategy, same as
  everywhere else in this repo, not `ansible-builder build` itself.
- **Publish**: an in-cluster OpenShift `BuildConfig`/`ImageStream` in
  `zuno-ai-build`, via the existing shared task
  `ansible/tasks/apply_openshift_build.yml` (new role
  `ansible/roles/aap_execution_environment_build`) - the **internal
  OpenShift registry**
  (`image-registry.openshift-image-registry.svc:5000/zuno-ai-build/
  aap-execution-environment:latest`), i.e. path 1 of this repo's "two
  parallel build paths" pattern. The quay.io/GitHub Actions path (path 2)
  is explicitly NOT used here - it remains a separate, currently-unused
  release mechanism.
- **Register in Controller**: two corrections found while designing this,
  both confirmed live:
  - There is **no `ExecutionEnvironment` CRD** (`oc get crd` lists 9
    `tower.ansible.com` kinds, none for execution environments) - EE
    registration is unconditionally a raw Controller-API call
    (`POST /api/controller/v2/execution_environments/`), never a CR.
  - `AnsibleCredential` *does* expose a generic `inputs` field (confirmed
    via `oc explain ansiblecredential.spec`), so a Container Registry
    credential is CR-expressible in principle - but every existing
    credential in this repo sources its secret material via
    `kubernetes_bearer_token_secret` (a *reference* to a k8s Secret),
    never inline, and `inputs` has no such indirection. **Decision: the
    registry credential is created via the same raw-API GET-then-POST
    idiom already used elsewhere in `aap_config/tasks/install.yml`**
    (e.g. the organization/host upsert blocks), not via a CR, to keep the
    registry password out of any committed manifest. Its password is the
    token of the `aap-installer` ServiceAccount (the `zuno-aap-installer`
    credential's underlying SA, not the credential's own name) via its
    existing `aap-installer-token` Secret (already created by
    `gitops/charts/aap-config/templates/serviceaccount.yaml`) - once
    `zuno-aap` is added to the image-puller RoleBinding loop (below), no
    new ServiceAccount is needed.
  - Both the credential-registration and EE-registration steps, plus the
    per-Job-Template `execution_environment` PATCH, live in a **new**
    `ansible/roles/aap_config/tasks/wire_execution_environment.yml`,
    called from `ansible/playbooks/day1_build.yml` right after the image
    build - **not** from `aap_config`'s own Day 0 `install.yml` flow,
    since the image and its Controller EE object don't exist yet at
    Day 0.
- **RBAC**: add `zuno-aap` (the AAP namespace) to the `system:
  image-puller` RoleBinding loop in both
  `ansible/tasks/apply_openshift_build.yml` and
  `ansible/roles/image_mirrors/tasks/install.yml` (kept symmetric per
  that file's own documented convention) - needed for the Kubernetes-
  level pull; separate from the Controller-level registry credential
  above, which drives AAP's own podman-via-Receptor pull mechanism.
- **Assignment - narrow, not broad**: assign the custom EE only to the
  Job Templates that actually reach one of the three binaries, per
  ADR-0418's own least-privilege-by-default posture. Traced statically:

  | Template | Playbook | Binary(ies) | Path |
  |---|---|---|---|
  | `zuno-day2-check` | `day2_check.yml` | kustomize, cosign | `agents/tasks/check.yml` → `run_acceptance_gate.yml` → `apply_kustomize.yml`; and → `verify_okf_signatures.yml` |
  | `zuno-day2-install` | `day2_install.yml` | oc | `mlops`/`rag_ingestion` install (`oc whoami -t`) |
  | `zuno-day1-build` | `day1_build.yml` | oc | `apply_openshift_build.yml` (`oc start-build`, verb=build) |
  | `zuno-day2-build` | `day2_build.yml` | oc | same |
  | `zuno-day3-sign` | `day3_sign.yml` | cosign | `verify_okf_signatures.yml` |

  `zuno-day1-check`/`zuno-day3-check`/`zuno-day3-test` touch none of the
  three binaries (confirmed) and stay on the stock EE. Re-grep before
  finalizing in case a later commit adds a new
  `apply_kustomize.yml`/build-verb/`verify_okf_signatures.yml` caller.

## Verification checklist (live, unresolved - do not assume)

- **Build-time egress**: does the `zuno-ai-build` BuildConfig's build pod
  reach GitHub Releases to download `kustomize`/`cosign`? This cluster's
  NetworkPolicies are allowlist-based elsewhere (see
  `ansible/roles/image_mirrors/README.md`'s whole rationale for mirroring
  base images specifically to avoid needing such egress) - if blocked,
  mirror the release tarballs first instead of downloading at build time.
- **`oc` via RPM**: confirm `dnf install openshift-clients` succeeds
  under this cluster's RHN auto-attach subscription during the EE image
  build (already proven for the `aap` role's own install, not yet for a
  BuildConfig build pod specifically).
- **TLS trust**: does Controller's podman-in-task-pod process trust the
  internal registry's service-ca-signed certificate the same way kubelet
  does automatically for normal pod image pulls? Unverified - may need
  `verify_ssl: false` or an explicit CA bundle on the registry credential.
- **NetworkPolicy egress** `zuno-aap` → `openshift-image-registry:5000`:
  no existing allow rule found - confirm whether one is actually needed
  before adding it speculatively.

## Out of scope / deferred

- Any change to `verify_okf_signatures.yml`'s own logic - the unrelated
  `.rc`/`no_log` reporting bug in that file was found in the same live
  run and already fixed directly (not part of this WP).
- Re-signing any agent bundle whose signature is stale - a data-state
  issue, not an execution-environment one (see WP-31/33/35/36's own
  retroactive-signing work for that).

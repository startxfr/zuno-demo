# Installation Workflow

Before the first `make day0|d0 install`, copy `ansible/confidential.example.yml`
to `ansible/confidential.yml` and fill in the values (Google OAuth client,
SMTP technical credentials, Atlassian Confluence token) - the `vault` role
(the first Day 0 component that needs them) fails fast if this file is
missing. It is gitignored and re-read on every `vault` install, so it can
be deleted again afterwards unless Vault needs to be reinstalled later.

The public operator interface is intentionally small, structured as Day 0
(cluster prerequisites) / Day 1 (build + run the platform) - ADR-0056:

```bash
make day0|d0 check [component]
make day0|d0 install [component]
make day0|d0 uninstall [component]  # reverse order
make day0|d0 all [component]        # check + install, in order

make day1|d1 check [component]      # `agents` runs the ADR-0053 acceptance gate
make day1|d1 build [component]
make day1|d1 install [component]
make day1|d1 uninstall [component]  # reverse order
make day1|d1 all [component]
```

The Makefile dispatches implementation work to Ansible playbooks and roles.
Each Day 0/Day 1 role applies its own component's two ArgoCD `Application`
manifests directly (`ansible/tasks/apply_gitops_app.yml`, `-d0` then `-d1` -
see `gitops/apps/README.md`) - this is the only mechanism the `day0`/`day1`
targets use to reconcile GitOps-managed state (ADR-0311).

## Alternative: pure-GitOps bootstrap (documentation example only)

`gitops/root-app-of-apps.yaml` is a root ArgoCD "App-of-Apps" `Application`
that recurses over `gitops/apps/` and manages every `application-d0.yaml`/
`application-d1.yaml` it finds as a child Application. It is kept in the
repository as a worked example of bootstrapping the platform with ArgoCD
alone, with no Ansible involved: install the OpenShift GitOps operator,
then `oc apply -f gitops/root-app-of-apps.yaml`. This path is illustrative
only - it is never applied by `make day0|d0`/`day1|d1`, and isn't
exercised by `make day1|d1 check agents` (the ADR-0053 gate) or CI. It
also has no native ordering between a
component's `-d0` and `-d1` Applications (unlike the `make day0|d0`/
`day1|d1` path, where Ansible applies `-d0` and waits for it to be
Synced+Healthy before applying `-d1`) - see ADR-0311 and ADR-0312's
addendum.

# Installation Workflow

Before the first `make day0|d0 install`, copy `ansible/confidential.example.yml`
to `ansible/confidential.yml` and fill in the values (Google OAuth client,
SMTP technical credentials, Atlassian Confluence token) - the `vault` role
(the first Day 0 component that needs them) fails fast if this file is
missing. It is gitignored and re-read on every `vault` install, so it can
be deleted again afterwards unless Vault needs to be reinstalled later.

The public operator interface is intentionally small, structured as Day 0
(cluster prerequisites) / Day 1 (AI-platform-operator stack) / Day 2 (AI
infrastructure + content ingestion) / Day 3 (agent test/stresstest
operations) - ADR-0056/ADR-0060:

```bash
make day0|d0 check [component]
make day0|d0 install [component]
make day0|d0 uninstall [component]  # reverse order
make day0|d0 all [component]        # check + install, in order

make day1|d1 check [component]
make day1|d1 build [component]
make day1|d1 install [component]
make day1|d1 uninstall [component]  # reverse order
make day1|d1 all [component]

make day2|d2 check [component]      # `agents` runs the ADR-0053 acceptance gate
make day2|d2 build [component]
make day2|d2 install [component]
make day2|d2 uninstall [component]  # reverse order
make day2|d2 all [component]

make day3|d3 test [component]
make day3|d3 stresstest [component]
```

The Makefile dispatches implementation work to Ansible playbooks and roles.
Each Day 0/Day 1/Day 2 role applies its own component's ArgoCD `Application`
manifest(s) directly (`ansible/tasks/apply_gitops_app.yml`, `-d0` then `-d1` -
see `gitops/apps/README.md`) - this is the only mechanism the `day0`/`day1`/
`day2` targets use to reconcile GitOps-managed state (ADR-0311). The
`-d0`/`-d1` Application-suffix pattern is an internal "operator install vs
live service" two-phase convention per component, orthogonal to which
macro day (day0/day1/day2) actually invokes that role - it is not
renamed to `-d2`/`-d3` for components that moved tiers (ADR-0060).

## Alternative: pure-GitOps bootstrap (illustrative only)

`gitops/root-app-of-apps.yaml` is a worked example of bootstrapping with
ArgoCD alone, no Ansible: install the OpenShift GitOps operator, then
`oc apply -f gitops/root-app-of-apps.yaml`. Never applied by `make
day0|d0`/`day1|d1`/`day2|d2`, not exercised by the acceptance gate or CI,
and has no native `-d0`/`-d1` ordering (unlike the Ansible path above) -
see ADR-0311/ADR-0312.

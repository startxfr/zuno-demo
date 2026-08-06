# Installation Workflow

The public operator interface is intentionally small, structured as Day 0
(cluster prerequisites) / Day 1 (build + run the platform) - ADR-0056:

```bash
make day0|d0 check [component]
make day0|d0 install [component]
make day0|d0 configure [component]
make day0|d0 all [component]        # check + install + configure, in order

make day1|d1 check [component]      # `agents` runs the ADR-0053 acceptance gate
make day1|d1 build [component]
make day1|d1 configure|run [component]
make day1|d1 all [component]
```

The Makefile dispatches implementation work to Ansible playbooks and roles.
Each Day 0/Day 1 role applies its own component's ArgoCD `Application`
manifest directly (`ansible/tasks/apply_gitops_app.yml`, one per directory
under `gitops/apps/`) - this is the only mechanism the `day0`/`day1`
targets use to reconcile GitOps-managed state (ADR-0311).

## Alternative: pure-GitOps bootstrap (documentation example only)

`gitops/root-app-of-apps.yaml` is a root ArgoCD "App-of-Apps" `Application`
that recurses over `gitops/apps/` and manages every `application.yaml` it
finds as a child Application. It is kept in the repository as a worked
example of bootstrapping the platform with ArgoCD alone, with no Ansible
involved: install the OpenShift GitOps operator, then
`oc apply -f gitops/root-app-of-apps.yaml`. This path is illustrative only -
it is never applied by `make day0|d0`/`day1|d1`, and isn't exercised by
`make check` or CI. See ADR-0311.

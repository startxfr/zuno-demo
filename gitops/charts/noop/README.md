# noop

A Helm chart with no templates - it renders zero Kubernetes resources.

## Purpose

Every platform component under `gitops/apps/` has two ArgoCD Applications,
`<app>-d0` (operator/cluster-scoped install) and `<app>-d1` (CRD instances,
pods, secrets - the live service). Most components only have real content on
one side (e.g. `vault` has no OLM operator at all, so all of its content is
`-d1`; `namespaces` only creates Namespaces/Quotas, so all of its content is
`-d0`). Rather than omitting the empty half's `application-d0.yaml` or
`application-d1.yaml` file, this chart is used as its `spec.source` - keeping
the `-d0`/`-d1` naming convention uniform and visible in `gitops/apps/`
without any component being a silent exception.

`spec.destination.namespace` for a `noop`-sourced Application is set to
`openshift-gitops` (a namespace that always exists) - it has no effect since
nothing is ever deployed.

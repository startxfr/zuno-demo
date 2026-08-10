# admin-context

Cluster-admin-level objects every other Day 0 component implicitly depends
on. `priorityClasses.enabled` (Day 0 `-d0`) renders the four zuno
`PriorityClass` objects; `helmChartRepository.enabled` (Day 0 `-d1`) renders
the `startx` `HelmChartRepository` (`helm.openshift.io/v1beta1`),
registering the startx Helm repo in the cluster's Developer Catalog.

This is separate from the ArgoCD-native repository `Secret`
(`ansible/roles/argocd/kustomize/appproject/repository-startx.yaml`), which
only lets ArgoCD itself resolve `startx` chart dependencies at render time.

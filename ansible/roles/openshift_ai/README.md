# openshift_ai

Installs the Red Hat OpenShift AI operator (OLM `Subscription`, ADR-0002's
3.5 EA2 channel) and applies the `DataScienceCluster` with `kserve` (model
serving) enabled. PREP_COMPONENT only - no CONFIG_SCOPE. The `datascience`
role owns the project namespace scaffolding that layers on top of this.

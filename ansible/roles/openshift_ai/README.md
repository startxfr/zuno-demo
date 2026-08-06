# openshift_ai

Installs the Red Hat OpenShift AI operator (OLM `Subscription`, channel
discovered from the cluster's own catalog - ADR-0048, see below) and
applies the `DataScienceCluster` with `kserve` (model serving) enabled.
A Day 0 component (ADR-0056) with all three verbs: `check`/`install`
subscribe the operator, wait for the CRD, apply the `DataScienceCluster`
and wait for `Ready`, then create the `zuno-ai-run` project namespace (RHOAI-
dashboard-labeled, shared with the rest of the AI/agent-serving stack -
ai-gateway, agent-runtime, mcp-gateway, mcp-sales-db); `configure` applies
a `ResourceQuota` capping GPU consumption at 1 (this demo has exactly one
24GB L4 budgeted for the single local model). This role used to be split
across `openshift_ai` (operator + DataScienceCluster) and a separate
`datascience` role (namespace + quota) - merged into one role for one
conceptual prerequisite as part of ADR-0056, since the split never
reflected two genuinely independent concerns.

## Channel discovery (ADR-0048)

`tasks/install.yml` reads the `rhods-operator` `PackageManifest`'s
published channels and selects the one matching the `3.5` family (falling
back to the manifest's own `defaultChannel`, and failing with a clear
diagnostic - listing every published channel - if neither is available)
instead of a hardcoded `eus-3.5` guess. The exact EA2/GA channel name
published by a given catalog snapshot isn't standardized, and the
previous hardcoded value was explicitly flagged as an unverified
assumption.

## RawDeployment, not Serverless (ADR-0047)

The `DataScienceCluster`'s `kserve.serving.managementState` is `Removed`,
not `Managed` - a deliberate fix, not the original value. `Managed` (with
a `name: knative-serving` KNativeServing reference) implicitly requires
the Red Hat OpenShift Service Mesh Operator, the Red Hat OpenShift
Serverless Operator, and cert-manager, none of which this repository ever
installed - so on a real cluster this `DataScienceCluster` would never
have reached `Ready`. This demo's one model
(`gitops/charts/models`) is always-on (`minReplicas == maxReplicas == 1`)
with no use for Serverless's scale-to-zero, so `Removed` (RawDeployment
mode) is the correct choice here, not a workaround - see
`tasks/install.yml`'s inline comment for the full reasoning, and
`gitops/charts/models/README.md` for the InferenceService-level annotation
that makes the same choice explicit at that layer too.

Connectivity Link, LeaderWorkerSet and MaaS-related dependencies (also
named in ADR-0047's Operational considerations) are deliberately not
installed either - see `platform/openshift-ai/README.md` for why none of
them are applicable to this repository's actual v0 feature set.

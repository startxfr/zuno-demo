# datascience

`prepare.yml` creates the `zuno-datascience` namespace the `models` role's
`InferenceService` deploys into (labeled for the RHOAI dashboard).
`configure.yml` applies a `ResourceQuota` capping GPU consumption at 1 -
this demo has exactly one 24GB L4 budgeted for the single local model.
Depends on `openshift_ai` (`DataScienceCluster` Ready) having run first.

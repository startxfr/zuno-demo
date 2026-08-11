# tempo

Installs the Red Hat build of the Tempo Operator and a demo-scale
`TempoMonolithic` (`tempo`, `zuno-telemetry` namespace, PV storage, no
multi-tenancy) via `gitops/apps/tempo/application-d0.yaml` (operator) and
`application-d1.yaml` (instance) - see `gitops/apps/README.md` and
`gitops/charts/tempo/README.md`.

Stores traces exported by the `observability` role's Collector
(`otlp/tempo` exporter) and is queried by the `kiali` role's Kiali instance.
Depends on `observability` (the Collector must exist to export anything
useful) but not on `service_mesh` directly - traces from any OTLP source
land here, not just mesh sidecars.

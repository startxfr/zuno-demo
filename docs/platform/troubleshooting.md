# Troubleshooting

Troubleshooting procedures will be expanded as implementation proceeds. The first diagnostic entry point is `make day1|d1 check agents` (the ADR-0053 acceptance/security gate) plus component-specific Ansible role diagnostics (`make day0|d0 check [component]`, `make day1|d1 check [component]`). To roll back a misbehaving component, `make day0|d0 uninstall [component]` / `make day1|d1 uninstall [component]` reverse the install in the reverse dependency order.

## A CSV keeps flapping between `Installed` and `Installing`

Seen on `mariadb-operator.v26.6.0` in `openshift-operators` (2026-08-18): the console/`oc get csv`
kept oscillating between `Installed` and `Installing` instead of settling. Diagnosis steps that
generalize to any OLM-managed operator doing this:

1. **Find the CSV's own Deployment and check restarts.** `oc get pods -n openshift-operators` (or
   the CSV's install namespace) — a high restart count on the operator's own controller-manager
   pod is the usual cause; OLM only reports a CSV `Succeeded` while its owned Deployment reports
   `Available`, so a pod that keeps restarting makes the CSV phase flap in lockstep.
2. **Read the pod's events, not just its logs**: `oc get events -n <ns>
   --field-selector involvedObject.name=<pod>  --sort-by=.lastTimestamp`. `Unhealthy`/`ProbeError`
   on `/healthz`/`/readyz` followed by a `Killing: ... failed liveness probe` event means kubelet
   is killing it on a probe timeout, not a crash - check `oc adm top pod` next to see whether it's
   CPU or memory that's actually starved (don't assume; the mariadb-operator case had already been
   tuned for a memory OOMKill previously - this time it was CPU throttling that tripped the probes,
   with memory usage comfortably under its limit throughout).
3. **If the operator is an operator-sdk Helm-operator** (`helm-operator` in its logged version
   banner, `ownerKind: <Something>` reconciling via an embedded chart), its resource sizing is
   whatever the `Subscription`'s `spec.config.resources` sets - in this repo that's
   `operator.subscription.operator.config.resources` in the component's `gitops/charts/<c>/values.yaml`
   (see `gitops/charts/mariadb/values.yaml` for the mariadb-operator precedent: bumped
   `limits.cpu` from `500m` to `1` after 100+ restarts/day were traced to probe timeouts under CPU
   throttling during the operator's own API-discovery startup - this cluster carries 400+ CRDs,
   which makes that discovery pass unusually CPU-heavy). OLM's `SubscriptionConfig` does not expose
   probe-timeout overrides, so resource headroom is the lever available from GitOps.
4. **Don't assume every suspicious `sh.helm.release.v1.<name>.v<rev>` secret in the same namespace
   belongs to the operator you're investigating.** OLM installs many CSVs' Helm-operator
   controllers into the shared `openshift-operators` namespace, and each release secret only says
   which *release* it's for, not which *pod*. Confirm ownership before trusting a lead - e.g. by
   checking which live objects carry a matching `meta.helm.sh/release-name` annotation:
   `oc get <kind> -A -o json | jq '.items[] | select(.metadata.annotations["meta.helm.sh/release-name"]=="<release>") | .metadata.namespace, .metadata.name'`
   across the object kinds the suspect chart is likely to own (`deployment`, `serviceaccount`,
   `role`, `clusterrole`, `service`, `validatingwebhookconfiguration`, ...). In the mariadb
   investigation, a fast-incrementing `default-base` release in `openshift-operators` looked like
   the smoking gun but actually belonged to the ServiceMesh (Sail) operator's `default` Istio CR,
   not mariadb-operator at all - a real, separate issue worth its own look, but not this one.
5. **A cpu/memory bump alone may not fully fix it - check `oc logs`/`--previous`, not just
   events.** Seen again on the same operator, later the same day (2026-08-18): after step 3's
   `limits.cpu` bump the pod was still crash-looping (73 restarts/~10h), but this time the
   container's own stdout - not the kubelet `Unhealthy`/`Killing` events from step 2 - had the
   real story: `"error":"leader election lost"` immediately after
   `client rate limiter Wait returned an error: context deadline exceeded`. This operator-sdk
   Helm-operator watches *all* namespaces across every dependent kind (`ClusterRole`, `Role`,
   `Service`, `ConfigMap`, `Deployment`, `ServiceAccount`, `ValidatingWebhookConfiguration`, ...)
   with 16 reconcile workers; this cluster's client-side API throttling (visible in other
   operators' logs too via the same "Waited ... due to client-side throttling" lines - a shared
   cluster trait, not unique to this operator) occasionally delays the shared client's
   leader-election lease-renewal call past its ~10s deadline, and controller-runtime exits(1)
   rather than risk running unelected - fatal with only one replica to fail over to. The fix that
   generalizes: scope `WATCH_NAMESPACE` (via the same `operator.subscription.operator.config.env`
   mechanism in the component's `values.yaml`) down to only the namespace(s) that actually hold
   the operator's activation CR - this cuts the reconcile-time API call volume feeding the
   throttling. It doesn't replace step 3's cpu headroom, though: discovery/RESTMapper startup
   cost isn't namespace-scoped, so a cluster with 400+ CRDs can still throttle during startup even
   with the watch scoped down.

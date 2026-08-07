# namespaces chart

Creates the five agent namespaces (ADR-0023), each labeled
`zuno.io/agent: <name>` and `zuno.io/status: active|placeholder`, plus a
default `ResourceQuota` and a default-deny-other-namespaces `NetworkPolicy`
for every one of them regardless of status.

Also applies the same default-deny-other-namespaces `NetworkPolicy` shape
(ADR-0052) to three platform namespaces this chart does not itself create
(`zuno-auth`, `zuno-data`, `zuno-telemetry` - `values.yaml`'s
`platformNamespaces`), each with a small, explicit list of known real
cross-namespace callers. `zuno-ai-run` is deliberately excluded - see
`values.yaml`'s comment on why ADR-0037 needs per-workload NetworkPolicies
there instead of a namespace-wide baseline.

Referenced by `gitops/apps/namespaces/application-d0.yaml` (all of this
chart's content is cluster-scoped, so it's entirely `-d0`;
`application-d1.yaml` is a no-op - see `gitops/apps/README.md`), applied
by `ansible/roles/namespaces`, a Day 0 component (ADR-0056 - reachable via
`make d0 install namespaces`). The formerly separate
`gitops/apps/agents/application.yaml` (a stale, orphaned duplicate
pointing at this same chart) has been removed.

## Why all five exist, not just zuno-agent-tekos

Only `zuno-agent-tekos` (`status: active`) hosts real workloads in v0 - the
Tekos FE/BFF from `gitops/charts/tekos`, plus the Agent Runtime/MCP
Gateway/RAG service owned by other tracks. `zuno-agent-comage`, `zuno-agent-advantage`,
`zuno-agent-finage` and `zuno-agent-arkos` (`status: placeholder`) are created and
labeled but intentionally have nothing scheduled in them: this is what
makes the namespace-per-agent isolation model (ADR-0023) demonstrably real
infrastructure rather than a diagram for a system that, per ADR-0007, is
only declaratively defined for four of its five agents in v0. A reviewer
can run:

```sh
oc get namespaces -l zuno.io/agent
```

and see all five agent boundaries already exist, each independently
quota'd and network-isolated, ready to receive a workload the moment that
agent's OKF `status` flips to `active` and a FE/BFF chart is added for it.

See `platform/architecture/agent-platform-separation.md` for the full
platform-vs-instance split this chart is one half of.

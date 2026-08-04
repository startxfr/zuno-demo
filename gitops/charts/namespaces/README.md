# namespaces chart

Creates the five agent namespaces (ADR-0023), each labeled
`zuno.io/agent: <name>` and `zuno.io/status: active|placeholder`, plus a
default `ResourceQuota` and a default-deny-other-namespaces `NetworkPolicy`
for every one of them regardless of status.

Referenced by exactly one Application: `gitops/apps/agents/application.yaml`
(applied by `ansible/roles/agents`, reachable via `make install`).

## Why all five exist, not just zuno-tekos

Only `zuno-tekos` (`status: active`) hosts real workloads in v0 — the
Tekos FE/BFF from `gitops/charts/tekos`, plus the Agent Runtime/MCP
Gateway/RAG service owned by other tracks. `zuno-comage`, `zuno-advantage`,
`zuno-finage` and `zuno-arkos` (`status: placeholder`) are created and
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

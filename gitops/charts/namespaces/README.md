# namespaces chart

Creates the platform namespaces (`values.yaml`'s `platformNamespaces`:
`zuno-auth`, `zuno-vault`, `zuno-data`, `zuno-monitoring`,
`zuno-ai-build`, `zuno-ai-run`, `zuno-mesh`), and applies a default-deny-
other-namespaces `NetworkPolicy` to each, with a small, explicit
list of known real cross-namespace callers. `zuno-ai-run` is deliberately
excluded from that baseline - see `values.yaml`'s comment for why it needs
per-workload NetworkPolicies there instead of a namespace-wide baseline.

Agent workloads no longer get their own namespace, quota or NetworkPolicy
baseline here - every active agent's FE/BFF deploys into the shared
`zuno-ai-run` namespace instead (`gitops/charts/tekos`).

Referenced by both `gitops/apps/namespaces/application-d0.yaml` (Namespace
objects only, `namespace.enabled: true`) and `application-d1.yaml`
(ResourceQuota + NetworkPolicy, `policy.enabled: true`) - same chart, two
Applications, each turning on only its own top-level `enabled` toggle (see
`values.yaml`; both default `false`, mirroring `gitops/charts/cert-manager`'s
operator/ClusterIssuer split). `-d0` is applied by `ansible/roles/namespaces`
as a Day 0 component (`make d0 install namespaces`); `-d1` is
applied separately as a Day 1 component (`make d1 install namespaces`,
first in `day1_install.yml`) so a bare Day 0 install creates namespaces
without the quota/netpol overlay until Day 1 explicitly layers it on.

## Why only Tekos runs workloads, in the shared zuno-ai-run namespace

Of the five agents, only Tekos (`status: active`) has FE/BFF workloads
deployed (`gitops/charts/tekos`, into `zuno-ai-run`), alongside the shared
Agent Runtime/AI Gateway/MCP Gateway/RAG service owned by other tracks.
Comage, Advantage, Finage and Arkos (`status: placeholder`) exist only as
`agents/<name>/agent.okf.md` declarative bundles, with no dedicated
namespace, quota or workload of their own; they inherit no infrastructure
footprint until their OKF `status` flips to `active` and a FE/BFF chart is
added for them into `zuno-ai-run`.

See `platform/architecture/agent-platform-separation.md` for the full
platform-vs-instance split this chart is one half of.

## Targeted mTLS and egress (ADR-0602 / WP-224)

`templates/peerauthentication-namespace.yaml` renders, for an entry with
`peerAuthentication` (zuno-data, zuno-auth, zuno-ai-run only), a namespace-wide
`default` PeerAuthentication in `mode` (PERMISSIVE until the live rehearsal,
then STRICT: a one-line flip) and one workload-scoped PeerAuthentication per
exception, opening only the listed container ports to plaintext for a named
non-mesh caller (`reason:`, rendered as the `zuno.io/permissive-reason`
annotation). `templates/egressfirewall-namespace.yaml` renders the deny-all
EgressFirewall of an entry with `egressFirewall` (zuno-ai-run), from its host
list, once the d1 Application passes `clusterBaseDomain`. An entry with
`egressFirewall.redis` (zuno-ai-run) also allows `redisExternal`, the external
Redis endpoint `ansible/tasks/redis_seam_values.yml` passes in ADR-0352
external mode only (WP-214; nothing for the built-in or a `*.svc` name). zuno-unifai's
EgressFirewall lives in `gitops/charts/unifai`, like the other experience
charts (ADR-0590). `platform/security/check_mesh_mtls.py` guards both.

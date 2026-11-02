# WP-182 evidence: OpenClaw spike

- **Work package:** [WP-182](../work-packages/wp-182-openclaw-preparation.md)
- **ADR:** [ADR-0589](../../adr/0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md)
- **Cluster:** demo333 (OpenShift 4.22.8)
- **Started:** 2026-11-02
- **Constraint:** the GPU nodes are NotReady; the spike uses the external providers of
  `platform/ai-gateway/provider-routing.yaml` (C1/C2) and records local-model errors without being blocked by them.

## User decisions (2026-11-02)

- Keep claw-operator. Front door: oauth2-proxy (Keycloak `zuno`) in front of the Control UI, plus OpenClaw's own
  password auth, because the operator does not allow trusted-proxy mode (step 6).
- claw-operator is installed on demo333 pinned by digest and kept for WP-183; only the scratch namespace
  `zuno-claw-scratch` is removed at the end.
- Model calls go to the external providers at C1/C2, with demo prompts only.
- Personas: `consultant-02` and `sale-01`, the same pair as Open WebUI (WP-180), reused by WP-184.

## Step 1: operator and pins

**Source read.** `codeready-toolchain/claw-operator`, branch `master`, commit
`f5aa592276ae9eebf3b295bb95107b0371fd8bbe` (2026-10-23). This is the authoritative code:
`redhat-et/claw-project` holds design documents only ("No code lives here") and links to the
`redhat-et/claw-operator` fork, which has diverged (last commit `ce75611b`, 2026-07-31). Files read:
`api/v1alpha1/claw_types.go`, `internal/controller/claw_{providers,egress,auth}.go`,
`internal/proxy/injector_oauth2.go`, `config/rbac/role.yaml`, `docs/user-guide.md`, `docs/architecture.md`.

**Catalog.** `quay.io/codeready-toolchain/claw-operator-catalog:latest` resolves to

    quay.io/codeready-toolchain/claw-operator-catalog@sha256:847abf9c9d697cc0069656819920e48a355c3852c6c033f5dd28c956e9b8cd25

(built 2026-10-23). Its file-based config holds one package `claw-operator`, one channel `staging` with a single
entry `claw-operator.v0.0.227-commit-f5aa592` (`skipRange >=0.0.0 <0.0.227-commit-f5aa592`): the catalog is built
from the commit read above. Every new upstream commit replaces the catalog content; there are no tagged releases.

**Images of the bundle** (referenced by tag in the catalog; digests resolved 2026-11-02):

| Role | Reference in the bundle | Digest |
|---|---|---|
| bundle | `quay.io/codeready-toolchain/claw-operator-bundle:v0.0.227-commit-f5aa592` | `sha256:92e54d50352eaafa27349ca7daf52cc4e41bd42c6213c31c26e79edf343b4ae5` |
| manager | `quay.io/codeready-toolchain/claw-operator:f5aa592` | `sha256:4a8363da3ec484b4437ddf4e5beac158219aa6d17bca6f58694e4cb21bde44cd` |
| proxy | `quay.io/codeready-toolchain/claw-proxy:f5aa592` | `sha256:b3ad798c7364f79075a1049ea2b87126dbba2bec092497928ac8546597e59f5a` |
| kubectl | `quay.io/openshift/origin-cli:4.21` | `sha256:f3fc63fc3d2fd1c3a2c3311bf517b776f6596244e697dad32d62ca9fd6482fe5` |

**OpenClaw image.** The CRD default is `ghcr.io/openclaw/openclaw:2026.7.1-2`
(`sha256:8789721d2e9b24b780a1504b56deb4c6bd5c7dbf96a1dd117e7c45c2ed72c8ac`, 2026-08-04). The latest stable release
is `2026.10.9` (`sha256:1a2a3ce113e435039dbeac5ae261759bb4759908563d91c81059e896b38c5d98`, 2026-10-29). The spike
starts on the operator's default (the version it is tested with). **Tested 2026-11-02 (WP-183): `2026.10.9` does not
work with operator f5aa592.** It first asks for a state-database migration (`audit-events-v2`, `openclaw doctor
--fix`), then, on an empty volume, refuses the operator's `openclaw.json` (`agents.list`, `agents.defaults.models`,
`memorySearch` moved; `gateway.controlUi.dangerouslyDisableDeviceAuth` retired). The operator owns those keys: the
OpenClaw image follows the operator's default.

**Signatures.** No cosign signature exists for the catalog, the manager or the OpenClaw image (no
`sha256-<digest>.sig` tag). ADR-0586's signature and attestation verification cannot apply; the pin is by digest
only. The bundle references its images by **tag**, so the catalog digest alone does not freeze the manager and proxy
images: WP-183 records the four digests above and its check compares the running pods' image IDs with them.

**RBAC** (`config/rbac/role.yaml`, ClusterRole `manager-role`): cluster-wide `get/list/watch/create/update/patch/
delete` on ConfigMaps, Secrets, Services, ServiceAccounts, PVCs, Deployments, NetworkPolicies, Roles,
RoleBindings, Routes (with `routes/custom-host`), ServiceMonitors and its own CRDs (`Claw`,
`ClawDevicePairingRequest`, `ClawOperatorConfig`); `pods` list and `pods/exec` create; ClusterRoles get and
delete. **No Namespace permission: the operator creates no namespace.** A `Claw` lives in a namespace created
beforehand, so the `openclaw` chart creates the per-persona namespaces with `zuno.io/experience-client: "true"`
(WP-179 step 3).

**Already on demo333.** No `claws.claw.sandbox.redhat.com` CRD. The Community Operators catalog offers an
unrelated `openclaw-operator` package (the community operator ADR-0589 rejects); it is not used.

**Install modes.** The CSV supports only `OwnNamespace` and `SingleNamespace` (`AllNamespaces` fails with
`UnsupportedOperatorGroup`). One operator watches one namespace (the manager reads `WATCH_NAMESPACE` from
`olm.targetNamespaces`). Upstream's model is one namespace per user, each with its own operator. For the spike: the
operator in `claw-operator`, OperatorGroup `targetNamespaces: [zuno-claw-scratch]`. Consequence for WP-183, see
step 8. The CSV also carries two more images by tag: `alpine/git:2.47.2` (git-sync) and
`mirror.gcr.io/otel/opentelemetry-collector:0.152.1`, used only by features the spike does not enable.

**Live install (2026-11-02, user's go).** CatalogSource `claw-operator-catalog` (digest above), Subscription
`installPlanApproval: Manual`, InstallPlan approved for `claw-operator.v0.0.227-commit-f5aa592`, CSV Succeeded. The
manager pod runs `quay.io/codeready-toolchain/claw-operator@sha256:4a8363da…` (the pinned digest).

## Steps 2 and 3: custom provider and credential proxy

The spike `Claw` (`zuno-claw-scratch/spike`) declares two `oauth2` credentials (client-credentials, `tokenURL` on the
Keycloak **Route** `https://keycloak.apps.demo333.startx.fr/realms/zuno/protocol/openid-connect/token`), one per
domain: `ai-gateway.zuno-ai-run.svc` (with `defaultHeaders` `X-Zuno-Agent: openclaw`,
`X-Zuno-Data-Classification: C2`) and `mcp-gateway.zuno-ai-run.svc`. A `customProviders` entry `zuno`
(`openai-completions`, `baseUrl: http://ai-gateway.zuno-ai-run.svc:8080/v1`, model `auto`) uses the first.

How it works (source and live config): the operator writes `models.providers.zuno` with a dummy `apiKey`; the
gateway container has `HTTP_PROXY`/`HTTPS_PROXY` set to its proxy and **no** `.svc` in `NO_PROXY` (unless
`network.inClusterBypass`), so a plain-HTTP call to the ai-gateway goes to the proxy, which matches the route by
host, strips any `Authorization`, obtains and caches a client-credentials token (`golang.org/x/oauth2`, refreshed on
expiry), sets `Authorization: Bearer` and the default headers, and forwards over plain HTTP. On failure to obtain a
token the proxy answers 502 `credential injection failed`; it never forwards without one. **No first-party
`claw-token-proxy` is needed.**

Results from the gateway pod:

| Test | Result |
|---|---|
| `GET /v1/models` through the proxy | 200, models filtered for C2 |
| Same, 15 min later (token expired and refreshed through the EgressFirewall) | 200 |
| `GET /v1/models` with `--noproxy '*'` (direct) | no answer: the operator's gateway egress policy allows only the proxy and DNS |
| `POST /v1/chat/completions` through the proxy | 500 after 300 s, see below |

The token reaches the ai-gateway as the client `openclaw-spike`: raw Prometheus (thanos-querier) shows
`zuno_model_calls_total{client="openclaw-spike", agent="openclaw", outcome="error", provider=~"local.*"}` and the
duration and cost series, the first `client` series of an experience client (confirmed independently by the WP-179
session). The 401 path for a token-less request from a labelled namespace was proved by WP-179.

**Chat latency with the GPU nodes down.** The ai-gateway walks the four local provider pairs first; each `*-maas`
times out after about 60 s, so the chain passes 300 s before any external provider. The proxy's
`ResponseHeaderTimeout` is 300 s (`internal/proxy/server.go`), hence a 500. This is an ai-gateway behaviour during a
GPU outage, not an OpenClaw one; it is taken by the WP-179 session as a separate work package. It does not block
WP-183, whose model-path proof is the `client` series above.

## Step 4: egress

The operator writes three policies per instance: `<name>-ingress` (router namespace to the gateway on 18789),
`<name>-egress` (gateway to its proxy and DNS only) and `<name>-proxy-egress` (proxy to TCP 443 **anywhere**, DNS,
and the in-cluster MCP targets: `kubernetes.io/metadata.name: zuno-ai-run` on 8080, derived from `mcpServers`). The
proxy filters at L7: an unknown domain gets 403 (`blocked CONNECT to unknown domain`).

**Gap: hard-coded passthrough domains.** `builtinPassthroughDomains` (`internal/controller/claw_proxy.go`) always
adds `clawhub.ai`, `openrouter.ai`, `github.com`, `codeload.github.com`, `raw.githubusercontent.com` (two paths) and
`registry.npmjs.org`, without injection and without a switch. Live, `https://clawhub.ai` answered 200 through the
proxy. Additive NetworkPolicies cannot take that away, since the operator already allows 443 to anywhere.

**Fix: an OVN `EgressFirewall` per namespace** (the cluster runs OVNKubernetes), owned by the `openclaw` chart:

```yaml
apiVersion: k8s.ovn.org/v1
kind: EgressFirewall
metadata: {name: default}
spec:
  egress:
    - {type: Allow, to: {dnsName: keycloak.apps.demo333.startx.fr}}
    - {type: Deny, to: {cidrSelector: 0.0.0.0/0}}
```

It acts on traffic leaving the cluster only; in-cluster services are unaffected. With it, from the gateway pod:

| Destination | Result |
|---|---|
| `https://clawhub.ai`, `https://registry.npmjs.org`, `https://github.com` (via the proxy) | timeout (proxy logs `dial tcp …:443: i/o timeout`) |
| `https://example.com` (via the proxy) | refused by the proxy (unknown domain) |
| `https://example.com` (direct) | no answer |
| ai-gateway, mcp-gateway, Keycloak token refresh | working |

The namespace label `zuno.io/experience-client: "true"` is set by whoever creates the namespace (the operator creates
none), so by the `openclaw` chart.

## Step 5: lockdown

There is no setting that disables ClawHub. The block is the egress above; the configuration narrows the rest.
Applied through `spec.config.raw` (`mergeMode: merge`):

```yaml
skills: {allowBundled: [], install: {allowUploadedArchives: false}}
plugins: {allow: [memory-core]}
browser: {enabled: false}
tools: {elevated: {enabled: false}}
```

All four reach `openclaw.json`. `gateway.auth.rateLimit` is **dropped** (the operator owns `gateway.auth.*`).
Messaging channels: none configured (the operator writes `channels.*` only from `credentials[].channel`).

| Test (in the gateway pod) | Result |
|---|---|
| `openclaw plugins install clawhub:weather` | `fetch failed … Proxy response (502)` |
| `openclaw skills install weather` | same failure |
| `openclaw plugins list` | 1/69 enabled (`memory-core`) |

`openclaw security audit` after lockdown: critical `gateway.control_ui.device_auth_disabled` (the operator sets
`dangerouslyDisableDeviceAuth` from `spec.auth.disableDevicePairing`, default true) and `fs.config.perms_writable`
(OpenShift's arbitrary UID with group 0); warnings `gateway.auth_no_rate_limit` and `fs.state_dir.perms_group_writable`;
`browser control: disabled`. The rate limit and the device check are compensated by the oauth2-proxy in front
(step 6).

## Step 7: MCP

`mcpServers.zuno` (`streamable-http`, `http://mcp-gateway.zuno-ai-run.svc:8080/mcp`, `credentialRef: zuno-mcp`). The
operator adds the proxy egress rule to `zuno-ai-run:8080` by itself. The mcp-gateway's JSON-only `/mcp` (no SSE)
works with OpenClaw's client: `openclaw mcp probe` lists `zuno: 5 tools`, renamed provider-safe
(`zuno__confluence-page-search`, …).

| `tools/list` through the proxy (identity `openclaw-spike`, consultant-02's groups) | Result |
|---|---|
| no `X-Zuno-Agent` | the front-door read-only set: `confluence.page.search`, `confluence.page.read`, `knowledge.tech.search`, `aap.platform.audit`, `aap.cluster.audit` |
| `X-Zuno-Agent: openclaw` | `[]`: no `openclaw` OKF agent exists yet |

So the MCP credential carries no `X-Zuno-Agent` until the `openclaw` agent is admitted in zuno-demo-agents
(WP-183 step 7). The per-persona filter is proven there.

## Step 6: front door

**No trusted-proxy mode.** `spec.auth.mode` accepts `token` or `password` only, and the operator owns
`gateway.auth.*`: `config.raw` cannot set `gateway.auth.mode: trusted-proxy` (`internal/controller/claw_auth.go`).
Decision (user, 2026-11-02): oauth2-proxy in front, plus OpenClaw's password; ADR-0589 clause 5 is superseded in part
by ADR-0590.

**The operator always applies its own Route** (`<claw>-<namespace>.apps…`, edge, to the gateway on 18789), with no
switch, so a second Route for oauth2-proxy would leave the Control UI reachable around it. Tested fix: the front-door
Route claims the **same host first**. The router admits the oldest Route for a host, so the operator's Route,
re-applied afterwards, stays `Admitted=False, HostAlreadyClaimed` and the `Claw` stays `Ready`. The operator logs
`Route exists but status not populated, requeuing` on each reconcile (a periodic requeue, no error). The host is
unchanged, so `controlUi.allowedOrigins` (set by the operator from its Route host) matches the front door.
In WP-183 the chart creates the front-door Route **before** the `Claw` (lower sync wave).

oauth2-proxy `quay.io/oauth2-proxy/oauth2-proxy:v7.15.5`
(`sha256:8498b0d0ef0a7b29686414000a08aee467f02d0299c9ed1e006a8f33fc017916`, index; amd64
`sha256:0d989b27…`), `--provider=oidc` on the Keycloak Route issuer, PKCE S256, `--authenticated-emails-file` holding
the persona's email only, upstream `http://<claw>.<ns>.svc:18789`. Two extra NetworkPolicies: router to oauth2-proxy
on 4180, and oauth2-proxy to the gateway pod on 18789 (the operator's ingress policy admits the router only).

| Test | Result |
|---|---|
| `GET https://spike-zuno-claw-scratch.apps.demo333.startx.fr/` without a session | 302 to the Keycloak `auth` endpoint, `client_id=openclaw-spike`, PKCE |
| Operator Route after a forced reconcile | `HostAlreadyClaimed`; front-door Route admitted |
| Browser login as consultant-02 through Keycloak SSO (run by the user, 2026-11-02) | the OpenClaw Control UI loads behind oauth2-proxy |
| sale-01 refused | proven by configuration only (the emails file holds consultant-02's email alone); the browser refusal is part of WP-183's acceptance |

The device check stays disabled (`disableDevicePairing` default true), decided by the user: oauth2-proxy and the
password are the two barriers; the residual risk goes into ADR-0590.

## Step 8: decision and values for WP-183

**claw-operator, not the fallback.** It expresses ADR-0589's decisions 2 to 4 natively: a refreshable
client-credentials token injected by its proxy with the `X-Zuno-*` headers, no usable token in the pod, gateway pod
egress limited to its proxy, MCP through the same proxy, and per-instance policies. The two gaps have tested fixes
owned by the `openclaw` chart: the hard-coded passthrough domains (EgressFirewall) and the operator Route (host
claimed first). `openclaw-kube` (`waTeim/openclaw-kube`, last commit 2026-03-13) has neither a proxy, nor
NetworkPolicies, nor a Route; it would mean rewriting what the operator already does.

**Layout (user, 2026-11-02): one namespace and one operator per persona**, the upstream model and ADR-0589's
"one namespace per persona" bound. Each namespace has its own OperatorGroup (`OwnNamespace`) and Subscription on the
same pinned catalog; the spike's operator in `claw-operator` is removed when WP-183 installs.

**Personas:** `consultant-02` (groups `consultant` and five confluence subgroups, `agent_tekos`, `agent_arkos`,
`aap_ops`: five front-door tools) and `sale-01` (`sales`, `agent_comage`, `agent_finage`: no front-door tool, per the
WP-180 test). The same pair as Open WebUI, reused by WP-184.

**Values WP-183 sets**, per persona `<p>` in `{consultant-02, sale-01}`:

| Item | Value |
|---|---|
| Namespace | `zuno-claw-<p>`, labels `zuno.io/experience-client: "true"`, outside the mesh |
| Catalog | `quay.io/codeready-toolchain/claw-operator-catalog@sha256:847abf9c…cd25`, channel `staging` |
| Subscription | `claw-operator`, `installPlanApproval: Manual`, `startingCSV: claw-operator.v0.0.227-commit-f5aa592`; the role approves only the InstallPlan naming that CSV |
| Image check | running manager and proxy image IDs equal the digests of step 1 |
| `Claw` | name `assistant`; `auth.mode: password` (Vault `openclaw/<p>`, key `ui_password`) |
| Credentials | `zuno-ai` (`oauth2`, domain `ai-gateway.zuno-ai-run.svc`, `X-Zuno-Agent: openclaw`, `X-Zuno-Data-Classification: C2`) and `zuno-mcp` (`oauth2`, domain `mcp-gateway.zuno-ai-run.svc`, `X-Zuno-Agent: openclaw` once the agent is admitted); client `openclaw-<p>`, token URL on the Keycloak Route |
| Provider | `customProviders: zuno`, `openai-completions`, `http://ai-gateway.zuno-ai-run.svc:8080/v1`, model `auto` |
| MCP | `zuno`, `streamable-http`, `http://mcp-gateway.zuno-ai-run.svc:8080/mcp`, `credentialRef: zuno-mcp` |
| Lockdown | the `config.raw` of step 5 |
| Egress | `EgressFirewall` of step 4 |
| Front door | oauth2-proxy v7.15.5 by digest, emails file = the persona's email, Route on the operator's host created first, the two NetworkPolicies of step 6; Keycloak needs `standardFlowEnabled` and the redirect `https://assistant-zuno-claw-<p>.apps.demo333.startx.fr/oauth2/callback` on `openclaw-<p>` |
| Keycloak | client `openclaw-<p>` (confidential, service account and browser flow, groups mapper), its service-account user in the persona's groups; WP-179's four-place recipe |
| Vault | `keycloak/openclaw-<p>` (client secret), `openclaw/<p>` (`ui_password`, `cookie_secret`) |

**Limits recorded for ADR-0590:** no signature on any claw-operator or OpenClaw image (pinned by digest, ADR-0586
decision 7 posture for third parties; the bundle references its images by tag, hence the image-ID check); the
operator is alpha, built per commit, with no releases; the proxy allows TCP 443 anywhere and relies on the
EgressFirewall; device auth disabled; no auth rate limit in OpenClaw; chats are slow or fail while the GPU nodes are
down (ai-gateway fallback walk).

## Cleanup (2026-11-02, user's go)

Deleted: the `Claw` `spike` (the operator removed its Deployments, Services, Route, policies and proxy CA), the
namespace `zuno-claw-scratch` (EgressFirewall, oauth2-proxy, Secrets), the live-only Keycloak client `openclaw-spike`
with its service-account user, and the spike's operator install in `claw-operator` (Subscription, CSV, namespace),
redundant with the one-operator-per-persona layout. Kept for WP-183: the three `claw.sandbox.redhat.com` CRDs and the
CatalogSource `openshift-marketplace/claw-operator-catalog` pinned at `sha256:847abf9c…`, both of which the `openclaw`
chart will own.

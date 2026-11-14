# WP-214: Redis internal/external mode

- **State:** Done (2026-11-11)
- **ADRs:** [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md), [ADR-0609](../../adr/0609-rehearse-on-canary-namespaces-of-demo333.md) (where the rehearsal runs)
- **Depends on:** WP-143
- **Related:** [WP-143](wp-143-mariadb-internal-external-pilot.md) (the pilot, whose pattern this follows), [WP-211](wp-211-keycloak-internal-external-mode.md) (the seam mechanism and the Vault way-back lesson), [WP-177](wp-177-finish-the-maas-quota-delegation.md) (the quota ledger in Redis), [ADR-0557](../../adr/0557-manage-the-cluster-from-a-remote-argocd-natively-or-via-rhacm.md)
- **Target:** v0.17
- **Files touched:** the redis role (`tasks/{install,install_internal,install_external,external_assert,precheck,uninstall}.yml`, README), `ansible/tasks/{resolve_redis_endpoint,redis_seam_values,apply_gitops_app}.yml`, `ansible/confidential.example.yml`, `gitops/charts/namespaces` (values, EgressFirewall template, README), a comment in `gitops/charts/ai-gateway/values.yaml`

> Why: ADR-0352 clause 9 lands the internal/external mode contract one component per work package. MariaDB (WP-143),
> External Secrets (WP-216), cert-manager (WP-217) and Keycloak (WP-211) are done. Redis is one of the two Day-1
> components that may be external (clause 3, Tier A-endpoint Day 1). UnifAI's own Redis stays inside UnifAI's namespace
> and is owned by unifai-operator (ADR-0572 clause 4), so it is out of scope, like Dify's bundled `dify-redis` and AAP's.

## Goal

`zuno_redis_mode: internal | external` works end to end: internal mode renders and behaves bit for bit as today,
external mode runs the consumer unchanged against a Redis the platform does not own, and the switch is proven live
against a Redis simulated in a canary namespace, there and back.

## The contract for Redis (ADR-0352)

- **Payload (clause 2), in `ansible/confidential.yml`:** `zuno_redis_mode`, `zuno_redis_external_host`, `_port`
  (`"6379"`), `_password` (the sentinel or `""` = no AUTH, as the ADR's schema says) and `_ca_bundle` (`""` =
  plaintext). Optional: `zuno_redis_external_min_clients` (default 100).
- **Install (clause 4):** skip both `zuno-redis` Applications; validate the payload before any write; seed the password
  into Vault `zuno/redis/session-store`; assert the endpoint with an in-cluster client Job (hard fail).
- **Check:** the same assertion, record only. Never Application or StatefulSet state in external mode.
- **Uninstall:** strict no-op against the external instance.
- **Clause 7:** reachable; AUTH succeeds when a password is supplied; the connection budget (`maxclients`) is at least
  the floor when the server lets us read it.
- **Clause 10:** Redis is a Day-1 component, not one of the seven vital Day-0 components, so it is not in the Day-1
  vital gate. Its precheck is its functional assertion in `make d1 check`, in both modes.
- **Clause 11:** no consumer reads `zuno_redis_mode`; ai-gateway receives an address (Helm value) and a Secret (Vault).

## Consumer inventory (2026-11-11, origin/devel b6cbec9d)

Searched with `grep -rn -i "zuno-redis|redis/session-store|redis-master|REDIS_ADDR|REDIS_URL|REDIS_HOST"` over
`gitops/`, `ansible/` and `platform/` (vendored chart excluded). The consumers of clauses 5 and 7 (agent-runtime, the
agent frontends' session stores, tekos, the aiagent-operator) are retired (WP-156, ADR-0561): nothing references them.

| Consumer | Where | Today | External mode |
|---|---|---|---|
| ai-gateway `REDIS_ADDR` | `gitops/charts/ai-gateway/values.yaml` `semanticCache.redis.addr`, `templates/deployment.yaml` | `zuno-redis-master.zuno-auth.svc.cluster.local:6379`, one env var read by three modules: the semantic cache (off by default), the quota ledger (`quotaLedger.store: redis`, set on demo333) and the routing-decision side-channel (always written when the address is set, 120 s TTL) | `redis_seam_values.yml` sets the value |
| ai-gateway `REDIS_PASSWORD` | `templates/externalsecret-redis.yaml` (`ai-gateway-redis-credentials`, zuno-ai-run) | Vault `redis/session-store`, `optional: true` | the redis role overwrites the Vault value |
| zuno-ai-run EgressFirewall | `gitops/charts/namespaces` (WP-224) | no Redis rule (the built-in is in-cluster) | new `redisExternal` value and `egressFirewall.redis` flag: an Allow rule for the endpoint, none for a `*.svc` name |
| zuno-auth PeerAuthentication exception `redis-metrics-from-monitoring` | `gitops/charts/namespaces/values.yaml` | port 9121 of the built-in exporter | unchanged in both modes; its selector matches no pod, so it is inert, not wrong (clause 6) |
| the redis chart's NetworkPolicy, ExternalSecret, exporter and ServiceMonitor | `gitops/charts/redis` | built-in only | not applied; the `redis_*` series of the Grafana and Perses data dashboards lose their source |
| Vault grants | `platform/vault/secret-access.yaml` (zuno-ai-run, zuno-auth) | `redis/session-store` | unchanged; zuno-auth's grant is unused |

TLS: the ai-gateway code has no Redis TLS option. `components/ai-gateway/app/{semantic_cache,quota,routing_decisions}.py`
build `redis.Redis(host=..., port=..., password=...)`, plain TCP, and the chart has no TLS value. No code was changed
(it needs an image rebuild): see Limits.

## Design

**Mode dispatch, the WP-143 shape.** `install.yml` loads `confidential.yml`, then includes `install_internal.yml`
(today's two applies, byte for byte) or `install_external.yml`. `precheck.yml` and `uninstall.yml` gate on the same key.

**External install, in order:** sentinel host, port and CA shape checked; a CA bundle refused (the consumer cannot
use TLS, so the install does not claim a working external mode); `vault kv put zuno/redis/session-store password=...`
as `ansible-seeder` (an empty value for no AUTH; a new KV version, the internal one stays in the history);
`external_assert.yml` with a hard fail. Who seeds: the vault role still seeds the internal value create-if-missing
(ADR-0345), so it never overwrites the external one; the redis role owns the external seed, like the mariadb role.

**The assertion** (`external_assert.yml`): a `redis-external-assert` Job in `zuno-auth`, image
`registry.redhat.io/rhel9/redis-7` (override `zuno_redis_client_image`), credentials through a short-lived Secret and
`REDISCLI_AUTH`, never the pod spec or the log. PING must answer PONG (with `--tls --cacert --sni` when a CA is given);
`CONFIG GET maxclients` must be at least the floor when readable (a managed tier that refuses `CONFIG` is recorded,
not failed). The Job output is read back into the run's message. Why `zuno-auth`, not the consumer's zuno-ai-run: every
Job in zuno-ai-run is enrolled into Kueue and would queue behind model pulls. The consumer's own path is opened by the
EgressFirewall seam and proven by the rehearsal.

**One resolution, one seam.** `ansible/tasks/resolve_redis_endpoint.yml` sets `redis_endpoint_{host,port,addr,tls,
ca_bundle}`; internal values are today's literal. `ansible/tasks/redis_seam_values.yml`, included by
`apply_gitops_app.yml` for d1 Applications in external mode only (the WP-211 `keycloak_seam_values.yml` mechanism),
merges `semanticCache.redis.addr` into ai-gateway's values and `redisExternal` into the namespaces chart's. It refuses
to render the sentinel host. Internal mode never includes it, so the Application values are unchanged.

**Egress (clause 6).** Egress policies now exist (WP-224), so the external endpoint is an allowlist input: the
zuno-ai-run EgressFirewall gets `dnsName: <host>` (or `cidrSelector: <ip>/32`) on the port. A `*.svc` name gets no rule:
in-cluster traffic is not filtered, and OVN cannot resolve cluster names.

## Steps

1. Mode key and payload in `confidential.example.yml`. Done.
2. Symmetric verb gating in the redis role, the assertion Job. Done.
3. Seams: the resolver, the seam task, the namespaces EgressFirewall rule. Done.
4. Rehearse the there-and-back on demo333 in `zuno-canary-wp-214` (below). Needs the owner's go.
5. `make d1 check` green at the internal end state; WP-214 Done; ADR-0352 clause-9 note.

## Live rehearsal (demo333, canary namespace, ADR-0609)

**Data: no copy (preferred).** What the built-in Redis holds is disposable by design: quota-ledger counters
(`zuno:quota:*`, fixed windows, each key expires after two windows; the gateway reads the larger of its local and the
Redis value), routing decisions (`zuno:ai-gateway:routing-decision:*`, 120 s) and no semantic-cache entries (the cache is
off). The cost of not copying: after each flip the current quota windows restart from zero once (ai-gateway restarts,
so its local counters reset too). Option B, if a flip must not refill budgets: copy the `zuno:quota:*` keys with
`redis-cli --scan` then `DUMP`/`RESTORE ... REPLACE` (TTL kept with `PTTL`) right before restarting ai-gateway. Option A
is the default: the data is a cache and counters, and a copy adds a step that can fail for no lasting benefit.

1. Owner's go, outside any freeze. Canary:
   `ansible-playbook -i ansible/inventories/demo/hosts.yml ansible/playbooks/canary_namespace.yml -e canary_wp=WP-214`.
2. Simulated external Redis from one-shot manifests kept out of the repo charts: a Deployment of
   `quay.io/fedora/redis-7` (arbitrary UID, already pinned for UnifAI in `ansible/clusters/demo333.yml`) with
   `--requirepass` from a Secret, a Service `zuno-redis-ext:6379`, and a NetworkPolicy admitting 6379 from zuno-ai-run
   (`app.kubernetes.io/name=ai-gateway`) and zuno-auth (`job-name=redis-external-assert`); the canary policy admits only
   its own namespace.
3. Baseline: `zuno:quota:*` key count in the built-in, no `quota ledger redis ... failed` line in the ai-gateway log.
4. ✋ Out: `make d1 uninstall redis` (the PVC is kept by the StatefulSet), then in `confidential.yml`:
   `zuno_redis_mode: external`, host `zuno-redis-ext.zuno-canary-wp-214.svc.cluster.local`, the simulated password,
   `zuno_redis_external_ca_bundle: ""`. `make d1 install redis` (asserts, seeds), `make d1 check redis` (installed).
   Force-sync the ExternalSecret `ai-gateway-redis-credentials` (zuno-ai-run), then `make d2 install namespaces` (no
   rule expected for a `.svc` name) and `make d2 install llm` (the new REDIS_ADDR rolls ai-gateway; the new pod reads
   the new password).
5. Proofs: the ai-gateway pod's `REDIS_ADDR` is the canary; a few gateway calls (golden path) put `zuno:quota:*` and
   routing-decision keys into the canary Redis; no ledger fault in the log; `make d1 uninstall redis` in external mode
   leaves the canary Redis untouched and `make d1 check redis` still reports it installed; a wrong password fails the
   install with the Job's NOAUTH/WRONGPASS line; `make d1 check` green.
6. ✋ Back: `zuno_redis_mode: internal`; restore the internal password (`vault kv rollback -version=<n>
   zuno/redis/session-store`, the version before the external put: the vault role seeds create-if-missing, so the
   path otherwise keeps the external value, the WP-211 lesson); `make d1 install redis`; force-sync both ExternalSecrets
   (`zuno-redis-auth` in zuno-auth, `ai-gateway-redis-credentials`); `make d2 install namespaces` and
   `make d2 install llm` (both Applications lose the seam values: `helm.values` is one string, replaced whole);
   restart ai-gateway. Same proofs against the built-in, then `make d1 check` green and the golden path.
7. Teardown: the canary playbook with `-e canary_state=absent`.

Expected impact: no outage. Redis is best effort for all three uses; between the uninstall and the ai-gateway roll the
gateway logs ledger faults and keeps local counters.

Not rehearsed by this canary: the EgressFirewall rule for a host outside the cluster (a canary Service is in-cluster
and gets no rule), proven by render only; a TLS endpoint (refused, see Limits); a no-AUTH endpoint (an empty password
in Vault, then in the ExternalSecret).

## Limits

- **TLS.** ai-gateway opens plain TCP to Redis. Lifting it: a `REDIS_TLS`/CA value in the chart, `ssl=True` and
  `ssl_ca_certs` in the three client constructors, an image rebuild, then remove the refusal in `install_external.yml`.
  The assertion already speaks TLS (tested locally against a TLS Redis with the right CA, a wrong CA, and a plaintext
  client).
- **No AUTH needs protected mode off.** A Redis 7 without a password and with protected mode on answers `DENIED` to
  any non-loopback client (measured locally); the assertion reports it.
- **Redis ACL users** other than `default` are not supported: ai-gateway sends a password only.
- **AAP checkouts** do not carry `confidential.yml`: run the redis role and the consumer roles locally while the mode
  is external (WP-143 finding c).
- **Connection budget.** ai-gateway builds a new async client per semantic-cache and routing-decision call, so the
  connection count follows concurrency; the floor of 100 is a sanity bound, not a sizing.

## Live rehearsal result (2026-11-11)

Run on demo333 with the user's go ([evidence](../evidence/wp-214-redis-there-and-back-2026-11-11.md)). The external
mode asserted the canary Redis and seeded Vault; ai-gateway ran on it through the seam (golden path 13/13, keys written
there, no ledger error). The way back restored the built-in password from the Vault history and the consumers' values
(golden path 13/13, the built-in's 40 quota keys kept). `make d1 check` at the internal end state: 22 of 23 installed,
with `openshift-ai` not installed for the RHOAI 3.6 EA reasons that predate this WP.

Two role defects found and fixed during the rehearsal:
- the endpoint is now asserted BEFORE the external password is written to Vault, so a wrong password never reaches
  ai-gateway;
- the assertion Job deletes cascade to their pods, and its log is read from the current run's pod.

Named exceptions, by the user's choice of variant (the session's safety check refused `make d1 uninstall redis`):
- the built-in Redis kept running during the window, so a platform without the built-in was not exercised;
- the external-mode uninstall was not run live (read in the code: it removes only the assertion Job and Secret);
- the EgressFirewall rule for a host outside the cluster is proven by render only;
- TLS is refused by design (Limits).

## Verification (repository part, 2026-11-11)

- Render proof, internal mode: the Applications `zuno-{ai-gateway,llm,namespaces,redis}-d{0,1}` rendered by the real
  `apply_gitops_app.yml` (cut before the cluster apply) and the real role tasks, demo333 cluster values, before and
  after: byte-identical. `helm template` of ai-gateway and of namespaces (d0 and d1 values) before and after:
  byte-identical (the redis chart is not touched).
- External fixtures (DNS host, `.svc` host, IPv4): only `zuno-ai-gateway-d1` (`semanticCache.redis.addr`) and
  `zuno-namespaces-d1` (`redisExternal`) change; the EgressFirewall gains `dnsName` or `cidrSelector .../32` on the
  port, nothing for `.svc`; `platform/security/check_mesh_mtls.py` passes.
- Resolver fixtures in both modes, the idempotence guard, and the negative paths (sentinel host, bad port, CA without
  PEM, CA refused, the seam refusing the sentinel), all failing before any cluster call.
- The assertion script against local Redis 7 containers: right, wrong and missing password, `maxclients` under the
  floor, no-AUTH server, unreachable port, TLS with the right and a wrong CA.

## Acceptance

- Internal mode renders and behaves exactly as before (no diff on a nominal cluster). Met in the repository.
- External mode runs ai-gateway unchanged against the canary Redis (keys written there, no ledger fault), the way back
  restores the built-in with the internal password, and `make d1 check` is green in both modes. Live part, open.

## Status updates (then re-run check_docs.py)

- **2026-11-11 - Repo work in review.** Repository part built (local commit, not pushed). Left: review and push (Repo work
  merged), the live rehearsal above (Operator pending), then
  Done and the ADR-0352 clause-9 note.

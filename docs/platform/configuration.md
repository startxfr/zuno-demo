# Platform Configuration

The `Makefile` is the source of truth for what each day installs and in what
order (ADR-0323); `platform/docs/check_docs.py` validates this page's commands
against it. The lists below are the component *names* the verbs accept — the
real execution order lives in `ansible/playbooks/day{0,1,2,3}_*.yml`, which
differs in places (Day 0 runs `argocd` first and also installs `image-mirrors`,
which is not an addressable component).

**Day 0** — cluster prerequisites (ADR-0056/ADR-0421): `admin-context`,
`argocd`, `namespaces`, `openshift-rbac-groups`, `vault`, `cert-manager`,
`external-secrets`, `machines`, `postgresql`, `keycloak`, `aap`, `aap-config`.
Verbs: `check`, `install`, `uninstall`, `reconcile`, `all`, `reinstall`.

**Day 1** — the AI-platform-operator stack (ADR-0060/ADR-0421): `smtp`, `nfd`,
`nvidia-gpu`, `custom-metrics-autoscaler`, `redis`, `observability`,
`service-mesh`, `mesh-monitoring`, `kiali`, `grafana`, `mariadb`, `tempo`,
`openshift-oauth`, `connectivity-link`, `lws`, `jobset`, `kueue`,
`openshift-ai`, `lightspeed`, `rhtas`, `aiagent-operator`. Buildable:
`ai-gateway`, `supply-chain-signer`, `aiagent-operator`,
`aap-execution-environment`. Verbs: `check`, `install`, `build`, `uninstall`,
`reconcile`, `all`, `reinstall`.

**Day 2** — AI infrastructure and content ingestion (ADR-0060): `namespaces`,
`llm`, `models`, `rag`, `rag-ingestion`, `mcp`, `agents`, `mlops`,
`trustyai-config`, `mlflow`, `lightspeed-config`, `supply-chain`
(check-only — it has no install path). Buildable: `mcp`, `rag`,
`rag-ingestion`, `agent`, `mlops`, `trustyai-eval`. Verbs: `check`, `install`,
`build`, `uninstall`, `all`, `reinstall` — **no `reconcile`**.

**Day 3** — operations (ADR-0057/ADR-0058): `test` and `sign` take `agents`
(`test` also `platform`), `backup`/`restore` take `postgresql`, and
`lightspeed`, `lightspeed-config`, `trustyai-config`, `mlflow` are check-only.
Verbs: `test`, `stresstest`, `backup`, `restore`, `check`, `sign`,
`scenario-failover-node`.

`make dN <verb> [component]` applies one or all components in controlled order;
`uninstall` walks each list in reverse. `make help` prints the current lists and
the full verb table, and `make dN` with no verb prints that day's usage.

A component's day is not guessable from its name — `openshift-ai`,
`service-mesh` and `openshift-oauth` are Day 1 while `cert-manager`,
`postgresql` and `keycloak` are Day 0 — and the wrong day is rejected outright
with `Unsupported dayN component`. `check_docs.py` validates every `make`
command printed by a `debug` or `fail` task for exactly this reason (ADR-0344).

See `ansible/README.md` for the per-role contract and
[prerequisites.md](prerequisites.md) for what must be true before Day 0.

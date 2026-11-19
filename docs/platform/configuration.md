# Platform Configuration

Last reviewed: 2026-11-19

The `Makefile` is the source of truth for what each day installs and in what
order (ADR-0323); `platform/docs/check_docs.py` validates this page's commands
against it. The lists below are the component *names* the verbs accept — the
real execution order lives in `ansible/playbooks/day{0,1,2,3}_*.yml`, which
differs in places (Day 0 runs `argocd` first and also installs `image-mirrors`,
which is not an addressable component).

**Day 0**: cluster prerequisites (ADR-0056/ADR-0421): `admin-context`, `argocd`, `namespaces`, `openshift-rbac-groups`, `vault`,
`external-secrets`, `cert-manager`, `machines`, `postgresql`, `keycloak`, `aap`, `aap-config`, `world-model-gpu`.
Verbs: `check`, `install`, `uninstall`, `reconcile`, `all`, `reinstall`.

**Day 1**: the AI-platform-operator stack (ADR-0060/ADR-0421): `smtp`, `nfd`, `nvidia-gpu`, `custom-metrics-autoscaler`, `nfs-provisioner`,
`redis`, `observability`, `service-mesh`, `mesh-monitoring`, `kiali`, `grafana`, `perses`, `mariadb`, `tempo`, `openshift-oauth`,
`connectivity-link`, `lws`, `jobset`, `kueue`, `openshift-ai`, `lightspeed`, `rhtas`, `rhtas-config`, `openshift-pipelines`. Buildable:
`ai-gateway`, `supply-chain-signer`, `aap-execution-environment`. Verbs: `check`, `install`, `build`, `uninstall`, `reconcile`, `all`,
`reinstall`.

**Day 2**: AI infrastructure, agents and experiences (ADR-0060; the RAG and its ingestion are UnifAI's since ADR-0568): `namespaces`, `llm`,
`models`, `quay-registry`, `mcp`, `agents`, `mlops`, `trustyai-config`, `mlflow`, `lightspeed-config`, `unifai`, `open-webui`, `openclaw`,
`dify`, `kagent`, `world-model`, `praxis`, and `supply-chain` (check-only, it has no install path). Buildable: `mcp`, `mlops`,
`trustyai-eval`, `token-proxy`, `dify-knowledge`, `world-model`, `praxis`. Verbs: `check`, `install`, `build`, `uninstall`, `all`,
`reinstall`, and `reconcile` for `models` only.

**Day 3**: operations (ADR-0057/ADR-0058, ADR-0624): `test` takes `agents` and `platform`; `backup` and `restore` take `postgresql`, `unifai`
and `quay-registry`; `check` also takes the check-only components `lightspeed`, `lightspeed-config`, `trustyai-config`, `mlflow`, `operators`,
`drift` and `recovery`; `admit` takes `agents`; `run` takes `mlops`; `release` takes `supply-chain`. Verbs: `test`, `stresstest`,
`stresstest-collect`, `backup`, `restore`, `check`, `admit`, `run`, `release`, `scenario-failover-node`
([stresstest runbook](stresstest.md)).

These lists were copied from the Makefile on 2026-11-19 (`DAY0_COMPONENTS` to `DAY3_*`); `make help` prints the current ones and is the
reference when they differ.

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

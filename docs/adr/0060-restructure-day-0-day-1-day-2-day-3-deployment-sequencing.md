# ADR-0060: Restructure deployment into Day 0 / Day 1 / Day 2 / Day 3 sequencing

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-22
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0056 established the Day 0 (cluster prerequisites) / Day 1 (build +
run the platform) split. In practice Day 1 grew to cover two genuinely
different concerns at once: the AI-platform-operator stack (service
mesh, Keycloak, databases, Kueue, OpenShift AI, etc. - infrastructure an
operator installs once and rarely touches again) and content-ingestion
components (RAG, MCP servers, agents, MLOps - things an operator
iterates on far more often while developing/demoing). Separately, "Day
2" already meant something unrelated - the agent test/stresstest
operations ADR-0057/ADR-0058 introduced - which collided with the
natural next tier number once content-ingestion needed its own stage.

## Decision

Split the sequencing into four stages:

- **Day 0** - unchanged in kind, narrower in scope: bare cluster
  prerequisites only (`admin-context`, `argocd`, `namespaces`,
  `openshift-rbac-groups`, `vault`, `cert-manager`, `external-secrets`,
  `openshift-oauth`, `smtp`, `machines`, `nfd`, `nvidia-gpu`,
  `custom-metrics-autoscaler`).
- **Day 1** - the AI-platform-operator stack: `redis`, `observability`,
  `service-mesh`, `mesh-monitoring`, `kiali`, `grafana`, `postgresql`,
  `mariadb`, `tempo`, `keycloak`, `connectivity-link`, `lws`, `jobset`,
  `kueue`, `openshift-ai` (all moved out of Day 0), plus
  `aiagent-operator`, which runs last - standard operator-before-CR
  ordering, since Day 2's `agents` component creates the `AIAgent` CRs it
  reconciles. Only `ai-gateway` builds here.
- **Day 2** (new) - namespace policy overlay, AI infrastructure, and
  content ingestion: `namespaces`' quota/NetworkPolicy overlay (moved
  from Day 1, runs first for the same "in place before other components"
  reasoning as before, just one tier later), `llm`, `models` (moved from
  Day 1, since `agents`/`rag` in this same tier need models available),
  and `sql-schema`, `rag`, `rag-ingestion`, `mcp`, `agents`, `mlops`
  (moved from Day 1). `mcp`, `rag`, `rag-ingestion`, `agent`, `mlops`
  build here.
- **Day 3** (renamed from the old "Day 2") - agent test/stresstest
  operations (ADR-0057/ADR-0058), decision content unchanged, only the
  day-tier number moved to free up "Day 2" for the new install tier
  above.

`make` keeps its `make dayN|dN <verb> [component]` dispatch shape,
extended to four tiers instead of two: `day0`/`d0` (unchanged),
`day1`/`d1` (narrowed), `day2`/`d2` (new, mirrors Day 1's
check/build/install/uninstall/all/reinstall verb set exactly), `day3`/`d3`
(renamed from the old `day2`/`d2`, same `test`/`stresstest` verbs).

Internal naming stays put where renaming would cascade further than the
entry points warrant: `namespaces`' Day-2-half tasks/Application still
say `install_d1`/`precheck_d1`/`uninstall_d1`/`zuno-namespaces-d1`
(implementation detail, not the macro tier it's invoked from);
`platform/testing/day2_*.py` (the Day 3 stresstest driver scripts) keep
their `day2_` prefix for the same reason.

## Alternatives considered

- Insert the new content-ingestion tier as "Day 1.5" or split Day 1 into
  1a/1b instead of renumbering the test-ops tier. Rejected: a real
  numbered Day 3 reads cleaner in `make help` and documentation than a
  fractional tier, and the test-ops tier's own decision content
  (ADR-0057/0058) is unaffected by the renumber - it's a pure rename.
- Rename `namespaces`' Day-2-half internal task files
  (`install_d1.yml`→`install_d2.yml`) and Application
  (`zuno-namespaces-d1`→`zuno-namespaces-d2`) to match the new tier.
  Rejected: no other file depends on that specific name (confirmed via
  `grep -rn "zuno-namespaces-d1\|namespaces-d1"`), and the day2-test→
  day3-rename already established the "entry points only, internal names
  stay" convention for exactly this kind of situation - renaming here too
  is a second unforced cascade for no functional benefit.
- Keep `aiagent-operator` in the new Day 2 alongside `agents`. Rejected:
  the operator must already be running before any `AIAgent` CR it
  reconciles is created - keeping it a tier ahead (Day 1) preserves that
  ordering for free; moving it to Day 2 would require an in-tier ordering
  guarantee Day 2's flat component list doesn't otherwise need.

## Consequences

Operators get a cleaner three-way split of "cluster prerequisites" /
"platform-operator stack" / "AI infrastructure and content" instead of
one large Day 1 covering two different iteration cadences. The
test/stresstest tier's number changes (Day 2 → Day 3) - a breaking
change to any muscle memory or script invoking `make day2|d2
test|stresstest` directly; `docs/adr/0057-*.md`/`0058-*.md` and
`docs/roadmap/work-packages/wp-062-*.md`/`wp-063-*.md` are left
unedited per this repo's "ADRs/closed WPs are immutable historical
records" convention, so those documents still narrate the old "Day 2"
framing for the period they actually describe.

## Security considerations

`namespaces`' ResourceQuota/default-deny-NetworkPolicy overlay now lands
one tier later than before (Day 2 instead of Day 1). Kubernetes
NetworkPolicies are additive and evaluated per-request, not by install
order - each of Day 1's 15 platform-operator components carries its own
allow-rules in its own chart regardless of when the namespace-wide
default-deny baseline lands, so this doesn't change the platform's final
network posture, only widens (by one tier) the window during which the
namespace has no default-deny policy at all while Day 1 installs.
ResourceQuota enforcement is deferred the same way - components can use
more resources during Day 1 than they could once the quota lands, not a
new kind of gap, just a longer instance of the same one Day 0-only state
already had before Day 1 ran.

## Operational considerations

`make day2|d2 install` (no component) must build content-ingestion
images first, matching Day 1's existing "install with no component
builds first" behavior. `make day2|d2 check agents` must still run the
real ADR-0053 acceptance/security gate (`tasks_from: check`, not
`precheck`), carried over unchanged from where this special-case lived
in the old `day1_check.yml`.

## Implementation state

**Implemented (2026-08-22).** Landed across two commits: the Day 0
shrink, Day 1 reshape (to its interim, since-revised scope), and the
Day 2 test-ops → Day 3 rename (role directory, playbook filenames, the
internal hardcoded kustomize path in
`ansible/roles/day3/tasks/stresstest_job.yml`); then this decision's own
scope - moving `namespaces`/`llm`/`models` out of Day 1 into the new Day
2, creating the four `day2_{install,check,build,uninstall}.yml`
playbooks, and rewriting the Makefile end to end for all four tiers
(component/verb lists, `DAY2_RECIPE` modeled structurally on `DAY1_RECIPE`,
`DAY3_RECIPE` retargeted at the renamed `day3_{test,stresstest}.yml`,
`.PHONY`, help text, footer summaries).

- **Verified**: `ansible-playbook --syntax-check` on every touched/created
  playbook; `make help` renders all four tiers correctly; Make-level
  validation paths exercised without a cluster (`make d1 install
  bogus-component`, `make d2 install bogus-component`, `make d3 test
  bogus-component` each fail with the expected diagnostic listing the
  new component/verb sets); `python3 platform/docs/check_docs.py`
  passes (three stale `README.md` examples using components that moved
  tiers were caught and fixed by this check).
- **Not executed**: no live OpenShift cluster exists in this
  environment, so the actual Day 1 → Day 2 → Day 3 sequence, the
  `namespaces` Day-2-half overlay timing, and the new `day2_*.yml`
  playbooks' real Ansible execution were not exercised against a real
  cluster.

See [Standard clauses](README.md#standard-clauses) for Acceptance criteria.

## Related ADRs

- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) -
  extended, not superseded: the Day 0/Day 1 split concept is preserved,
  only component boundaries move and Day 2/Day 3 tiers are added.
- [ADR-0057](0057-introduce-day-2-agent-availability-test-and-stresstest-operations.md) -
  decision content unchanged, now runs under Day 3.
- [ADR-0058](0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md) -
  decision content unchanged, now runs under Day 3.

## Review evidence

This decision follows directly from operator direction (this session):
separate the AI-platform-operator stack from content-ingestion within
what was previously one large Day 1, and free up a "Day 2" number for
that new tier by renumbering the existing test/stresstest tier to Day 3.

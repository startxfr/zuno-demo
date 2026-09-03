# WP-090: Salesforce link, quota and telemetry on the Zuno project id (promotes ADR-0528)

- **State:** Done (2026-08-30) - the telemetry criterion is confirmed live and the `tool-policy.yaml` decision is recorded (no change); `zuno.project_id`'s presence is now regression-tested in all three services (ai-gateway, agent-runtime, agent-bff - see the 2026-08-30 note below); the live Salesforce pass is carved out to [WP-101](wp-101-salesforce-sandbox-credentials.md) (v0.7) rather than gating this WP's closure, since it depends on a sandbox credential this repo cannot provision.

> Sequencing note (2026-08-27): step 2 landed early, inside WP-088 Part A.
> Removing `_bind_project_if_required` was not separable - `agent_chat`
> cannot compile against a binding step that no longer matches the
> server-resolved project - so `_require_customer_project` shipped with the
> backend it depends on. Steps 1 and 3-6 landed here as briefed.

> Amendment (2026-08-30): closing ADR-0528/WP-090 was blocked only on "the
> live Salesforce pass" - itself blocked on the WP-22/WP-33 sandbox
> credential gap, which has no repo-side fix and no owning WP. Carrying
> both indefinitely at `Repo work merged` misrepresented the roadmap the
> same way ADR-0218 found Aramis/Salesforce ingestion doing in a
> different corner of the tree. [WP-101](wp-101-salesforce-sandbox-credentials.md)
> now owns the credential provisioning and the confirming live pass,
> targeted v0.7; this WP and ADR-0528 close on the acceptance criteria the
> repository can independently verify (all four Decision clauses,
> fixture-tested cause taxonomy, live-verified telemetry, recorded policy
> decision). Also added while closing: a regression test for
> `zuno.project_id`'s presence in ai-gateway (`tests/test_telemetry.py`)
> and agent-bff (`internal/telemetry/telemetry_test.go`), plus the
> equivalent in agent-runtime (`tests/test_telemetry.py`) - none existed
> before, so a refactor could have silently dropped the attribute with CI
> staying green (see this WP's own "Still missing" note below, now closed).
- **ADRs:** ADR-0528 (Proposed -> Repo work merged -> Implemented 2026-08-30; the live Salesforce sandbox pass is tracked separately by WP-101, not a precondition for `Implemented`)
- **Depends on:** WP-088 (needs `projects.salesforce_*` and the server-resolved `project_id` on graph state)
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root.
>
> Tracked in [docs/roadmap/implementation-roadmap.md](../implementation-roadmap.md) Phase 21.

## Goal

Move Salesforce verification from conversation start to project create/update,
make `project_required` mean "a customer project", emit `X-Zuno-Project-Id` for
every project rather than only for marked tasks, and add the `zuno.project_id`
span attribute that exists nowhere today - without the Salesforce identifier
ever leaving the database.

## ADR references

Primary: [docs/adr/0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md](../../adr/0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md).

Read also: [ADR-0512](../../adr/0512-introduce-project-bound-tasks-with-salesforce-verified-context.md)
(clauses 1, 2 and most of 4 still stand - only clause 3 and the keying move),
[ADR-0511](../../adr/0511-define-okf-quota-policy-enforced-via-kuadrant.md)
(the precedence this WP feeds a wider population into),
[ADR-0029](../../adr/0029-instrument-model-usage-costs-and-distributed-traces.md)
(why `zuno.project_id` is a span attribute and never a metric label).

## Preconditions (verify before starting)

- WP-088 merged and its tests green.
- Read `components/agent-runtime/app/project_binding.py` in full (it is retained
  unchanged - only its caller moves), `app/main.py`'s `_bind_project_if_required`,
  `app/clients/model_router.py`'s header block and its comment explaining the
  abuse channel, the eight `project_id=` call sites in `app/graph/nodes.py` plus
  the equivalent in `arkos_nodes.py`, `components/ai-gateway/app/{main.py,quota.py,telemetry.py}`,
  `components/agent-bff/internal/telemetry/telemetry.go`, and
  `policies/quotas/quota-policy.yaml`'s header and `project_binding` block.

## Repo changes (step by step)

1. **Verification at project save.** Call `project_binding.verify_project_binding()`
   from the `POST`/`PUT /v1/projects` handlers under the editing admin's own
   identity, stamping `projects.salesforce_verified_at` on success. Keep the
   three causes distinguishable (404 unknown / 403 no access / 503 unreachable);
   a failure rejects the save rather than storing an unverified link. Re-verify
   on read past `project_binding.validity_window`.
2. **`project_required` means customer.** Replace `_bind_project_if_required`
   with a check against the conversation's own project: 400 with no project,
   403 in a free project, one re-verification when the stamp has aged out. No
   Salesforce call remains on the ordinary chat path.
3. **Quota header.** In `model_router.py`, drop nothing from the code - only
   rewrite the comment to state the new guarantee (the id is server-resolved
   after a membership check, never client-asserted). In `nodes.py` and
   `arkos_nodes.py`, change every `project_id=state.get("project_id") if
   task.project_required else None` to `project_id=state.get("project_id")`, and
   replace the local comment with a pointer to the single guarantee in
   `agent_chat`.
4. **Telemetry.** Add an optional `project_id` to `ai-gateway`'s
   `model_call_span`, `agent-runtime`'s `graph_run_span` and `api_request_span`,
   and `agent-bff`'s `bff_request` span, each setting `zuno.project_id` beside
   the existing `zuno.run_id` **only when non-empty**. Do not add it to any
   counter's attributes - unbounded cardinality, the same reasoning those
   modules already apply to `run_id`. agent-bff reads it from the path on the
   project routes, from `ChatResponse` on the non-streaming path, and from the
   SSE `start` event in `proxySSE`'s existing peek.
5. **Policy prose.** `policies/quotas/quota-policy.yaml`: update the header
   comment (the project dimension is now a membership-verified Zuno project, not
   a Salesforce-verified binding) and restate `project_binding.validity_window`
   as per-project. No structural change to the classes or budgets.
6. **Tests.** `tests/test_quota_headers.py` (new): the header is set from a
   plain `project_id`; the `project_required` gate is gone; and a negative
   assertion that no Salesforce identifier appears anywhere in the outgoing
   headers of a customer project's call.

## What NOT to touch

- `project_binding.py`'s verification logic, its regex or its error taxonomy -
  only its call site moves.
- MCP Gateway: zero changes, as ADR-0512 required and ADR-0528 preserves -
  verification still rides the existing `salesforce.opportunity.read`
  intersection.
- `policies/tools/tool-policy.yaml`. Finage's `finance` group is still absent
  from `salesforce.opportunity.read`'s `allowed_groups`, so no Finage user can
  set a customer link today; that is a standalone reviewed policy decision, not
  a drive-by here. Surface it, do not fix it.
- `components/ai-gateway/app/quota.py` - the ledger already keys on
  `project_id`; only the population reaching it changes.

## Acceptance checks (run from repo root; all must pass)

- `cd components/agent-runtime && for t in tests/test_*.py; do .venv/bin/python3 "$t" || exit 1; done`
- `cd components/ai-gateway && for t in tests/test_*.py; do .venv/bin/python3 "$t" || exit 1; done`
- `cd components/agent-bff && go build ./... && go test ./...`
- `python3 platform/okf/validate_quota_policy.py`
- `python3 platform/docs/check_docs.py`

## Operator / human follow-up (not executable by the model)

- ~~A live Salesforce pass (set a real opportunity on a project, confirm the
  three failure causes) remains blocked on the standing WP-22/WP-33 sandbox
  credential gap - the same block ADR-0512 already carried.~~ **Carved out
  2026-08-30 to [WP-101](wp-101-salesforce-sandbox-credentials.md) (v0.7)** -
  the gap has no repo-side fix, so it no longer gates this WP's or
  ADR-0528's closure; WP-101 owns the credential provisioning and the
  confirming pass when a sandbox exists.
- ~~A reviewed `tool-policy.yaml` decision on whether `finance` gains
  `salesforce.opportunity.read`.~~ **Decided 2026-08-29: no change.**
  `salesforce.opportunity.read` keeps `allowed_groups: [sales, board]`
  (`policies/tools/tool-policy.yaml`).

  The grant would widen CRM reach onto a room that is empty. No Salesforce
  credential exists anywhere in this cluster and none can: `ansible/roles/vault/
  tasks/install.yml` seeds `zuno/salesforce/technical` only when
  `zuno_salesforce_url`/`zuno_salesforce_access_token` differ from their
  `xxxxxx` placeholder, which they do not - so there is no Vault path, no
  ExternalSecret, no `salesforce-mcp` Deployment and no Argo Application, and
  the server's own docstring concedes "no real Salesforce org is wired in this
  demo". Granting access to a backend that does not exist buys nothing and
  quietly widens the blast radius for the day one does.

  Not free to reverse, which is the other half of the reasoning: adding
  `finance` changes the generated authorization matrices in
  `agents/finage/agent.okf.md` and `agents/comage/agent.okf.md`, which changes
  those bundles' bytes, which invalidates their OKF signatures and requires
  `make d3 sign agents` before agent-runtime will start. That is the right
  price to pay alongside a working sandbox, and the wrong one to pay for
  nothing.

  **Revisit when WP-22/WP-33 lands a sandbox** - at which point the change is
  one line plus a matrix regeneration. Nothing else in the repo needs touching:
  no test asserts the current group list, and `evaluations/finage/scenarios.yaml`
  scenario 12 stays green because its 403 comes from the agent_declaration
  factor, not the group factor.
- ~~After redeploy, confirm `zuno.project_id` appears on a real trace and joins
  to `zuno.run_id` across agent-bff, agent-runtime and ai-gateway.~~
  **Confirmed 2026-08-29 against live Tempo** (`TempoMonolithic tempo` in
  `zuno-monitoring`, query API reached by a temporary port-forward - it has no
  Route by design). Turn `zuno.run_id=3e33c0b1-0172-451c-aa55-76c07bd4a33b`
  (comage, 2026-08-28 09:34:26 UTC) carries
  `zuno.project_id=0b4daf98-dd1e-486c-bc5c-4b4716f65320` on all three:
  `bff_request` (agent-bff), `agent_graph_run` + `api_request` (agent-runtime)
  and `model_call` (ai-gateway). The gateway span shows a genuine call -
  `zuno.provider=local-wesh-maas`, `zuno.model=qwen3.5-9b-wesh`, 1001/66
  tokens - not a stub, and carries no Salesforce identifier, satisfying the
  adjacent negative clause. Coverage is 3 of 3: the database holds exactly
  three project-bound conversations and every one produced the full
  three-service attribute set, on two different agents.

  **Nuance worth knowing before someone opens Jaeger:** the three services do
  not share a trace id - each roots its own trace, with no W3C context
  propagation between them. The criterion is still met as written, because it
  asks for joinability on `zuno.run_id`, which is exactly how
  `gitops/charts/grafana/templates/dashboard-run-trace.yaml` queries (21
  `zuno.run_id` references, no trace-tree traversal). But there is no single
  waterfall to look at.

  ~~**Still missing, and not closed by this:** no test in ai-gateway or
  agent-bff asserts the attribute. It is proven present in production and
  unguarded against regression - a refactor could drop it and CI would stay
  green.~~ **Closed 2026-08-30**: `components/ai-gateway/tests/test_telemetry.py`,
  `components/agent-bff/internal/telemetry/telemetry_test.go` and
  `components/agent-runtime/tests/test_telemetry.py` (the last one closing
  the same gap there too - it turned out to have zero coverage as well,
  correcting this WP's original claim) now assert `zuno.project_id` is
  present when set and absent when not, on every span that carries it.

## Status updates (then re-run check_docs.py)

- After merge (2026-08-27/29): ADR-0528 -> `Repo work merged`; index row to
  match; Phase 21 tracker row -> `Repo work merged`.
- After closing on repo-verifiable criteria, with the live Salesforce pass
  carved out to WP-101/v0.7 (2026-08-30): ADR-0528 -> `Implemented`; this WP
  -> `Done`; tracker row -> `Done`; index row to match; a dated `MEMORY.md`
  bullet.
- When WP-101 lands a sandbox and runs the confirming live pass: no further
  status change here (this WP is already `Done`) - update WP-101 and
  ADR-0512's own residual-gap note instead.

## Out of scope / deferred

- Per-project quota classes or budgets distinct from ADR-0511's existing two.
- Non-Salesforce project registries.
- Dropping `conversations.project_id_verified_at`, which this WP stops writing;
  keep the column one release and drop it separately.
- The live Salesforce sandbox pass and its credential provisioning - see
  [WP-101](wp-101-salesforce-sandbox-credentials.md) (v0.7).

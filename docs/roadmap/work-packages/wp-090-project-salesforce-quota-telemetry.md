# WP-090: Salesforce link, quota and telemetry on the Zuno project id (promotes ADR-0528)

- **State:** Not started
- **ADRs:** ADR-0528 (Proposed -> Repo work merged after this WP; Implemented needs a live Salesforce pass, still blocked on the WP-22/WP-33 sandbox credential gap)
- **Depends on:** WP-088 (needs `projects.salesforce_*` and the server-resolved `project_id` on graph state)
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root.
>
> Tracked in [docs/roadmap/v0.1-v0.3-implementation-roadmap.md](../v0.1-v0.3-implementation-roadmap.md) Phase 21.

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

- A live Salesforce pass (set a real opportunity on a project, confirm the three
  failure causes) remains blocked on the standing WP-22/WP-33 sandbox credential
  gap - the same block ADR-0512 already carried.
- A reviewed `tool-policy.yaml` decision on whether `finance` gains
  `salesforce.opportunity.read`.
- After redeploy, confirm `zuno.project_id` appears on a real trace and joins to
  `zuno.run_id` across agent-bff, agent-runtime and ai-gateway.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0528 -> `Repo work merged`; index row to match; Phase 21
  tracker row -> `Repo work merged`.
- After the live Salesforce pass: ADR-0528 -> `Implemented`; tracker -> `Done`;
  a dated `MEMORY.md` bullet.

## Out of scope / deferred

- Per-project quota classes or budgets distinct from ADR-0511's existing two.
- Non-Salesforce project registries.
- Dropping `conversations.project_id_verified_at`, which this WP stops writing;
  keep the column one release and drop it separately.

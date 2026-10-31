# WP-164: Generate stack configuration from the corp release

- **State:** Repo work in review
- **ADRs:** [ADR-0581](../../adr/0581-derive-stack-configuration-from-the-admitted-corp-bundle.md)
- **Depends on:** [WP-160](wp-160-admit-the-corp-okf-release-in-zuno-demo.md), [WP-163](wp-163-okf-v0-3-schema-and-consumers.md)
- **Related:** [ADR-0530](../../adr/0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md), [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [WP-157](wp-157-slim-the-ai-gateway-via-maas.md), [WP-162](wp-162-keyless-okf-verification-in-unifai-operator.md)
- **Target:** v0.12
- **Estimated files touched:** ~25 in `zuno-demo` — `platform/okf/generate_stack_config.py` and tests, the generated files of ADR-0581 clause 2, the charts that merge them (`keycloak`, `models`, `connectivity-link`, `ai-gateway`, `unifai`, per-agent charts still alive), the keycloak reconcile Job script, `lint.yml`, `okf-promote.yml`, removal of `generate_quota_enforcement.py` and of `zuno_unifai_values.okf.bundles` from `confidential.yml` handling.

> Every value copied by hand from a bundle today becomes generated or
> disappears.

## Progress (2026-10-23)

Part 1 of 2, the generator, is built. `platform/okf/generate_stack_config.py`
writes ONE file, `platform/okf/stack-config.generated.yaml`, from the
release in `agents.lock` (verified first, through `admit_okf_bundle.extract`):
`keycloak.groups`, `agents.<name>` (version, digest reference,
classification, groups, tasks, tool and knowledge unions) and
`unifai.bundles` (reference + ceilings per agent). `--check` runs in the
`okf-release` job of `lint.yml`; `okf-promote.yml` regenerates it in the
promotion PR. 3 unit tests; proven on the devel release. With the lock
still empty, the committed file is empty.

Part 2, the consumers, is under way and coordinated:

- `unifai` role: done (zuno-demo-68). It reads the generated file, builds
  `okf.bundles` from `unifai.bundles` merged BY NAME with the platform's own
  `zuno_unifai_bundle_settings.<agent>` (groupTeam/teamId, entitlement,
  overrides), and passes `unifai.verify.keyless` and the committed
  `trusted_root.json` to the chart. While the generated list is empty,
  `zuno_unifai_values.okf` stays the only source; the two lists are never
  merged. Needs unifai-operator 0.1.25 (WP-162); first live use waits for a
  pinned release;
- Keycloak: done and live on demo333 (f60942a9, 2026-10-23). The
  ADR-0530 client-reconcile Job also creates the `agent_*` groups of
  `keycloak.groups` the realm lacks; it never deletes, never touches
  membership, and reports a live `agent_*` group the release no longer
  declares. `ansible/roles/keycloak` passes `agentGroups`. Proven offline
  (bash -n, fake kcadm) and live: one coordinated sync, the Job logged
  `0 groups created, 8 groups already present`, a consultant-01 token
  probe returned 200 with its groups intact;
- quotas, MaaS subscriptions, model routing and guardrail inputs wait for
  WP-157 (ADR-0570), which reshapes the same files and has no owner yet;
- per-agent chart values (arkos, naveo) are skipped: WP-156 deletes those
  charts.


## Goal

`generate_stack_config.py` produces, from the locked release, the Keycloak
groups, MaaS subscriptions, Kuadrant policies, ai-gateway routing and
guardrail inputs, per-agent values and UnifAI bundle values; `--check` gates
every PR; the hand-maintained copies are gone.

## Steps

1. **Inventory** each target in ADR-0581's table: read the current file,
   list hand-written vs agent-derived entries, decide the merge (separate
   generated values file layered by the chart).
2. **Generator** with one emitter per target and golden-file tests; absorb
   `generate_quota_enforcement.py` (coordinate with WP-157 if it has
   changed that script to emit TokenRateLimitPolicies).
3. **Charts** read the generated files; remove the duplicated hand-written
   entries.
4. **Keycloak** reconcile Job (ADR-0530) extended to `agent_<name>` groups:
   create and update, never delete, never touch membership.
5. **UnifAI** bundles values generated with digests from the corp index and
   `verify.keyless` (WP-162); drop the `confidential.yml` path.
6. **Wire** `--check` into `lint.yml` and the generation into
   `okf-promote.yml`.
7. **Live on demo333:** promote a release that adds a tool to one task and a
   new group to one agent; check the generated diff, the RateLimitPolicy
   `Enforced` plus a real 429 (WP-54 lesson), the group created in Keycloak,
   and the UnifAI bundle re-emitted.

## Acceptance

`--check` green; no agent-derived value is hand-written anywhere in
`gitops/`; the step 7 promotion produces exactly the expected diff and
takes effect live; a release that widens beyond corp policies is refused
before generation.

## Update (2026-10-24)

Part 2 is live on demo333 through the `unifai` role (`zuno_unifai_released_bundles`): arkos, comage and
tekos are served from the released bundles and the Keycloak groups come from the generated file. The
admission of a release now also checks that each allowed knowledge domain is served by a tagged UnifAI
RAG source (a warning when it is not). Open: quotas, MaaS subscriptions and routing (WP-157), the
promotion of release 0.3.0 to prove the "takes effect live" acceptance, and the frozen
`publicKeyRef` path of the hand-pinned Transit bundles.

## Update (2026-10-25)

The frozen Transit path is removed. No cluster pinned a bundle by hand any more, and all 8
demo333 bundles were already keyless. The changes:

- the `unifai` role no longer passes `okf.publicKey`;
- `files/zuno-platform-signer.pub` is deleted;
- the chart drops the `zuno-platform-signer` Secret and the `publicKeyRef` branch;
- `checks.yaml` refuses bundles without `okf.verify.keyless`.

Rendered with the demo333 released values, the chart differs only by the unused Secret
leaving. That takes effect at the next `unifai` role run. The Vault Transit key stays as
the image-signing rollback (ADR-0535).

Step 7, the live promotion proof, is done (below).

## Update (2026-10-25): step 7 proven on demo333

The test release is zuno-demo-agents v0.6.1 (corp `sha256:3b46220a…`): tekos 0.4.1 adds
`list_drive_files` to the task `find-relevant-docs` and declares a second group,
`agent_tekos_preview`. Release 0.6.0 was never cut; 0.6.1 carries its change plus a prompt example.

- **Generated diff.** Promotion PR #8 (merged as `db049ead`) changed only `agents.lock` and
  `stack-config.generated.yaml`. The diff held the release and reference, `+agent_tekos_preview` in
  `keycloak.groups` and in `agents.tekos.groups`, the tekos version and digest, and the tekos
  UnifAI bundle reference. The 5 quota files did not change, because the corp policy layer is
  byte-identical. A local rebuild gave the same digests for the other 7 agents. This was predicted
  before the release: the exact diff came from a local build fed to the generator. `--check` passed
  for both generators against the extracted release, and the admission diff read
  `tekos: version 0.3.0 -> 0.4.1; groups +agent_tekos_preview; find-relevant-docs tools +list_drive_files`.
- **Refused before generation.** A copy of the bundle declaring a tool absent from tool-policy
  failed `validate_okf_bundle.py` (`unknown tool ... (not in tool-policy.yaml)`).
- **Keycloak.** The `keycloak` role ran; the reconcile Job logged
  `created group agent_tekos_preview` and `1 groups created, 8 groups already present`. Membership
  was not touched.
- **mcp-gateway.** Before the `mcp` role, a `stress-consultant-01` call to `list_drive_files` as
  tekos/`find-relevant-docs` returned `403 task 'find-relevant-docs' does not allow tool
  'list_drive_files' (ADR-0011 task_rights)`. After the role (okf-fetch on the v0.6.1 corp digest),
  the same call passed task rights and stopped at the downstream check, the same 403 as for
  `check-my-drive-docs`: `requires a delegated google-workspace credential`.
- **UnifAI.** The `unifai` role ran (zuno-demo-68). Bundle `tekos` sits at
  `okf-tekos@sha256:f1168f9d…`, keyless `Verified=True` (`publish.yml@refs/tags/v0.6.1`), Valid,
  WithinCeilings, Emitted, Ready. Team `agent-tekos` has members `agent_tekos` and
  `agent_tekos_preview`.
- **Quotas (WP-54 lesson).** `zuno-token-quota` and the six `maas-trlp-*` TokenRateLimitPolicies
  are Accepted and Enforced. The tekos stresstest's real 429 passed (`stresstest-429`, 0 5xx).
  - The first run (56/59) hit MaaS 500s left over from a cluster outage: stale Authorino
    connections, fixed by an Authorino restart, recorded in the WP-157 inventory.
  - The rerun scored 58/59: acceptance 18/18, gate 5/5, quota 3/3, coverage 10/10, bulk 10/10,
    security 13/14.
  - The one failure is unrelated: the A2A-gateway denial check (ADR-0583, added the same night)
    cannot reach `a2a-gateway`, whose NetworkPolicy admits only UnifAI's `multiagent` pods.

Still open against ADR-0581 clause 2: no consumer reads the per-agent `models`, `guardrails`
and `limits` fields the generator already emits. MaaS subscriptions from groups x model roles,
ai-gateway routing and guardrail inputs, and per-agent limits in the TokenRateLimitPolicies are
therefore not generated yet. The quota budgets themselves are generated from the corp policy
(WP-157, WP-177).

## Update (2026-10-25): consumers of the per-agent fields

68 split the open consumers into four lots, user-approved:

1. **MaaS subscriptions, live on demo333** (devel `0f80d954` + `c5c724b0`).
   - `values.agents.generated.yaml` is generated, and the models role passes it to the chart.
   - One `<model>-agents` subscription per local model (agent groups, priority 10, 100000 tokens/1h)
     replaces the hand-written `<model>-tekos`.
   - `/sales` (priority 1, 5000/1h) and the ServiceAccount subscriptions stay hand-written.
   - The entitlement auth policies hold `/sales` plus the agent groups.
   - Order applied: the models role ran from the branch first (a no-op on the live chart), then the
     merge switched everything at once.
   - Live result: 16 subscriptions, the four `-tekos` replaced by `-agents` (Active), and all six
     MaaSModelRefs Ready. 7 golden tests.
2. **Model routing.** Designed in the 2026-10-25 amendment of ADR-0581:
   - a generated routing file mounted in ai-gateway;
   - corp candidate sets;
   - agent roles reorder them (user decision);
   - `forbidden` becomes a new `exclude` field.

   With release 0.6.1 nothing changes. Code next, repo only; ai-gateway is rebuilt only with the user's go.

   **Code landed, not enabled (2026-10-25).**
   - The generator writes `gitops/charts/ai-gateway/files/model-routing.generated.yaml`, steps 1-4
     of the amendment. With release 0.6.3 it equals the corp policy exactly (24 entries); 7 tests.
   - ai-gateway: the `exclude` field (after eligibility and local-only, before `prefer`/`strict`,
     fail closed when nothing is left). The routing watcher reloads the policy file. A missing
     mounted file falls back to the copy baked into the image. 9 tests; suite 280/280.
   - Chart: a ConfigMap, the mount and `MODEL_ROUTING_POLICY_PATH` behind `modelRouting.generated`
     (default false; the default render is unchanged). The llm role passes
     `zuno_ai_gateway_model_routing_generated`. okf-promote commits the new file.
   - To enable, with the user's go:
     1. `make d1 build ai-gateway`, then check that the image contains this commit;
     2. set `zuno_ai_gateway_model_routing_generated: true` in `ansible/clusters/demo333.yml`;
     3. run the llm role.
     Proof: the gateway logs `loaded model-routing policy from /app/config-model-routing/...`, and
     a tekos chat routes as before.
3. **Guardrail modes.** Decided 2026-10-31 (user): keep `observe` on C1, C2 and C3, and generate a
   per-agent mode. **Code landed, not enabled (2026-10-31).**
   - The generator writes `gitops/charts/ai-gateway/files/guardrails-modes.generated.yaml`: the corp
     `minimum_mode_by_classification` and each agent's `zuno.guardrails.mode`. Release 0.6.3: all
     minimums `observe`, tekos declares `observe`, so nothing changes. 4 tests.
   - ai-gateway (`app/guardrails.py`): the effective mode is the strictest of `modeByClassification`,
     the corp minimum and the calling agent's mode. `X-Zuno-Agent` is caller-supplied, so it can only
     harden. The routing watcher reloads the file. `categories` is not consumed yet. 6 tests; suite
     286/286.
   - Chart: ConfigMap, mount and `GUARDRAILS_AGENT_MODES_PATH` behind `guardrails.modesGenerated`
     (default false, default render unchanged); the llm role passes
     `zuno_ai_gateway_guardrails_modes_generated`; okf-promote commits the file.
   - Enabling shares the lot 2 rebuild: set the variable to true with the lot 2 one, run the llm role.
     Proof: the gateway logs `loaded guardrails agent modes`; then, as a reverted test, a release
     declaring `block` for one agent shows `mode=block` in the guardrails log for that agent only.
4. **Per-agent limits.**
   - `memory.history` goes to unifai-operator.
   - Token budgets go to `quota.py`, keyed by agent, since Kuadrant cannot key on the agent.

## Update (2026-10-25): tekos stresstests after the search budget

Scenario #11's web leg (cite `docs.redhat.com` on "What is a namespace in OpenShift?") failed in three
runs of four. Causes found: the `web_search` stub returned the same two pages for any query, and tekos
re-queried until the run timed out. Fixes, in order:

- `web_search` answers honestly that no provider exists (`c5175c48`).
- The tekos prompt gets a search budget of at most three searches (release 0.6.3, promoted).
- Retriever `top_k_results` goes from 5 to 10 (`5009745e`).
- The UnifAI operator gets a cap on identical calls (a9).
- `zuno.limits.max_steps` is added (corp ceiling 30, release 0.7.0, admission check `6fc768ae`; not promoted, no
  agent sets it yet).

| Series | Run | Score | #11 | Notes |
|---|---|---|---|---|
| Before 0.6.3 (cap + top_k 10) | 1 | 57/59 | fail | no timeout |
| | 2 | 59/59 | pass | |
| | 3 | void | - | qwen35-9b down 16:57-17:16Z |
| Prompt 0.6.3 | 1 | 57/59 | pass | first token 22 s; one security check timed out |
| | 2 | 58/59 | pass | first token 45 s |
| | 3 | 57/59 | fail | no timeout; a check expected a retriever tool event |
| After the corpus scoping (WP-168) | 1 | 57/59 | fail | first token 8.3 s |
| | 2 | 57/59 | fail | first token 16.9 s; unifai-backend restarted at 20:49Z mid-run |
| | 3 | partial | pass | the report kept only 9 results; the Job log shows #11 passing |
| Quiet stack (2026-10-31) | 1 | 51/52 | pass | first token 9.7 s; #10 passes via the Tempo `rag.search` fallback |

- **The loop is fixed:** no timeout since 0.6.3.
- **#11 is a ranking problem now:** on the misses tekos answers in time, names the Confluence page and
  cites no OCP URL. The retriever ranks installation guides above the definition (WP-168 update).
  Ranking work is with a9.
- **First-token latency** is above the 6 s target in every run (8-45 s). On a quiet stack
  (2026-10-31: no other test, GPU nodes at 7% CPU, no restart) it is still 9.7 s, so it is not
  load. The bulk pass gives p50 23.8 s and p95 62.8 s per full answer (10 interactions, 0 errors).
- **Harness:** with retrieval done before reasoning, the retriever call does not always appear as a
  tool event (`tool_calls=[]` on a passing answer). The check that expects that call needs to accept
  either.
- **Lot 1 follow-up:** the `<model>-agents` and `<model>-sales` subscriptions carry both group
  spellings since `e515508a`, for API-key callers (WP-157 inventory).
- **Lot 1 verified with per-persona API keys (2026-10-25, demo333).** The `maas-api` route was not
  exposed (`NotAllowedByListeners`: the gateway listener did not allow `redhat-ai-gateway-infra`); `59b9be49`
  / `f648cb56` added it. Each persona logged in to OpenShift through the `openshift` OpenID IdP (this
  generates the `User`, `Identity` and the unslashed groups), minted a 2 h key at
  `POST /maas-api/v1/api-keys`, then sent one chat to `gpt-oss-20b`:

  | Persona (Keycloak groups) | Subscription bound to the key | Chat | Limitador counter |
  |---|---|---|---|
  | tekos-entitlement-only-user-01 (`agent_tekos`) | `gpt-oss-20b-agents` | 200 | agents, 100,000/h |
  | arkos-entitlement-only-user-01 (`agent_arkos`) | `gpt-oss-20b-agents` | 200 | agents |
  | comage-entitlement-only-user-01 (`agent_comage`) | `gpt-oss-20b-agents` | 200 | agents |
  | sale-01 (`sales`, `agent_comage`, `agent_finage`) | `gpt-oss-20b-agents` | 200 | agents (priority 10 beats sales) |
  | sales-role-only-user-01 (`sales`) | `gpt-oss-20b-sales` | 200 | sales, 5,000/h |
  | consultant-role-only-user-01 (`consultant`) | none | key refused: 400 `invalid_subscription`; its OpenShift token on the model route: 403 | none |

  No credential: 401. A revoked key: 403. Afterwards every test key was revoked, the OAuth access
  tokens, the generated groups (`agent_arkos`, `agent_comage`, `agent_finage`, `consultant`, `sales`),
  the `Identity` and `User` objects were deleted, and the test user was removed from `agent_tekos`;
  the cluster is back to its earlier user and group list. Not covered: `sale-02`-style users that
  hold only `agent_*` groups of other agents, and the 429 behaviour at the tier ceiling (the sales
  tier is 5,000 tokens/h; not exhausted on purpose).


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
3. **Guardrail modes.** They wait for a user decision on the hook.
4. **Per-agent limits.**
   - `memory.history` goes to unifai-operator.
   - Token budgets go to `quota.py`, keyed by agent, since Kuadrant cannot key on the agent.

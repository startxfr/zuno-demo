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

Still open: step 7, the live promotion proof.

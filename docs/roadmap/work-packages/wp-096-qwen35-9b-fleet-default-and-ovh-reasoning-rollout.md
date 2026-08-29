# WP-096: Roll out qwen3.5-9b as the fleet default and extend OVHcloud reasoning access

- **State:** Repo work in review
- **ADRs:** ADR-0531 (Proposed → Implemented once landed)
- **Depends on:** WP-087 (created `qwen3.5-9b`/`qwen3.5-9b-wesh` as live providers), WP-092
  (confirmed both live and node-separated)
- **Estimated files touched:** 5 (`policies/model-routing/model-routing-policy.yaml`,
  `platform/ai-gateway/provider-routing.yaml` comment fix, `docs/adr/0419-...md` +
  `docs/adr/README.md` status fix, this brief + roadmap tracker row)

## Goal

Make `qwen3.5-9b` the platform's default local model everywhere no task-specific override
applies (replacing today's implicit `qwen3.6-27b-instruct` file-order default), pair it with
Comage's `qwen3.5-9b-wesh` fine-tune for both Tekos (primary base / fallback wesh) and Comage
(primary wesh / fallback base), and extend `ovhcloud-gpt-oss-120b`'s reasoning-task preference
(previously Arkos-only, ADR-0416) to Tekos's `answer-technical-question` and Comage's
`compare-historical-deals`. Pure `policies/model-routing/model-routing-policy.yaml` content
change - no code, no new provider, no classification tier, no infrastructure impact. See ADR-0531
for the full numbered decision and rationale.

## What changed

`policies/model-routing/model-routing-policy.yaml`'s `preferences:` block, one row per touched or
newly-created `(agent, task)` entry (`preferred:` is this ADR-0419 schema; entries not listed
below - `arkos`'s three tasks - are untouched):

| Agent | Task | Before | After (leading candidates) |
|---|---|---|---|
| tekos | answer-technical-question | gpt-oss → wesh → qwen3.6 → OVH | **OVH → gpt-oss → qwen3.5-9b → wesh** → qwen3.6 |
| tekos | find-relevant-docs | qwen3.6 → wesh → gpt-oss → OVH | **qwen3.5-9b → wesh** → qwen3.6 → gpt-oss → OVH |
| tekos | check-my-drive-docs | qwen3.6 → wesh → gpt-oss → OVH | **qwen3.5-9b → wesh** → qwen3.6 → gpt-oss → OVH |
| tekos | write-code | mistral-codestral → wesh → gpt-oss → qwen3.6 | unchanged |
| comage | compare-historical-deals | wesh → gpt-oss → qwen3.6 | **OVH → gpt-oss → wesh → qwen3.5-9b** → qwen3.6 |
| comage | check-deal-status | wesh → qwen3.6 → gpt-oss | wesh → **qwen3.5-9b** → qwen3.6 → gpt-oss |
| comage | update-opportunity-status | wesh → qwen3.6 → gpt-oss | wesh → **qwen3.5-9b** → qwen3.6 → gpt-oss |
| comage | check-my-drive-and-mail | wesh → qwen3.6 → gpt-oss | wesh → **qwen3.5-9b** → qwen3.6 → gpt-oss |
| advantage | answer-project-question, identify-new-business-with-po, monthly-sales-report | gpt-oss → qwen3.6 | **qwen3.5-9b** → gpt-oss → qwen3.6 |
| advantage | check-my-drive-and-mail | *(no entry - implicit qwen3.6 default)* | **qwen3.5-9b** → gpt-oss → qwen3.6 |
| finage | identify-business-ready-to-invoice, monthly-invoice-report | gpt-oss → qwen3.6 | **qwen3.5-9b** → gpt-oss → qwen3.6 |
| finage | answer-finance-question, check-my-drive-and-mail | *(no entry)* | **qwen3.5-9b** → gpt-oss → qwen3.6 |
| cognos | coming-soon | OVH → gpt-oss → qwen3.6 (inert) | OVH → **qwen3.5-9b** → gpt-oss → qwen3.6 (inert) |
| cognos | review-historical-commercial-data | *(no entry, inert)* | **qwen3.5-9b** → gpt-oss → qwen3.6 (inert) |
| naveo | answer-onboarding-question | *(no entry, pre-live)* | **qwen3.5-9b** → gpt-oss → qwen3.6 (pre-live) |
| soursage | coming-soon | *(no entry, pre-live)* | **qwen3.5-9b** → gpt-oss → qwen3.6 (pre-live) |

Plus: a stale comment fix in `provider-routing.yaml` (`local-qwen35` was documented as "preferred
by no agent" - no longer true), and `docs/adr/0419-...md` + `docs/adr/README.md`'s `Status:`
corrected from `Proposed` to `Implemented` (the mechanism has been live for some time; only the
field was stale).

## Verification checklist

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | `python3 -c "import yaml; yaml.safe_load(open('policies/model-routing/model-routing-policy.yaml'))"` | Parses clean | |
| 2 | `python3 platform/docs/check_docs.py` | `adr_index`/`wp_state` pass (ADR-0419 status, ADR-0531/WP-096 rows) | |
| 3 | `python3 platform/okf/generate_authorization_matrix.py` then `--check --all` | Regenerated matrices committed, `--check` clean | |
| 4 | `python3 evaluations/tekos/gate_checks.py` | `tekos_write_code_prefers_mistral_codestral` still passes | |
| 5 | ai-gateway image rebuilt + rolled out (this file is baked into the image, not a ConfigMap) | New pod serving the updated policy | |
| 6 | `evaluations/tekos/stress_test.py`'s `layer1_model_routing` category, live | Self-computed expectation matches live `zuno_provider` for every Tekos task | |
| 7 | Live curl, `tekos/answer-technical-question` at C1 | `zuno_provider` = `ovhcloud-gpt-oss-120b` | |
| 8 | Live curl, `comage/compare-historical-deals` forced to C3 via `knowledge.sxa-legacy` | `zuno_provider` is local-only (never OVH) | |
| 9 | Live curl, `advantage/check-my-drive-and-mail` (new entry) | `zuno_provider` = `local-qwen35-maas` (or `local-qwen35` if MaaS unreachable) | |
| 10 | `oc get pods -n zuno-ai-run -o wide` | No churn - no new provider, no placement change | |

## Status updates

- 2026-08-30: `model-routing-policy.yaml` content changed, ADR-0531 + this brief written,
  `docs/adr/README.md`/`docs/adr/0419-...md` status corrected, roadmap tracker row added. Static
  checks (1-4) pending; live verification (5-10) deferred pending an ai-gateway image
  rebuild/rollout and explicit operator go-ahead (this repo's shared-cluster convention).

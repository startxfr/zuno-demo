# WP-096: Roll out qwen3.5-9b as the fleet default and extend OVHcloud reasoning access

- **State:** Done (live-verified 2026-08-30)
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
| 1 | `python3 -c "import yaml; yaml.safe_load(open('policies/model-routing/model-routing-policy.yaml'))"` | Parses clean | ✅ |
| 2 | `python3 platform/docs/check_docs.py` | `adr_index`/`wp_state` pass (ADR-0419 status, ADR-0531/WP-096 rows) | ✅ PASS |
| 3 | `python3 platform/okf/generate_authorization_matrix.py` then `--check --all` | Regenerated matrices committed, `--check` clean | ✅ 7 agents regenerated (advantage, cognos, comage, finage, naveo, soursage, tekos), Arkos untouched; `--check --all` PASS |
| 4 | `python3 evaluations/tekos/gate_checks.py` | `tekos_write_code_prefers_mistral_codestral` still passes | ✅ all 4 checks PASS |
| 5 | ai-gateway image rebuilt + rolled out (this file is baked into the image, not a ConfigMap) | New pod serving the updated policy | ✅ `oc start-build ai-gateway -n zuno-ai-build` (build `ai-gateway-14`, commit `d8d6e91d`), auto-rolled to `ai-gateway-5788f9cfbb-5kjts`; confirmed via `oc exec` reading the live pod's mounted policy file - new content present |
| 6 | `evaluations/tekos/stress_test.py`'s `layer1_model_routing` category, live | Self-computed expectation matches live `zuno_provider` for every Tekos task | ⚠️ Not run as the packaged script (would persist demo-persona conversations needing cleanup); ran a direct-equivalent check instead (same request shape: Keycloak ROPC token, `X-Zuno-Agent`/`X-Zuno-Task`/`X-Zuno-Data-Classification` headers straight to `/v1/chat/completions`) from an in-cluster debug pod labelled `acceptance-gate` - see checks 7-9 |
| 7 | Live check, `tekos/answer-technical-question` at C1 | `zuno_provider` = `ovhcloud-gpt-oss-120b` | ✅ confirmed |
| 8 | Live check, `tekos/find-relevant-docs` at C1 (new default) | `zuno_provider` = `local-qwen35-maas` | ✅ confirmed |
| 9 | Live check, `comage/compare-historical-deals` at C2 then C3 | C2 → `ovhcloud-gpt-oss-120b`; C3 → a local-only provider, never OVH | ✅ confirmed: C2 → `ovhcloud-gpt-oss-120b`, C3 → `local-gpt-oss-maas` |
| 10 | Live check, `advantage/check-my-drive-and-mail` (new entry) at C1 | `zuno_provider` = `local-qwen35-maas` | ✅ confirmed |
| 11 | `oc get pods -n zuno-ai-run -o wide` | No churn on model-serving pods - no new provider, no placement change | ✅ `qwen35-9b-kserve`, `qwen35-9b-wesh-kserve`, `gpt-oss-20b-kserve`, `qwen36-27b-instruct-kserve` all same pod name/age as the pre-change baseline |

## Status updates

- 2026-08-30: `model-routing-policy.yaml` content changed, ADR-0531 + this brief written,
  `docs/adr/README.md`/`docs/adr/0419-...md` status corrected, roadmap tracker row added. Static
  checks (1-4) passed. Committed separately (`e11cb4d4`) after a shared-workdir commit race with
  a concurrent session bundled it into an unrelated commit first - recovered without rewriting
  the other session's history (see MEMORY.md `git-commit-shared-workdir-race`).
- 2026-08-30: pushed to `origin/main` (commit `d8d6e91d` HEAD at push time), `ai-gateway` image
  rebuilt (`ai-gateway-14`) and auto-rolled out. Live verification (checks 5, 7-11) all passed
  from an in-cluster `acceptance-gate`-labelled debug pod (cleaned up after). Check 6's literal
  script run was skipped in favor of an equivalent direct check (see check 6's note) - WP closed
  as Done on that basis.

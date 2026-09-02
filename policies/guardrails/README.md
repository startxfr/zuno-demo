# Policy: guardrails

Prompt, response, injection and unsafe-action guardrail policy.

**Observe-only.** Nothing here blocks, refuses, or alters a reply. Every
detection is logged and counted while the flagged exchange still reaches
the user unmodified. That asymmetry is the contract, not a gap: ADR-0534
makes the observe-to-block transition a separate, later decision that
needs the evidence this policy exists to collect.

## Where the machine-readable policy lives

`gitops/charts/trustyai-config/files/nemo-rails/observe/config.yml`,
under `custom_data.zuno_patterns`.

It is not in this directory, and that is deliberate. Helm's `.Files.Get`
is chart-root-relative and cannot traverse out of its chart (the same
constraint `gitops/charts/rag-service/templates/configmap-schema.yaml`
documents), so a copy here could not be rendered into the ConfigMap the
NeMo Guardrails server mounts. Rendering it from the chart keeps the
policy under ArgoCD rather than applied out-of-band (ADR-0311/ADR-0312).
This file is the human-readable specification; that one is the source of
truth.

## What is covered

| Class | Detection names |
|---|---|
| PII | `email`, `us-social-security-number`, `credit-card` |
| Prompt injection / jailbreak | `injection-ignore-instructions`, `injection-disregard-rules`, `injection-persona-override`, `injection-pretend-unrestricted`, `injection-system-prompt-leak` |

These names are a **metrics contract**: they surface as the detection
label on `zuno.guardrails_detections` and are queried by the
`zuno-trustyai` Grafana dashboard. Renaming one splits its series.

## Two things not to change casually

- **The `{0,2}` filler window** in the injection patterns is load-bearing.
  The 2026-09-02 live test (run `d9445c2a`) proved that
  `ignore all PREVIOUS instructions` slips a single-filler pattern.
  Tightening it needs that test re-run.
- **`config.yml` has no `models:` block**, so no rail calls an LLM. Every
  detection is a pattern match executed by `actions.py`. Adding a rail
  that reasons (self-check, fact-checking, topical rails) makes every
  observed exchange an inference call on a cluster whose GPU quota is
  fully saturated (ADR-0351/ADR-0537) — that is an ADR-level cost
  decision, not a config edit.

## Backends

`gitops/charts/agent-runtime/values.yaml` `guardrails.backend` selects
which observer answers:

- `nemo` — the `NemoGuardrails` server, policy as data (above).
- `builtin` — the `GuardrailsOrchestrator` built-in detector, whose
  equivalent patterns are compiled into the agent-runtime image as
  `DETECTOR_PARAMS`. Retained as the fallback until the nemo path is
  live-proven; `components/agent-runtime/tests/test_guardrails.py`
  (`PolicyParityWithRails`) fails if the two copies drift.

See [ADR-0534](../../docs/adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md)
and [ADR-0540](../../docs/adr/0540-express-guardrail-policy-as-nemo-rails-configuration.md).

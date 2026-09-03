# ADR-0540: Express guardrail policy as NeMo rails configuration, not in-image detector parameters

- **Status:** Accepted
- **Target:** v0.7
- **Date:** 2026-09-02 (amended 2026-09-03)
- **Decision owners:** Zuno Demo architecture team
- **Amends:** [ADR-0534](0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md) Phase 2 -
  clarifies the guardrails backend without retiring GuardrailsOrchestrator

## Context

ADR-0534 delivered observe-only guardrails: after every agent exchange, the user prompt and the
model reply are POSTed to the TrustyAI built-in detector and any detections are logged, never
blocked on. The chain is live and visible (WP-113's `zuno-trustyai` Grafana dashboard, WP-115's
dashboard flags).

The **policy**, however, is a Python dict literal. `DETECTOR_PARAMS` in
`components/agent-runtime/app/clients/guardrails_client.py` carries three named PII classes and
five prompt-injection regexes, compiled into the agent-runtime image. Changing one detection
pattern — the routine act for a guardrail, and the whole point of running observe-only first —
means editing Python, rebuilding an image, and redeploying a request-path service. That is the
wrong cost for the thing this platform expects to tune most often, and it puts security policy
outside the `policies/` convention every other policy in this repo follows
(`policies/data-classification/classification.yaml`, `policies/tools/tool-policy.yaml`).
`policies/guardrails/README.md` has been a two-line stub with no policy file since it was created.

A capability review of the 43 never-instantiated RHOAI CRDs on this cluster found the operand
already offers the right surface. Three live findings frame this decision:

- The TrustyAI operator runs with `--enable-services TAS,LMES,GORCH,NEMO_GUARDRAILS,EVALHUB`
  (argv read live, 2026-09-02) while `DataScienceCluster.spec.components.trustyai.
  mcpGuardrailsMode` is `false`. **The NeMo Guardrails controller has been running all along** —
  no DSC change is needed, and none is wanted: WP-108 proved that flipping that flag to `true`
  redeploys the operator with `--enable-services NEMO_GUARDRAILS` *only*, killing the LMEvalJob
  controller (an ADR-0108 regression), EvalHub, TrustyAIService and GuardrailsOrchestrator. It
  was flipped and reverted the same hour.
- `NemoGuardrails.spec.nemoConfigs[]` takes `{name, default, configMaps[]}`, and every file in
  the referenced ConfigMaps is mounted at `/app/config/$name`. A Helm-rendered ConfigMap is
  therefore a complete, GitOps-managed policy delivery mechanism.
- Zero `NemoGuardrails` CRs exist, so there is no adoption conflict.

The constraint that shapes the design: NeMo Guardrails is normally an LLM-proxying rails engine,
and this cluster's GPU quota is fully saturated (`mig-1g.24gb` 3/3, `mig-2g.48gb` 2/2 —
ADR-0351/ADR-0537). An observation that costs an inference call per exchange has no slice to run
on.

## Decision

1. **Guardrail policy becomes data, rendered from Git.** The patterns live in
   `gitops/charts/trustyai-config/files/nemo-rails/observe/config.yaml` under
   `custom_data.zuno_patterns`, rendered into ConfigMap `zuno-nemo-rails-observe` and mounted by
   a `NemoGuardrails/zuno-guardrails` CR in `zuno-ai-run`. Canonical location is the chart, not
   `policies/guardrails/`: Helm's `.Files.Get` is chart-root-relative and cannot traverse out of
   the chart, and rendering from the chart keeps the policy under ArgoCD rather than applied
   out-of-band (ADR-0311/ADR-0312). `policies/guardrails/README.md` becomes the human-readable
   specification and points at it.
2. **The rails carry no model.** `config.yaml` has an empty `models:` block; every rail is a
   pattern match executed by a generic action in `actions.py` that reads
   `custom_data.zuno_patterns`. No rail reasons, so no observation costs inference. `actions.py`
   contains no policy — adding or tuning a detection class is a YAML edit ArgoCD syncs, and the
   code never changes. Adding a rail that *does* need a model (self-check, fact-checking,
   topical rails) is an ADR-level cost decision, not a config edit.
3. **Observe-only is enforced in three independent places, and stays that way.** The Colang
   flows record and never `stop`; the client ignores the generated message and reads only the
   activated-rails log; and the client call remains fire-and-forget, spawned after the response
   has already been delivered. ADR-0534's observe-to-block transition remains a separate, later
   decision.
4. **The backend is selectable, and `builtin` remains the default until the nemo path is
   live-proven.** `gitops/charts/agent-runtime/values.yaml` `guardrails.backend` chooses between
   `nemo` and the existing `builtin` detector. The `GuardrailsOrchestrator/zuno-guardrails-smoke`
   instance is **not** deleted: it stays as ADR-0534's proof and as the fallback. `DETECTOR_PARAMS`
   is likewise retained, because deleting it would drop the injection heuristics from the fallback
   path — a real loss of coverage. A unit test (`PolicyParityWithRails`) fails if the two copies
   drift. The flip happened on 2026-09-03 (WP-120).

   *Amended 2026-09-03 (WP-120)* — the original text ended "and both are deleted in the same
   commit that flips the default." That instruction contradicted this same decision's own
   retention of the `GuardrailsOrchestrator` as the fallback, which its Non-goals restate.
   `DETECTOR_PARAMS` **is** that fallback's entire policy: the orchestrator applies no patterns of
   its own, they travel on every request in `detector_params`. Deleting the dict would therefore
   leave `backend: builtin` wired, healthy and detecting nothing — turning the documented rollback
   for this flip into a silent loss of observation, which is precisely the failure mode the rest of
   this ADR is written to avoid.

   The retention is therefore **not** time-limited to the flip. `DETECTOR_PARAMS` and
   `PolicyParityWithRails` live as long as the `GuardrailsOrchestrator` is the declared fallback;
   whichever decision retires that instance is the one that deletes them. The cost of keeping them
   is a duplicated policy, and `PolicyParityWithRails` already fails on drift — a guarded
   duplicate, against an unguarded empty rollback.

## Non-goals

Blocking on a detection (ADR-0534's separate deferred decision); deleting the
`GuardrailsOrchestrator` smoke instance; changing `mcpGuardrailsMode`, which stays `false`;
configuring `TrustyAIService`, which ADR-0534 deliberately leaves unconfigured because it
monitors predictive-model bias and this platform serves generative models.

## Operational considerations

- **Detection-name cardinality changes.** The builtin detector reports a single `custom-regex`
  name for every custom pattern; the rails report one name per class
  (`injection-ignore-instructions`, `email`, …). The `zuno.guardrails_detections` label set
  therefore widens at the flip, and the `zuno-trustyai` dashboard's detections panel must be
  updated with it. The names are a metrics contract: renaming one splits its series.
- **A missing ConfigMap is silent.** A `NemoGuardrails` whose ConfigMap is absent mounts an empty
  `/app/config` and detects nothing while reporting healthy. The precheck reports the ConfigMap's
  key set, not just its presence, for exactly this reason.
- **The operand's activated-rails log shape is not pinned by the CRD.** The client parses it
  defensively: an unrecognised payload yields zero detections rather than raising. A silent zero
  presents as a flat detections series on the dashboard — the intended failure mode for an
  observer, but one to check before concluding traffic is clean.
- `status.ca` exposes three independent CA-discovery booleans and `status.bbrPlugin` a fourth; a
  `NemoGuardrails` that never becomes ready usually explains itself there rather than in
  `conditions`.
- The `{0,2}` filler window in the injection patterns is load-bearing: the 2026-09-02 live test
  (run `d9445c2a`) proved `ignore all PREVIOUS instructions` slips a single-filler pattern.
- **The ConfigMap key must be `config.yaml`.** The NeMo library accepts either spelling; the
  RHOAI image's startup wrapper checks the `.yaml` name by hand and exits before the library
  runs. Live, that one character CrashLoopBackOff'd the server after a ~14GB image pull.
- **The server's image is ~14GB and its pod must not schedule on a control-plane node.** The
  first deployment left scheduling free, landed on a master with 21GB of image-filesystem
  headroom, and evicted 43 pods cluster-wide. `nemoGuardrails.pod` excludes both
  `node-role.kubernetes.io/control-plane` and the deprecated `-master`.
- **The CRD forbids `spec.replicas: 0`** (minimum 1), and the operator reconciles a directly
  scaled Deployment straight back — so "scale the observer to zero" is not an available way to
  test the unavailable path. Black-holing `GUARDRAILS_NEMO_URL` is.

## Migration / evolution

Executed by [WP-120](../roadmap/work-packages/wp-120-guardrail-policy-as-nemo-rails.md).
`guardrails.backend` was flipped to `nemo` on 2026-09-03 once the live proof passed.

Decision 4's second half — deleting `DETECTOR_PARAMS` and `PolicyParityWithRails` in that same
commit — was not executed, and Decision 4 is amended above rather than followed: the retention now
tracks the `GuardrailsOrchestrator`'s lifetime instead of the flip. Whichever decision retires that
instance deletes them.

Separately and later: ADR-0534's observe-to-block decision, which this work makes cheaper by
putting the policy where a reviewer can read it.

Live evidence, 2026-09-03 (see WP-120 for the full gate). Decision 2's cost claim holds in
practice — `llm_calls_count: 0`, `dialog_rails_duration: null` — but only on the exact request
shape: `config_id` and `options` nest under `guardrails`, and a `model` field is required though
no rail resolves it. At the top level `options` is silently DROPPED rather than rejected, the
dialog rails then run, and the request needs an LLM the config does not have.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0534](0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md) - the observe-only
  guardrails this amends; its `mcpGuardrailsMode` finding is why no DSC change is proposed.
- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md),
  [ADR-0312](0312-route-operator-installs-through-argocd-applications.md) - why the policy is rendered
  from the chart rather than applied out-of-band.
- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md),
  [ADR-0537](0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md) - the saturated
  GPU quota that makes an LLM-free rails design a requirement rather than a preference.

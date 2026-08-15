# Policy: optimization (ADR-0309)

`optimization-policy.yaml` is the governance contract for the platform's
only autonomous-change surface: `components/ai-gateway/app/optimizer.py`'s
bounded tuning controller (WP-42). It enumerates exactly which parameters
may be auto-tuned (initial scope: semantic-cache TTL within a declared
range; routing choices between pre-approved equivalent candidates only),
the allowed ranges, the evaluation window, and the rollback triggers.

Rules:

- **Autonomy acts on runtime configuration only, never Git.** The tuner
  mutates in-process runtime overrides (cache TTL, adapter choice); it
  never writes to `policies/model-routing/` or any other Git-tracked
  file. Promoting a tuned value into Git stays a human-reviewed PR
  (ADR-0304).
- **Classification and authorization are never auto-tunable** - enforced
  structurally in `optimizer.py` (a hard denylist independent of this
  file's content, tested), so no edit here can widen autonomy onto them.
- **Every automated change is recorded with its evidence** (the
  recommendation that motivated it, old/new values, timestamps) and is
  reversible; a quality-floor or error-rate breach inside the evaluation
  window reverts it automatically.
- **`kill_switch: true` disables all autonomy in one change** - refuses
  new actions and reverts everything currently applied. `enabled: false`
  (the shipped default) keeps autonomy off until the operator's own
  observed-cycle sign-off (the WP-42 brief's follow-up).

The file ships inside the ai-gateway image
(`components/ai-gateway/Dockerfile`), alongside
`policies/model-routing/model-routing-policy.yaml` - same bake-in +
`/admin/reload-routing` reload lifecycle.

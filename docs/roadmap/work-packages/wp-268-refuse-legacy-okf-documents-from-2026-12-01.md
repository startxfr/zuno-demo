# WP-268: Refuse legacy OKF documents from 2026-12-01

- **State:** Not started
- **ADRs:** [ADR-0615](../../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (clause 13)
- **Depends on:** WP-267 (no locked release may contain a legacy document)
- **Target repositories:** this one, `startxfr/zuno-demo-agents` and the startx fork of UnifAI
- **Estimated files touched:** the reader hooks of WP-263, the operator dispatch of WP-264, the agents validators, the legacy schema files, the conformance cases

> Dated work package. The operator change must be on the fork's `devel` before the weekly release of Friday
> 2026-11-27 (17:00 UTC), because the operator's 0.1 line freezes from 2026-12-01 to 2026-12-14. The pin waits for the
> owner's go on 2026-12-01.

## Content

1. Every zuno-demo reader refuses `okf_version: v0.2` and `v0.3`, with the message `unsupported okf_version`.
2. The operator drops the legacy schemas and their dispatch. Its docs page lists the change.
3. The agents repository deletes the legacy schemas and switches the legacy conformance cases to "refused".

## Proof

- The conformance cases for legacy documents expect a refusal and pass.
- After the operator pin: every `UnifaiAgentBundle` is Ready and the golden path passes.

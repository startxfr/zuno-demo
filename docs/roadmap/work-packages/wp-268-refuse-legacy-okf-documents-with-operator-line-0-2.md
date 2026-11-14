# WP-268: Refuse legacy OKF documents with the unifai-operator 0.2 line

- **State:** Not started
- **ADRs:** [ADR-0615](../../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (clause 13, amended 2026-11-14)
- **Depends on:** WP-267 (no locked release may contain a legacy document)
- **Target repositories:** this one, `startxfr/zuno-demo-agents` and the startx fork of UnifAI
- **Estimated files touched:** the reader hooks of WP-263, the operator dispatch of WP-264, the agents validators, the legacy schema files, the conformance cases

> Retargeted on 2026-11-14 by the owner. The unifai-operator 0.1 line keeps reading `v0.2` and `v0.3` documents for as
> long as it lives, so the refusal is not in the weekly release of 2026-11-27. It ships with the operator's 0.2 line,
> not before the 0.1 freeze of 2026-12-01 and the 0.2 promotion planned for 2026-12-15 (the fork's calendar). The
> date is set with the owner's go and sent to the fork's maintainers; no WP-268 patch goes to the fork before it.

## Content

1. Every zuno-demo reader refuses `okf_version: v0.2` and `v0.3`, with the message `unsupported okf_version`.
   - A prepared branch exists: `wp-268-readers-refuse-legacy-okf` (1cb48214, not pushed).
   - It merges only once the lock holds a profile 1.0 release, and together with the operator 0.2 pin, so that the
     readers and the operator refuse the same documents.
2. The operator drops the legacy schemas and their dispatch in its 0.2 line. Its docs page lists the change.
3. The agents repository deletes the legacy schemas and switches the legacy conformance cases to "refused".
4. Follow-ups proposed by the fork's maintainers:
   - publish the profile schemas as a versioned artifact with its sha256, for the fork to consume;
   - write a rollback page for the refusal (re-pin the previous corp digest);
   - add a conformance test that fails when the locked release holds a legacy document.

## Proof

- The conformance cases for legacy documents expect a refusal and pass.
- After the operator 0.2 pin: every `UnifaiAgentBundle` is Ready and the golden path passes.

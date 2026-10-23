# UnifAI adoption: closing evidence for WP-149, WP-150 and WP-154

Measured on `demo333` on 2026-10-24 (operator 0.1.32, UnifAI stack `zuno-unifai`, released OKF
bundles of `zuno-demo-agents` v0.1.1, signed keyless).

## WP-150: the operator turns signed OCI bundles into UnifAI objects

- `unifai-operator` 0.1.32 is `Succeeded`; `UnifaiAgentBundle` verifies each bundle (keyless, identity
  `publish.yml@refs/tags/v0.1.1` of `startxfr/zuno-demo-agents`, offline against the committed trusted
  root) before parsing it.
- `arkos`, `comage` and `tekos` are `Ready`; `advantage`, `cognos`, `finage`, `naveo` and `soursage`
  are `Pending` by decision (placeholder agents, ADR-0007: nothing is served). 12 workflows and 13 LLM
  objects are `Ready`.
- The three stacks (`unifai-devel`, `unifai-olm`, `zuno-unifai`) are `Ready` side by side.
- The open questions are settled: the verification key is the Sigstore identity, not a Transit key
  (ADR-0577, ADR-0578); the OKF fields without a UnifAI equivalent (models, guardrails, limits) are
  listed in the bundle status, not dropped.

## WP-149: hybrid RAG, sources and backup

- Hybrid search (dense + sparse, rank fusion) and the group ACL are in the fork and tested
  (238 RAG unit tests); an exact-identifier query and a paraphrase both return their page.
- `tekos-satellite` (90 pages) and `tekos-openshift` (411 pages) are Confluence `UnifaiRAGSource`
  objects; a second sync re-embeds nothing; since 2026-10-23 the Red Hat documentation joins them as
  38 public `web` sources (WP-168).
- Restore: `UnifaiRestore` drill on the live stack (MongoDB and Qdrant restored, counts identical,
  [evidence](unifai-restore-drill-2026-10-23.md)).

## WP-154: the tekos pilot

- Acceptance gates run by 08 on 2026-10-24 as the `eval-*` personas: tekos scenarios 18/18, security
  checks 12/12, platform checks 4/4 (OVERALL PASS), catalogue 8/8; `make d3 test` 15/15.
- Smoke chats just now as `consultant-02` and `sale-01`: tekos names the right Confluence page in
  5 s, arkos writes a one-day workshop plan in 66 s; comage answers that Salesforce is unavailable
  (its sandbox credentials are WP-101, not started).
- The real-key bundle question is closed by the keyless release (WP-158, WP-159, WP-160).
- `unifai-devel` and `unifai-olm` are `Ready`.
- Still open elsewhere: the rate-limit notice in a browser (WP-148, 59).

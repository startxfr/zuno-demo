# ADR index change log

Renumberings, retargetings, band changes and superseding decisions, newest
first. These accumulated as a wall of dated notes at the top of the
[ADR index](README.md) until 2026-09-03, where they had grown longer than the
conventions they surrounded and had begun to contradict the tables beneath
them - one described a table as "now-removed" while it was still there. The
index states what is true now; this file records how it got there.

Per-ADR status is *not* recorded here. The index is the sole authority for it.

## Numbering note (2026-09-03)

ADR-0541 is FREE and is the only gap in the 05xx band - the next author should take it rather than the next sequential number. It was drafted for an ADR putting the endpoint picker back in the data path and moving MaaS aliasing onto `InferenceModelRewrite`, then dropped by user decision: the EPP is deliberately out of the data path (ADR-0521 routes every real rule at the workload Service, leaving only a synthetic anchor rule on the InferencePool), so those CRDs are structurally inert here and making them useful would partially reopen the empty-body incident. ADR-0542 was already written when that landed, so the gap stayed. Separately the same day, ADR-0543 was authored for run_id trace propagation and deliberately did NOT reclaim 0541 - the gap's status was unconfirmed at the time, and renumbering a published ADR would have meant rewriting 25 citations across 15 files a second time to close a cosmetic hole.

## Correction note (2026-09-03)

Three v0.4 model decisions contradicted each other and none
recorded it. ADR-0518 decision 1 made `qwen3.6-27b-instruct` the chat/agents model and classed
`Qwen3.5-9B` as a training base only; five days later ADR-0531 decision 1 made `qwen3.5-9b` the
fleet-wide default, and ADR-0531 decision 3 narrowed ADR-0526 decision 7 from "all four" of
Comage's tasks to three. All three records read `Implemented` and current. Resolved **without a
supersession** — by dated correction notes in each body — because only the *default-model role*
moved: ADR-0518's embedding, training-base and no-infrastructure decisions are all still in force,
and ADR-0526's fine-tune is untouched. No `Status:` field changes, so no index row moves.

Two defects surfaced doing this, both fixed the same day. ADR-0531 decision 1 claims every declared
`(agent, task)` pair carries an explicit routing entry; `arkos/structure-demo` did not, because
decision 7 counted "all three of Arkos's declared tasks" where the bundle declares four — so that
task alone still rode `provider-routing.yaml` file order onto the 27B, while `agents/arkos/README.md`
and WP-31 both claimed it rode the 9B default. It now has an explicit entry pinning the chain file
order already produced (live behaviour unchanged, regenerated matrix byte-identical). And the
architectural roles themselves are now declared rather than implied: `provider-routing.yaml` carries
a `role` key (`default`, `quality`, `reasoning`, `specialized`, `reasoning-external`, `code`,
`general-external`), the OKF authorization matrices render each provider's model id and role instead
of an opaque provider name, and `platform/docs/check_docs.py`'s new `model_roles` check enforces all
three invariants — including ADR-0531 decision 1's own, which nothing had verified.

## Implementation note (2026-09-02, same day)

ADR-0534 moved `Accepted` -> `Implemented` - all
three implementing WPs (WP-107/108/109) closed `Done` with live verification on demo222 the same
day, including one amendment executed live: the `mcpGuardrailsMode` flip was proven destructive
(it disables the LMEvalJob controller) and reverted, the ADR's Phase 2 text corrected in place.
Evidence lives in each WP brief's Live findings; the observe-to-block enforcement transition and
the follow-ups on WP-109's two real findings (a PEFT regression FAIL on the adopted wesh model, a
reproducible Garak MitigationBypass signal) are explicitly deferred, not part of this closure.

## Acceptance note (2026-09-02)

ADR-0534 (Integrate TrustyAI for AI evaluation and guardrails)
moves from `Proposed` to `Accepted` - its three implementing phases now have concrete WP briefs
(WP-107, WP-108, WP-109; see the [roadmap](../roadmap/implementation-roadmap.md) Phase 28
and [versions.md](../roadmap/versions.md)'s v0.7 band). None of the three has started execution
yet. Numbering and `Target` (v0.7) are unchanged; only `Status` moves.

## Retargeting note (2026-09-02)

ADR-0352 (v0.7 -> v0.9) - the day-0
internal/external-mode tiering effort is still `Proposed` and not yet
started (no work package exists for it). It leaves v0.7's long-term/harder
band, whose remaining occupants (ADR-0111, ADR-0115, the OKF v0.2/v0.3
chain) stay blocked on the external GitHub-billing/Quay-cutover decision
and the `zuno-okf` repository provisioning respectively - neither of which
touches ADR-0352. It joins ADR-0307/ADR-0410/ADR-0535 in v0.9. Numbering is
unchanged; only `Target` moves.

## Retargeting note (2026-08-30, third move same day)

ADR-0506, ADR-0507, ADR-0508 (OKF v0.2 -> v0.7) and ADR-0509, ADR-0510 (OKF v0.3 -> v0.7) - all five are `Proposed` and `Not started` (WP-48 through WP-53), gated on an owner-created `zuno-okf` GitHub repository that has not yet been provisioned. Scheduled to land alongside v0.7's other not-yet-started work (ADR-0352, ADR-0534) rather than open a dedicated OKF band with no active work. This is a docs-only move: no code, no repository provisioning, no live cluster action. Numbering (05xx band) is unchanged; only `Target` moves. WP-48 through WP-53 stay tracked in the [OKF roadmap](../roadmap/okf-roadmap.md)'s own tracker, per the precedent set when ADR-0511/ADR-0512 moved out of OKF v0.1 (WP-54/WP-55 stayed tracked there too).

## Retargeting note (2026-08-30, second move same day)

ADR-0307 and ADR-0410 (v0.7 -> v0.9) - both are `Proposed` under Cancelled WP-41 (2026-08-23), which will not pursue the sixth-agent deployment gate that would discharge either. User decision: Naveo is not to be pursued as the new-agent-onboarding proof before at least v0.9, possibly later - so rather than sit in v0.7's long-term/harder band, they move on to join ADR-0535 in the newer v0.9 band. This is a docs-only move; the merged template generator (`platform/templates/agent/`) and Naveo agent bundle (`agents/naveo/`) are untouched. Numbering is unchanged; only `Target` moves. (Earlier the same day: ADR-0307 and ADR-0410 moved v0.4 -> v0.7 - both are `Proposed` under Cancelled WP-41 (2026-08-23) - rather than leave them blocking v0.4's closure indefinitely. v0.4 has no remaining open items after that first move.)

## Retargeting note (2026-08-30)

ADR-0517 (v0.6 -> v0.8) - the demo333 from-scratch redeploy is deprioritized behind v0.7's release-automation work. v0.6 was created solely for this ADR and is now a vacant band; a new v0.8 band is opened to carry it (same goal text, unchanged Status/scope). Numbering is unchanged; only `Target` moves.

## Retargeting note (2026-08-30)

V0.7 is split by done-ness into a short-term closeout band and a long-term/harder band. ADR-0105, ADR-0206, ADR-0213 and ADR-0218 (v0.7 -> v0.6) - all four are already closed out (WP-22/WP-23 Done, ADR-0213 Superseded, ADR-0218 Implemented) and only need formal retargeting; they fill the band left vacant by ADR-0517's move to v0.8. ADR-0111 and ADR-0115 stay in v0.7 (externally blocked on the same WP-04 GitHub-billing lock), joined there by ADR-0352 (a large, not-yet-started day-0 tiering effort, previously carried in v0.7's now-removed second table). Numbering is unchanged; only `Target` moves.

## Superseding note (2026-08-30)

New ADR-0535 (v0.9, Proposed) adopts RHTAS as the platform's artifact-signing mechanism, superseding ADR-0420 (v0.4 -> Superseded by ADR-0535). This is a product-demonstration decision, not a security-driven reversal - ADR-0420's Vault Transit mechanism stays technically sufficient and cheaper; RHTAS is adopted to demonstrate Red Hat's own trusted-supply-chain product on this platform, the same rationale already behind AAP/TrustyAI/OpenShift Lightspeed. WP-068/WP-069/WP-070 (ADR-0420's implementing WPs) are unaffected and remain `Done` - real work already delivered, not retroactively invalidated. A new v0.9 band is opened for this ADR (v0.6 was reused earlier today for an unrelated closeout cluster, v0.7/v0.8 are already occupied by differently-blocked work); see `docs/roadmap/versions.md`.

## Retargeting note (2026-08-26)

ADR-0111 (v0.1 -> v0.7, Partially implemented -> Deferred) - its sole remaining gap (immutable chart image tags) is blocked on the same WP-04 external GitHub billing lock that already parked ADR-0115 in Deferred status under the v0.7 milestone; ADR-0111 now groups there alongside it. Numbering (01xx band) is unchanged; only `Target`/`Status` move.

## Retargeting note (2026-08-26)

ADR-0105 (v0.1 -> v0.7) and ADR-0206 (v0.2 -> v0.7) move to the v0.7 band as a separate, unrelated deferred-items group - not part of WP-04's GitHub-Actions release-automation scope already there. Status unchanged for both (`Partially implemented`); only `Target` moves.

## Retargeting note (2026-08-24, evening)

ADR-0354 (Add Ansible Automation Platform as a new Day 0 component, v0.3) is amended in place - it was never implemented, so this is a correction rather than a superseding decision. Placement moves from a Day 0 sequence ADR-0060 has since retired (`... keycloak → aap → machines ...`) to Day 1, immediately after `openshift_oauth`; scope is split into two components (`aap` for the platform itself, `aap-config` for repository/Job-Template registration, mechanism decided from a live CRD inventory rather than assumed); sizing is explicitly non-HA; `Target` moves v0.3 -> v0.2. The file is renamed to `0354-add-ansible-automation-platform-as-a-day-1-component.md` to keep the filename in sync with the corrected title. ADR-0355 is a new companion ADR (v0.3) covering the follow-on `mcp-aap` server that lets agents launch/read AAP. ADR-0418 (execute Day 0/Day 1 operations as AAP Job Templates, v0.4) is unchanged.

## Retargeting note (2026-08-24, afternoon)

Three new platform version bands added - v0.5 (make the MaaS governance plane live and used by agents), v0.6 (prove platform automation via a from-scratch redeploy on a new cluster), v0.7 (GitHub-Actions-based release automation). ADR-0201/ADR-0511/ADR-0512 move again, this time from the morning's generic v0.3 catch-all into the dedicated v0.5 MaaS milestone (same root blocker, better-scoped home). ADR-0115 (v0.1 -> v0.7) joins WP-04's GitHub Actions release-pipeline scope. ADR-0517 is a new small ADR authored for v0.6 (demo333 cluster redeploy). No new ADR numbering band was reserved - v0.5/v0.7 reuse existing ADR numbers, and ADR-0517 simply takes the next free sequential number after ADR-0516.

## Retargeting note (2026-08-24, morning)

ADR-0201 (v0.2 -> v0.3) and ADR-0511/ADR-0512 (OKF v0.1 -> v0.3) all retargeted together - the upstream Kuadrant wasm-shim defect blocking WP-27/WP-54 has no repo-side fix, and ADR-0512/WP-55 has a hard `Depends on: WP-54`, so it moves with ADR-0511 rather than sitting blocked inside their original milestones. Numbering (02xx/05xx band) is unchanged; only the `Target` column moves.

## Banding note (2026-08-18)

The 05xx band is reserved for the OKF stream (ADR-0501, its own version line OKF v0.1 – OKF v0.3, tracked in the [OKF roadmap](../roadmap/okf-roadmap.md)); a future platform v0.5 stream takes the next free band.

## Renumbering note (2026-08-15)

Three decisions were re-streamed to the version that actually delivers them. ADR-0113 -> ADR-0350 (v0.1 -> v0.3, the CRD/operator is delivered by ADR-0327/ADR-0308), ADR-0348 -> ADR-0211 (v0.1 -> v0.2), ADR-0306 -> ADR-0410 (v0.3 -> v0.4). The old numbers are retired; each moved record carries a `Renumbered:` line.

## Renumbering note (2026-08-13)

The roadmap reorganization moved open decisions into the v0.1 stream. ADR-0026 -> ADR-0113, ADR-0049 -> ADR-0114, ADR-0051 -> ADR-0115 (unimplemented 00xx records), and ADR-0207 -> ADR-0116, ADR-0210 -> ADR-0117 (promoted from v0.2 as concretely implementable). The old numbers are retired; each moved record carries a `Renumbered:` line.

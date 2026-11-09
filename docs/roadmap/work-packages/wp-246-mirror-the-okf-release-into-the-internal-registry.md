# WP-246: Mirror the OKF release into the internal registry

- **State:** Not started (needs the owner's go for each cluster step)
- **ADRs:** [ADR-0611](../../adr/0611-mirror-the-admitted-okf-release-into-the-internal-registry.md)
- **Depends on:** [WP-242](wp-242-canary-namespace-pattern.md)
- **Related:** [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md),
  [WP-161](wp-161-fetch-okf-content-at-pod-start.md), [ADR-0609](../../adr/0609-rehearse-on-canary-namespaces-of-demo333.md)
- **Target:** v0.17
- **Estimated files touched:** ~8: `platform/supply-chain/admit_okf_bundle.py` and its tests, the two gateway
  Deployments and NetworkPolicies, the `agents` and `mcp` roles, the promotion workflow, the demo-day runbook

> Why: on 2026-11-09 a gateway pod hung in `okf-fetch` on a `quay.io` blob served from a CDN address the EgressFirewall
> does not allow (3 of 10 `cdn01.quay.io` addresses reachable). A retry bounds it; the mirror removes it.

## Goal

A gateway pod starts with `quay.io` unreachable, from the internal registry, with the same digest and the same offline
verification.

## Steps

1. **Measure in a canary.** In `zuno-canary-wp-246`, push the corp artifact with `oras copy -r` to the internal
   registry; read it back with `oras` and `cosign verify`; record whether signatures and attestations survive and
   whether referrers are listed. If not, switch to a small registry in `zuno-ai-build` and amend ADR-0611.
2. **`mirror` step.** Add it to `admit_okf_bundle.py` with tests (digest preserved, failure on mismatch, no secret
   printed), run by `make d3 admit agents`.
3. **Chart.** `okf.fetch.mirrorReference` derived from the locked reference; the init container tries the mirror, then
   `quay.io`, each with the existing timeout and retry; a non-digest reference still fails the render.
4. **NetworkPolicy.** Egress from both gateways to the internal registry only; EgressFirewall untouched.
5. **Promotion check.** The promotion pull request runs the `mirror` step and cannot merge if it fails.
6. **Live on demo333** with the owner's go and a golden path before and after: roll one gateway from the mirror.
7. **Drill.** In the canary, block `quay.io` and show a gateway pod starting from the mirror; set a forged digest and
   show the pod stays in `Init`.

## Result of step 1 (2026-11-09)

Canary `zuno-canary-wp-246` (egress to the registry on 5000 only), OpenShift 4.22.20, corp artifact of release 0.14.3
copied from `quay.io` through the registry's external route. The internal registry **fails the gate**:

- It cannot store an artifact by digest alone: the push returns 201, but the image is not linked to the ImageStream and
  every read answers `manifest unknown`. The ImageStream must exist first, and the artifact must be pushed **with a
  tag**; then it reads back by digest.
- It does not hold the signature. The Sigstore bundle is an OCI 1.1 referrer of the corp artifact. The registry has no
  Referrers API, and the tag-schema fallback (an index tagged `sha256-<digest>`) is refused with a 500 at
  `CreateImageStreamMapping`. `cosign verify --offline` through `admit_okf_bundle.py verify` then answers "no signatures
  found" on the mirror, while the same command passes on `quay.io`.
- Pulling the blobs works; what fails is trust.

So the internal registry is not a usable mirror for signed OKF artifacts. Next: step 1 again against a small OCI
registry in `zuno-ai-build` (clause 1 of ADR-0611 names it); it needs the owner's go and an image source that the
cluster can pull. The canary namespace stays until that is measured, then it is removed.

## Acceptance

With `quay.io` blocked, a new mcp-gateway and a2a-gateway pod reach Ready from the mirror; a forged digest is refused;
the golden path passes 14 of 14; no CDN range was added to the EgressFirewall.

## Open questions

- Does the internal registry list referrers, or do signatures only resolve by tag? Answered by step 1.
- Retention: keep the last three releases in the mirror?

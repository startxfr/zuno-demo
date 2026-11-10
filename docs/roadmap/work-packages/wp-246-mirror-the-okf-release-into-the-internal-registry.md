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
4. **The mirror registry as a chart** (`okf-mirror`: zot pinned by digest, PVC, service-CA TLS, ingress NetworkPolicy
   admitting the two gateways only). The gateways' policies are ingress-only, so they need no egress rule; the
   EgressFirewall is untouched.
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

## Result of step 1, repeated with zot (2026-11-09)

Same canary: zot v2.1.22 (`ghcr.io/project-zot/zot-linux-amd64`, pinned by digest `sha256:46f688dc…`), one replica,
`emptyDir`, no authentication, reachable only inside the namespace. **The gate passes.**

- `oras cp -r` of the corp artifact keeps the digest (`sha256:2918e463…`) and lists the Sigstore bundle as a referrer.
- That is **not enough**: `cosign verify` still said "no signatures found" until the legacy tags
  `sha256-<digest>.sig` and `sha256-<digest>.att` were copied too (`oras cp -r` does not copy tags that merely name a
  digest). With them, `verify` and `verify-attestation --offline` pass, from the workstation and from a pod in the
  canary reading `zot.zuno-canary-wp-246.svc:5000` (cosign needs `--allow-http-registry --allow-insecure-registry` on
  plain HTTP). `oras pull` from the service returned the four layers; `quay.io` was unreachable from that pod.
- **The index names `quay.io` itself.** `okf-index.json` lists each agent as `quay.io/zuno/okf-<agent>@sha256:…`.
  A pull of the corp artifact from the mirror would still fetch the eight agent artifacts from `quay.io`. The consumer
  must replace the registry prefix of those references with the mirror's (the digest, which the signature covers,
  does not change), and the `mirror` step must copy every agent artifact with its `.sig` and `.att` tags.
- The registry used here is plain HTTP; the real one serves TLS from the service CA (to do in step 3).

Not yet measured: mirroring the eight agent artifacts, extraction end to end through `okf-fetch` from the mirror, and
the forged-digest case. The canary (namespace, zot, ImageStream `signer`) stays for steps 2 to 7. One RoleBinding I
tried to add in `zuno-ai-build` to let the canary pull the signer image was refused by the auto-mode classifier and
not created; the image was copied into the canary's own ImageStream instead.

## Result of step 2 (2026-11-09)

`admit_okf_bundle.py` gains `mirror` (verify at the source, `oras cp -r` of the corp artifact and the eight agent
artifacts plus their `.sig` and `.att` tags, digest checked after the copy, verify again from the mirror) and
`--mirror` / `--plain-http` on `verify` and `extract` (the agent references of the index are read from the mirror;
plain HTTP applies to the mirror host only, the source stays on TLS). Four new unit tests; the supply-chain suite
passes (122). Run live against zot in the canary through a port-forward: 9 artifacts mirrored in 95 s, then
`extract` from the mirror alone returned VERIFIED, release 0.14.3, 8 agents.

Still to do: wiring the step into `make d3 admit agents` behind `zuno_okf_registry_mirror` (step 2 tail), then steps 3
to 7.

## Result of step 3 (2026-11-09)

`okf.fetch.mirror.{prefix,plainHttp}` in the mcp-gateway and a2a-gateway charts: set, the init container reads the
mirror first (2 attempts of 60 s), clears `/okf` and falls back to the source registry (4 attempts of 150 s); the
pod-template gains the annotation `zuno.startx.fr/okf-mirror`. Default empty: the script block gains an inert `if`, which
changes the pod template, so merging rolls both gateways once. Run in the canary with the rendered script and the
new `admit_okf_bundle.py`: from the mirror with `quay.io` blocked, exit 0 (VERIFIED, release 0.14.3, 8 agents); with a
digest the mirror does not hold, the mirror is refused, the fallback tries `quay.io` (blocked) and the pod never
succeeds (fail closed). The signer image must be rebuilt for the real pods to know `--mirror` (step 6).

## Result of step 4 (2026-11-10)

Chart `gitops/charts/okf-mirror` (zot v2.1.22 pinned by digest, Recreate, one 1 Gi volume, read-only root filesystem,
ingress NetworkPolicy for `mcp-gateway` and `a2a-gateway` pods, plain HTTP inside the mesh), added to the hardening
check (9 checks pass). Rendered into the canary: Ready, volume bound, and `admit_okf_bundle.py mirror` filled it
(9 artifacts, verified again from the mirror). No Application and no role installs it yet, so nothing is deployed.

Not proven here: that the NetworkPolicy excludes other pods. The canary's own namespace-wide policy already admits
every pod of the namespace (policies add up), so an unlabelled pod read the mirror too. Measure it in `zuno-ai-run`,
which has pod-level policies only, at step 6. Also open: the mesh in strict mTLS with a port-forward write.

## Acceptance

With `quay.io` blocked, a new mcp-gateway and a2a-gateway pod reach Ready from the mirror; a forged digest is refused;
the golden path passes 14 of 14; no CDN range was added to the EgressFirewall.

## Open questions

- Does the internal registry list referrers, or do signatures only resolve by tag? Answered by step 1.
- Retention: keep the last three releases in the mirror?

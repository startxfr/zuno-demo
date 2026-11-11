# ADR-0611: Mirror the admitted OKF release into the internal registry so pod start does not depend on quay.io

- **Status:** Implemented
- **Target:** v0.17
- **Date:** 2026-11-09
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0353](0353-source-runtime-images-by-family-internal-registry-or-quay-io-zuno.md), [ADR-0577](0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md), [ADR-0609](0609-rehearse-on-canary-namespaces-of-demo333.md)

## Context

ADR-0580 makes mcp-gateway and a2a-gateway fetch the corp OKF release from `quay.io` in an `okf-fetch` init container,
and names a mirror as the mitigation if that pull is not reliable ("the mirror option of the operational considerations").
WP-161 left it open: "the pull from quay.io works directly on demo333, so the registry mirror is not needed there".
On 2026-11-09 that stopped being true.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | A new mcp-gateway pod stayed in `Init` because `oras` stalled on a blob; killing the process let the init restart and pass. | Session notes of 2026-11-09; golden path 14/14 after |
| F2 | The namespace egress rule is an OVN `dnsName` rule: only the addresses the node itself resolved are allowed, and a blocked connection times out instead of being refused. | Probe of 2026-11-09 from a throwaway pod in `zuno-ai-run` |
| F3 | Measured reachability by name: `quay.io` 10 of 12 addresses, `cdn01.quay.io` **3 of 10** (Akamai), `cdn02.quay.io` 4 of 4, `cdn03.quay.io` 11 of 12. An address allowed by any name rule works whatever name the client used. | Same probe; 40 DNS rounds, TCP+TLS to each address, 4 s timeout |
| F4 | `oras` had no timeout, so one blob redirected to a blocked `cdn01` address hung the init for good. A per-attempt timeout with four attempts now bounds it (commit a10c10b3), which lowers the odds of a stall but keeps the dependency. | `gitops/charts/{mcp,a2a}-gateway/templates/deployment.yaml` |
| F5 | The same mechanism stalled large S3 copies earlier. | Memory note on the S3 `dnsName` pool |

## Decision

**Admission copies the admitted OKF release, by digest, into the internal registry, and `okf-fetch` pulls from there
first. `quay.io` stays only as a second source, and no CDN address range is opened.**

1. **Gate on a measurement.** Before anything is built, WP-246 proves in a canary namespace (ADR-0609) that the
   mirror stores these artifacts with their signatures and that `cosign` and `oras` read them back.
   **Measured 2026-11-09: the OpenShift internal registry fails** (no Referrers API, the tag-schema fallback is refused,
   `cosign verify` finds no signature; see WP-246). The mirror is therefore a small OCI registry in `zuno-ai-build`
   (or `zuno-ai-run`). **Measured the same day on zot v2.1.22: it passes**, provided the legacy `.sig` and `.att` tags
   are copied with the artifact; the rest of the decision does not change. Every `image-registry...:5000`
   address in clauses 2 and 6 reads as that registry.
2. **Mirror at admission.** `admit_okf_bundle.py` gets a `mirror` step run by `make d3 admit agents`: `oras copy -r` of
   the corp artifact, every agent artifact it lists, and their signatures and attestations, to
   the mirror registry. The `.sig` and `.att` tags that `cosign verify` reads are copied
   too. The digest is identical to `quay.io`'s; the step fails if it is not.
3. **Pull from the mirror, verify as before.** `okf-fetch` tries the mirror reference, then `quay.io`, with the retry
   and timeout of commit a10c10b3 on each. Verification is unchanged: offline, by the Sigstore identity of ADR-0578,
   pinned by the digest in `platform/okf/agents.lock`. The mirror is an untrusted transport; it cannot widen what a pod
   accepts. `okf-index.json` names each agent artifact on `quay.io`, so the consumer replaces that registry prefix with
   the mirror's; the digest, covered by the signature, is unchanged.
4. **The lock stays the only pin.** The chart derives the mirror reference from the locked reference; no second digest is
   recorded anywhere.
5. **Mirror before merge.** A promotion pull request cannot roll the gateways before the mirror holds its digest. The
   promotion check runs the `mirror` step, and the merge is blocked if it fails. The `quay.io` fallback covers the
   window if a pod restarts earlier anyway.
6. **Network.** The gateways' namespace policies are ingress-only, so the gateways need no egress rule. The mirror
   registry gets an ingress NetworkPolicy that admits only the two gateways. It runs in the meshed `zuno-ai-run` namespace, so the mesh carries the traffic
   over mTLS and the registry itself speaks plain HTTP (a service-CA certificate would need that CA in the init
   container, for no gain inside the mesh). Admission writes through a port-forward, not through a route. The EgressFirewall is left as it is: no Akamai
   or other CDN range is added.
7. **Scope.** Only the OKF release fetched by `okf-fetch`. The bundles `unifai-operator` pulls (ADR-0564) and the
   `quay.io/zuno` runtime images (ADR-0353) are not covered; they are named here so nobody assumes otherwise.

## Alternatives considered

- **Open the CDN address ranges in the EgressFirewall.** Akamai's space is large and shared with unrelated services; it
  would be a wide hole for one pull. Rejected.
- **Keep only the retry and timeout.** It is in place and bounds a stall, but a pod start still depends on a third-party
  CDN the cluster cannot control. Kept as the fallback, not as the answer.
- **Bake the release into the image.** ADR-0580 removed this on purpose: a prompt edit would need an image build again.
- **A pull-through cache of `quay.io`.** Still pulls from the same CDN on a miss and serves referrers unevenly; not
  measured. Revisit if clause 1 fails.

## Consequences

- A new gateway pod starts without leaving the cluster, which also helps the freeze and rehearsal windows.
- Promotion gains one step and one failure mode (mirror push), caught before merge.
- The internal registry holds a few small artifacts per release; old ones are pruned with the release history.

## Security considerations

The digest and the keyless signature decide trust, not the registry, so a modified mirror yields a refused pod, not a
changed agent. The push credential is a short-lived ServiceAccount token of `zuno-ai-build` held by the operator running
admission; no secret enters git. The change shrinks the pod's outbound reach rather than widening it.

## Operational considerations

`make d3 admit agents` now also writes to the cluster (the mirror). Re-measure with the 2026-11-09 probe after any
firewall change. A promotion cycle is timed before and after to show the effect.

## Work packages

[WP-246](../roadmap/work-packages/wp-246-mirror-the-okf-release-into-the-internal-registry.md) (measurement, `mirror`
step, chart, NetworkPolicy, drill with `quay.io` blocked).

## Update 2026-11-11: retention and the check before rolling

Decisions of the owner. **The mirror keeps the last three releases the lock has pinned**, in the order of the git
history of `platform/okf/agents.lock` (one commit per promoted release). `make d3 admit agents` runs `prune` after a
successful `mirror`: it lists what no kept release names (release artifacts with their referrers, and the legacy
`.sig` / `.att` tags of dropped artifacts) and deletes nothing unless `OKF_MIRROR_PRUNE=1`, so every deletion is a
decision of the operator running admission from the workstation. `prune` refuses to run when the locked release is not
on the mirror, skips a kept release the mirror never received (the mirror fills naturally at each promotion, nothing is
back-filled), and leaves tags it does not recognise alone. Measured the same day: one release is about 100 KB of
manifests and layers, so the 1 Gi volume holds the three releases with a large margin and is not resized.

**Clause 5 holds at the roll, not at the merge.** The promotion workflow runs on GitHub and cannot reach a registry
inside the cluster, so it cannot check the mirror. The check lives where the cluster is reachable:
`ansible/tasks/okf_mirror_holds_lock.yml` runs in `make d2 check agents` and first in `make d2 install mcp`, which also
installs a2a-gateway, and stops with the command that feeds the mirror when the locked digest is not on it. The
`quay.io` fallback of clause 3 still covers a pod that restarts before the mirror is fed.

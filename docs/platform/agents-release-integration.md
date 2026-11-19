# Agents release integration: how zuno-demo consumes zuno-demo-agents

Last reviewed: 2026-11-19

Agent definitions and the corp policies live in
[startxfr/zuno-demo-agents](https://github.com/startxfr/zuno-demo-agents), as signed releases in the Zuno OKF
profile 1.0 ([ADR-0615](../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md)).
The format, authoring and release of a bundle are documented there
([docs/](https://github.com/startxfr/zuno-demo-agents/tree/main/docs)). This page covers the platform side: what
zuno-demo pins, how a release is promoted, admitted and mirrored, who reads it, and how to roll back.

The agents repository never calls this platform. zuno-demo decides when to take a release
([ADR-0576](../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md),
[ADR-0580](../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)).

## The pin

`platform/okf/agents.lock` holds one line: the `okf-corp` reference, pinned by digest. It is the only file that names
an agents release. It changes through a promotion pull request, or through
`make d3 admit agents RELEASE=vX.Y.Z UPDATE_LOCK=1`, and never by hand.

## Promotion

`.github/workflows/okf-promote.yml` runs every day at 06:17 UTC, or on demand (`release`, `base`, default `devel`):

1. `admit_okf_bundle.py latest` finds the newest release and compares it with the lock.
2. `admit_okf_bundle.py admit --release vX.Y.Z --update-lock` does four things:
   - **verifies** offline the keyless signatures (identity `publish.yml` on a `v*` tag) and the contract-tests
     attestations, against `platform/okf/sigstore/trusted_root.json`;
   - **extracts** the release;
   - **validates** that every preferred model, tool and knowledge domain is servable here;
   - **checks** that no bundle widens the corp policies, using a level comparison so that profile 1.0 and v0.3 are
     both narrowed.
3. The generators write the platform configuration derived from the release:

   | File | Written by | Read by |
   |---|---|---|
   | `platform/okf/stack-config.generated.yaml` | `generate_stack_config.py` | Keycloak groups, the `unifai` role (`UnifaiAgentBundle` per agent), the mcp role (the corp reference) |
   | `gitops/charts/models/values.agents.generated.yaml` | `generate_stack_config.py` | MaaS subscriptions of the local models |
   | `gitops/charts/ai-gateway/files/{model-routing,guardrails-modes,classification-floors}.generated.yaml` | `generate_stack_config.py` | ai-gateway (mounted) |
   | `gitops/charts/connectivity-link/templates/quota-*ratelimitpolicies.yaml`, `components/ai-gateway/app/quota_*.yaml` | `generate_quota_enforcement.py` | Kuadrant, ai-gateway |

4. A pull request `okf-promote/vX.Y.Z` moves the lock and the generated files, with a summary of what changes.
   **Merging it is the promotion.**

The scheduled run uses the workflow file of `main`. If `main` lags `devel`, run it "from: devel", and check that the
pull request carries the quota files.

## Mirror before roll

The gateways read the release from the internal Quay (ADR-0611, ADR-0612). Before rolling a promotion, copy it:

```sh
OKF_MIRROR_TO=quay-quay-zuno-registry.apps.<domain>/zuno make d3 admit agents
```

This verifies the release, copies the corp artifact, every agent artifact and their `.sig`/`.att` tags by digest,
verifies them again from the mirror, and prunes old releases (the last 3 are kept). `make d2 install mcp` refuses
to roll while the mirror lacks the locked digest (`ansible/tasks/okf_mirror_holds_lock.yml`).

## Who reads the release

| Consumer | When | How |
|---|---|---|
| mcp-gateway, a2a-gateway | At pod start | The `okf-fetch` init container runs `admit_okf_bundle.py extract` into `/okf`, from the mirror first and then the source registry. Any verification failure keeps the pod in Init. The code comes from the `supply-chain-signer` image, so a change to admission needs that image rebuilt. |
| unifai-operator (startx fork) | On reconcile | `make d2 install unifai` renders one `UnifaiAgentBundle` per agent from `stack-config.generated.yaml`: the digest reference, keyless verification and the ceilings. The operator pulls, verifies, validates against its embedded schemas and emits the agents. See the [operator page](https://github.com/startxfr/UnifAI/blob/devel/fork/unifai-operator/docs/okf-agent-bundles.md). |
| ai-gateway, mlops | At image build | Their build stage verifies and extracts the locked release (`platform/okf/release_cache.py`). Rebuild them after a promotion. |
| Ansible checks, evaluations, `check_docs.py`, acceptance gate | At run time | `platform/okf/release_cache.py` extracts the release once per digest into `.cache/okf-release/<digest>/` and verifies it first. |

Every reader dispatches on the document version with the same table
([ADR-0615](../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) clause 5):
profile 1.0, or legacy v0.2/v0.3 until the unifai-operator 0.2 line (WP-268). The legacy refusal is **not active yet**:
every 0.1 operator release from 0.1.71 reads both (0.1.70 and earlier refuse profile 1.0), and the refusal of legacy
bundles arrives with the operator line 0.2, from 2027-01-05 (R-556). The operator's side is in
[its OKF page](https://github.com/startxfr/UnifAI/blob/devel/fork/unifai-operator/docs/okf-agent-bundles.md). The conformance cases shipped in the corp artifact keep the readers
aligned.

## Rolling a promotion

Run these after the promotion pull request is merged. Each step needs the owner's go:

1. Copy the release into the mirror (the `make d3 admit agents` command above).
2. Run `make d2 install mcp` (both gateways) and `make d2 install unifai` (the bundles). The gateways pick up the new
   release on their next pod start. If ArgoCD self-heal reverts a rollout restart, delete the pod instead.
3. Rebuild ai-gateway and mlops.
4. Check:
   - both `okf-fetch` logs say `VERIFIED`;
   - every `UnifaiAgentBundle` is `Ready` on its new digest;
   - the golden path passes (ADR-0605).

### Lessons from the v1.1.1 and v1.1.2 rollouts (2026-11-18 and 2026-11-19)

- **Give the mirror step a throwaway `DOCKER_CONFIG`.** Use it for both `oras login` and `make d3 admit agents`, for
  example `DOCKER_CONFIG=$(mktemp -d)`. `offline_trust()` in `platform/supply-chain/admit_okf_bundle.py` points `HOME`
  at an empty directory, so cosign does not see `~/.docker`; a login stored there is ignored. The fix in the code is
  deferred.
- **`make d2 install mcp` is required even for a prompt-only release.** The gateways fetch the corp bundle at pod
  start (the `okf-fetch` init container), so a release that changes no code still needs the pods replaced. Confirmed on
  v1.1.1: acceptance case D9 failed until the roll.
- **Do not run `make d2 check agents` right after a stresstest.** On 2026-11-19 at 01:12Z, MaaS answered 429 on
  gpt-oss and the gate fell to 15 of 19 with one security case failing. At 01:27Z, after the quota window reset, the
  same gate passed 18 of 19. A 429 in the gate is the token limit, not the release: wait for the window, then rerun.
  A SaaS failure shows differently, see [rotating a SaaS provider key](saas-provider-key-rotation.md).

## Roll back

Revert the lock commit (and its generated files), then repeat the steps above. The previous release must still be in
the mirror: `prune` keeps the last 3. Nothing is ever re-tagged in the agents repository; a broken release is fixed by
a new one. To stop one agent at once, whatever the pin, use the revocation list
([agent-revocation-runbook.md](agent-revocation-runbook.md)).

## Related

- [Release sequence](release-sequence.md): the steps of a platform release that includes an agents release.
- [ADR-0580](../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md) (pin and
  promotion), [ADR-0581](../adr/0581-derive-stack-configuration-from-the-admitted-corp-bundle.md) (generated
  configuration), [ADR-0611](../adr/0611-mirror-the-admitted-okf-release-into-the-internal-registry.md) (mirror),
  [ADR-0615](../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (profile 1.0).

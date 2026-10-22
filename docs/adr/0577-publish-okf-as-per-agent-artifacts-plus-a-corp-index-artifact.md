# ADR-0577: Publish OKF as per-agent artifacts plus a corp index artifact

- **Status:** Accepted
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md) in part (clause 1, artifact layout only; amends the rest)
- **Related:** [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md), [ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md), [ADR-0581](0581-derive-stack-configuration-from-the-admitted-corp-bundle.md)

## Context

ADR-0564 publishes one OCI artifact per agent bundle:
`platform/supply-chain/publish_okf_bundle.py` builds one deterministic
tar.gz layer (mtime 0, uid/gid 0, mode 0644) of the whole bundle directory,
pushes it with `oras push` as `application/vnd.zuno.okf.bundle.v1` to
`<prefix>/okf-<agent>:okf-<digest[:16]>`, and carries the Transit signature
of the content digest in the annotation `zuno.okf.signature`. The layer
includes `tests/`, READMEs and the generated `deployment/` snapshots,
because the content digest of `sign_okf_bundle.py` covers every file.

With ADR-0576 the corp policies leave `zuno-demo` too, and they bound every
agent. An agent artifact alone no longer carries what the platform needs to
admit it: a bundle is valid only against a given version of the corp
policies. The user also asked for two publication grains: one agent, or the
whole organisation at once.

## Decision

**1. One artifact per agent, runtime files only.** Each agent is published
to `<registry>/okf-<agent>` (default registry `quay.io/zuno`) with artifact
type `application/vnd.zuno.okf.bundle.v2` and one layer
`application/vnd.zuno.okf.bundle.v2.tar+gzip`. The layer holds what a
consumer reads: `agent.okf.md`, `tasks/`, `prompts/`, `skills/`, `tools/`,
`rag/`, `policies/`. `tests/` and `README.md` files stay in git: the tests
run in CI and their result travels as an attestation (ADR-0578 clause 3),
not as payload. Manifest annotations: `org.opencontainers.image.source`
(the repository URL), `org.opencontainers.image.revision` (the git commit),
`zuno.okf.version` (the schema version, `v0.2` or `v0.3`) and
`zuno.okf.agent`.

**2. One corp artifact, which is the release.** `<registry>/okf-corp` with
artifact type `application/vnd.zuno.okf.corp.v1` holds two layers:

- `application/vnd.zuno.okf.policies.v1.tar+gzip`: the corp policy set of
  ADR-0576 clause 1;
- `application/vnd.zuno.okf.index.v1+json`: an index listing, per agent, its
  name, its artifact reference `okf-<agent>@sha256:...` and its schema
  version, plus the `platform-contract.json` digest the release was
  validated against.

The corp artifact is what `zuno-demo` pins (ADR-0580). Agent artifacts are
reached only through it, by digest.

**3. Two publication grains, one rule.** A tag `v<semver>` on
`zuno-demo-agents` publishes every agent whose content changed plus a new
corp artifact. A tag `<agent>-v<semver>` publishes that agent and a new corp
artifact whose index differs from the previous one by that agent's line
only. Either way a new corp digest is produced; an agent artifact never
becomes deployable on its own.

**4. Digests are the only references; tags are aliases.** Tags
(`v1.4.0`, `tekos-v1.2.0`, `latest`) exist for humans browsing the registry.
Every consumer and every index entry uses `@sha256:`.

**5. Builds are reproducible.** The layer builder is the one of
`publish_okf_bundle.py` (sorted entries, fixed mtime, owner and mode), moved
into `zuno-demo-agents` as a library. Building twice from one commit yields
one digest; CI checks it by building twice.

**6. What changes in ADR-0564.** Clause 1's layout and its 2026-10-17
amendment (content-digest signature in an annotation, media type `v1`) are
replaced by this record and by ADR-0578. The `UnifaiAgentBundle` kind, its
ceilings, the verify-then-parse order, the shapes and the OKF-to-UnifAI
mapping (clauses 2 to 7) stand; the operator reads `v2` and, during the
transition, `v1`.

## Consequences

The platform admits one coherent release instead of n independent agents,
so an agent can never be deployed against corp policies it was not
validated with. A single-agent change still costs one small corp artifact,
which is cheap.

Consumers that read `tests/` from the bundle (the acceptance-gate ConfigMap
generator in `ansible/roles/agents/kustomize/`) read from git or from
evaluations instead (WP-165).

## Security considerations

Each artifact is signed on its own manifest digest (ADR-0578). The corp
index binds agent digests, so verifying the corp signature and then each
listed agent signature proves the whole set came from the same release
workflow. A consumer must verify both; verifying only the corp artifact
proves nothing about layers it did not pull.

## Operational considerations

The registry namespace is a parameter (`OKF_REGISTRY` in the publish
workflow); quay.io is the default. The repositories are public, so pulling
needs no credential; pushing uses a quay.io robot account held as a GitHub
Actions secret.

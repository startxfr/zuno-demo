# ADR-0564: Deliver OKF bundles to unifai-operator as signed OCI artifacts

- **Status:** Superseded in part by ADR-0577 and ADR-0578 (2026-10-22) - clause 1 (artifact layout, and the Transit content-digest signature of its 2026-10-17 amendment) and the key-only `spec.verify` of clause 2 are replaced; the `UnifaiAgentBundle` kind, ceilings, verify-then-parse order, shapes, OKF-to-UnifAI mapping and digest-bump cadence stand.
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md) (enforce OKF bundle signing and validation)
- **Related:** [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md), [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md), [ADR-0420](0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md), [ADR-0509](0509-deliver-okf-content-as-mounted-versioned-artifacts.md), [ADR-0510](0510-make-the-aiagent-operator-watch-the-zuno-okf-repository.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

An agent is defined by its OKF bundle, `agents/<name>/`: `agent.okf.md`
(frontmatter `zuno.graph_shape`, `zuno.tasks`, `zuno.rag.top_k`,
`zuno.model.preferred_classification`, `zuno.access.groups`, `zuno.ui`),
`tasks/*.md` (`zuno.allowed_tools`, `zuno.allowed_knowledge`,
`zuno.max_tokens`), `prompts/`, `tools/`, `policies/`, `rag/` and `tests/`. The
schemas are in `platform/okf/schema/`. Today two consumers read a bundle. First,
`components/agent-runtime/app/registry.py` loads every bundle baked into its
image and fails fast (ADR-0039). Second, `operator/aiagent-operator` records an
`okfBundleRef` string on the `AIAgent` CR without resolving it (ADR-0327,
ADR-0507 clause 3). Live `AIAgent` CRs exist for Arkos and Naveo (ADR-0308
status).

Bundles are signed in-cluster with the Vault Transit key
`zuno-platform-signer`, and the public key is committed as
`agents/zuno-platform-signer.pub` (ADR-0420). `make d3 sign agents`
(`ansible/playbooks/day3_sign.yml`) signs a digest that covers every file
under the bundle directory and writes the signatures to Vault KV
`zuno/okf-signatures`. An ExternalSecret then syncs them into agent-runtime,
which enforces `ZUNO_REQUIRE_SIGNED_BUNDLES=true` (ADR-0106). Two failure
modes are on record. Editing a bundle without re-signing wedged the rollout
(`day3_sign.yml` header, 2026-08-28). A regenerated Transit key silently broke
every offline check (ADR-0106 note of 2026-08-25).

ADR-0509 and ADR-0510, both `Proposed` and unimplemented, planned to deliver
bundles to running pods as operator-rendered ConfigMaps and to poll a
`zuno-okf` git repository. Both assume the AIAgent operator and agent-runtime,
which ADR-0561 retires.

`unifai-operator` knows nothing of OKF. Its object kinds take a raw UnifAI
`cfg_dict` (`spec.config`) or a `BlueprintDraft` (`UnifaiWorkflow.spec.blueprint`,
`UnifaiTemplate.spec.draft`), resolve `$ref:<kind>/<name>` references, and
dry-run-validate before pushing to the multi-agent API
(`fork/unifai-operator/api/v1alpha1/{common,resource,workflow}_types.go`,
`fork/unifai-operator/README.md`). The `UnifaiAgent` types are
`custom_agent_node`, `orchestrator_node`, `deep_agent_node`,
`claude_agent_node`, `a2a_agent_node`, `branch_chooser_node` and
`mock_agent_node` (`resource_types.go:287`).

## Decision

**1. OKF stays the source of truth, and a bundle reaches the cluster as a
signed OCI artifact pinned by digest.** Each agent bundle version is published
as one OCI artifact, with the bundle directory as its single layer and the
OKF schema version in its annotations. It is referenced by `@sha256:` digest
only. A tag is never a valid reference. The publish step and the signing step
are the same verb: WP-150 extends `make d3 sign agents` to push the artifact
and sign its manifest digest with the existing Transit key through cosign's
`hashivault://` mode (ADR-0420). The two cosign tlog flags ADR-0420 names stay
mandatory.

**2. A new kind, `UnifaiAgentBundle` (`unifai.startx.fr/v1alpha1`,
namespaced), is the only entry point.** Its fields:

- `spec.source.oci`: `reference` (repository plus digest; CEL rejects a tag)
  and an optional `pullSecretRef`.
- `spec.verify`: required, and exactly one of `publicKeyRef` (a Secret key
  holding a PEM public key) or `vaultTransit` (`address`, `mount`, `keyName`,
  Kubernetes-auth `role`, used to fetch the public key only). No "skip"
  value exists. A CR without `verify` is rejected by the API server.
- `spec.ceilings`: `toolCapabilities`, `knowledgeDomains` and
  `maxClassification`, reviewed in Git like ADR-0327's CR fields.
- `status`: `resolvedDigest`, `okfVersion`, the list of emitted children, and
  conditions `Verified`, `Valid`, `WithinCeilings`, `Emitted` and `Ready`.

**3. The operator verifies first, parses second, then emits owned objects.**
The pipeline runs in a fixed order:

1. Pull the manifest by digest.
2. Verify the signature against the key from `spec.verify`. On failure, set
   `Verified=False` and parse nothing.
3. Unpack the layer, then validate it against the OKF JSON schemas embedded
   in the operator at a pinned schema version.
4. Check every declared tool, knowledge domain and classification against
   `spec.ceilings`. A widening sets `WithinCeilings=False` and emits nothing.
   This is ADR-0510 clause 2's one-way authority rule, kept.
5. Emit `UnifaiAgent`, `UnifaiWorkflow` and, for catalog display,
   `UnifaiTemplate` objects, each with an ownerReference to the bundle CR.
   Argo CD owns the bundle CR, and the operator owns the children, as in
   ADR-0327.

**4. ADR-0342's graph shapes become blueprint templates embedded in the
operator.** `retrieve_reason_respond` and `plan_draft_write` are each a
parameterized `BlueprintDraft` under `internal/okf/shapes/`, versioned with the
operator. `zuno.graph_shape` selects one. An unknown or missing shape is a
`Valid=False` condition, and nothing is emitted. Today that applies to
soursage and cognos, which declare none. Adding a shape is an operator
release, as it is an agent-runtime release today.

**5. The mapping from OKF to UnifAI is fixed in the operator, never in
UnifAI:**

- Each prompt body becomes the system prompt of its task's agent node.
- `allowed_tools` select the MCP Gateway `UnifaiProvider` and the tool names
  exposed to the node.
- `allowed_knowledge` and `rag.top_k` configure the retriever (ADR-0568).
- `preferred_classification` becomes the session floor (ADR-0565).
- `max_tokens`, agent and task feed ADR-0563's templated headers.
- `access.groups` becomes UnifAI visibility. If UnifAI has no group-gated
  visibility, ADR-0569 adds it, and until then the bundle sets `Valid=False`
  with reason `EntitlementUnsupported` rather than publishing an ungated
  agent.
- Model selection is never emitted per bundle. Every node uses the shared
  `UnifaiLLM` of type `openai_compatible` that points at the ai-gateway
  (ADR-0560).

**6. Zuno-specific code is isolated.** OKF parsing, the shapes and the mapping
live in `fork/unifai-operator/internal/okf/` and the `UnifaiAgentBundle`
controller. Nothing under `multi-agent/`, `rag/`, `backend/` or `ui/` learns
about OKF (ADR-0575). The generic kinds keep their behavior unchanged.

**7. Change cadence is a digest bump in Git.** No git polling and no tracking
ref are used. A merged change to a bundle produces a new signed digest, a PR
updates `spec.source.oci.reference`, Argo CD applies it, and the operator
re-emits. An `UnifaiTemplate` has no update API and is deleted and recreated
(`fork/unifai-operator/README.md`). Workflows and agents are updated in place.

## Amendment (2026-10-17) - as implemented by WP-150

Corrected while `Accepted` and before the kind's first release, after
implementation exposed the following. Every other clause stands as written.

- **Clause 1, what is signed.** The artifact carries the bundle's existing
  signature instead of a new signature over the manifest digest. `make d3
  sign agents` already signs the bundle *content* digest with the Transit
  key (`sign_okf_bundle.py`); `publish_okf_bundle.py` re-verifies it and
  pushes one deterministic layer with that signature in the manifest
  annotation `zuno.okf.signature`. The operator recomputes the content digest
  from the pulled layer and verifies the signature before parsing. Integrity
  is the same (the content digest covers every file, the reference pins the
  manifest), no second signing call is added, and the existing offline
  `sign_okf_bundle.py verify` still checks the same signature. Publication is
  a step of the same verb, run after signing and verification, and only when
  `zuno_okf_oci_repository_prefix` is set.
- **Clause 2, fields.** `spec.verify` has `publicKeyRef` only: the Transit
  public key is the committed `agents/zuno-platform-signer.pub`, placed in a
  Secret by the deployment (ADR-0574). `vaultTransit` is not implemented; a
  key rotation therefore still needs that Secret updated. The classification
  ceiling is named `ceilings.minClassification`: the least restrictive level
  a bundle may declare (C1 < C2 < C3), which is what "never widen" means for
  classification. `spec.entitlement` (`Enforced` by default, or
  `GatewayOnly`) makes clause 5's `EntitlementUnsupported` refusal the
  default while allowing the ADR-0562 interim of gateway-only enforcement on
  an explicitly reviewed CR.
- **Clause 3, schemas.** The OKF JSON schemas had drifted from the bundles
  they describe (8 of 50 documents failed, Tekos's primary task among them):
  hand-kept enums of tool names and entitlement groups, and the arkos
  `prompts` slots. The tool and group enums became name patterns (the
  vocabulary stays in `policies/tools/tool-policy.yaml`, checked by
  `validate_okf_bundle.py`) and `prompts` was added; all 50 now validate,
  and the operator embeds copies of these schemas.
- **Clause 4, shapes.** Only `retrieve_reason_respond` has a blueprint
  template. `plan_draft_write` (Arkos) is refused with
  `Valid=False/ShapeNotImplemented` until its template exists.
- **Clause 3 step 5 and clause 5, emitted objects.** No `UnifaiTemplate` is
  emitted yet (catalog display moves to ADR-0569). Each task gets its own
  `UnifaiLLM`, identical to the shared ai-gateway LLM except for its Zuno
  headers (agent, task, effective classification): UnifAI cannot attach
  per-node headers to one shared LLM. Model selection is still never emitted
  per bundle. Per-task tool names and `rag.top_k` are not mapped onto the
  provider and retriever (both are shared objects); they are listed in
  `status.unmapped`, and tools stay enforced by mcp-gateway.

## Planned supersession

At cutover (WP-156):

- **In full:** ADR-0308 and ADR-0327 (the AIAgent operator and its contract;
  the ownership split and the no-inline-secrets rule migrate into clause 3),
  ADR-0350 (declarative agent instances migrate into `UnifaiAgentBundle`),
  ADR-0509 (mounted artifacts, replaced by clause 1), ADR-0510 (git watch,
  replaced by clause 7; its ceiling rule migrates into clause 3).
- **In part:**
  - ADR-0106: only the verification point ("the Agent Runtime registry
    startup refuses") and the ExternalSecret distribution into agent-runtime.
    Signing, the Day 1 agents check, and schema and policy validation remain
    its own decisions.
  - ADR-0507: clause 3 only (`okfBundleRef` semantics on the AIAgent CR).
  - ADR-0508: clause 1's hook designations for agent-frontend, agent-runtime
    and agent-bff. `internal/okf/` becomes a hook bound by clauses 2-3, and
    the mcp-gateway and ai-gateway hooks stand.

## Consequences

The bundle becomes an immutable, verifiable, addressable artifact instead of
bytes baked into an image. A prompt change no longer needs a runtime image
rebuild, which is what ADR-0509 wanted. The same artifact can be verified
offline with `cosign verify` and the committed public key.

Shapes stop being Python modules and become versioned data in the operator.
The operator becomes the only component that interprets OKF semantics. That
deliberately reverses ADR-0327's "never the source of truth for OKF semantics",
and the ceiling check makes the reversal safe.

## Security considerations

Signature verification happens before any byte of the layer is parsed, so a
malicious bundle never reaches the YAML or Markdown parser. Digest pinning
prevents a mutable tag from swapping content between verification and use.
The verification key is a public key fetched from a Secret or from Vault's
read-only Transit public-key endpoint. The operator never holds signing
material. A rotated Transit key then propagates through Vault instead of a
committed file, the failure mode ADR-0106's 2026-08-25 note recorded.

Ceilings are the privilege boundary: a bundle can narrow, never widen. The MCP
Gateway and ai-gateway still enforce with the caller's JWT (ADR-0563), so a
ceiling bug cannot grant a tool the user lacks. Children are written through
the multi-agent API with `spec.owner` (default `admin`). That operator
identity is highly privileged inside UnifAI, so the namespace allowlist and
CR RBAC must restrict who may create an `UnifaiAgentBundle`. Bundles carry no
secrets by construction (ADR-0506).

## Operational considerations

`kubectl get unifaiagentbundle` shows the digest and conditions per agent. A
verification failure, an unknown shape or a ceiling violation is a named
condition that leaves the previously emitted children serving, never a
partial emit. Deleting a bundle CR deletes its children in UnifAI. What that
does to existing sessions that reference the deleted workflow is
**unverified** and is tested in the pilot (ADR-0573) before any deletion on
`demo222`.

`make d3 sign agents` remains the one verb to run after any bundle edit. It
now prints the new digests to put in the bundle CRs. The OKF schemas embedded
in the operator are pinned and checked by a conformance test in the operator's
`make test`, following ADR-0508 clause 2.

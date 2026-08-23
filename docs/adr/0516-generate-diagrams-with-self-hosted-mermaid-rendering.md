# ADR-0516: Generate diagrams with self-hosted Mermaid rendering, alongside SDXL image generation

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-23
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0415 gave arkos/comage (and cognos, forward-declared) `generate_image`,
consuming `stable-diffusion-xl` via OVHcloud AI Endpoints. Live-cluster
testing (2026-08-23, once a separate `NetworkPolicy` gap blocking
`mcp-gateway` from reaching `ai-gateway` was found and fixed) confirmed the
call genuinely reaches real OVHcloud SDXL — but for a structured technical
ask ("a schema of the relation between a Kubernetes node, pod, configmap and
service"), the result was illegible: melted text, approximate boxes, no
reliable arrows. This is not a configuration problem: SDXL is a
general-purpose photorealistic/artistic diffusion model with no
diagram-specialized mode, and diffusion models as a class are well known to
render precise structured content (exact text, exact box/arrow
relationships) unreliably.

OVHcloud's AI Endpoints catalog was checked directly
(`ovhcloud.com/en/public-cloud/ai-endpoints/catalog/`) for an alternative
image-generation model specialized in diagrams/charts — it lists exactly one
image-generation model, `stable-diffusion-xl-base-v10`. No second option
exists there today, diagram-specialized or otherwise.

What the actual requirement — diagrams, charts, sequence/workflow diagrams,
no photorealism — calls for is **diagram-as-code** (Mermaid, PlantUML,
Graphviz DOT): an LLM writes a precise structural description, and a
deterministic renderer draws it exactly, rather than a diffusion model
approximating it in pixels. This is not a new capability for the LLMs
already in this platform: Arkos's own testing this session showed the model
spontaneously producing valid Mermaid/SVG-style diagram syntax unprompted,
in plain prose, when asked for a diagram.

`agents/arkos/README.md` and `draft-architecture-testimonial.md` originally
named **Lucidchart** as Arkos's intended diagram integration
(`components/mcp-servers/lucidchart` exists only as a placeholder README,
never built) — predating ADR-0415. A real Lucidchart integration was
considered as part of this decision and rejected: it requires an external
SaaS account/credential and would send diagram *content* (which can
describe internal system topology, or for Comage, deal-specific details)
outside the cluster, the same class of exposure a free public Mermaid
rendering API (`mermaid.ink`) would also introduce — both rejected for the
same reason (see Alternatives).

## Decision

1. **A second, purpose-built visual tool**, `generate_diagram` (capability
   `diagram.generation.create`), coexisting with `generate_image` — not
   replacing it. The calling LLM chooses between them based on the
   request: `generate_image`'s own tool description is tightened to say
   "NOT for diagrams... use generate_diagram for those instead"; the new
   tool's description says the reverse. SDXL remains the right tool for
   genuinely photorealistic/illustrative asks with no precise structure.
2. **Mermaid syntax**, written directly by the calling LLM as the tool's
   `mermaid_source` argument (not a natural-language prompt requiring a
   second internal LLM call to translate) — the model is already
   demonstrably comfortable producing it unprompted.
3. **Self-hosted, in-cluster rendering** — a new component,
   `components/diagram-render` (Node.js, headless Chromium,
   `@mermaid-js/mermaid-cli`), reached by a new MCP Gateway handler,
   `components/mcp-gateway/app/handlers/diagram_gen.py`, mirroring
   `image_gen.py`'s shape exactly (same ADR-0011 authorization intersection,
   same in-process `transport`) but calling an in-cluster service instead
   of an external SaaS endpoint. No external API, no credential, no
   diagram content ever leaves the cluster.
4. **`min_classification: C1`**, not `generate_image`'s `C2`
   (`policies/tools/tool-policy.yaml`) — `generate_image`'s C2 ceiling
   exists specifically to gate a C3 agent's one deliberate exception to
   reach an external SaaS boundary (ADR-0415 decision 3); `generate_diagram`
   never reaches one, so there is no boundary to gate and C1 (the
   least-restrictive default) is the correct classification, not a
   copy-pasted ceiling.
5. **Output as `image/svg+xml`, not PNG** — the frontend's existing
   `<img src="data:${mime_type};base64,${data_base64}">` rendering
   (`components/agent-frontend/web/src/chat/Chat.tsx`, ADR-0415) already
   works unchanged for an SVG data URI (browsers render both natively), and
   SVG gives crisper, infinitely-scalable diagrams than a rasterized PNG.
   This also gives every consumer a precise, reliable way to distinguish "a
   real Mermaid render" from "an SDXL result" — `mime_type`, not a separate
   field — used directly by the boundary tests in decision 7 below.
6. **Reuses the exact `generated_images` state field and artifact shape**
   `generate_image` already established (`data_base64`/`mime_type`/`alt`) —
   a rendered diagram is indistinguishable in shape from a generated image,
   just a different `mime_type`. Zero frontend code changes.
7. **Scope: Arkos, Comage, and Tekos** — a deliberate carve-out for Tekos,
   which ADR-0415 never gave `generate_image` (`evaluations/tekos/
   gate_checks.py`'s `tekos_declares_no_dat_or_image_generation_capability`,
   `security_checks.py`'s boundary check, `stress_test.py`'s
   `image_generation_boundary` category all assert this). Tekos gets
   `diagram.generation.create` only — those three checks are updated to
   assert the narrower, precise guarantee that actually holds now ("no
   `image/png` ever", not "no images ever"), plus a new positive check
   proving the diagram path genuinely works for Tekos. Tekos still never
   declares `image.generation.create`; nothing about SDXL/photorealistic
   access changes for it.
8. **Defense in depth**: `diagram-render` validates a shared
   `X-Zuno-Gateway-Token` header (ADR-0037's existing pattern for
   `mcp-servers/*`), and its own `NetworkPolicy` restricts ingress to
   `mcp-gateway` only — written correctly from the start, applying the
   lesson of the incident in the Context above (a missing NetworkPolicy
   rule silently broke `generate_image` for a full session before being
   caught).

## Alternatives considered

- **A different OVHcloud-hosted image model** — rejected: checked the live
  catalog directly, no diagram-specialized alternative exists there today
  (see Context).
- **A public Mermaid rendering API (`mermaid.ink`)** — rejected: zero new
  infra, but sends diagram *content* outside the cluster with no
  data-classification gate, inconsistent with how every other
  externally-reaching call in this codebase treats that as a deliberate,
  gated decision (`generate_image`'s own fixed C2 ceiling being the closest
  precedent, and even that only exposes a short prompt string, never
  structured content).
- **A real Lucidchart integration**, the originally-planned diagram path —
  rejected: external SaaS account/credential, same external-exposure
  concern as `mermaid.ink` above, and strictly worse (a paid third-party
  service vs. a free public one) for no capability gain over self-hosted
  Mermaid. `components/mcp-servers/lucidchart`'s placeholder README is
  superseded by this decision, not implemented.
- **PlantUML or Graphviz DOT instead of Mermaid** — rejected: Mermaid has
  the best native browser-rendering story (irrelevant here since rendering
  is server-side, but relevant to the LLM-familiarity argument) and this
  session's own live testing already showed the model defaulting to
  Mermaid-shaped output unprompted; PlantUML would need a JVM-based
  renderer (heavier than headless Chromium) for no proven quality gain.
- **Replacing `generate_image` entirely** rather than adding a second tool
  — rejected: SDXL remains the right tool for genuinely illustrative/
  mockup asks with no precise structure; removing it would regress
  ADR-0415's own use cases.
- **Folding diagram-render into `mcp-gateway`'s own image** (Node/Chromium
  baked into a Python service) — rejected: awkward multi-runtime image, no
  precedent in this repo; a separate component matches how `ai-gateway`
  already backs `image_gen.py` as its own deployable, and how
  `components/mcp-servers/*` are each their own image for the same
  "different runtime/dependency needs" reason.

## Accepted risks (and their remediations)

- **Headless Chromium under OpenShift's restricted SCC (random non-root
  UID, no privileged sandbox) is a real class of container-hardening
  friction**, mitigated with the standard, documented `--no-sandbox
  --disable-dev-shm-usage` Puppeteer flags and a writable `/tmp` `emptyDir`
  (matching every other restricted-SCC workaround already in this repo).
  Remediation if this proves insufficient in practice: revisit resource
  limits/flags against real cluster behavior, same posture as every other
  "unverified until live-tested" note in this repo's own ADRs.
- **Mermaid source is LLM-generated, unvalidated text run through a real
  browser rendering engine** — a more interesting attack surface than a
  plain API pass-through (e.g. Mermaid can reference external image URLs,
  a possible SSRF vector during render). Remediation: `NetworkPolicy`
  restricts `diagram-render`'s own egress is *not* currently restricted
  (only ingress is, matching every other `mcp-servers/*` chart) — this is
  a real gap worth a follow-up if diagram-render's egress needs
  restricting too; not blocking for this decision since the render
  service has no credential to exfiltrate and its blast radius is
  contained to its own pod.
- **`generate_image`'s tool description was already ambiguous about
  diagrams** ("picture, diagram, illustration or mockup") before this
  decision, because Lucidchart (Context) was never built — a real user
  could plausibly still ask for a diagram in a way that reads as
  ambiguous even after the description tightening in decision 1.
  Remediation: none beyond the description wording; if this proves
  insufficient in practice, a follow-up could add an explicit disambiguation
  turn, but that's speculative ahead of real usage data.

## Related ADRs

- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
- [ADR-0045](0045-stream-responses-end-to-end-with-sse.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0415](0415-consume-stable-diffusion-xl-via-ovhcloud-ai-endpoints.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)

See [Standard clauses](README.md#standard-clauses) for Consequences, Security/Operational
considerations, Migration/evolution, Acceptance criteria and Review evidence.

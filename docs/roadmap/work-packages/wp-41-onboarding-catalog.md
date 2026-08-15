# WP-41: Self-service onboarding and catalog expansion (promotes ADR-0307 + ADR-0306)

- **State:** Part A merged (2026-08-15); Part B (sixth agent) next.
  **Part A** promoted ADR-0307 verbatim and delivered
  `platform/templates/agent/`: `scaffold_agent.py` (a hand-rolled
  parameterized generator, repo convention - one `render_*` function per
  output file type over an `AgentSpec` dataclass) writes 18 real files
  into the real tree per agent: OKF bundle skeleton (agent.okf.md +
  primary task + prompt + tasks README), a CR-managed GitOps chart
  (`templates/aiagent.yaml` rendering a single `AIAgent` CR - the
  post-WP-38-migration Arkos shape, so "self-service" and "CR-managed"
  arrive together, never a raw-manifest chart), `gitops/apps/<name>/`
  Applications, and a full evaluations skeleton (20-scenario
  scenarios.yaml reusing the shared ADR-0342 runner's exact type
  vocabulary, gate_config.yaml, thin wrapper scripts, a generated
  security_checks.py with the agent-generic ADR-0032/0033/0040 checks
  plus a scaffold-ceiling self-consistency check). Two things it
  deliberately does NOT write, documented in its own docstring:
  policies/*.yaml entries and realm-zuno.json (both hand-curated,
  densely commented files a programmatic YAML/JSON round-trip would
  corrupt) - it emits `agents/<name>/keycloak-fragment.json` +
  `NEXT_STEPS.md` (an explicit human checklist) instead.
  `test_scaffold_validate_discard.py` (the brief's own
  scaffold-validate-discard CI test) scaffolds a throwaway
  `zzz-scaffold-ci-test` agent, runs the composed validators
  (`validate_okf_bundle.py` - 6 bundles PASS with the throwaway present -
  `check_knowledge_refs.py`, `helm lint`) and ALWAYS discards it in a
  `finally` block; verified end-to-end locally (exit 0, tree left
  byte-identical) and wired into `.github/workflows/lint.yml`'s
  `policy-as-code` job as a blocking step. Two real generator bugs found
  and fixed by actually running it: a REPO_ROOT parents[] off-by-one
  (files landed under platform/ instead of the repo root) and a
  hyphenated-slug-in-Python-identifier crash in the generated
  security_checks.py (fixed with an underscored py_name variant for the
  one function name, keeping the real slug everywhere else).
  `python3 platform/docs/check_docs.py` PASS.
- **ADRs:** ADR-0307 (Partially implemented, Part A), ADR-0306 (Proposed -> promoted in Part B)
- **Depends on:** WP-38 (merged — the operator is the onboarding substrate); all four slices merged
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root. Order:
> 0307 (template + validation) first, 0306 (sixth agent proving it) second.

## Goal

Promote both stubs, then: (Part A, ADR-0307) an agent template/scaffold +
validation workflow so a team can define a new agent as a reviewed PR;
(Part B, ADR-0306) a sixth demo agent created purely from that template,
proving the platform onboards beyond the initial five.

## ADR references

Stubs (verbatim, from `docs/adr/0300-v0.3-roadmap.md`):
- ADR-0307: "Provide controlled templates, validation and workflows for teams to define new agents."
- ADR-0306: "Demonstrate that the generic platform supports broader enterprise agent onboarding."

## Preconditions

- WP-38 merged (AIAgent CR is the deployment interface for new agents);
  five agents active (WP-36 done).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: one complete agent slice (bundle + CR/chart + evaluations), the
  WP-37 contract, `platform/docs/check_knowledge_refs.py` and the OKF
  validation from WP-05 (the validators the workflow composes).

## Step 0 — ADR promotions

1. `docs/adr/0307-support-self-service-agent-onboarding.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.3`).
   Decision: promotion sentence + stub text, then: "A new agent is created
   from a repository template (`platform/templates/agent/`) that scaffolds
   the OKF bundle skeleton, `AIAgent` CR, Keycloak entitlement fragment,
   policy entries and a 20-scenario evaluation skeleton. A validation
   workflow (composing the OKF, knowledge-reference, policy and contract
   validators) gates the onboarding PR; a template-created agent reaches
   `active` through exactly the same ADR-0326 completion pattern and
   ADR-0027/0028 gates as the first five — self-service changes who
   authors the definition, never the acceptance bar." Related: 0306, 0326,
   0327, 0308, 0106.
2. `docs/adr/0306-expand-the-agent-catalog-beyond-the-initial-five-agents.md`
   (same header pattern). Decision: promotion sentence + stub text, then:
   "Prove ADR-0307's path by onboarding a sixth demo agent (synthetic
   persona, existing knowledge domains and capabilities only, no new
   external systems) end to end: template scaffold → validation workflow →
   review → deployment via `AIAgent` CR → evaluation gate. The sixth agent
   is a permanent template regression proof." Related: 0307, 0326.
3. `docs/adr/0300-v0.3-roadmap.md`: KEEP both headings; bodies → promotion
   pointer lines (`(WP-41 implementation)`).
4. `docs/adr/README.md`: both rows → direct links, `To be implemented`.
5. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes

1. **Part A:** `platform/templates/agent/` — parameterized scaffold
   (cookiecutter-style or a `scaffold_agent.py` generator) emitting: OKF
   bundle skeleton, sample `AIAgent` CR, Keycloak fragment, policy entries,
   evaluation skeleton; `platform/templates/agent/README.md` = the
   onboarding workflow doc; a CI validation job composing the existing
   validators on template output; test: scaffold a throwaway agent in CI,
   validate, discard.
2. **Part B:** run the generator for the sixth demo agent (synthetic
   persona; reuse `knowledge.tech` + delegated Drive read-only, nothing
   new); complete its bundle/scenarios; wire its CR; evaluations reviewed
   like every slice. **Human review checkpoint on persona + scenarios.**

## What NOT to touch

Standard list; plus: the five production agent slices; no new knowledge
domains or external backends for the sixth agent.

## Acceptance checks

- Scaffold-validate-discard CI test passes; `validate_contract.py` exit 0
- `python3 platform/docs/check_knowledge_refs.py`; `python3 platform/docs/check_docs.py` → PASS
- Sixth agent passes the same repo-side checks as WP-31's list

## Operator / human follow-up

1. User: review the sixth agent's persona + scenarios.
2. Operator: deploy via its CR, run the 75% gate, flip to `active` —
   discharges ADR-0306; the template flow having produced it discharges
   ADR-0307.

## Status updates (then re-run check_docs.py)

- After merge: both →
  `Partially implemented (template, validation workflow and sixth-agent definition merged; deployment gate pending)`;
  after the gate: ADR-0307 → `Implemented - see \`platform/templates/agent/\`.`;
  ADR-0306 → `Implemented - see the sixth agent under \`agents/\`.`;
  index rows + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- A UI/portal for onboarding (would be a new ADR).
- Catalog governance beyond the demo (new ADR territory).

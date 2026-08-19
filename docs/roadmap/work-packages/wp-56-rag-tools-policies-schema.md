# WP-56: rag/tools/policies schema (delivers ADR-0513)

- **State:** Done (2026-08-19). Executed as briefed: three new schemas
  authored and validated against the draft 2020-12 meta-schema;
  `validate_okf_bundle.py` extended with a third check category;
  Tekos - the sole Stage-2 agent - populated end-to-end (2 `rag/` notes, 3
  `tools/` notes, 1 `policies/` addendum) as the worked example. Arkos,
  Comage, Advantage, Finage deliberately left untouched (still Stage 1
  with reserved structure per ADR-0502 clause 4; they gain real content at
  their own promotion, same as `deployment/`/`tests/`).
- **ADRs:** ADR-0513
- **Depends on:** WP-43 (the maturity-model alignment that first gave every
  agent a stage-aware README to update)
- **Blocks:** none
- **Estimated files touched:** ~15

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).

## Goal

Give `agents/<name>/rag/`, `tools/` and `policies/` - stub directories
since the original scaffolding commit, explicitly named "drift" by
ADR-0502 - a real, machine-checkable format, and prove it works against
the one agent (Tekos) where it can hold real content today.

## ADR references

ADR-0513 (full file, no stub promotion needed): three new schemas
(`zuno-okf-{rag,tool,policy}-v0.2.schema.json`), one Markdown file per item
(domain / capability / constraint), documentation-only and
narrowing-only - never a second authorization source, same posture as the
ADR-0503 Authorization matrix.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: ADR-0502, ADR-0503, ADR-0038; the three existing schemas under
  `platform/okf/schema/`; `platform/supply-chain/validate_okf_bundle.py`;
  `agents/tekos/agent.okf.md` and `agents/tekos/tasks/*.md`.
- Confirm `git status` is clean on `agents/`, `platform/okf/`,
  `platform/supply-chain/` and `docs/` before editing (parallel sessions
  commit mid-turn in this repository).

## Repo changes (step by step)

1. Author `platform/okf/schema/zuno-okf-rag-v0.2.schema.json`,
   `zuno-okf-tool-v0.2.schema.json`, `zuno-okf-policy-v0.2.schema.json`
   following the existing schemas' conventions (draft 2020-12, `$id`,
   `additionalProperties: false`, ADR-citing descriptions). Validate each
   with `jsonschema.validators.validator_for(schema).check_schema(schema)`.
2. Extend `platform/supply-chain/validate_okf_bundle.py` with a third
   check: for every `*.md` under a bundle's `rag/`, `tools/`, `policies/`,
   parse frontmatter, check `okf_version`/`type`, and resolve
   `used_by_tasks`/`applies_to.tasks` (plus `domain`/`capability`) against
   the bundle's own declared tasks - fail closed on any dangling
   reference, same style as the existing tool/knowledge checks.
3. Populate `agents/tekos/rag/tech.md`, `agents/tekos/rag/project.md`,
   `agents/tekos/tools/search_confluence.md`,
   `agents/tekos/tools/web_search.md`,
   `agents/tekos/tools/list_drive_files.md`,
   `agents/tekos/policies/web-search-scope.md` from Tekos's real
   `agent.okf.md`/`tasks/*.md` declarations - no invented capability or
   domain. Rewrite `agents/tekos/{rag,tools,policies}/README.md` as short
   indexes (matching `agents/tekos/tasks/README.md`'s existing style,
   replacing the three-line "assets will be maintained here" stub).
4. Update `agents/tekos/README.md`'s directory-tree annotation: the
   `policies/`, `rag/`, `tools/` lines change from `(stub)` to a one-line
   description matching the `deployment/`/`tests/` lines' style.
5. Run `python3 platform/supply-chain/validate_okf_bundle.py` (all
   bundles), `python3 platform/docs/check_knowledge_refs.py`,
   `python3 platform/docs/check_docs.py` - all must pass.

## What NOT to touch

Standard list; plus: no `zuno.status` flips, no policy or realm edits, no
`gitops/` changes; Arkos/Comage/Advantage/Finage's `rag/`/`tools/`/`policies/`
stubs stay exactly as they are (they are not promoted by this WP - each
gains real content only at its own promotion, per ADR-0502 clause 4); no
change to `agents/*/tests/` (ADR-0504/WP-46 territory).

## Acceptance checks (run from repo root; all must pass)

- The three new schemas parse as valid JSON and validate as draft 2020-12
  JSON Schema.
- `agents/tekos/{rag,tools,policies}/` contain real, schema-conformant
  content; the other four full-skeleton agents are unchanged.
- `python3 platform/supply-chain/validate_okf_bundle.py` passes for all
  eight bundles, and fails on a deliberately broken cross-reference tested
  by hand (e.g. a `used_by_tasks` entry naming a task the bundle doesn't
  declare).
- `python3 platform/docs/check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

None - documentation/structure only; no cluster state changes.

## Status updates (then re-run check_docs.py)

On merge: ADR-0513 → `Implemented - see platform/okf/schema/zuno-okf-{rag,tool,policy}-v0.2.schema.json,
platform/supply-chain/validate_okf_bundle.py and agents/tekos/{rag,tools,policies}/.`
(no operator dependency); index row + okf-roadmap tracker + MEMORY.md
accordingly.

## Out of scope / deferred

- Populating Arkos/Comage/Advantage/Finage's `rag/`/`tools/`/`policies/` -
  each happens at that agent's own Stage-2 promotion
  (`platform/templates/agent/PROMOTION.md`).
- Any runtime consumption of these files by Agent Runtime, MCP Gateway or
  the portal - deliberately out of scope per ADR-0513 (documentation
  only, never an enforcement input).

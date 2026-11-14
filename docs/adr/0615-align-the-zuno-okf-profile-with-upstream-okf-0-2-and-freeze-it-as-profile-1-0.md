# ADR-0615: Align the Zuno OKF profile with upstream OKF 0.2 and freeze it as profile 1.0

- **Status:** Accepted (2026-11-14, the user's decisions of the day; rollout WP-262 to WP-267 planned for the weekend of 2026-11-14/15, WP-268 dated 2026-11-27)
- **Target:** v0.17
- **Date:** 2026-11-14
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md) in part (its envelope fields `provenance`, `verification`, `freshness`, free-text `sources`, and the per-document value `okf_version: v0.2`), [ADR-0513](0513-give-okf-rag-tools-and-policies-directories-a-real-schema.md) in part (the closed `capability` list of tool notes and the one-direction `used_by_tasks` check), [ADR-0579](0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md) in part (`okf_version: v0.3` as the version of the Zuno extension, and clause 6 as amended on 2026-11-05)
- **Related:** [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md), [ADR-0006](0006-extend-okf-with-zuno-agent-specific-metadata.md), [ADR-0508](0508-isolate-okf-parsing-behind-per-component-adaptation-hooks.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0577](0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md), [ADR-0581](0581-derive-stack-configuration-from-the-admitted-corp-bundle.md), [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [ADR-0612](0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md)

## Context

ADR-0005 and ADR-0038 (2026-08-04/05) chose "Open Knowledge Format v0.2" as the agent definition contract. OKF is
Google Cloud's open, vendor-neutral format for knowledge as Markdown files with YAML frontmatter (Apache-2.0,
v0.1 announced 2026-06-12, v0.2 announced 2026-07-24; see [Resources](#resources)). The repository never linked the
upstream specification, and its schemas grew a Zuno envelope that they label "[OKF CORE]".

On 2026-11-14 the user asked for an audit of how `startxfr/zuno-demo-agents` uses OKF (origin/devel `78b2472`, i.e.
release v0.14.4 plus one release-tooling fix). Score: **13/20**. The profile's tooling scored 17/20, the alignment
with the upstream spec 9/20, and the freshness of the bundle content 11/20. The user then decided to align, freeze and
deploy the profile in one go, even at the cost of a new UnifAI operator release and a new agents release.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | The published artifacts meet upstream's conformance MUSTs (§11): every published `.md` has a frontmatter with a non-empty `type`. The git tree does not: README and NEXT_STEPS files have no frontmatter, and upstream does not reserve `README.md`. They are never published. | Audit script over `agents/*`; `platform/release/okf_release.py` (`RUNTIME_FILES`, `RUNTIME_DIRS`, README excluded) |
| F2 | `okf_version` is misused. Upstream declares `okf_version: "0.2"` (a bare number) once, in the bundle-root `index.md` (§8, §12). The profile writes `v0.2` or `v0.3` in every document, and `v0.3` is the version of the Zuno extension (ADR-0579), not an OKF version: it will collide with a future upstream 0.3. | `platform/okf/schema/zuno-okf-v0.3.schema.json` (`const: "v0.3"`) |
| F3 | The fields labelled "[OKF CORE]" are Zuno inventions: `provenance: {maintainer, repository}`, `verification.status`, `freshness.last_reviewed`, and `sources` as free strings. Upstream (§5) uses `sources: [{id, resource, title, …}]`, `generated: {by, at}`, `verified: [{by, at}]`, `status` (draft, stable, deprecated) and `stale_after`. | Agent schemas v0.2 and v0.3; upstream SPEC.md §5 |
| F4 | Bundles have no `index.md` and no Markdown links between documents (upstream §6, §8). Tasks are linked by name in `zuno.tasks`. | `agents/*/` |
| F5 | Every schema refuses unknown keys (`additionalProperties: false`), and every reader refuses an unknown version. Upstream says a consumer MUST NOT reject unknown keys or types (§11). For an authorization contract this strictness is deliberate, but no document says so. | Schemas; ADR-0508 hooks |
| F6 | The trust metadata is never maintained. All 8 agents say `provenance.repository: zuno-demo` (stale since the extraction of 2026-10-22), `verification.status: unverified` and `last_reviewed` 2026-08-05 or 2026-08-15. | `agents/*/agent.okf.md` |
| F7 | The published prose is stale. There are about 110 references to retired or foreign things: "Agent Runtime" 30, `agent-frontend` 20, `v0` 17, `components/` 15, `agent-runtime` 10, `MEMORY.md` 8, `evaluations/` 5. tekos alone has 32, in 9 of its 12 published files. Some sentences are false: "the only agent with status active", the knowledge union `[knowledge.tech]`, "three tasks". One reference dangles: `policies/data-classification`. The non-published READMEs add 99 stale mentions, a doubled `PROMOTION.md` URL in 11 places and 12 directories holding only a README. The scaffold writes zuno-demo `gitops/` and `evaluations/` files. | Audit of 2026-11-14 |
| F8 | The tool and rag notes are incomplete. tekos documents 3 of its 13 tools; the other agents document none. The tool-note schema's `capability` is a closed list of 18 values that misses 17 of the 34 names of `policies/tools/tool-policy.yaml` (for example `k8s.*`, `aap.*`, `diagram.generation.create`, `metrics.query`), so those notes cannot even be written. The validator checks `used_by_tasks` one way only: the `list_drive_files` note omits `find-relevant-docs` and passes. | `zuno-okf-tool-v0.3.schema.json`; `platform/supply-chain/validate_okf_bundle.py` |
| F9 | 12 tasks have no prompt, 6 of them on active agents (tekos 3, comage 2, arkos 1). For those, the operator builds the system message from the description and the task body. | `agents/*/prompts/`; operator `internal/okf/bundle.go` |
| F10 | Versions are mixed. Six agents are entirely v0.2, arkos mixes v0.3 and v0.2, and tekos is entirely v0.3. The release annotation and the corp index report only the version of `agent.okf.md`. | `okf_release.okf_version()` |
| F11 | **The narrowing check is gated on equality.** `okf_narrowing.py` (zuno-demo) and `check_narrowing.py` (agents) apply the v0.3 rules only when `okf_version == "v0.3"`. Any new version value would skip the model, limit, guardrail, delegation and skill narrowing in silence. | `platform/supply-chain/okf_narrowing.py:119`; agents `platform/okf/check_narrowing.py:145` |
| F12 | zuno-demo has ten reader hooks (ADR-0508), and each accepts exactly `v0.2` and `v0.3`. None reads `provenance`, `verification`, `freshness` or `sources`. Admission does not validate JSON schemas: only the agents CI and the operator do. | `admit_okf_bundle.py:523`, `components/{mcp,a2a}-gateway/app/agent_declarations.py`, `components/mlops/src/mlops.py:1279`, `evaluations/common/okf_release.py`, `platform/docs/check_docs.py:1060`, `ansible/roles/agents/tasks/check.yml:137` |
| F13 | The operator embeds 13 closed schemas, accepts only `v0.2` and `v0.3`, and skips any document with no frontmatter or an unknown `type`. It shows `provenance.maintainer` in `status.display`. Its copies of the v0.2, v0.3 and task-v0.3 schemas have drifted from the agents repository. | `startx-unifai` `fork/unifai-operator/internal/okf/schema.go:14-42,117-123`, `bundle.go:224,330` |
| F14 | Documentation gaps. No page covers the architecture, the integration with a platform, the end-to-end lifecycle of a bundle, the operator fork or the upstream spec. `docs/agents/okf-workflow.md` here is stale (2026-09-07). WP-255 to WP-259 shipped their pages in agents v0.14.4, yet the tracker still said "Not started". | `zuno-demo-agents/docs/`; `docs/roadmap/implementation-roadmap.md` Phase 54 |
| F15 | The tooling is sound. The six release checks pass: schema, bundle, quota, narrowing, authorization matrix, contract tests. Artifacts are reproducible and signed keyless, every agent has its own version under a gate, and the authorization matrix is generated. | `publish.yml`; run of 2026-11-14 on `78b2472` |

## Decision

**zuno-demo-agents moves to the Zuno OKF profile 1.0. Each document conforms to upstream OKF 0.2: `okf_version: "0.2"`,
upstream provenance and trust fields, and a generated root `index.md`. The Zuno version moves to `zuno.profile`, and the
profile is frozen. Every bundle is migrated and cleaned, and the documentation is rewritten in each repository. The
profile ships as zuno-demo-agents v1.0.0 with unifai-operator v0.1.71 and is deployed on demo333. Legacy `v0.2` and
`v0.3` documents are refused from 2026-12-01.**

1. **Upstream is the base.** The base specification is upstream OKF 0.2 ([SPEC.md](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)).
   The Zuno profile adds the `zuno` block and the constraints of this record, and nothing else. Where this record and
   upstream disagree, the difference is listed in the deviations table of clause 8 (WP-262).
2. **Version keys.** Every published document carries `okf_version: "0.2"`, a quoted string with the upstream meaning,
   and `zuno.profile: "1.0"`. Prompt documents get a minimal `zuno: {profile: "1.0"}`. Repeating `okf_version` in each
   document is a declared deviation: upstream declares it once, in the root `index.md`. We repeat it so that a reader
   can dispatch one file at a time, which the gateways and the operator do.
3. **Root `index.md`.** Each agent bundle has a root `index.md` in the upstream §8 shape: no frontmatter except
   `okf_version: "0.2"`, then headings with bundle-relative links (`/tasks/…`) and a one-line description for every
   published document. It is generated by `platform/okf/generate_index.py`, checked in CI with `--check`, and
   published in the agent artifact (`RUNTIME_FILES`). A reader never treats a missing `index.md` as an error, because
   legacy bundles have none (WP-262).
4. **Envelope: upstream fields replace the Zuno ones.**

   | Profile 1.0 | Replaces | Rule |
   |---|---|---|
   | `resource` | `provenance.repository` | `https://github.com/startxfr/zuno-demo-agents/blob/main/<path>`. It points at `main`, not a tag, so a release does not change every file. |
   | `sources: [{id, resource, title}]` | free-text `sources` | `resource` is required (upstream §5); `id` is used by body footnotes. |
   | `verified: [{by, at}]` | `verification.status` | `by` is `human:<github-login>` (a reviewer) or `process:zuno-demo-agents/<check>` (CI). An empty or absent list means unverified, so the trust tier is derived as upstream says. It is a list, never a bare mapping. |
   | `stale_after` | `freshness.last_reviewed` | An ISO 8601 instant with an offset, by default 6 months after the last `verified[].at`. CI warns when it is past and never fails on it. |
   | `zuno.maintainer` | `provenance.maintainer` | The operator shows it in `status.display`, and falls back to `provenance.maintainer` for legacy documents. |
   | `status` (optional) | — | Must agree with `zuno.status`: `stable` (or absent) for active, `draft` for placeholder, `deprecated` for deprecated or retired. |

   Also allowed: `title`, `description`, `tags` and `generated: {by, at}`. Timestamps are ISO 8601 with an offset,
   always quoted.
5. **One dispatch rule, implemented in every reader.** The agents tooling, each zuno-demo hook (each keeps its own
   copy, per ADR-0508) and the operator all apply it:

   | `okf_version` | `zuno.profile` | Result |
   |---|---|---|
   | `"v0.2"` or `"v0.3"` | absent | Legacy document, legacy schema. Readable until 2026-12-01 (clause 13). |
   | `"0.2"` | `"1.0"` | Profile 1.0 schema |
   | `"0.2"` | absent or another value | Refused: `unsupported zuno.profile` |
   | anything else, including the unquoted YAML number `0.2` | — | Refused: `unsupported okf_version` |

   The version is checked one document at a time, so a mixed bundle is still read. The agents CI requires one profile
   per bundle. The conformance cases (`conformance/cases/`, shipped in the corp artifact) cover each row.
6. **Narrowing by level, never by equality.** Each reader computes a level: legacy v0.2 < legacy v0.3 ≤ profile 1.0.
   Every rule that applied to v0.3 now applies at "v0.3 or above". A conformance case proves that a profile 1.0 bundle
   is narrowed (F11).
7. **The profile is frozen.** The schemas are flat files, `platform/okf/schema/zuno-okf-profile-1.0-<type>.schema.json`,
   one for each of agent, task, prompt, tool, rag, policy, skill, experience-client and index. They are generated by
   `build_profile_schemas.py` and recorded in a committed `SHA256SUMS`. Changing a frozen file fails CI; a change
   needs a new profile version. A minor profile version (1.1) may only add optional fields, and a reader accepts only
   the profile versions it embeds. The agents repository is the source. The operator embeds copies synchronized by
   `hack/sync-okf-schemas.sh <agents-ref>`, which records the agents commit and the hash of each file in
   `internal/okf/schema/SOURCE`, and a test fails on drift. The legacy schema files stay as they are (WP-262, WP-264).
8. **Strictness stays, and is documented as a deviation.** Unknown top-level keys outside the upstream list, unknown
   `zuno` keys, unknown versions and a bare `verified` mapping are refused. An agent bundle is an authorization
   contract: a misspelled key must fail, not be ignored. The deviations table (WP-262 docs) lists this rule and
   clause 2. Upstream's trust tiers are advisory, and so is `verified` here: it never grants anything.
9. **One tool vocabulary.** The `capability` of a tool note is any tool or capability name of
   `policies/tools/tool-policy.yaml`. The schema checks a name pattern, the validator checks the vocabulary, and
   `used_by_tasks` is checked in both directions.
10. **Content is platform-neutral and complete.**
    - Published prose names no path of another repository and no retired component, and a lint enforces it.
    - All 8 agents migrate to profile 1.0, along with the experience clients, the corp skills and the corp policies.
    - Every active agent documents every tool and knowledge domain it declares in `tools/` and `rag/`.
    - Every task has a prompt (a new profile rule). For an active agent, the prompt starts from today's effective
      system message (description plus task body), so behaviour moves as little as possible, and it is evaluated
      before the release.
    - Agent READMEs are rewritten. `NEXT_STEPS.md` files and directories holding only a README are deleted.
    - `platform/templates/agent/scaffold_agent.py` writes only the agent's own files.
    - The rule "a placeholder declares exactly one task" is dropped: it was never enforced, and advantage and finage
      pre-declare their tasks (WP-265, WP-266).
11. **Documentation lives in the repository that owns the code.**
    - **zuno-demo-agents** (`docs/`): the architecture, the profile reference (dispatch, mapping, deviations, upstream
      links), the lifecycle of a bundle that configures an agent (write, check, version, release, consumption), and
      updates to the existing pages (WP-262).
    - **zuno-demo**: a new `docs/platform/agents-release-integration.md` covering the pin, promotion, admission, the
      Quay mirror, the consumers (okf-fetch, the operator, the ai-gateway and mlops builds, evaluations) and rollback.
      `docs/agents/okf-workflow.md` becomes a pointer (WP-267).
    - **startx-unifai fork**: `fork/unifai-operator/docs/okf-agent-bundles.md` describes how the operator pulls,
      verifies and maps a bundle, the field mapping, and which profile and schema versions each operator version
      accepts. The operator README links to it (WP-264).
12. **Readers first, then releases, each live step on the owner's go.** The order is:
    1. Agents tooling, with no bundle converted (WP-262).
    2. zuno-demo readers and the image rebuilds, with the lock still on v0.14.4 (WP-263).
    3. unifai-operator v0.1.71. The patch goes to the fork owner session, which applies it on the fork's `devel`; then
       a canary on `devel-<sha>`, a manual cut, a copy into the internal Quay, and finally the pin (WP-264).
    4. Conversion of every bundle (WP-265, WP-266).
    5. zuno-demo-agents **v1.0.0**, with every agent version set to 1.0.0.
    6. The promotion (WP-267).

    After step 3, every existing `UnifaiAgentBundle` must stay Ready on its current digest. The CRD does not change,
    which keeps an OLM rollback to 0.1.69 possible.
13. **Legacy documents are refused from 2026-12-01.** Every reader reads `v0.2` and `v0.3` documents until then. The
    weekly operator release of 2026-11-27 and the zuno-demo readers then refuse them (WP-268). They are pinned on
    2026-12-01 with the owner's go, before the operator's 0.1 line freezes. This replaces ADR-0579 clause 6 as
    amended on 2026-11-05.

## Alternatives considered

- **A "v0.4" that adds the upstream fields and keeps `okf_version` as the Zuno version.** Less work in the readers, but
  it keeps the main deviation (F2), and a future upstream 0.3 or 0.4 would collide with it. Rejected.
- **Freeze v0.3 and clean the content only.** The lowest risk, but aligning later would break the format a second
  time, so the spec would not really be stable. Rejected.
- **Declare `okf_version` only in `index.md`, as upstream does.** Readers that open one file at a time (the gateways,
  the operator) would lose the version. Rejected; recorded as a deviation (clause 2).
- **Follow upstream's lenient consumer rules.** A misspelled authorization key would be ignored silently. Rejected
  (clause 8).

## Consequences

- Every agent digest changes once, at v1.0.0: one promotion, which also carries the pending release-annotation fix
  `78b2472`.
- For two weeks, readers carry two forms. WP-268 removes the legacy form.
- demo333 jumps from operator 0.1.69 to 0.1.71 (0.1.70 is pinned on its own first by its owner session, if that
  happens before).
- The repository becomes a reference others can copy: an upstream-conformant format, a documented profile, and a
  documented consumer (zuno-demo) and runtime (the operator).
- Adding prompts changes the behaviour of the active agents; evaluating them is part of WP-266.

## Security considerations

The trust chain does not change: keyless signature by `publish.yml` on a release tag (ADR-0578), offline verification,
and a single digest pin (ADR-0580). The new envelope fields are advisory metadata and never grant access.
Authorization stays in the `zuno` blocks and the corp policies, still checked by the narrowing level of clause 6,
which closes the silent-skip trap (F11). Strict schemas keep a misspelled authorization key from passing unnoticed.

## Operational considerations

Each step that touches demo333 has a go from the owner: the image rebuilds, the operator copy into Quay, the operator
pin, approval of the release pull request, then the promotion with `make d2 install mcp` and `make d2 install unifai`.

Rollback for each step:
- **Image rebuild:** re-tag the previous ImageStream tag.
- **Operator:** OLM does not downgrade on a pin revert. The documented procedure is to delete the CSV and the
  Subscription, then reinstall with `startingCSV` 0.1.69 from the previous catalog digest. The CRs survive, because
  the CRD is unchanged.
- **Agents:** revert the lock commit and re-run the same targets. `admit prune` must keep v0.14.4 in the internal Quay.

The internal Quay holds every release before it is rolled (ADR-0612). Other sessions that pin UnifAI or edit
`gitops/charts/unifai/values.yaml` are told before each operator step.

## Work packages

| WP | Repository | Content |
|---|---|---|
| [WP-262](../roadmap/work-packages/wp-262-okf-profile-1-0-schemas-tooling-and-agents-docs.md) | zuno-demo-agents | Profile 1.0 schemas and generator, validator dispatch and narrowing level, the tool vocabulary, `generate_index.py`, release tooling, conformance cases, and the agents-repo docs |
| [WP-263](../roadmap/work-packages/wp-263-zuno-demo-okf-readers-accept-profile-1-0.md) | zuno-demo | The ten reader hooks and the narrowing level, tests, image rebuilds |
| [WP-264](../roadmap/work-packages/wp-264-unifai-operator-reads-okf-profile-1-0.md) | startx-unifai fork | Operator dispatch, embedded schemas with sync and drift test, `zuno.maintainer`, the operator docs page, v0.1.71, pin |
| [WP-265](../roadmap/work-packages/wp-265-migrate-and-clean-every-okf-bundle-to-profile-1-0.md) | zuno-demo-agents | Conversion of every bundle, platform-neutral prose, READMEs, scaffold |
| [WP-266](../roadmap/work-packages/wp-266-complete-tool-and-rag-notes-and-task-prompts.md) | zuno-demo-agents | Tool and rag notes for the active agents, the 12 missing prompts, their evaluation |
| [WP-267](../roadmap/work-packages/wp-267-release-and-promote-zuno-demo-agents-v1-0-0.md) | zuno-demo | Release v1.0.0, promotion and deployment on demo333, the platform integration page |
| [WP-268](../roadmap/work-packages/wp-268-refuse-legacy-okf-documents-from-2026-12-01.md) | both + fork | Refusal of `v0.2` and `v0.3` documents, from the 2026-11-27 operator release |

## Resources

Checked on 2026-11-14.

- Upstream specification, canonical: <https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md>
- Upstream repository (reference agent, visualizer, sample bundles; Apache-2.0): <https://github.com/GoogleCloudPlatform/open-knowledge-format>
- Earlier copy of the specification, in Knowledge Catalog: <https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md>
- v0.1 announcement, "Introducing the Open Knowledge Format" (Google Cloud blog, 2026-06-12): <https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing>
- v0.2 announcement, "Open Knowledge format v0.2 tackles agentic trust" (Google Cloud blog, 2026-07-24): <https://cloud.google.com/blog/products/data-analytics/okf-v0-2-adds-trust-signals>
- Upstream sections this record relies on: §3 (bundle and reserved files), §4 (frontmatter), §5 (provenance, trust,
  lifecycle), §6 (links), §8 (index), §11 (conformance), §12 (versioning).
